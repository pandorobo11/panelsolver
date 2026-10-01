# Internal sectional load integration (A3)

[ADR 0019](../adr/0019-sectional-aerodynamic-load-distributions.md) defines the
numerical contract. A3 ends at the internal numerical result: it adds no stable
Python API, root exports, retained `SolveResult` context, CSV, CLI, or GUI.

## Call and result boundary

`core._sectional_integration.integrate_sectional_loads(mesh, spec, local_loads, case)`
accepts `PanelMesh`, A1's `ResolvedSectionalLoadSpec`, `LocalLoads`, and
`CommonCasePayload`. A4 retains these inputs from the same solve and calls
this boundary after A1 resolution through `postprocess.compute_sectional_loads`.
Its public `SectionalLoads` subtype adds the original physical case signature,
reusing these nested immutable objects without duplicate coefficient state.
The public returned fields are specified in the
[Python API reference](../../docs/running/python-api.md#sectional-aerodynamic-load-distributions);
core constructors remain internal. The integrator calls
`compute_sectional_fragment_geometry(mesh, spec)` once, consuming A2's exact
[`SectionalFragmentGeometry` interface](sectional-geometry.md#geometry-handoff):
`source_face_indices`, `bin_indices`, `areas_m2`, `origins_stl_m`, and
`area_first_moments_local_stl_m3`. It does not repeat clipping or shielding.

The result contracts are internal, frozen, slotted dataclasses:

- `SectionalLoadResult(spec, case, total, components)` retains resolved bins and
  the existing numerical references; it introduces no signature or artifact ID.
- `SectionalComponentDistribution(component_id, distribution)` identifies each
  selected component in `spec.selected_component_ids` order.
- `SectionalLoadDistribution` contains `wetted_area_m2` `(B,)`, and
  `force_coeff_stl`, `force_coeff_body`, `force_coeff_stability`,
  `moment_area_coeff_body_m`, `moment_coeff_body`, each `(B, 3)`.

All arrays are independently owned float64 immutable buffers, including after
pickling. The eight `(B,)` read-only coefficient views are derived from the
vectors: `CA=-Fx_body`, `CY=Fy_body`, `CN=-Fz_body`, `CD=-Fx_stability`,
`CL=-Fz_stability`, and `Cl/Cm/Cn` are the normalized body moment components.
These internal names are not public naming guarantees; A4 owns that decision.

Input types and face counts are checked before geometry. Selected face/component
alignment and A2 face/bin bounds are checked before lookup and reduction. A2
continues to validate topology against stored source geometry. As with A1/A2,
the caller retains the matching mesh/spec pair; matching index ranges alone do
not establish topology identity. There is no new fingerprint or cache system.

## Numerical evaluation and aggregation

For each A2 fragment from face `j`, force is
`traction_coeff_stl[j] * (area / case.Aref_m2)`. Model scalars are never read.
The reference-relative first moment is evaluated directly as
`q_ref = q_local + area * (origin - case.moment_reference_stl_m)`.
The body moment numerator is
`cross(stl_to_body(q_ref), stl_to_body(traction)) / case.Aref_m2`.
It has units of metres. This never forms a large absolute first moment, divides
by a tiny fragment area, or scales the original face moment by area fraction.

Original face IDs map fragments to components, including sparse IDs. A
dictionary groups fragment row indices by component/bin, retaining source order;
`math.fsum` reduces area and each force/moment component. The selected total is
another `fsum` reduction of those component/bin primitives. No independent
geometry/load pass or residual redistribution occurs. Empty bins stay zero,
and a one-component selection retains both total and component distributions.
Wetted area includes shielded and coincident surfaces as separate source faces.

The existing `stl_to_body` and `body_to_stability` helpers transform each bin,
using `case.alpha_stability_deg` without resolving attitude again. Moment
normalization uses `Lref_Cl_m`, `Lref_Cm_m`, `Lref_Cn_m` independently. Nonfinite
derived values raise a shared contract error. Beyond A2, work and storage are
O(selected faces + positive-area fragments + components × bins), including the
required output size. No face × bin traversal or parallelism is added.

## Verification and numerical limits

`tests/sectional_load_oracle.py` independently computes source areas, local lever
arms, forces, and moments with 80-digit Decimal arithmetic from stored SI
vertices, traction, and references. Local tolerance is `1e-11` times area,
the sum of force contribution norms, or a local first-moment scale bound. The
latter uses `A*norm(traction)/Aref` times
`(norm(v1-v0)+norm(v2-v0))/3 + norm(v0-reference)`, so cancellation or translation
cannot enlarge the test using absolute coordinate magnitudes.

Separately, stored-area error and stored-centroid/reference-subtraction error
are measured against that higher-precision source oracle, without inspecting
A3 output. They propagate through ADR 0019's `B_F` and `B_M`, including the
area-error term in `B_M`. A conservative `1e-70` relative allowance covers the
oracle's own rounding for these fixtures; budgets round outward to float64.
Stored-integrator comparisons add those budgets to local tolerance. Moment
coefficient bounds are divided by their individual reference lengths. No budget
enters production integration or relaxes A2 source consistency validation.

Tests cover fixed analytic strips and partial ranges; the required translated
triangle and its origin counterpart; oblique axes; unequal references;
forward/backward/lateral stability angles; deterministic many-fragment and
cancellation reductions; sparse selection and empty bins; immutable contracts;
Hypersonic normal and Sentman tangential loads; and both ray backends on real
repository meshes. Full-coverage checks compare every selected component and
the selected total to existing integration/aggregation; all-component selections
also compare directly with the whole-case result.

Float64 fragment evaluation retains finite-precision cancellation and extreme
range limitations. Stable reduction does not recover precision already lost in
individual contributions. Legacy absolute centroids remain translation-sensitive;
A3 intentionally does not reproduce or correct that stored representation error.
