# Compatibility policy

Panel Solver supports:

- batch commands `panelsolver fmf` and `panelsolver hypersonic`;
- GUI commands `panelsolver-gui fmf` and `panelsolver-gui hypersonic`;
- normal launcher-driven GUI operation;
- only the seven package-root imports described in the
  [Python API reference](../running/python-api.md);
- documented CSV, XLSX, and XLSM case files and their domain schemas/defaults;
- documented [Summary CSV](../results/summary-csv.md) and
  [VTP](../results/vtp.md) semantics;
- documented numerical values, signs, frames, normalizations, and
  model-specific behavior.

The compatibility guarantee covers the documented public behavior above.
Private implementation details—including invalid-input quirks, exact exception
text and tracebacks, object identity, pickle globals, and cache internals—are
outside this guarantee.

Known limitations include the
[macOS table-accessibility crash](../running/troubleshooting.md#macos-gui-crashes-during-accessibility-inspection).

## Updating predecessor workflows

Use the canonical `panelsolver` package and commands in place of predecessor
names. Convert `.xls` case tables to `.xlsx` or CSV, and remove the rejected
`save_npz_on` column from older tables. Calculation-result files are Summary CSV
and VTP. Current schemas exclude NPZ output and the `Cp_n` array.

## Distribution and artifact version

Panel Solver is distributed as `panelsolver`. Summary CSV and VTP
`solver_version` fields, defined in their result references, record the
installed `panelsolver` distribution version that generated them.

Automatic VTP loading requires both the current case ID and current case
signature. Regenerate predecessor-product VTPs with Panel Solver; those formats
are outside the compatibility guarantee. **Open VTP...** can inspect a file
manually when it contains the data required by the viewer.
