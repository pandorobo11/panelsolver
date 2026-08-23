# Troubleshooting

## An STL cannot be found

Relative STL paths are resolved from the input table's directory. Check the path
from that directory and use semicolons only between complete component paths.

## The input table is rejected

Use the reported spreadsheet row and field. Common causes are a missing required
header, a non-finite value, a non-positive reference quantity, an incomplete FMF
Mode A/B pair, an invalid equation selector, or an attitude outside the reader
domain. See the solver-specific input reference.

Legacy Excel 97–2003 `.xls` files are no longer supported. Resave the workbook
as `.xlsx` in Excel or another spreadsheet application, or export it as CSV.

## Embree is unavailable

Install the optional extra with `python -m pip install '.[rayaccel]'`, or set the
case's `ray_backend` to `rtree`. An explicit `embree` request intentionally does
not fall back.

## The result path is rejected

The summary may not alias the input file, an STL, or any planned VTP path.
Choose a distinct filename and directory. Collision checks are deliberately
portable across case-insensitive Windows and common macOS filesystems.

## A VTP does not load automatically

Confirm that `save_vtp_on=1`, that the file is under the resolved `out_dir`, and
that it was generated for the selected case. Automatic loading requires the case
ID and an accepted current or legacy signature to match.

## A canceled run does not stop immediately

Cancellation is observed between cases. A currently executing ray query or
physical-model solve is allowed to finish. Treat artifacts from failed or
canceled runs as partial state.

## A legacy Python import fails

The installed distribution is `panelsolver`; its version appears in newly
generated FMF and Hypersonic Summary CSV/VTP artifacts. Direct-Python APIs under
`fmfsolver.*` and `newtsolver.*`, including legacy `__version__` attributes, have
been removed. Use the documented `panelsolver` package-root API or a supported
command. Do not install the shared and legacy distributions together.
