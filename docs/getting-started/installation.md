# Installation

## Requirements

- Python 3.12 or newer; **macOS currently requires Python 3.12 or 3.13**
- A platform supported by the required Python dependencies, including Qt,
  PyVista/VTK, Trimesh, SciPy, pandas, and rtree
- A normal desktop display for the GUI

On macOS, installation selects PySide6/Qt 6.9.0 to avoid the QTBUG-149612
table-accessibility crash. That dependency does not support Python 3.14 or
newer, and `pip` rejects installation on those Python versions during dependency
resolution. Use Python 3.12 or 3.13 and keep the selected PySide6 version.
The macOS pin will be reassessed when the upstream Qt fix is available and
validated.

The pinned version still has a known
[macOS accessibility limitation](../running/troubleshooting.md#macos-gui-crashes-during-accessibility-inspection).

Panel Solver's package requirement remains Python 3.12+. Windows/Linux use the
current Qt 6 dependency range without the macOS-specific Python upper limit;
installation still requires compatible versions of all dependencies.

## Install a wheel

Install the Panel Solver v0.1.0 wheel from the directory containing the file:

```bash
python -m pip install ./panelsolver-0.1.0-py3-none-any.whl
```

To include the optional accelerated Embree ray backend:

```bash
python -m pip install "./panelsolver-0.1.0-py3-none-any.whl[rayaccel]"
```

## Install from a checkout

From a checkout:

```bash
python -m pip install .
```

The equivalent checkout install with Embree is:

```bash
python -m pip install ".[rayaccel]"
```

## Verify the installation

```bash
panelsolver --help
panelsolver fmf --help
panelsolver hypersonic --help
panelsolver-gui --help
panelsolver-gui fmf --help
panelsolver-gui hypersonic --help
python -c "from importlib.metadata import version; print(version('panelsolver'))"
```

The version printed by the final command is the installed `panelsolver`
distribution version.

## Run your first case

Continue with [Quickstart](quickstart.md) to run a supplied example.
