# Installation

## Requirements

- Python 3.12 or newer
- A platform supported by the required Python dependencies, including Qt,
  PyVista/VTK, Trimesh, SciPy, pandas, and rtree
- A normal desktop display for the GUI

On macOS, installation selects PySide6/Qt 6.9.0 to avoid a table-accessibility
crash in newer Qt versions. Keep the dependency version selected by Panel
Solver; do not independently upgrade PySide6 in this environment. Other
platforms use the supported Qt 6 dependency range.

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
