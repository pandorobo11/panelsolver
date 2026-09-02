# Ray shielding

Ray shielding is the model-neutral geometry-occlusion method shared by FMF and
Hypersonic. Setting `shielding_on=1` enables this method for a case. The
[FMF input reference](fmf-input.md) and
[Hypersonic input reference](hypersonic-input.md) remain the canonical sources
for the accepted `shielding_on` and `ray_backend` values and their defaults.

## Geometry-occlusion method

The resolved unit freestream direction points in the direction in which the
freestream travels. Its canonical definition is in
[Coordinate and attitude conventions](coordinate-and-attitude-conventions.md#frames-direction-and-angle-units).
Ray shielding tests the opposite, upstream direction.

For each panel, the method starts one upstream ray in the neighborhood of that
panel's face center and tests it against the complete case mesh, including every
ordered STL component. The first hit determines the result: when that hit is a
face other than the source panel, the source panel is marked ray-shielded. This
is the supported face-center first-hit model; it is not a general illumination,
multiple-reflection, or flow-interaction calculation.

The shielding mask therefore depends on both the complete case geometry and the
resolved flow direction. It is separate from classifying a panel as windward or
leeward for a pressure model.

For a ray-shielded panel, the physical model must return an exact-zero complete
local traction vector. The common area/reference-area weighting consequently
produces exact-zero `C_face_stl` for that panel, so it contributes no force or
moment. See [Load and coefficient conventions](load-and-coefficient-conventions.md#local-traction-and-panel-contributions)
for the common integration contract.

## Ray shielding versus `leeward_eq=shield`

These are different operations:

- **Ray shielding (`shielding_on=1`)** is available to both FMF and Hypersonic.
  It performs the upstream geometry-occlusion test and sets a hidden panel's
  complete traction to exact zero.
- **Hypersonic `leeward_eq=shield`** is a Hypersonic-only pressure-model
  selector. It assigns zero local pressure to an active leeward panel and does
  not trace rays or determine geometry occlusion. FMF has no `leeward_eq`
  selector.

Ray shielding can zero an occluded panel regardless of which windward or
leeward pressure equation would otherwise apply to that panel. The
[Hypersonic solver page](../solvers/hypersonic.md#leeward-shield) owns the
pressure-model definition and equations.

## Backend behavior

`auto` selects an available ray-intersection implementation. `rtree` explicitly
selects the Trimesh triangle-intersection path. `embree` selects the accelerated
path and requires the optional Embree dependency. If `embree` is requested
explicitly but unavailable, the case fails with an error; it does not silently
fall back to `rtree`. When shielding is disabled, no ray backend is used for the
case.

The effective backend and mask/count are represented in results as
`ray_backend_used`, `shielded`, and `shielded_faces`. Their complete
serialization contracts remain in the
[Summary CSV reference](../results/summary-csv.md#execution-and-artifact-fields),
the VTP [common cell data](../results/vtp.md#common-cell-data) for `shielded`,
and the VTP [common field data](../results/vtp.md#common-field-data) for
`ray_backend_used`.

Ray-query batching can be tuned as described in the
[Environment-variable reference](environment-variables.md). Generic workers,
execution ordering, checkpoints, cancellation, artifact failures, and recovery
are covered separately in
[Batch execution and recovery](../user-guide/batch-execution-and-recovery.md).
