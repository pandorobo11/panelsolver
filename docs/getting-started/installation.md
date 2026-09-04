# Installation

## Requirements

- Python 3.12 or newer
- A platform supported by the required Python dependencies, including Qt,
  PyVista/VTK, Trimesh, SciPy, pandas, and rtree
- A normal desktop display for the GUI

You can start with the supplied example mesh and case table; you do not need to
prepare your own STL before trying the software.

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
python -c 'import importlib.metadata as m; print(m.version("panelsolver"))'
```

The version printed by the final command is the installed `panelsolver`
distribution version. Newly generated FMF and Hypersonic Summary CSV/VTP
artifacts record that value as `solver_version`.

## Run your first case

Continue with [Quickstart](quickstart.md). A checkout already contains
`examples/`. For a wheel installation, extract the matching
`panelsolver-examples-v<version>.zip` from the release alongside your working
files, or use **File > New from Example > Basic** in the GUI to copy a bundled
example to a workspace.
