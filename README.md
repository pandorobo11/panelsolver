# Panel Solver

`panelsolver` is a single Python distribution for two STL panel-method flow
domains:

| Canonical domain | Use it for | Physical model or methods |
|---|---|---|
| `fmf` | Free-molecular and rarefied-flow surface loads | Sentman |
| `hypersonic` | Hypersonic pressure loads | Newtonian-family methods |

Choose FMF when molecular thermal interaction and tangential surface load matter.
Choose Hypersonic for continuum pressure estimates using Newtonian,
modified Newtonian, tangent-wedge, tangent-cone, or Prandtl–Meyer methods. See
[Choosing a solver](docs/index.md#choosing-a-solver) for the model limits.

## Requirements and installation

Python 3.12 or newer is required. Panel Solver v0.1.0 is distributed through
[GitHub Releases](https://github.com/pandorobo11/panelsolver/releases), not
PyPI. Download `panelsolver-<version>-py3-none-any.whl` from the release, then
install that local wheel:

```bash
python -m pip install ./panelsolver-<version>-py3-none-any.whl
python -m pip install "./panelsolver-<version>-py3-none-any.whl[rayaccel]"  # optional Embree backend
```

From a checkout:

```bash
python -m pip install .
```

For the optional accelerated Embree ray backend:

```bash
python -m pip install '.[rayaccel]'
```

The built-in `rtree` backend remains supported. See the
[installation guide](docs/getting-started/installation.md).

## Run

Launch either canonical GUI, then select its example case file:

```bash
panelsolver-gui fmf
panelsolver-gui hypersonic
```

Run the same examples without the GUI:

```bash
panelsolver fmf --input examples/fmf/basic.csv --workers 1 --checkpoint-every-cases 0
panelsolver hypersonic --input examples/hypersonic/basic.csv --workers 1 --checkpoint-every-cases 0
```

`fmf` is the free-molecular-flow domain selector. The selected physical model is
Sentman.

Case tables may be CSV, XLSX, or XLSM files. CSV input and Summary CSV output
use UTF-8 with BOM (`utf-8-sig`); BOM-less UTF-8 CSV files remain accepted on
input for compatibility.

Results are written below each example's `outputs/` directory. The
[quickstart](docs/getting-started/quickstart.md) explains the files and the main
CLI options.

## Documentation

Every wheel includes a self-contained offline HTML site. In the GUI, use
**Help → Documentation**. Release attachments also include
`panelsolver-docs-v<version>.zip`; open its root `index.html` directly with no
server or network access.

- [Documentation home](docs/index.md)
- [GUI guide](docs/user-guide/gui.md) and [CLI guide](docs/user-guide/cli.md)
- [Case-file guide](docs/user-guide/case-files.md)
- [FMF](docs/solvers/fmf.md) and
  [Hypersonic](docs/solvers/hypersonic.md)
- [FMF input](docs/reference/fmf-input.md),
  [Hypersonic input](docs/reference/hypersonic-input.md), and
  [output reference](docs/reference/output-formats.md)
- [Developer documentation](devdocs/README.md)

## Compatibility

One `panelsolver` distribution provides the two canonical command entry points.
Summary CSV and VTP artifacts record the installed distribution version. The
package-root Python API is stable. See the
[compatibility policy](docs/reference/compatibility.md) and
[CHANGELOG.md](CHANGELOG.md) for the supported surface and release changes.

## License

Panel Solver code, documentation, examples, and project-generated material are
licensed under the [Apache License 2.0](LICENSE). Third-party and public-domain
rights and provenance, including US1976 and PDAS, are documented in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
