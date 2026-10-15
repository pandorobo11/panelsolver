# Detailed user-visible behavior

This page keeps implementation-level behavior that was removed from the user
documentation in favor of shorter, task-based explanations. The user pages in
`docs/` remain the product contract; this page records how that behavior is
achieved and edge cases that matter for maintenance, review, and support. When
the two disagree, the current code and accepted ADRs decide, and both pages
must be corrected together.

## GUI ordinary run: reload, retained Summary results, and protection

User summary: [Using the GUI](../../docs/guides/gui.md#run-cases).

After editing the case table externally, choose **Reload** beside **Select Input
File** to reread the current CSV, XLSX, or XLSM without choosing it again. These
two buttons stay together and wrap below the input path when space is limited. Reload
resets the case selection; select rows again to run a subset. The button is
disabled until an input is loaded and during ordinary or sectional calculation
and saving. If reading fails, the previous cases are cleared and cannot be run;
fix the source and open it again. Reload does not reread sectional definition
CSVs; use **Reload** in the corresponding Sectional dialog for those files.

The run writes the selected Summary CSV and, when enabled, one VTP per case at
`<input_dir>/outputs/<case_id>.vtp`, where `<input_dir>` is the input table's
directory (ADR 0021). See Case files
for path rules.

If the final Summary CSV cannot be saved, the **Output Errors** message offers
**Retry**, and **Retry Save...** appears beside **Cancel** for later use. Either
saves the retained result to the same or another CSV destination without
recalculating cases or writing VTP files again. Fix the cause first, such as
freeing disk space or closing a program that holds the file open. The message
below the progress bar identifies the retained run's input filename and case
count. Reloading inputs or changing selections does not change that result.
Original and currently loaded case tables, STL files, planned VTP outputs, and
sectional definition files are protected against overwriting, including file
aliases and unselected cases.

The button disappears after a successful retry or a later completed calculation
replaces the retained result. Failed or cancelled calculations leave a previous
unsaved result available; they do not add their partial results to it. Results
are retained only for the current application session. Saving runs in the
background and temporarily disables ordinary and sectional calculations. If a
pending window close meets a Summary CSV save failure, the window remains open
for retry. Closing the window while a result is retained asks whether to save
it first: **Save** closes after a successful save, **Discard** closes without
it, and **Cancel** keeps the window open. Other output errors, such as a VTP
failure, remain in Diagnostics.

During cancellation, progress shows **Cancelling** until workers finish cleanup.
Closing the window during a run also requests cancellation and waits for cleanup.
Batch execution and recovery
explains cancellation boundaries and which outputs remain available.

The retained projection and export worker are described in
[Architecture: Execution and artifacts](overview.md#execution-and-artifacts).

## GUI sectional dialogs

User summary: [Sectional loads and Cp](../../docs/guides/sectional.md).

The definition table supports opening and reloading files, not definition
editing. Edit the CSV externally and reload it before starting a new batch.
A failed reload clears the runnable definitions and reports the error.
The open definition CSV is protected from ordinary Summary CSV output as well
as sectional output, including while the Sectional Loads window is hidden.
Opening or reloading definitions is disabled during ordinary calculation.

Starting a run freezes both selections and definitions. Later selection/file
changes do not relabel completed results. Run and export status are separate:
cancelled or failed batches save any successful pairs to the chosen destination,
with their actual terminal status. If no pair succeeds, the output is unchanged.
A save failure retains the calculation and offers **Retry** in the error
dialog. It opens the save chooser after the export worker has finished cleanup.
**Close** dismisses that message; **Retry Save...** remains available to select a
destination and save without rerunning physics. These actions also save retained
partial results with their original failed or cancelled batch status. The button is hidden after
successful saving and never substitutes current selections for the failed-save
snapshot.
Result rows include their actual case signatures, section IDs and terminal
batch status, including partial results.

Normal case solving and sectional solving cannot run simultaneously. Cancel
requests stop at safe boundaries; already-running parallel cases can finish.
Closing during a run requests cancellation and waits for calculation, automatic
export of successful pairs, and worker cleanup. Ordinary runs remain disabled
until both calculation and saving finish.
If saving fails while a close request is waiting, the window remains open so
you can use **Retry Save...**. Closing the Sectional dialog (including Esc) or
the main window while a failed-save result is retained offers **Save**,
**Discard**, and **Cancel**. Save closes only after a successful export; cancelling
the file chooser or another save failure keeps the window and results available.
Discard releases that dialog's unsaved result, and Cancel keeps it open.
Main-window close also checks hidden Sectional dialogs and checks Loads and Cp
independently when both hold unsaved results. Results are held only in the current
application session.
No intermediate Summary CSV or VTP is required or created by sectional runs.

## Viewer smooth colors

User summary: [Viewing results in the GUI](../../docs/guides/gui-viewer.md#smooth-color-distributions).

Smooth colors uses the arithmetic mean of adjacent panel values at each vertex,
then interpolates those values across each face. The display copy joins exactly
coincident vertices within each STL component and shielding group. It does not
average across those groups or along sharp edges exceeding 30 degrees. Where a
sharp edge ends inside a surface, the vertex at its tip is not split, so values
there can still blend across that edge. The exact threshold is subject to
floating-point precision. The original mesh and result arrays, calculations,
Summary/sectional CSVs and VTP files remain unchanged. Automatic color limits
still use the original panel values, so switching display modes preserves the
color scale.

The colorbar title includes **(interpolated)** while active, including in saved
images. This is a visualization aid: peaks may be reduced and jumps within a
smooth surface may blur. Switch it off to inspect original panel values.
**Shielded**, **STL index**, and boolean fields always use panel values; the
control is disabled for these fields and resumes its previous choice when a
continuous scalar is selected. The choice applies to subsequent loaded results
and image exports in the current window.

If interpolation fails, the Viewer keeps the requested setting, uses panel
values for that display only, labels the colorbar with the failure, and logs
the reason in Diagnostics once. A failure is not retried for the same loaded
result; reload the VTP to retry. Subsequent valid results resume interpolation.
If any panel would be lost from the smoothed display, the whole view falls back
to panel values rather than showing a partial surface. Malformed `stl_index` or
`shielded` arrays do not prevent ordinary VTP inspection; only Smooth colors
falls back. Both modes treat every nonzero `shielded` value as shielded, and
imported shading normals are kept.

With Smooth colors off, imported VTPs keep PyVista's existing preference for
point data when a name exists in both associations.

The Viewer does not repair winding or reorient normals: the 30-degree split
uses normals from the original face winding. Oppositely oriented coplanar faces
therefore remain separate rather than being averaged, and non-manifold
junctions may also remain separated. Resolve mesh orientation problems before
calculation instead of relying on display interpolation to hide them.

## Summary CSV checkpoint writes

User summary: [Batch runs and recovery](../../docs/guides/batch-runs.md#checkpoints).
Delta checkpoint appends record the original byte length, synchronize new rows,
and truncate back to that length on a caught write failure. A rollback failure
disables further appends for the run and is reported explicitly; the final
atomic write is still attempted. The decision and its evidence are in
[ADR 0016](../adr/0016-append-csv-checkpoints.md).

## Case signature contents

The `case_signature` (SHA-256, `panelsolver.case` v2) incorporates the numerical
geometry, the normalized common and model case, the model algorithm version,
and the shielding configuration including the effective backend. See
[ADR 0005](../adr/0005-case-signature-versioning.md) and
[ADR 0017](../adr/0017-full-direction-attitudes.md).

## VTP connectivity encoding

Before writing, each triangle is stored in the flattened VTK connectivity array
as `[3, i0, i1, i2]`. Ordinary VTK/PyVista readers expose the same values as
triangle cells. Encoding details are outside the documented VTP guarantee.

## Sectional definitions

`section_id` values are trimmed and Unicode NFC normalized before the
uniqueness check, and remain case-sensitive. Selected component IDs are sorted
for output.

## Sectional loads moment integration

Sectional strips integrate moments topology-locally, which avoids loss from
rounding absolute face centroids. Full-range sums can therefore differ from the
stored whole-face-centroid integrator within the source geometry's
representation error; no conservation residual is redistributed. See
[Internal sectional load integration](sectional-integration.md).

## Sectional Cp intersection precision

User summary: [Sectional Cp CSV](../../docs/reference/sectional-cp-csv.md).

The intersection predicates use exact rational arithmetic on stored float64
vertices, origins and normalized directions. Automatic plane offsets retain exact
projected extrema and exact interpolation (the midpoint for one plane) through
intersection testing. Only their reported positions and endpoint coordinates are
rounded to float64; an explicitly supplied position uses the supplied float64
value. No epsilon snaps nearby surfaces together. Source topology is checked
against the same geometry validation used by sectional loads.

If both endpoints round to exactly the same float64 coordinates, that segment
is omitted and the plane has `warning` status. `omitted_segment_count` records
the plane-wide omitted count, repeated on each surviving segment row; do not sum
this repeated value across rows of the same plane. All remaining segments and
their unchanged panel values are saved. If none remain, one warning status row has blank segment/value
fields. Such planes count as completed in the batch; GUI/CLI logs also report the
warning, including original source face indices (zero-based). Failure reasons
also go to the logs. CSV contains no `message` column or detailed diagnostic text.
The Python API retains `message`. A coplanar triangle still fails the entire plane.

This rule is exact equality after rounding, not a length threshold or epsilon.
Representable short segments remain. When adjacent segments share the exact
endpoints, omitting the collapsed segment preserves closure in the saved
coordinates; no contour assembly, gap repair, or closure guarantee is added.
The omitted panel's scalar is not transferred to adjacent panels. Rational
arithmetic costs more than a floating point-only slice; large meshes with many
planes may be slower.

CSV output is atomic. Successful and failed plane records from completed
extractions are saved even when batch status is failed. If no extraction returns
records, the destination is unchanged. Cancellation occurs between definitions
(serial), or between cases (parallel); an active extraction finishes first.
Existing Summary CSV, sectional load CSV and VTP outputs are unchanged.

The decision and its amendments are in
[ADR 0020](../adr/0020-sectional-cp-segments.md).

## Python API result context

Solver-produced results retain their immutable topology and common references
privately for postprocessing, from the same physical execution. Existing
`SolveResult` constructor arguments are unchanged. Manually constructed results,
including results reconstructed by `dataclasses.replace`, have no retained
solve context and cannot be used for sectional postprocessing. A deep copy of
an original solver-produced result retains its immutable data and context.

## macOS Qt accessibility limitation

User summary:
[Troubleshooting](../../docs/guides/troubleshooting.md#macos-gui-crashes-during-accessibility-inspection).
The macOS dependency pin selects PySide6/Qt 6.9.0 to avoid the QTBUG-149612
table-accessibility crash; that pin does not support Python 3.14 or newer. The
pinned version still has the native table-accessibility bug QTBUG-134784: the
GUI can crash after an accessibility tool reads table-cell values. This was
observed with Computer Use and reproduced in an isolated Qt test. It has not
been reproduced with ordinary mouse and keyboard use alone, and a
VoiceOver-specific reproduction has not been established. Qt 6.9.1 fixes this
defect but fails a separate selected-cell accessibility regression. The pin
will be reassessed when both defects are addressed. See also the
[GUI visual-smoke helper](../development/gui-visual-smoke.md).
