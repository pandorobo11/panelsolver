# Using the GUI

Start the GUI for a flow domain:

```bash
panelsolver-gui fmf
panelsolver-gui hypersonic
```

The window title shows the domain: `Panel Solver — FMF` or
`Panel Solver — Hypersonic`.

![Panel Solver Hypersonic GUI with a loaded multi-case table and empty Viewer](../assets/screenshots/gui-overview.png)

*A loaded Hypersonic case table, ready to run and inspect.*

The window has three areas: the case table at the top, the Viewer below it,
and the Diagnostics log. Drag the divider between the table and the Viewer to
resize them.

## Run cases

1. **Open a case table.** Choose **Select Input File** or **File > Open Input
   File...** (or use your system's Open shortcut), or drag a CSV, XLSX, or XLSM
   file onto the window. Before a table is open, the empty area also offers
   **Select Input File...** and **New from Example**.
2. **Choose the cases.** Select one or more rows to run only those cases. With
   no rows selected, all cases run; **Clear selection** returns to that. The
   **Run scope** line below the table shows what will run, for example
   `Run scope: 2 of 5 cases selected`.
3. **Check the run settings.** For a first run, keep the default **Workers**
   value. **Show advanced** reveals the **Checkpoint** setting. See
   [Batch runs and recovery](batch-runs.md) for when to change them.
4. **Start the run.** Choose **Run All Cases** or **Run Selected Cases**, then
   choose where to save the Summary CSV. The suggested file is
   `<input folder>/outputs/<input name>_result.csv`. You can also use
   **Run > Run Cases** (Ctrl+R; ⌘R on macOS).
5. **Follow progress.** The progress bar shows the run state. Open
   **Diagnostics** for warnings and errors.

Each run writes the Summary CSV and, unless `save_vtp_on=0`, one VTP per case at
`<input folder>/outputs/<case_id>.vtp`, where `<input folder>` is the folder
that contains the case table; see
[Preparing cases](preparing-cases.md#paths-vtp-destinations-and-components).

### If the case table has errors

When a case table has problems, the **Input Validation Errors** window lists
every problem found, with its **Row**, **Case ID**, **Field**, and
**Message**. No cases are loaded. Choose **Copy** to copy the list as
tab-separated text, which you can paste into a spreadsheet or a problem report.
Fix the table, then open it again. The
[common validation](preparing-cases.md#common-validation) list describes the
checks.

### Edit and reload

After you edit the case table in another program, choose **Reload** (next to
**Select Input File**) to read it again. Reload clears the row selection. If
the edited file has errors, the old cases are cleared too; fix the file and
open it again. **Reload** is not available while a run is in progress.

### Cancel a run

Choose **Cancel** or **Run > Cancel Run** (Ctrl+.; ⌘. on macOS). The progress
bar shows **Cancelling** until the cases already in progress finish. Closing
the window during a run also cancels it. See
[Batch runs and recovery](batch-runs.md#cancellation-and-calculation-failures)
for which results are kept.

### If the Summary CSV cannot be saved

If the final Summary CSV cannot be written, for example because the disk is
full or another program has the file open, an error message offers **Retry**.
Fix the cause first, then retry; you can also pick another file. The
calculated results are kept, so nothing is calculated again and no VTP files
are rewritten.

If you close the message, a **Retry Save...** button stays next to **Cancel**
until the results are saved or a new run finishes. The results are kept only
while the window is open. If you close the window before saving, you are asked
whether to **Save**, **Discard**, or **Cancel**.

Panel Solver never lets a result overwrite your input files: the case table,
STL files, sectional definition files, and planned VTP files are all
protected.

## Start from an example

Choose **File > New from Example** and pick an example. Select a folder; the GUI
copies the case table and its geometry there and opens the copied table.
Existing files that you have changed are not overwritten. Edit and run this
copy freely. The [Quickstart](../getting-started/quickstart.md) walks through
the **Basic** example, and [Examples](../getting-started/examples.md) describes
the others.

## Work with the case table

- The table shows every input column, including your own extra columns.
  Headers show units, and the **Case ID** column stays visible while you
  scroll sideways.
- Hover over a geometry cell to see its full path. If the input path is too
  long for its field, the start is shortened; hover over it, or right-click and
  choose **Copy Path**.
- The window position, divider position, column widths, Diagnostics
  visibility, and **Show advanced** state are remembered for each domain.
  **View > Reset Layout** restores the original layout. Open files, selections,
  run settings, and color ranges are not remembered.

## View results and run sectional batches

To look at surface results and save images, see
[Viewing results in the GUI](gui-viewer.md). For sectional loads and Cp, see
[Sectional loads and Cp](sectional.md).

## Diagnostics and run status

**Show diagnostics** opens the log; **Hide diagnostics** closes it again.
Messages keep arriving while it is closed. **Clear log** clears the messages
and the warning and error counts.

| Status | What it means | What to do |
|---|---|---|
| Input validation error | The case table has a problem. The **Input Validation Errors** window names the row, case ID, and column. | Fix the table, then reopen it. |
| **Failed** | A case could not be calculated, for example because its geometry could not be loaded. | Read Diagnostics for the cause. |
| **Completed with output errors** | All cases were calculated, but a VTP or the Summary CSV could not be written. | Read the error summary and Diagnostics. |

Error messages in the Viewer include a **Diagnostics** button that opens the
log. If a VTP could not be written, an older file with the same name may still
exist. The GUI does not load it automatically, but you can open it with
**Open VTP...**. See [Batch runs and recovery](batch-runs.md) for how to rerun
cases.

## Help menu

- **Help > Documentation** opens this documentation in your web browser. It is
  installed with Panel Solver and works offline.
- **Help > About** shows the installed version, the active domain, and the
  license. Include the version and domain when you report a problem.

See [Troubleshooting](troubleshooting.md) for common problems.
