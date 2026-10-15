# Sectional load CSV

This file has one row for each combination of case, definition, scope, and
strip (bin). It is separate from the Summary CSV and VTP files. See
[Sectional loads and Cp](../guides/sectional.md#sectional-loads-from-the-cli) to
create it, and the [definition reference](sectional-definitions.md#sectional-load-definitions)
for its input.

Rows are ordered by case (case-table order), then definition (file order),
then scope (`total` first, then each part by component ID), then strip
(increasing `bin_index`). Empty strips are included as zeros. Even with one
selected part, there is a `total` row and a `component` row. All scopes use the
same strips and the case's own reference quantities.

`total` means the selected parts within the range. It is the whole vehicle
only when both `all_components_selected` and `covers_selected_geometry` are
true. Coverage is about geometry, so surfaces with zero load still count. A
range that misses the geometry is a valid result with zeros.

If a run fails or is cancelled, the file contains only the case–section pairs
that finished, and their `batch_status` is `failed` or `cancelled`. Pairs that
did not finish have no rows; they are never written as zeros. See
[Sectional loads and Cp](../guides/sectional.md#sectional-loads-in-the-gui) for
cancelling, errors, and saving again.

## Columns in order

The file is UTF-8 with a byte-order mark, like the Summary CSV. Empty cells are
described below. The columns are, in this order:

<!-- sectional-result-columns -->
```text
case_id,case_signature,section_id,batch_status,
origin_x_stl_m,origin_y_stl_m,origin_z_stl_m,
direction_hat_x_stl,direction_hat_y_stl,direction_hat_z_stl,
selected_component_ids,all_components_selected,
range_mode,resolved_start_m,resolved_stop_m,
selected_geometry_min_m,selected_geometry_max_m,covers_selected_geometry,bin_count,
ref_x_stl_m,ref_y_stl_m,ref_z_stl_m,Aref_m2,Lref_Cl_m,Lref_Cm_m,Lref_Cn_m,alpha_stability_deg,
scope,component_id,bin_index,bin_start_m,bin_stop_m,bin_center_m,bin_width_m,wetted_area_m2,
delta_CA,delta_CY,delta_CN,delta_Cl,delta_Cm,delta_Cn,delta_CD,delta_CL
```

## Identity, completion and definition

| Columns | Meaning |
|---|---|
| `case_id`, `case_signature` | Actual solved case ID and unchanged physical case signature. Definitions do not alter that signature. |
| `section_id` | Normalized definition label from the run snapshot. |
| `batch_status` | `completed`, `failed`, or `cancelled`: how the calculation ended. A failed save does not change it. |
| `origin_*_stl_m` | Requested axis origin in STL metres. |
| `direction_hat_*_stl` | Normalized dimensionless axis direction in STL coordinates. |
| `selected_component_ids` | Resolved ascending original IDs, semicolon-separated. |
| `all_components_selected` | Boolean: all mesh components were selected. |
| `range_mode` | `auto` or `explicit`. |
| `resolved_start_m`, `resolved_stop_m` | Actual signed outer bounds, m. |
| `selected_geometry_min_m`, `selected_geometry_max_m` | Projected extrema of selected geometry, m. |
| `covers_selected_geometry` | Boolean: closed outer bounds cover all selected geometry. |
| `bin_count` | Requested number of equal-width bins. |

## References and bins

| Columns | Meaning |
|---|---|
| `ref_*_stl_m` | Original moment reference point in STL metres. This is independent of the section axis origin. |
| `Aref_m2` | Original global reference area, m². |
| `Lref_Cl_m`, `Lref_Cm_m`, `Lref_Cn_m` | Original roll, pitch and yaw reference lengths, m. |
| `alpha_stability_deg` | Original stability-frame angle, degrees. |
| `scope` | `total` or `component`. |
| `component_id` | Blank for total; original nonnegative mesh ID for component scope. |
| `bin_index` | Zero-based bin index. |
| `bin_start_m`, `bin_stop_m`, `bin_center_m`, `bin_width_m` | Signed bounds, center and positive width, all m. Internal boundary planes belong to the right-hand bin; the final upper edge is included. |

## Strip quantities

The coefficient columns follow the ordinary Summary CSV order:
`CA, CY, CN, Cl, Cm, Cn, CD, CL`, each prefixed with `delta_`.
The CSV contains only the eight aerodynamic coefficient views below; coordinate
vector components and moment-area coefficients remain available through the
Python API but are not CSV columns.

| Columns | Units and meaning |
|---|---|
| `wetted_area_m2` | Actual surface area in the strip, m²; includes shielded surfaces and counts distinct coincident faces separately. |
| `delta_CA`, `delta_CY`, `delta_CN` | Body force views: minus X, Y, minus Z. |
| `delta_Cl`, `delta_Cm`, `delta_Cn` | Normalized body roll, pitch and yaw moments. |
| `delta_CD`, `delta_CL` | Stability force views: minus X, minus Z. |

`delta_` means the total over this strip. It is not a derivative and not a
value per metre. In FMF the strip loads include the Sentman shear (tangential)
load. Axes, signs, and references follow the
[load and coefficient conventions](../methods/load-and-coefficient-conventions.md).
When all parts are selected and the range covers the geometry, the strips add
up to the case total, apart from small rounding differences.
