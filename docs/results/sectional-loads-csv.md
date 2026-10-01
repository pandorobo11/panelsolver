# Sectional load result CSV

This dedicated long-format file contains one row per
`case × section × scope × bin`. It is separate from Summary CSV and VTP.
Use the [definition reference](../inputs/sectional-loads.md) and
[CLI workflow](../running/cli.md#sectional-load-batches) to create it.

Rows follow input case order, selected definition-file order, total scope then
ascending original component ID, and increasing zero-based bin index. Empty
bins remain in the file. Even a single selected component has both total and
component rows. All scopes use the same bins and the original case references.

`total` means the selected components within the range. It means the whole
vehicle only when both `all_components_selected` and
`covers_selected_geometry` are true. Coverage is geometric, including surfaces
with zero loads. No-overlap is a successful zero result; a failed pair has no
rows at all.

## Columns in order

UTF-8 with BOM, quoted CSV cells and round-trippable finite numeric values use
the shared serializer. Blank fields are described below. The exact order is:

<!-- sectional-result-columns -->
```text
case_id,case_signature,section_id,batch_status,requested_pairs,completed_pairs,
origin_x_stl_m,origin_y_stl_m,origin_z_stl_m,direction_x_stl,direction_y_stl,direction_z_stl,
direction_hat_x_stl,direction_hat_y_stl,direction_hat_z_stl,
requested_component_ids,selected_component_ids,all_components_selected,
range_mode,requested_start_m,requested_stop_m,resolved_start_m,resolved_stop_m,
selected_geometry_min_m,selected_geometry_max_m,covers_selected_geometry,bin_count,
Aref_m2,ref_x_stl_m,ref_y_stl_m,ref_z_stl_m,Lref_Cl_m,Lref_Cm_m,Lref_Cn_m,alpha_stability_deg,
scope,component_id,bin_index,bin_start_m,bin_stop_m,bin_center_m,bin_width_m,wetted_area_m2,
delta_force_coeff_x_stl,delta_force_coeff_y_stl,delta_force_coeff_z_stl,
delta_force_coeff_x_body,delta_force_coeff_y_body,delta_force_coeff_z_body,
delta_force_coeff_x_stability,delta_force_coeff_y_stability,delta_force_coeff_z_stability,
delta_moment_area_coeff_x_body_m,delta_moment_area_coeff_y_body_m,delta_moment_area_coeff_z_body_m,
delta_moment_coeff_x_body,delta_moment_coeff_y_body,delta_moment_coeff_z_body,
delta_CA,delta_CY,delta_CN,delta_CD,delta_CL,delta_Cl,delta_Cm,delta_Cn
```

## Identity, completion and definition

| Columns | Meaning |
|---|---|
| `case_id`, `case_signature` | Actual solved case ID and unchanged physical case signature. Definitions do not alter that signature. |
| `section_id` | Normalized definition label from the run snapshot. |
| `batch_status` | `completed`, `failed`, or `cancelled`. Computation state, independent of whether a subsequent export succeeds. |
| `requested_pairs`, `completed_pairs` | Requested and successfully retained case × definition counts for this batch, repeated on every row. A partial export is therefore identifiable without the log. |
| `origin_*_stl_m` | Requested axis origin in STL metres. |
| `direction_*_stl`, `direction_hat_*_stl` | Requested dimensionless direction and normalized direction. |
| `requested_component_ids` | Ascending semicolon-separated requested IDs; blank means all. |
| `selected_component_ids` | Resolved ascending original IDs, semicolon-separated. |
| `all_components_selected` | Boolean: all mesh components were selected. |
| `range_mode` | `auto` or `explicit`. |
| `requested_start_m`, `requested_stop_m` | Signed requested bounds, blank for auto range. |
| `resolved_start_m`, `resolved_stop_m` | Actual signed outer bounds, m. |
| `selected_geometry_min_m`, `selected_geometry_max_m` | Projected extrema of selected geometry, m. |
| `covers_selected_geometry` | Boolean: closed outer bounds cover all selected geometry. |
| `bin_count` | Requested number of equal-width bins. |

## References and bins

| Columns | Meaning |
|---|---|
| `Aref_m2` | Original global reference area, m². |
| `ref_*_stl_m` | Original moment reference point in STL metres. This is independent of the section axis origin. |
| `Lref_Cl_m`, `Lref_Cm_m`, `Lref_Cn_m` | Original roll, pitch and yaw reference lengths, m. |
| `alpha_stability_deg` | Original stability-frame angle, degrees. |
| `scope` | `total` or `component`. |
| `component_id` | Blank for total; original nonnegative mesh ID for component scope. |
| `bin_index` | Zero-based bin index. |
| `bin_start_m`, `bin_stop_m`, `bin_center_m`, `bin_width_m` | Signed bounds, center and positive width, all m. Internal boundary planes belong to the right-hand bin; the final upper edge is included. |

## Strip quantities

| Columns | Units and meaning |
|---|---|
| `wetted_area_m2` | Actual surface area in the strip, m²; includes shielded surfaces and counts distinct coincident faces separately. |
| `delta_force_coeff_*_stl` | Integrated strip force vector in STL coordinates, dimensionless. |
| `delta_force_coeff_*_body` | Same vector in body coordinates, dimensionless. |
| `delta_force_coeff_*_stability` | Same vector in stability coordinates, dimensionless. |
| `delta_moment_area_coeff_*_body_m` | Strip body moment numerator divided by global area, m. |
| `delta_moment_coeff_*_body` | Body moment vector divided by the respective reference lengths, dimensionless. |
| `delta_CA`, `delta_CY`, `delta_CN` | Body force views: minus X, Y, minus Z. |
| `delta_CD`, `delta_CL` | Stability force views: minus X, minus Z. |
| `delta_Cl`, `delta_Cm`, `delta_Cn` | Normalized body roll, pitch and yaw moments. |

`delta_` denotes an integral over this strip, not a derivative or coefficient
per metre. Full model traction includes Sentman tangential loads. Frames, signs
and references follow the existing
[load conventions](../methods/load-and-coefficient-conventions.md). Fragment-local
moment integration can differ from stored whole-face-centroid integration by its
documented representation rounding; no conservation residual is redistributed.

## Failures and repeated export

The batch stops scheduling work after observing a calculation failure or a
cooperative cancellation. Already-dispatched cases can finish before the stop
is observed. Successfully retained pairs are exported in the same input order,
with the terminal status/counts above; uncompleted pairs are absent. The CLI
returns nonzero for failed/cancelled runs even when their partial CSV is saved.

When no pair succeeds, no CSV is written and an existing destination is left
unchanged. A save failure is separate from computation status. Atomic temporary
writing preserves an existing valid file on failure. Retained in-memory batch
results can be exported again without rerunning physics. Every export checks
the destination against the case table, definition CSV and all loaded STL
inputs, including unselected cases and existing file aliases.

There are no intermediate Summary/VTP files or sectional checkpoint/retry files.
