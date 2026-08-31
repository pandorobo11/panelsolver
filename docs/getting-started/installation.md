# Installation

## Requirements

- Python 3.12 or newer
- A platform supported by the required Python dependencies, including Qt,
  PyVista/VTK, Trimesh, SciPy, pandas, and rtree
- An STL mesh and a CSV, XLSX, or XLSM case table

## Install a release

Panel Solver v0.1.0 is published through the
[GitHub Releases page](https://github.com/pandorobo11/panelsolver/releases),
not PyPI. Download `panelsolver-<version>-py3-none-any.whl` from the selected
release, change to the download directory, and install that local wheel:

```bash
python -m pip install ./panelsolver-<version>-py3-none-any.whl
```

To install or reinstall the same downloaded wheel with the platform-specific
Embree binding used by the accelerated ray backend:

```bash
python -m pip install "./panelsolver-<version>-py3-none-any.whl[rayaccel]"
```

## Install from a checkout

From a checkout:

```bash
python -m pip install .
```

The equivalent checkout install with Embree is:

```bash
python -m pip install '.[rayaccel]'
```

## Verify the installation

```bash
panelsolver --help
panelsolver fmf --help
panelsolver hypersonic --help
panelsolver-gui --help
panelsolver-gui fmf --help
panelsolver-gui hypersonic --help
fmfsolver-cli --help
newtsolver-cli --help
python -c 'import importlib.metadata as m; print(m.version("panelsolver"))'
```

The version printed by the final command is the installed `panelsolver`
distribution version. Newly generated FMF and Hypersonic Summary CSV/VTP
artifacts record that value as `solver_version`.

## Legacy-distribution coexistence

Do not install this distribution in the same environment as either legacy
`fmfsolver` or `newtsolver` distribution. All of them provide overlapping
top-level packages and console commands. Remove the legacy packages first:

```bash
python -m pip uninstall fmfsolver newtsolver
python -m pip install ./panelsolver-<version>-py3-none-any.whl
```
