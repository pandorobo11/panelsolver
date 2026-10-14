# Viewing results in the GUI

The Viewer shows the surface result (VTP) for one case. Start a run as
described in the [GUI guide](gui.md#run-cases).

## Select a result

When a case saves VTP, the first selected case's result loads automatically.
Selecting a row also loads an existing `<out_dir>/<case_id>.vtp` when its
`case_id` and `case_signature` match the selected case. For missing or mismatched
files, the center of the Viewer explains why a matching result is unavailable.

![Panel Solver Viewer showing the newt_pm cube result colored by Cp](../assets/screenshots/gui-result.png)

*The `newt_pm` case with its matching VTP colored by `Cp`.*

Use **File > Open VTP...**, the Viewer **Open VTP...** button, or drop a `.vtp`
file onto the window to inspect a file manually, independently of the selected
row. A file does not need to match a loaded case to be inspected.

**Show info text** displays the case identity and conditions over the geometry.
There is no separate status row above the display. An empty Viewer displays
guidance for selecting a result or explains why a result is unavailable. Read
and write errors include a **Diagnostics** button below the central explanation.

## Choose surface data and coloring

Select a cell scalar, colormap, and camera direction below the Viewer. The
colorbar shows the scalar name above the bar and the tick values below it. The
scalar labels correspond to these [VTP fields](../reference/vtp.md):

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

**Camera** views the model from an STL axis direction, from one of two
isometric directions, or from **Upstream** or **Downstream** along the case
flow direction. **Fit** refits the model in the view without rotating it.

**Background** offers **Follow theme** (initial), **White**, and **Black**.
Following the theme uses white in light mode and black in dark mode. An explicit
color stays selected across theme changes for the current window. Text and axes
use a contrasting color, and saved images include the selected background.

## Smooth color distributions

Enable **Smooth colors** in the Display row to interpolate continuous panel
values across the surface. The default is off, preserving the original
constant value on each panel. Turn off **Show edges** for an uninterrupted
color distribution; edge visibility remains an independent choice.

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

## Save images

Use **Save Image...** to save the current view. For a VTP matched to a loaded
case, the suggested file is
`<out_dir>/images/<case_id>__<scalar_name>.png`, where `scalar_name` is the
VTP field name above, for example `normal_traction_coeff`. For an unmatched
manual VTP, the suggestion is under `images/` beside that VTP. Choose another
directory or name in the dialog as needed. Unsafe filename characters are
adjusted automatically.

**Save Selected Images...** exports images for the selected cases. It is
available when at least one selected case has a saved VTP. The suggested
directory is `images/` under their common output directory, or
`<input_dir>/outputs/images` if they use different output directories. Batch
export preserves existing images by adding a numeric suffix to duplicate names.
Manual export is also available for stale or unmatched VTPs, with the displayed
result preserved.
