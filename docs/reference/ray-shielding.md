# Ray shielding

FMF and Hypersonic use the same ray-shielding method to detect geometry
occlusion. Setting `shielding_on=1` enables this method for a case. The
[FMF input reference](fmf-input.md) and
[Hypersonic input reference](hypersonic-input.md) list the accepted
`shielding_on` and `ray_backend` values and defaults.

## Geometry-occlusion method

The resolved unit freestream direction points in the direction in which the
freestream travels. This direction is defined in
[Coordinate and attitude conventions](coordinate-and-attitude-conventions.md#frames-direction-and-angle-units).
Ray shielding tests the opposite, upstream direction.

For each panel, the method starts one upstream ray in the neighborhood of that
panel's face center and tests it against the entire case mesh, including every
ordered STL component. The first hit determines the result: when that hit is a
face other than the source panel, the source panel is marked ray-shielded.
The mask depends on the entire case geometry and the resolved flow direction.

A ray-shielded panel has an exact-zero local traction vector and therefore
contributes zero force and moment. This face-center first-hit approximation
excludes multiple reflections and flow interactions between surfaces.

## Ray shielding versus `leeward_eq=shield`

| Setting | Applies to | Effect |
|---|---|---|
| `shielding_on=1` | FMF and Hypersonic | Tests upstream geometric occlusion and zeros the entire traction vector on hidden panels, regardless of their orientation or selected pressure equation. |
| `leeward_eq=shield` | Hypersonic | Assigns `Cp = 0` to active leeward panels based on their orientation. |

The Hypersonic [leeward pressure equation](../solvers/hypersonic.md#leeward-shield)
can be used with ray shielding either on or off.

## Backend behavior

`auto` selects an available ray-intersection implementation. `rtree` explicitly
selects the Trimesh triangle-intersection path. `embree` selects the accelerated
path and requires the optional Embree dependency. If `embree` is requested
explicitly but unavailable, the case fails with an error. When shielding is
disabled, the effective backend is `not_used`.

Results record the effective backend as `ray_backend_used` in
[Summary CSV](../results/summary-csv.md#execution-and-output-fields) and
[VTP field data](../results/vtp.md#common-field-data). The per-panel mask is VTP
[`shielded`](../results/vtp.md#common-cell-data), and Summary CSV reports its
count as `shielded_faces`.

Ray-query batching can be tuned as described in the
[Environment-variable reference](environment-variables.md).
