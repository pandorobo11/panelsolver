# Viewing results in the GUI

The Viewer shows the surface result (VTP file) of one case: the geometry,
colored by a value such as `Cp` on each panel. Run your cases first as
described in [Using the GUI](gui.md#run-cases).

## Select a result

After a run, the Viewer shows the result of the first selected case. Selecting
another row shows that case's result, if its VTP exists in `out_dir` and was
made from the current case settings. Panel Solver checks this with the case ID
and the `case_signature` stored in the file. If the file is missing or was made
from different settings, the Viewer explains why nothing is shown.

![Panel Solver Viewer showing the newt_pm cube result colored by Cp](../assets/screenshots/gui-result.png)

*The `newt_pm` case with its matching VTP colored by `Cp`.*

To look at any VTP file, choose **File > Open VTP...** or the Viewer's
**Open VTP...** button, or drag the `.vtp` file onto the window. The file does
not need to match a case in the table.

**Show info text** shows the case ID and flow conditions on top of the
geometry. If a file cannot be read or written, the Viewer shows the error and a
**Diagnostics** button.

## Choose surface data and coloring

Below the Viewer, choose the value to color by (**Scalar**), the **Colormap**,
and the camera direction. The color bar shows the value name and its range.
The scalar names match these [VTP fields](../reference/vtp.md):

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

**Range:** enter **Min** and **Max** to fix the color limits. Leave a box empty
to set that limit automatically. If the text is not a valid number, the box is
marked, and its tooltip explains why the automatic limit is used.

**Camera:** view the model along an STL axis, from one of two diagonal
(isometric) directions, or from **Upstream** or **Downstream** along the flow.
**Fit** zooms to fit the model without rotating it.

**Background:** **Follow theme** (the default) uses white in light mode and
black in dark mode. **White** or **Black** keep that color in this window.
Text and axes switch to a contrasting color, and saved images use the same
background.

## Smooth color distributions

By default each panel shows one constant color. Turn on **Smooth colors** in
the Display row to blend the colors across panel edges, which can make the
overall distribution easier to see. Turn off **Show edges** as well for an
uninterrupted surface.

Smooth colors only changes the picture. The calculated values and all output
files stay the same, and automatic color limits still come from the original
panel values, so the color scale does not jump when you switch.

Keep in mind:

- Blending can lower peaks and blur sudden changes. Turn it off to see the
  true panel values.
- Colors are not blended between different STL parts, between shielded and
  unshielded panels, or across sharp edges (more than about 30 degrees).
- The color bar title shows **(interpolated)** while it is on, also in saved
  images.
- **Shielded**, **STL index**, and other on/off values are never blended; the
  option is disabled for them.
- If blending fails for a result, the Viewer shows panel values instead, notes
  this on the color bar, and logs the reason in Diagnostics.
- Blending does not fix mesh orientation. Fix inconsistent normals before you
  run the calculation.

## Save images

**Save Image...** saves the current view as a PNG. For a case in the table, the
suggested file is `<out_dir>/images/<case_id>__<scalar_name>.png`, where
`scalar_name` is the VTP field name from the table above, for example
`normal_traction_coeff`. For a VTP opened by hand, the suggestion is an
`images/` folder next to that file. You can change the folder and name.
Characters that are not allowed in file names are replaced.

**Save Selected Images...** saves one image for each selected case, colored by
the current scalar. Cases whose VTP is missing or does not match the current
case settings are skipped and listed in Diagnostics. The suggested folder is `images/` in
the cases' output folder (or `<input folder>/outputs/images` if the cases use
different output folders). Existing images are kept: a number is added to the
new file name instead.
