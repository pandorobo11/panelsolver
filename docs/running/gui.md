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
   XLSX, or XLSM case table. The platform's standard Open shortcut also works.
2. Select one or more rows to run those cases. Use **Clear selection** to return
   to running all loaded cases; **Run scope** shows the target and selected count.
3. Leave **Workers** and **Checkpoint** at their defaults for a first run.
   For larger batches, see [Batch execution and recovery](batch-execution-and-recovery.md).
   Both settings support direct entry, keyboard stepping, and minus/plus buttons.
4. Choose **Run All Cases** or **Run Selected Cases**, as shown for the selected
   rows, and select the Summary CSV destination. The suggested location is
   `<input_dir>/outputs/<input_stem>_result.csv`.
5. Follow the progress state. Open **Diagnostics** for warnings and errors.

The run writes the selected Summary CSV and, when enabled, one VTP per case at
`<out_dir>/<case_id>.vtp`. Relative `out_dir` values use the input table's
directory. See [Case files](../inputs/case-files.md#paths-vtp-destinations-and-components)
for path rules.

During cancellation, progress shows **Cancelling** until workers finish cleanup.
Closing the window during a run also requests cancellation and waits for cleanup.
[Batch execution and recovery](batch-execution-and-recovery.md#cancellation-and-calculation-failures)
explains cancellation boundaries and which outputs remain available.

## Organize the workspace

The case table shows all input fields, including extra fields, in their declared
order. Headers show units, and Case ID stays pinned while scrolling horizontally.
Hover over a geometry cell to read its full path.

Window placement, split position, column widths, and Diagnostics visibility are
remembered separately for each domain. Saved widths expand as needed to fit
headers. **View > Reset Layout** restores the initial workspace layout.
Input files, row selection, execution settings, and color-range values are not
restored by this layout feature.

Viewer controls remain available below the display. Related controls wrap
together in a narrow window, as do each run setting and its label; run and cancel
actions stay together.

## Start from an example

Choose **File > New from Example** and an example for the active domain. Select
a workspace directory; the GUI copies the case table and required geometry there,
keeping their relative layout, then opens the copied table. Edit and rerun this
workspace copy. The [Quickstart](../getting-started/quickstart.md) explains the
Basic example and its first results.

## View and export

### Select a result

When a case saves VTP, the first selected case's result loads automatically.
Selecting a row also loads an existing `<out_dir>/<case_id>.vtp` when its
`case_id` and `case_signature` match the selected case. For missing or mismatched
files, the Viewer status explains why a matching result is unavailable.

![Panel Solver Viewer showing the newt_pm cube result colored by Cp](../assets/screenshots/gui-result.png)

*The `newt_pm` case with its matching VTP colored by `Cp`.*

Use **File > Open VTP...** or the Viewer **Open VTP...** button to inspect a file
manually. Its **Manual VTP** status says whether it matches a loaded case, so
an unmatched file can be inspected independently of the selected row.

**Show info text** displays the case identity and conditions over the geometry.
For a matching current result, enabling it hides the duplicate compact status
row; disabling it restores that row. Manual, stale, and error states retain
explicit status. An empty Viewer displays guidance for selecting a result.

### Choose surface data and coloring

Select a cell scalar, colormap, and camera direction below the Viewer. The
scalar labels correspond to these [VTP fields](../results/vtp.md):

| VTP field | GUI label |
|---|---|
| `cp` | Cp |
| `normal_traction_coeff` | Normal traction coeff. |
| `tangential_traction_coeff` | Tangential traction coeff. |
| `shielded` | Shielded |
| `theta_deg` | Theta [deg] |
| `area_m2` | Area [m^2] |
| `center_x_stl_m` | Center X [m] |
| `center_y_stl_m` | Center Y [m] |
| `center_z_stl_m` | Center Z [m] |
| `stl_index` | STL index |

Set **Min** and **Max** to choose color limits; leave either endpoint blank for
an automatic limit. The colorbar shows the actual range. Invalid numeric text
falls back to automatic, with the input marked and a tooltip explaining why.

**Background** offers **Follow theme** (initial), **White**, and **Black**.
Following the theme uses white in light mode and black in dark mode. An explicit
color stays selected across theme changes for the current window. Text and axes
use a contrasting color, and saved images include the selected background.

### Save images

Use **Save Image...** to save the current view. For a VTP matched to a loaded
case, the suggested file is
`<out_dir>/images/<case_id>__<scalar_name>.png`, where `scalar_name` is the
VTP field name above, for example `normal_traction_coeff`. For an unmatched
manual VTP, the suggestion is under `images/` beside that VTP. Choose another
directory or name in the dialog as needed. Unsafe filename characters are
adjusted automatically.

**Save Selected...** exports images for the selected cases. The suggested
directory is `images/` under their common output directory, or
`<input_dir>/outputs/images` if they use different output directories. Batch
export preserves existing images by adding a numeric suffix to duplicate names.
Manual export is also available for stale or unmatched VTPs, with the displayed
result status preserved.

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
See [Batch execution and recovery](batch-execution-and-recovery.md) for retained
results and rerun options.

## Offline help

The **Help** menu provides:

- **Documentation:** opens the bundled offline site in your desktop browser,
  including with a wheel installation.
- **About:** shows Panel Solver, its installed distribution version, the active
  domain, and the Apache-2.0 license. Include the version and domain in problem
  reports.

See [Troubleshooting](troubleshooting.md) for common problems.
