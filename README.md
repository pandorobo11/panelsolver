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

Python 3.12 or newer is required. Install the published distribution with:

```bash
python -m pip install panelsolver
python -m pip install 'panelsolver[rayaccel]'  # optional Embree backend
```

From a checkout:

```bash
python -m pip install .
```

For the optional accelerated Embree ray backend:

```bash
python -m pip install '.[rayaccel]'
```

The built-in `rtree` backend remains supported. Do not install `panelsolver`
beside the legacy `fmfsolver` or `newtsolver` distributions because their package
and command names overlap. See the [installation guide](docs/getting-started/installation.md).

## Run

Launch either canonical GUI, then select its example case file:

```bash
panelsolver-gui fmf
panelsolver-gui hypersonic
```

Run the same examples without the GUI:

```bash
panelsolver fmf --input examples/fmf/basic.csv --workers 1 --flush-every-cases 0
panelsolver hypersonic --input examples/hypersonic/basic.csv --workers 1 --flush-every-cases 0

# Legacy compatibility commands remain available:
fmfsolver-cli --input examples/fmf/basic.csv --workers 1 --flush-every-cases 0
newtsolver-cli --input examples/hypersonic/basic.csv --workers 1 --flush-every-cases 0
```

`fmf` is the free-molecular-flow domain selector; it is not the legacy
`fmfsolver` product identity. The selected physical model is Sentman.

Case tables may be CSV, XLSX, or XLSM files. CSV input and Summary CSV output
use UTF-8 with BOM (`utf-8-sig`); BOM-less UTF-8 CSV files remain accepted on
input for compatibility.

The six `fmfsolver` / `newtsolver` commands remain legacy compatibility entry
points with unchanged command behavior and GUI titles.
Results are written below each example's `outputs/` directory. The
[quickstart](docs/getting-started/quickstart.md) explains the files and the main
CLI options.

## Documentation

Every wheel includes a self-contained offline HTML site. In either canonical or
legacy GUI, use **Help → Documentation** or **Help → Current Domain
Documentation**. Release attachments also include
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
- [Development guide](docs/development/setup-and-testing.md)
- [Migration and audit history](docs/history/README.md)

## Status and compatibility

The FMF/Hypersonic integration and Phase 8 audit are complete. One
`panelsolver` distribution (currently `0.1.0`) provides the canonical
`panelsolver` and `panelsolver-gui` command namespaces plus all six legacy
compatibility command names. Summary CSV and VTP artifacts record the installed
`panelsolver` distribution version for both domains. FMF `fmfsolver 1.3.8`
and Hypersonic `newtsolver 1.0.3` remain documented migration baselines and
private legacy-compatibility inputs, not current domain versions. Supported
commands, normal GUI use, documented case files,
and documented Summary CSV/VTP semantics are compatibility surfaces. The small
`panelsolver` package-root Python API is stable. Direct-Python APIs under
`fmfsolver.*` and `newtsolver.*` are unsupported and have been removed; those
package names remain only as private command frontends. See the
[compatibility policy](docs/reference/compatibility.md) and
[CHANGELOG.md](CHANGELOG.md).

## License

Panel Solver code, documentation, examples, and project-generated material are
licensed under the [Apache License 2.0](LICENSE). Third-party and public-domain
rights and provenance, including US1976 and PDAS, are documented in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
