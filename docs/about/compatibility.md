# Compatibility policy

This page lists what Panel Solver keeps compatible between releases. If you
rely only on these, your inputs, scripts, and result readers keep working.

## What is supported

- The commands `panelsolver fmf` and `panelsolver hypersonic`, including their
  `sectional-loads` and `sectional-cp` subcommands.
- The GUI commands `panelsolver-gui fmf` and `panelsolver-gui hypersonic`, used
  in the normal way through their windows and menus.
- The seven package-root imports and the `panelsolver.postprocess` sectional
  load and sectional Cp functions described in the
  [Python API reference](../reference/python-api.md).
- CSV, XLSX, and XLSM case tables with the documented columns and defaults.
- The documented meaning of the [Summary CSV](../reference/summary-csv.md) and
  [VTP](../reference/vtp.md) fields.
- The [sectional definition CSVs](../reference/sectional-definitions.md), the
  [sectional load CSV](../reference/sectional-loads-csv.md), and the
  [sectional Cp CSV](../reference/sectional-cp-csv.md).
- The documented numerical values, signs, axes, normalizations, and model
  behavior.

## What is not covered

Behavior that is not documented can change without notice. This includes how
invalid input happens to be handled, the exact text of error messages and
tracebacks, and Python internals such as object identity, pickling, and caches.

Known limitations include the
[macOS table-accessibility crash](../guides/troubleshooting.md#macos-gui-crashes-during-accessibility-inspection).

## Updating from earlier versions

- Use the `panelsolver` package and commands instead of the names of the older
  predecessor tools.
- Convert `.xls` case tables to `.xlsx` or CSV.
- Remove the `save_npz_on` column from older case tables. Results are written
  only as Summary CSV and VTP; NPZ output and the `Cp_n` array no longer exist.
- Remove the `out_dir` column from older case tables. VTP files are written to
  the `outputs/` folder next to the case table.
- The former `alpha_t_deg_resolved` and `beta_t_deg_resolved` result fields
  have been replaced. Use the `velocity_hat_*_stl` flow-direction fields and
  `alpha_stability_deg` instead.
- Case signatures now use version 2 of the signature format. Files made by
  earlier versions can still be opened with **Open VTP...**, but the GUI does
  not match them to cases automatically. Run those cases again to get matching
  files.

## Version recorded in results

The `solver_version` field in the Summary CSV and in each VTP records the
version of the installed `panelsolver` package that wrote the file.

The GUI shows a VTP automatically only when its case ID and `case_signature`
match the current case. VTP files from predecessor tools are not supported;
regenerate them with Panel Solver. **Open VTP...** can still display a file
if it contains the data the Viewer needs.
