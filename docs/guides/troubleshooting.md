# Troubleshooting

## An STL file cannot be found

Relative STL paths are relative to the folder that contains the case table,
not to the folder you run the command from. Check the path from the table's
folder. When a case has several parts, put semicolons only between complete
paths.

## The case table is rejected

The error names the row and column. Common causes are:

- a missing required column;
- a value that is not a finite number;
- a reference area or length that is zero or negative;
- in FMF, an incomplete pair (`S` without `Ti_K`, or `Mach` without
  `Altitude_km`), or both pairs filled;
- a misspelled Hypersonic pressure method;
- an attitude angle outside its allowed range.

Check the [FMF](../reference/fmf-case-table.md) or
[Hypersonic](../reference/hypersonic-case-table.md) case table reference.

Old Excel `.xls` files are not supported. Save the file as `.xlsx` or CSV in
your spreadsheet program.

## Embree is unavailable

The Embree ray backend is optional. Reinstall Panel Solver with the `rayaccel`
extra as shown in [Installation](../getting-started/installation.md). From a
source checkout you can also use `uv sync --extra rayaccel`. Or set the case's
`ray_backend` to `rtree`, which needs no extra install. See
[Ray shielding](../methods/ray-shielding.md#backend-behavior).

## The result path is rejected

The Summary CSV must not have the same path as the case table, an STL file, or
any VTP file the run will write. Choose a different file name or folder. File
names that differ only in upper and lower case count as the same file, because
Windows and macOS usually treat them that way.

## A VTP does not load automatically

The GUI loads a case's VTP automatically only if:

- `save_vtp_on=1` for that case;
- the file is in the case's `out_dir`;
- the file was made from the current case settings (its case ID and
  `case_signature` match).

If you changed the case, or the file came from an older program version, run
the case again. You can still look at any VTP with **Open VTP...**.

## A cancelled run does not stop immediately

Cases that are already running finish before the run stops. See
[Cancellation and calculation failures](batch-runs.md#cancellation-and-calculation-failures)
for which results are kept.

## macOS GUI crashes during accessibility inspection

On macOS, the GUI can crash when an accessibility or automation tool reads the
contents of a table. This is a known bug in the Qt version that Panel Solver
uses on macOS (QTBUG-134784). It has not been seen with ordinary mouse and
keyboard use, and it is not known whether VoiceOver triggers it.

This is a known limitation of v0.1.0. Keep the Qt version that Panel Solver
installs. Qt 6.9.1 fixes this crash but has a different accessibility
problem, so it is not used yet. If the GUI crashes, restart it and check your saved
results as described in [Batch runs and recovery](batch-runs.md). When you
report a crash, include the Qt version and any accessibility or automation
tools that were running.

## A Python import fails

The package is called `panelsolver`. Use the imports listed in the
[Python API reference](../reference/python-api.md#supported-imports-and-scope).
Code that uses package names from older predecessor tools must be updated to
these imports.
