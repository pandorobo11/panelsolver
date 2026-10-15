# Sectional Cp CSV

Each row is **one straight line segment where a cutting plane crosses one
panel**. The row stores both end points of the segment and that panel's value.
The value is constant along the segment. Values are not interpolated, averaged,
or smoothed between neighbouring panels. To plot against position, you can use
the midpoint of the two end points.

| Columns | Meaning |
|---|---|
| `case_id`, `case_signature`, `section_id` | Physical case and definition identity. |
| `batch_status` | `completed`, `failed`, or `cancelled`; distinct from each plane's status. |
| `origin_x_stl_m`, `origin_y_stl_m`, `origin_z_stl_m` | Definition origin in STL metres. |
| `direction_hat_x_stl`, `direction_hat_y_stl`, `direction_hat_z_stl` | Normalized plane normal. |
| `selected_component_ids` | Resolved selection as semicolon-separated original IDs. |
| `range_mode`, `resolved_start_m`, `resolved_stop_m`, `section_count` | Automatic/explicit positioning, actual first/last position, requested plane count. |
| `plane_index`, `position_m` | Zero-based plane index and signed distance from the origin along the normal. |
| `plane_status` | `ok`, `empty`, `warning`, or `failed`. |
| `omitted_segment_count` | Number of collapsed segments omitted from this plane; zero for `ok`/`empty`, positive for `warning`, blank for `failed` because extraction is incomplete. |
| `component_id`, `face_id` | Original component and mesh face indices. |
| `x0_stl_m`, `y0_stl_m`, `z0_stl_m` | First endpoint. |
| `x1_stl_m`, `y1_stl_m`, `z1_stl_m` | Second endpoint. |
| `scalar_name`, `scalar_value` | Hypersonic `cp` or FMF `normal_traction_coeff`, and its dimensionless value. |

## Row order

Rows are ordered by case (case-table order), then definition (file order),
then plane (increasing `plane_index`), then panel (mesh order). The two end
points of a segment are in an arbitrary order: they do not tell you the
direction around a contour or the upper or lower surface. Segments are not
joined into contours, and separate parts are not merged.

## Special cases

- A plane that only touches a vertex produces no segment there.
- A plane that runs exactly along an edge shared by two panels produces a
  segment for each panel, with each panel's own value, so the same coordinates
  can appear twice.
- A plane that lies exactly in the plane of a triangle makes that whole plane
  fail, because the cut is an area rather than a line. Other planes and
  definitions still run.
- An empty or failed plane gets one status row with the segment and value
  columns empty.
- A definition that cannot be applied to the case's geometry gets one failed
  row, with `plane_index` and the resolved fields empty.
- If the case itself cannot be solved, the error is reported in the batch
  errors and no rows are written for it.

## Very short segments

If both end points of a segment round to exactly the same coordinates, that
segment is left out and the plane gets status `warning`. All other segments
are kept with their values. `omitted_segment_count` is the number of segments
left out in that plane; it is repeated on every row of the plane, so do not add
it up across rows. If no segments remain, the plane gets one warning row with
empty segment and value columns. Warning planes count as completed. The GUI
and CLI logs list the affected panel indices (zero-based). The CSV has no
message column; the Python API keeps a `message` for each plane.

Only segments that become a single point after rounding are left out; short
segments are kept. No tolerance is applied to snap nearby surfaces together.
The intersection is calculated exactly, which can be slow for large meshes
with many planes.

## Saving

The CSV is written in one step, so an existing file is either fully replaced or
left unchanged. Finished planes are saved even when the batch status is
`failed`. If no extraction finished, the file is not written. Cancellation
takes effect between definitions (one worker) or between cases (several
workers); a plane that is being calculated finishes first. Running Sectional Cp
does not change any Summary CSV, sectional load CSV, or VTP file.
