# Viewing results in the GUI

The Viewer shows the surface result (VTP file) of one case: the geometry,
colored by a value such as `Cp` on each panel. Run your cases first as
described in [Using the GUI](gui.md#run-cases).

## Select a result

After a run, the Viewer shows the result of the first selected case. Selecting
another row shows that case's result, if its VTP exists in `outputs/` and was
made from the current case settings. Panel Solver checks this with the case ID
and the `case_signature` stored in the file. If the file is missing or was made
from different settings, the Viewer explains why nothing is shown.

![Panel Solver Viewer showing the newt_pm cube result colored by Cp](../assets/screenshots/gui-result.png)

*The `newt_pm` case with its matching VTP colored by `Cp`.*

To look at any VTP file, choose **File > Open VTP...** or the Viewer's
**Open VTP...** button, or drag the `.vtp` file onto the window. The file does
not need to match a case in the table.

If a file cannot be read or written, the Viewer shows the error and a
**Diagnostics** button.

## Choose surface data and coloring

Below the Viewer, choose the value to color by (**Scalar**) and the
**Colormap** (`jet`, `viridis`, or `bwr`). The color bar shows the value name and its range.
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

**Range:** enter a minimum and maximum to fix the color limits, for example to
compare several cases on the same scale. Leave a box empty to set that limit
automatically, or choose **Auto range** to clear both. If the text is not a
valid number, the box is marked, and its tooltip explains why the automatic
limit is used.

**Display:**

| Option | Default | What it does |
|---|---|---|
| **Show edges** | on | Draws the triangle edges. |
| **Smooth colors** | off | Blends colors across panels; see [below](#smooth-color-distributions). |
| **Shielded transparent** | on | Draws panels hidden by [ray shielding](../methods/ray-shielding.md) at 30% opacity, so you can see what is behind them. Turn it off to draw them solid. |
| **Show info text** | on | Shows the case ID and flow conditions on top of the geometry. |

**Camera:**

| Button | View |
|---|---|
| **+X**, **-X**, **+Y**, **-Y**, **+Z**, **-Z** | From that side of the model, along an STL axis. |
| **-X -Y +Z**, **+X -Y -Z** | From one of two diagonal (isometric) directions in STL coordinates. |
| **Upstream** | From upstream, looking along the flow direction of the case. |
| **Downstream** | From downstream, looking back against the flow. |
| **Fit** | Zooms to fit the model, without rotating it. |

You can also rotate, pan, and zoom with the mouse.

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
suggested file is `<input folder>/outputs/images/<case_id>__<scalar_name>.png`, where
`scalar_name` is the VTP field name from the table above, for example
`normal_traction_coeff`. For a VTP opened by hand, the suggestion is an
`images/` folder next to that file. You can change the folder and name.
Characters that are not allowed in file names are replaced.

**Save Selected Images...** saves one image for each selected case, colored by
the current scalar. Cases whose VTP is missing or does not match the current
case settings are skipped and listed in Diagnostics. The suggested folder is
`<input folder>/outputs/images`. Existing images are kept: a number is added to the
new file name instead.

If the suggested `images` folder does not exist yet, it is created when the save
dialog opens, so the dialog can start inside it. If you cancel or save
elsewhere, the folder is removed again as long as it is still empty.
