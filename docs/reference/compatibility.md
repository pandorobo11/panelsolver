# Compatibility policy

Panel Solver supports:

- batch commands `panelsolver fmf` and `panelsolver hypersonic`;
- GUI commands `panelsolver-gui fmf` and `panelsolver-gui hypersonic`;
- normal launcher-driven GUI operation;
- only the seven package-root imports described in the
  [Python API reference](python-api.md);
- documented CSV, XLSX, and XLSM case files and their domain schemas/defaults;
- documented [Summary CSV](../results/summary-csv.md) and
  [VTP](../results/vtp.md) semantics;
- documented numerical values, signs, frames, normalizations, and
  model-specific behavior.

Other package names and commands are not distributed. The compatibility
guarantee excludes invalid-input quirks, exact exceptions and tracebacks, object
identity, pickle globals, cache internals, and other private implementation
details.

`fmf` selects the free-molecular-flow domain and its Sentman model.
`hypersonic` selects the hypersonic panel-method domain and its Newtonian-family
methods.

Summary CSV and VTP are the only supported result files. Panel Solver does not
generate NPZ output.

## Distribution and artifact version

Panel Solver is distributed as `panelsolver`. Summary CSV and VTP
`solver_version` fields, defined in their result references, record the
installed `panelsolver` distribution version that generated them. Both domains
therefore record the same installed version when those files are produced by
the same release.

Automatic VTP loading requires both the current case ID and current case
signature. Files produced by predecessor products are unsupported and should be
regenerated with Panel Solver. **Open VTP...** remains a generic manual
inspection path when a file contains the data required by the viewer. This does
not make predecessor VTP formats part of the compatibility guarantee.
