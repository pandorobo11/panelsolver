# Troubleshooting

## An STL cannot be found

Relative STL paths are resolved from the input table's directory. Check the path
from that directory and use semicolons only between complete component paths.

## The input table is rejected

Use the reported spreadsheet row and field. Common causes are a missing required
header, a non-finite value, a non-positive reference quantity, an incomplete FMF
Mode A/B pair, an invalid equation selector, or an attitude outside the reader
domain. See the solver-specific input reference.

Excel 97–2003 `.xls` files are not a supported input format. Resave the workbook
as `.xlsx` in Excel or another spreadsheet application, or export it as CSV.

## Embree is unavailable

For a wheel installation, reinstall the Panel Solver wheel with the `rayaccel`
extra as shown in the [Installation guide](../getting-started/installation.md).
From a checkout, use `uv sync --extra rayaccel` or
`python -m pip install ".[rayaccel]"`. Alternatively, set the case's
`ray_backend` to `rtree`. An explicit `embree` request intentionally does not
fall back.

## The result path is rejected

The summary may not alias the input file, an STL, or any planned VTP path.
Choose a distinct filename and directory. Collision checks are deliberately
portable across case-insensitive Windows and common macOS filesystems.

## A VTP does not load automatically

Confirm that `save_vtp_on=1`, that the file is under the resolved `out_dir`, and
that it was generated for the selected case. Automatic loading requires the case
ID and current canonical signature to match. Regenerate predecessor-product VTPs
with Panel Solver when automatic loading is required; they are unsupported.

## A canceled run does not stop immediately

See [Cancellation and calculation failures](batch-execution-and-recovery.md#cancellation-and-calculation-failures)
for the cooperative boundary and how to recover completed artifacts.

## A Python import fails

The installed distribution and Python package are both `panelsolver`; its
version appears in newly generated FMF and Hypersonic Summary CSV/VTP artifacts.
Use the documented package-root API rather than predecessor-product package
names.
