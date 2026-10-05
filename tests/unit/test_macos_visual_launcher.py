"""Exercise the real native launcher without requiring a display or Qt."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.build_macos_visual_app import build
from scripts.macos_visual_runtime import runtime_info

ROOT = Path(__file__).resolve().parents[2]
MAC_ONLY = pytest.mark.skipif(sys.platform != "darwin", reason="macOS launcher")

# A substitute entry script in an isolated checkout. This tests process identity,
# venv/argv propagation, spawn and shutdown without touching the product GUI.
PROBE = """
import ctypes
import json
import multiprocessing
import os
from pathlib import Path
import sys

def child(_):
    return (os.getpid(), sys.executable, sys.prefix)

if __name__ == "__main__":
    buffer = ctypes.create_string_buffer(4096)
    size = ctypes.c_uint32(len(buffer))
    assert ctypes.CDLL(None)._NSGetExecutablePath(buffer, ctypes.byref(size)) == 0
    with multiprocessing.get_context("spawn").Pool(1) as pool:
        worker = pool.map(child, [0])[0]
    print(json.dumps({
        "argv": sys.argv[1:], "pid": os.getpid(), "image": os.fsdecode(buffer.value),
        "executable": sys.executable, "prefix": sys.prefix, "cwd": os.getcwd(),
        "worker": worker, "qt_platform": os.environ.get("QT_QPA_PLATFORM"),
        "vtk_offscreen": os.environ.get("PYVISTA_OFF_SCREEN"),
    }), flush=True)
    raise SystemExit(7)
"""


@pytest.mark.parametrize("framework", [False, True])
def test_runtime_discovery_preserves_venv_and_finds_shared_library(
    tmp_path, monkeypatch, framework
):
    library = tmp_path / ("Python" if framework else "libpython.dylib")
    library.touch()
    python = tmp_path / "venv/bin/python"
    values = {
        "LDLIBRARY": "missing-library" if framework else library.name,
        "LIBDIR": str(tmp_path),
        "PYTHONFRAMEWORK": "Python" if framework else None,
    }
    monkeypatch.setattr(
        "scripts.macos_visual_runtime.sysconfig.get_config_var", values.get
    )
    monkeypatch.setattr(sys, "base_prefix", str(tmp_path))
    monkeypatch.setattr(sys, "executable", str(python))
    assert runtime_info() == {"executable": str(python), "library": str(library)}
    library.unlink()
    with pytest.raises(RuntimeError, match="shared library"):
        runtime_info()


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / "checkout with spaces 日本語"
    bundle = root / "tools/macos/PanelSolverVisual.app"
    shutil.copytree(
        ROOT / "tools/macos/PanelSolverVisual.app",
        bundle,
        ignore=shutil.ignore_patterns("PanelSolverVisualNative"),
    )
    shutil.copyfile(
        ROOT / "tools/macos/visual_launcher.m", root / "tools/macos/visual_launcher.m"
    )
    (root / "scripts").mkdir()
    shutil.copyfile(
        ROOT / "scripts/macos_visual_runtime.py",
        root / "scripts/macos_visual_runtime.py",
    )
    (root / "scripts/gui_visual_smoke.py").write_text(PROBE)
    return root


@MAC_ONLY
@pytest.mark.slow
@pytest.mark.parametrize("use_uv", [False, True], ids=["venv", "uv-fallback"])
def test_native_process_argv_spawn_and_exit_survive_checkout_move(checkout, use_uv):
    if use_uv:
        (checkout / "pyproject.toml").write_text(
            '[project]\nname="launcher-probe"\nversion="0.0.0"\nrequires-python=">=3.12"\n'
        )
        # An existing lock matches the old uv run --locked fallback contract.
        subprocess.run(
            ["uv", "lock", "--offline", "--python", sys.executable],
            cwd=checkout,
            check=True,
            capture_output=True,
            timeout=30,
        )
    else:
        subprocess.run(
            [sys.executable, "-m", "venv", "--without-pip", str(checkout / ".venv")],
            check=True,
            capture_output=True,
            timeout=30,
        )
    build(checkout)
    # No build-time absolute checkout, Python library or interpreter path is baked in.
    moved = checkout.with_name("moved checkout 日本語")
    checkout.rename(moved)
    executable = (
        moved
        / "tools/macos/PanelSolverVisual.app/Contents/MacOS/PanelSolverVisualNative"
    )
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYVISTA_OFF_SCREEN="true")
    env.update(UV_OFFLINE="1", UV_PYTHON=sys.executable)
    args = ["--domain", "hypersonic", "space and 日本語", "$(literal);`value`"]
    with subprocess.Popen(
        [str(executable), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    ) as process:
        try:
            stdout, stderr = process.communicate(timeout=45)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise
        assert process.returncode == 7, stderr
        info = json.loads(stdout)
        assert info["pid"] == process.pid
    assert Path(info["image"]).resolve() == executable.resolve()
    # Foundation may use /var rather than /private/var; retain the venv leaf.
    interpreter = Path(info["executable"])
    assert interpreter.parent.resolve() == (moved / ".venv/bin").resolve()
    assert interpreter.name == "python"
    assert Path(info["prefix"]).resolve() == (moved / ".venv").resolve()
    assert Path(info["cwd"]).resolve() == moved.resolve()
    assert info["argv"] == args
    assert info["worker"][0] != info["pid"]
    assert info["worker"][1:] == [info["executable"], info["prefix"]]
    assert info["qt_platform"] is None and info["vtk_offscreen"] is None


@MAC_ONLY
@pytest.mark.slow
def test_invalid_runtime_is_reported_without_starting_gui(checkout):
    # Use the test interpreter for discovery, but supply a malformed probe result.
    python = checkout / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.symlink_to(sys.executable)
    probe = checkout / "scripts/macos_visual_runtime.py"
    probe.write_text('print("not JSON")\n')
    bundle = build(checkout)
    result = subprocess.run(
        [str(bundle / "Contents/MacOS/PanelSolverVisualNative")],
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == 1
    assert "invalid runtime information" in result.stderr
    assert result.stdout == ""
