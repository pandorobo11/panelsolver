# Sectional Cp CSV

Each ordinary row represents **one line segment inside one source panel**.
The CSV saves both endpoints, not the segment midpoint. The scalar is constant
on that segment. Neighbouring panels keep their own values, with no interpolation,
averaging, smoothing, or area normalization. A midpoint for plotting can be
computed as the average of the endpoints.

| Columns | Meaning |
|---|---|
| `case_id`, `case_signature`, `section_id` | Physical case and definition identity. |
| `batch_status` | `completed`, `failed`, or `cancelled`; distinct from each plane's status. |
| `origin_x_stl_m`, `origin_y_stl_m`, `origin_z_stl_m` | Definition origin in STL metres. |
| `direction_hat_x_stl`, `direction_hat_y_stl`, `direction_hat_z_stl` | Normalized plane normal. |
| `selected_component_ids` | Resolved selection as semicolon-separated original IDs. |
| `range_mode`, `resolved_start_m`, `resolved_stop_m`, `section_count` | Automatic/explicit positioning, actual first/last position, requested plane count. |
| `plane_index`, `position_m` | Zero-based plane index and signed distance from the origin along the normal. |
| `plane_status`, `message` | `ok`, `empty`, or `failed`, with failure detail. |
| `component_id`, `face_id` | Original component and mesh face indices. |
| `x0_stl_m`, `y0_stl_m`, `z0_stl_m` | First endpoint. |
| `x1_stl_m`, `y1_stl_m`, `z1_stl_m` | Second endpoint. |
| `scalar_name`, `scalar_value` | Hypersonic `cp` or FMF `normal_traction_coeff`, and its dimensionless value. |

Rows follow input case order, definition order, increasing plane index, then
source face order. Endpoint order follows source triangle connectivity; it does
not imply contour direction or upper/lower surface identity. Separate contours
and overlapping components are not joined.

Point-only contact produces no segment. When the plane contains a shared edge,
both incident panels retain their segments and values: coordinates can repeat.
A fully coplanar triangle makes that entire plane fail because its intersection
is an area, not a unique line. Other planes and definitions continue. Empty or
failed planes produce a status row with blank segment/value fields. A definition
that cannot resolve against the mesh produces a failed row with blank plane index
and unavailable resolved fields. A physical solve failure is reported in batch
errors; it cannot produce a signed result row.

The intersection predicates use exact rational arithmetic on stored float64
vertices, origins and normalized directions. Endpoint coordinates are rounded
to float64. No epsilon snaps nearby surfaces together. Source topology is checked
against the same geometry validation used by sectional loads. Unrepresentable
nonzero segments fail explicitly. Rational arithmetic costs more than a floating
point-only slice; large meshes with many planes may be slower.

CSV output is atomic. Successful and failed plane records from completed
extractions are saved even when batch status is failed. If no extraction returns
records, the destination is unchanged. Cancellation occurs between definitions
(serial), or between cases (parallel); an active extraction finishes first.
Existing Summary CSV, sectional load CSV and VTP outputs are unchanged.
