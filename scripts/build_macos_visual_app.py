"""Build the checkout-local macOS visual-smoke launcher (no Python SDK needed)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def build(root: Path) -> Path:
    if sys.platform != "darwin":
        raise RuntimeError("The visual-smoke app can only be built on macOS")
    root = root.resolve()
    bundle = root / "tools/macos/PanelSolverVisual.app"
    destination = bundle / "Contents/MacOS/PanelSolverVisualNative"
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Replace only after compilation succeeds; never truncate a running binary.
    with tempfile.TemporaryDirectory(dir=destination.parent) as directory:
        output = Path(directory) / destination.name
        subprocess.run(
            [
                "xcrun",
                "clang",
                "-fobjc-arc",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-framework",
                "Foundation",
                str(root / "tools/macos/visual_launcher.m"),
                "-o",
                str(output),
            ],
            check=True,
            timeout=120,
        )
        os.replace(output, destination)
    return bundle


def main() -> int:
    try:
        print(build(Path(__file__).resolve().parents[1]))
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Visual launcher build failed: {exc}", file=sys.stderr)
        print("Install Xcode Command Line Tools and retry on macOS.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
