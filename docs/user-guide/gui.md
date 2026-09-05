# GUI guide

Launch the GUI with a flow-domain selector:

```bash
panelsolver-gui fmf
panelsolver-gui hypersonic
```

These open `Panel Solver — FMF` and `Panel Solver — Hypersonic`. FMF
uses the Sentman physical model; Hypersonic provides Newtonian-family methods.

## Offline help

Both launchers provide the same **Help** menu:

- **Documentation** opens the bundled offline site home;
- **About** shows Panel Solver, the installed `panelsolver` distribution
  version, the active FMF or Hypersonic domain, and the Apache-2.0 license.

Documentation opens in your desktop browser and works offline with a wheel
installation. **About** is useful when reporting a problem because it shows the
installed version and active domain.

![Panel Solver Hypersonic GUI with a loaded multi-case table and empty Viewer](../assets/screenshots/gui-overview.png)

*A loaded Hypersonic multi-case table with run controls visible and the Viewer
ready for result inspection.*

## Run cases

1. Choose **Select Input File** or **File > Open Input File...** and open a CSV,
   XLSX, or XLSM case table.
2. Select one or more table rows to run those cases. With no selected rows,
   **Run All Cases** runs every loaded case.
3. Leave **Workers** and **Checkpoint** at their defaults for a first run.
   For larger batches, see [Batch execution and recovery](batch-execution-and-recovery.md).
4. Choose **Run All Cases** or **Run Selected Cases**, as shown for the selected
   rows, and select the Summary CSV destination. The suggested location is
   `<input_dir>/outputs/<input_stem>_result.csv`.
5. Follow the progress state. Expand **Diagnostics** for warnings and errors;
   messages remain available while the log is collapsed.

Normal results are the selected Summary CSV and, when enabled, one VTP per case
at `<out_dir>/<case_id>.vtp`. Relative `out_dir` values are based on the input
table's directory. See [Case files](case-files.md#paths-vtp-destinations-and-components)
and [Summary CSV](../results/summary-csv.md) for paths and coefficient meanings.

A run whose calculations finish with one or more output-directory preparation,
VTP write, or Summary CSV write failures ends as **Completed with output
errors**, not **Failed**, and summarizes the output errors at the end; details
remain in Diagnostics. **Failed** is reserved for case-computation failures such as
geometry loading or model execution errors. Continuation and recovery behavior
is in [Batch execution and recovery](batch-execution-and-recovery.md).
After a VTP failure, an older file at that case's planned path is not auto-loaded
as the newly calculated result. It remains available for explicit **Open VTP...**
inspection.

Input validation issues identify the spreadsheet row, case ID, field, and
problem to correct. Edit the source table and reopen it before rerunning.

## Organize the workspace

The case table shows every input field, including extra fields, in the declared
column order. Case ID stays pinned while scrolling horizontally. Full geometry
paths remain available in table tooltips. **Run scope** states the execution
target and selected count in one place. **Clear selection** returns to running all loaded cases.
The overlay identifies the displayed case and groups its conditions into
separate lines with units. For a matching current result, the duplicate status
row is hidden while **Show info text** is enabled; turning it off restores the
compact status row. Manual, stale, and error states retain explicit status.
Before a result is selected, guidance appears inside the empty Viewer only.
Workers and Checkpoint accept direct number entry and keyboard stepping;
the adjacent minus and plus controls decrease or increase the value.

Scalar, colormap, color range, display toggles, all camera directions, and image
export stay visible below the Viewer. Camera groups and display toggles wrap
onto another row when the window is narrow. Min and Max retain their
existing behavior: blank endpoints are automatic. The colorbar shows the actual
limits. Invalid numeric text falls back to the automatic range; the affected
input is marked and its tooltip explains the fallback.

**Show diagnostics** opens the log and changes to **Hide diagnostics**.
**Clear log** clears its contents and resets the warning and error counts, even
while the log is collapsed or a run is active. New messages continue to arrive
after clearing. The counts represent warning and error **messages received since
the last clear** (or application launch), not failed cases. Read and write error states provide a direct route
to Diagnostics. During cooperative cancellation, the progress display continues
to say **Cancelling** even when further progress arrives.

Window placement, split position, column widths, and Diagnostics visibility
are remembered separately for each domain. **View > Reset Layout** restores the
initial workspace layout. Input files, row selection, execution settings, and
color-range values are not restored by this feature. The platform's standard
Open shortcut opens an input file.

## Start from an example

Choose **File > New from Example** to see only the examples for the active FMF
or Hypersonic domain. Select a workspace directory; the GUI copies the chosen
case table and its required geometry there with their relative layout intact,
then opens the copied table. You can edit and rerun this workspace copy.
The [Quickstart](../getting-started/quickstart.md) explains the Basic example
and its first results.

## View and export

When a case saves VTP, the first selected case's result is loaded automatically.
A selected row also loads an existing `<out_dir>/<case_id>.vtp` when the file's
`case_id` and `case_signature` match the selected case ID and the signature
calculated from that case. Missing VTP files and files with a mismatched case ID
or signature are not rendered automatically. The compact status row above the
Viewer explains what result is displayed or why no matching VTP is available;
the [VTP reference](../results/vtp.md) lists the signature and case-level field
data.

![Panel Solver Viewer showing the newt_pm cube result colored by Cp](../assets/screenshots/gui-result.png)

*The `newt_pm` case with its matching VTP loaded automatically and the cube
geometry displayed using `Cp`.*

VTP files can be opened from **File > Open VTP...** or the Viewer
**Open VTP...** button. This manual operation can display a VTP that does not
match any row in the loaded case table. The status identifies the file as
**Manual VTP** and explicitly says whether it matched a loaded case. A manually
opened, unmatched VTP is not the result for the selected case,
even though its geometry remains visible. The viewer can switch among available
cell scalars, adjust the camera and coloring, open another VTP, and save images.
Scalar controls and color bars use human-readable labels such as `Cp`,
`Normal traction coeff.`, and `Tangential traction coeff.` while VTP retains
explicit machine-oriented field names.

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
Manual export remains available for stale or unmatched VTPs; saving an image
does not make that VTP the result of a newly calculated case.

Closing the window during a run requests cancellation and waits for worker
cleanup. Cancellation boundaries and retained output files are described in
[Batch execution and recovery](batch-execution-and-recovery.md#cancellation-and-calculation-failures).

See [Case files](case-files.md), the
[Summary CSV reference](../results/summary-csv.md), the
[VTP reference](../results/vtp.md), and
[Troubleshooting](troubleshooting.md).
