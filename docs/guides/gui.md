# GUI guide

Launch the GUI with a flow-domain selector:

```bash
panelsolver-gui fmf
panelsolver-gui hypersonic
```

These open `Panel Solver — FMF` and `Panel Solver — Hypersonic`.

![Panel Solver Hypersonic GUI with a loaded multi-case table and empty Viewer](../assets/screenshots/gui-overview.png)

*A loaded Hypersonic case table, ready to run and inspect.*

## Run cases

1. Choose **Select Input File** or **File > Open Input File...** and open a CSV,
   XLSX, or XLSM case table. The platform's standard Open shortcut also works,
   and you can drop a case table onto the window. Before a table is loaded, the
   empty case area offers **Select Input File...** and **New from Example**.
2. Select one or more rows to run those cases. Use **Clear selection** to return
   to running all loaded cases; **Run scope** below the table shows the target,
   for example `Run scope: all 5 cases` or `Run scope: 2 of 5 cases selected`.
3. Leave **Workers** at its default for a first run. **Checkpoint** is an
   advanced setting shown by **Show advanced**. For larger batches, see
   [Batch execution and recovery](batch-runs.md).
   Both settings support direct entry, keyboard stepping, and minus/plus buttons.
4. Choose **Run All Cases** or **Run Selected Cases**, as shown for the selected
   rows, and select the Summary CSV destination. The suggested location is
   `<input_dir>/outputs/<input_stem>_result.csv`. **Run > Run Cases**
   (Ctrl+R; ⌘R on macOS) does the same, and **Run > Cancel Run** (Ctrl+.; ⌘. on
   macOS) cancels an active run.
5. Follow the progress state. Open **Diagnostics** for warnings and errors.

After editing the case table externally, choose **Reload** beside **Select Input
File** to reread the current CSV, XLSX, or XLSM without choosing it again. These
two buttons stay together and wrap below the input path when space is limited. Reload
resets the case selection; select rows again to run a subset. The button is
disabled until an input is loaded and during ordinary or sectional calculation
and saving. If reading fails, the previous cases are cleared and cannot be run;
fix the source and open it again. Reload does not reread sectional definition
CSVs; use **Reload** in the corresponding Sectional dialog for those files.

The run writes the selected Summary CSV and, when enabled, one VTP per case at
`<out_dir>/<case_id>.vtp`. Relative `out_dir` values use the input table's
directory. See [Case files](preparing-cases.md#paths-vtp-destinations-and-components)
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
[Batch execution and recovery](batch-runs.md#cancellation-and-calculation-failures)
explains cancellation boundaries and which outputs remain available.

## Start from an example

Choose **File > New from Example** and an example for the active domain. Select
a workspace directory; the GUI copies the case table and required geometry there,
keeping their relative layout, then opens the copied table. Edit and rerun this
workspace copy. The [Quickstart](../getting-started/quickstart.md) explains the
Basic example and its first results.

## Organize the workspace

The case table shows all input fields, including extra fields, in their declared
order. Headers show units, and Case ID stays pinned while scrolling horizontally.
Hover over a geometry cell to read its full path. When the input path is longer
than its field, leading folders are shortened so the file name stays visible;
hover over the field for the full path, or use **Copy Path** from its context
menu. Drag the grip between the case table and the Viewer to resize them.

Window placement, split position, column widths, Diagnostics visibility, and
the **Show advanced** state are remembered separately for each domain. Saved
widths expand as needed to fit headers. **View > Reset Layout** restores the
initial workspace layout.
Input files, row selection, execution settings, and color-range values are not
restored by this layout feature.

Viewer file actions (**Open VTP...**, **Save Image...**, **Save Selected
Images...**) sit above the display; scalar, range, display, and camera controls
remain available below it. Related controls wrap together in a narrow window,
as do each run setting and its label; run and cancel actions stay together.

## View results and run sectional batches

To inspect surface results and save images, see
[Viewing results in the GUI](gui-viewer.md). For sectional
load and Cp batches, see [Sectional loads and Cp](sectional.md).

## Diagnostics and run status

**Show diagnostics** opens the log and changes to **Hide diagnostics**. Messages
continue to arrive while the log is collapsed. **Clear log** clears messages and
resets warning/error counts, including during an active run. Counts represent
messages received since the last clear or application launch.

| Status or issue | Meaning and action |
|---|---|
| Input validation issue | The message identifies the spreadsheet row, case ID, field, and problem. Edit the source table and reopen it before rerunning. |
| **Failed** | A case calculation failed, such as during geometry loading or model execution. Read Diagnostics for the cause. |
| **Completed with output errors** | Calculations finished, but output-directory preparation, VTP writing, or Summary CSV writing failed. Read the final error summary and Diagnostics. |

Read and write error states provide a direct route to Diagnostics. After a VTP
write failure, an older file at the planned path remains available through
**Open VTP...**, with automatic loading suppressed for that failed write.
See [Batch execution and recovery](batch-runs.md) for retained
results and rerun options.

## Offline help

The **Help** menu provides:

- **Documentation:** opens the bundled offline site in your desktop browser,
  including with a wheel installation.
- **About:** shows Panel Solver, its installed distribution version, the active
  domain, and the Apache-2.0 license. Include the version and domain in problem
  reports.

See [Troubleshooting](troubleshooting.md) for common problems.
