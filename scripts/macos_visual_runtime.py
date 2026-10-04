"""Describe this interpreter for the native launcher; stdlib only, no GUI import."""

from __future__ import annotations

import json
import sys
import sysconfig
from pathlib import Path


def runtime_info() -> dict[str, str]:
    if sys.implementation.name != "cpython":
        raise RuntimeError("The visual launcher requires CPython")
    candidates = []
    library = sysconfig.get_config_var("LDLIBRARY")
    libdir = sysconfig.get_config_var("LIBDIR")
    if library and libdir:
        candidates.append(Path(libdir) / library)
    framework = sysconfig.get_config_var("PYTHONFRAMEWORK")
    if framework:
        candidates.append(Path(sys.base_prefix) / framework)
        prefix = sysconfig.get_config_var("PYTHONFRAMEWORKPREFIX")
        version = sysconfig.get_config_var("VERSION")
        if prefix and version:
            candidates.append(
                Path(prefix) / f"{framework}.framework/Versions/{version}/{framework}"
            )
    for candidate in candidates:
        if candidate.is_file():
            return {
                # Keep the venv path: resolving this symlink loses its pyvenv.cfg.
                "executable": str(Path(sys.executable).absolute()),
                "library": str(candidate.resolve()),
            }
    raise RuntimeError("No CPython shared library found; use a shared/framework build")


if __name__ == "__main__":
    try:
        print(json.dumps(runtime_info()))
    except RuntimeError as exc:
        print(f"Visual launcher runtime discovery failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
