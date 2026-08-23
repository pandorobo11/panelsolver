# Installation

## Requirements

- Python 3.12 or newer
- A platform supported by the required Python dependencies, including Qt,
  PyVista/VTK, Trimesh, SciPy, pandas, and rtree
- An STL mesh and a CSV, XLSX, or XLSM case table

## Install

For normal use, install the canonical distribution:

```bash
python -m pip install panelsolver
```

To add the platform-specific Embree binding used by the accelerated ray backend:

```bash
python -m pip install 'panelsolver[rayaccel]'
```

From a checkout:

```bash
python -m pip install .
```

The equivalent checkout install with Embree is:

```bash
python -m pip install '.[rayaccel]'
```

For a reproducible development environment, use the locked setup instead:

```bash
uv sync --locked --extra rayaccel
```

Commands in that environment can be prefixed with `uv run`.

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

The distribution version is currently `0.1.0` and is the `solver_version`
recorded by newly generated FMF and Hypersonic Summary CSV/VTP artifacts. The
historical `fmfsolver 1.3.8` and `newtsolver 1.0.3` values are private legacy
artifact-signature inputs; they are not importable package versions or current
domain versions.

## Legacy-distribution coexistence

Do not install this distribution in the same environment as either legacy
`fmfsolver` or `newtsolver` distribution. All of them provide overlapping
top-level packages and console commands. Remove the legacy packages first:

```bash
python -m pip uninstall fmfsolver newtsolver
python -m pip install .
```

Operational rollback is documented separately in
[Release and rollback](../development/release-and-rollback.md).
