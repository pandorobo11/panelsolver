# Installation

## Requirements

- Python 3.12 or newer. **On macOS, use Python 3.12 or 3.13.**
- Windows, macOS, or Linux on a platform supported by the required packages
  (Qt, PyVista/VTK, Trimesh, SciPy, pandas, and rtree).
- A normal desktop display for the GUI.

On macOS, Panel Solver installs a fixed Qt version (PySide6 6.9.0) to avoid a
known table-accessibility crash (QTBUG-149612). That Qt version is not available for Python 3.14
or newer, so `pip` stops with a dependency error on those versions. Keep the
installed PySide6 version. It still has one
[known macOS accessibility issue](../guides/troubleshooting.md#macos-gui-crashes-during-accessibility-inspection).

Windows and Linux use the current Qt 6 releases and have no extra Python
version limit.

## Install a wheel

In the folder that contains the wheel file, run:

```bash
python -m pip install ./panelsolver-0.2.0rc1-py3-none-any.whl
```

To also install the faster Embree backend for
[ray shielding](../methods/ray-shielding.md), add the `rayaccel` extra:

```bash
python -m pip install "./panelsolver-0.2.0rc1-py3-none-any.whl[rayaccel]"
```

## Install from a source checkout

From the repository folder:

```bash
python -m pip install .
```

With Embree:

```bash
python -m pip install ".[rayaccel]"
```

## Check the installation

Each of these commands should print its help text:

```bash
panelsolver --help
panelsolver fmf --help
panelsolver hypersonic --help
panelsolver-gui --help
panelsolver-gui fmf --help
panelsolver-gui hypersonic --help
```

To print the installed version:

```bash
python -c "from importlib.metadata import version; print(version('panelsolver'))"
```

## Next step

Continue with the [Quickstart](quickstart.md) to run a supplied example.
