# GUI guide

Launch the canonical GUI with a flow-domain selector:

```bash
panelsolver-gui fmf
panelsolver-gui hypersonic
```

These open `Panel Solver — FMF` and `Panel Solver — Hypersonic`. FMF currently
uses the Sentman physical model; Hypersonic provides Newtonian-family methods.

The legacy compatibility commands `fmfsolver`, `fmfsolver-gui`, `newtsolver`,
and `newtsolver-gui` remain available with their existing titles and behavior.

## Offline help

Every launcher uses the shared **Help** menu:

- **Documentation** opens the bundled offline site home;
- **About** shows Panel Solver, the installed `panelsolver` distribution
  version, the active FMF or Hypersonic domain, and the Apache-2.0 license.

Pages are opened as local `file://` URLs through the desktop browser. The wheel
contains the complete site, so Help does not use the network or require MkDocs
at runtime. If the installed resource is missing or the browser rejects the
local URL, the GUI reports an error. An editable checkout may build a temporary
site with the docs dependency group installed; that temporary resource remains
alive for the lifetime of the window.

## Run cases

1. Choose **Select Input File** or **File > Open Input File...** and open a CSV,
   XLSX, or XLSM case table. Immediately after a new GUI launch, the dialog starts
   in the process current working directory. After a successful normal load, later
   dialogs in the same GUI session start in that file's parent directory. This
   directory is not carried over after the GUI exits and restarts. If it is deleted
   during the session, the dialog falls back to the process current working
   directory.
2. Select one or more table rows to run only those cases. With no selected rows,
   **Run All Cases** runs every loaded case.
3. Set **Workers**. Use `1` for the simplest deterministic run.
4. Set **Checkpoint every** in cases. The default is `2000`; use `0` to
   disable intermediate Summary CSV snapshots.
5. Choose **Run All Cases** or **Run Selected Cases**, as shown for the current
   selection, and select the summary CSV destination.
6. Follow the always-visible progress state. Select **Diagnostics** when detailed
   operational messages are useful.

The Diagnostics log is collapsed by default so cases, run controls, progress,
the Viewer, and Viewer provenance retain priority. Collapsing Diagnostics does
not discard its history: messages continue to accumulate and are available when
the section is expanded again.

The case table uses user-facing headers with source units while retaining the
canonical case-file columns internally. Comparable numeric values are right-
aligned; identifiers and text remain left-aligned, and 0/1 flags are centered.
This presentation layer does not round values, normalize scientific notation,
or convert units.

A successful calculation with one or more VTP, checkpoint, or final Summary CSV
write failures finishes as **Completed with output errors**, not **Failed**. The
run continues after per-case VTP failures and shows one bounded summary at the
end; complete details remain in the log. **Failed** is reserved for case
computation failures such as geometry loading or model execution errors.
After a VTP failure, an older file at that case's planned path is not auto-loaded
as the current result. It remains available for explicit **Open VTP...**
inspection.

Input validation issues are shown with spreadsheet row, case ID, field, and
message. The GUI uses the same reader, execution engine, checkpoint behavior,
and output serializers as the CLI.

## Start from an example

Choose **File > New from Example** to see only the examples for the active FMF
or Hypersonic domain. Select a workspace directory; the GUI copies the chosen
case table and its required geometry there with their relative layout intact,
then opens the copied table. Packaged examples are never run in place, and
opening one does not replace the session's remembered directory for normal input
files.

## View and export

When a case saves VTP, the first selected case's result is loaded automatically. A
selected row also loads an existing `<out_dir>/<case_id>.vtp` when its case ID
and accepted primary or legacy signature match. Missing, stale-signature, and
identity-mismatched artifacts are not rendered automatically. The compact status
row above the Viewer explains what result is displayed or why the selected case's
result is unavailable; the signature and field-data contract is documented in
[Output formats](../reference/output-formats.md).

VTP files can be opened from **File > Open VTP...** or the Viewer
**Open VTP...** button. This manual inspection path can display an artifact that
does not strictly match any current input row. The status identifies that
artifact as **Manual VTP** and explicitly says whether it matched a current case.
A manually opened unmatched artifact is not the current selected-case result,
even though its geometry remains visible. The viewer can switch among available
cell scalars, adjust the camera and coloring, open another VTP, and save images.
Scalar controls and color bars use human-readable labels such as `Cp`,
`Normal traction coeff.`, and `Tangential traction coeff.` while VTP retains
explicit machine-oriented field names.

| VTP/internal field | GUI label |
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

For a case-associated VTP, **Save Image...** starts at
`<resolved_out_dir>/images/<case_id>__<scalar_name>.png`. The scalar portion is
the machine-oriented VTP field name from the first column above, not its GUI
label. For example, the default may be
`outputs/images/case_001__normal_traction_coeff.png`.
Characters that are unsafe in portable filenames (`/`, `\`, `:`, `*`, `?`,
`"`, `<`, `>`, `|`, and control characters) are replaced with `_` in both the
case or VTP identifier and scalar portions. Leading and trailing whitespace and
trailing dots are removed; an empty result uses a safe fallback name.

For a VTP opened with **Open VTP...** that does not match a current case and
signature, the default is
`<vtp_parent>/images/<vtp_stem>__<scalar_name>.png`. A stale or
signature-mismatched VTP can still be inspected and exported manually.

**Save Selected...** starts at `<resolved_out_dir>/images` when every selected
case resolves to the same output directory. If selected cases use different
resolved output directories, it starts at `<input_dir>/outputs/images`,
independent of row order. Batch filenames use the same
`<case_id>__<scalar_name>.png` form. Existing files are never overwritten by a
batch export: Panel Solver adds `_2`, `_3`, and so on before `.png`, including
when names would collide within the current batch.

For **Save Image...**, the required image directory and missing parents are
created after the save dialog is confirmed. For **Save Selected...**, the
standard or remembered directory is created before the folder chooser opens so
it can be selected on the first export; canceling that chooser may therefore
leave an empty `images` directory. A creation failure is logged, the chooser is
not opened, and no screenshot is attempted. Calculations themselves do not
create image directories.

If another image directory is selected, it is reused as the starting directory
for later case-associated image saves while the same input file remains loaded.
This session-only choice is reset after a different input file loads
successfully; if the remembered directory is deleted, the standard directory is
created if needed and used again. An unmatched manually opened VTP always uses
its own parent-based standard location. Export buttons remain disabled until a
viewport or explicitly selected loaded cases, respectively, are available.

Relative `out_dir` values, automatic VTP loading, and case-associated default
image directories are all resolved from the loaded input table's directory.

Closing the window during a run requests cooperative cancellation and waits for
worker cleanup. An active ray query or model solve may finish before cancellation
is observed; files already written are not rolled back.

See [Case files](case-files.md), [Outputs](outputs.md), and
[Troubleshooting](troubleshooting.md).
