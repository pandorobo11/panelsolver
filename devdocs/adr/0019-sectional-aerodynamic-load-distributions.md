# ADR 0019: Model-neutral sectional aerodynamic load distributions

- Status: Accepted (user-approved A0 contract; implementation pending A1–A6)
- Date: 2026-09-17
- Parent: [Issue #304](https://github.com/pandorobo11/panelsolver/issues/304)
- Baseline: GitHub main `ad06a911c021f2f8c36623e757c2efb69b3c97ea`
- Refines: ADR 0002 load-vector integration and ADR 0006 mesh use.
- Supersedes: only ADR 0014's restriction that the package root is the sole
  supported Python surface, by authorizing the dedicated postprocessing surface
  below when A4 ships. Existing root exports remain supported and unchanged.

## Context and scope

Define finite-width sectional aerodynamic coefficient integrals along an
arbitrary STL-frame axis. This is surface-load integration over strips, not a
pressure section or a structural internal-load calculation. This ADR completes
A0 only: it does not implement numerical algorithms, API, CSV, CLI, or GUI.

The baseline architecture, user numerical specification, implementation, and
tests agree with Issue #304's traction, normalization, and moment design. The
issue was a working memo, not a replacement for the current contracts. This ADR
resolves its unspecified range, ownership, result, and input semantics.

Relevant existing decisions are [ADR 0002](0002-panel-load-vector-contract.md),
[ADR 0003](0003-dependency-direction.md),
[ADR 0006](0006-mesh-loading-and-fingerprints.md),
[ADR 0008](0008-supported-domain-compatibility.md),
[ADR 0014](0014-remove-legacy-direct-python-api.md),
[ADR 0017](0017-full-direction-attitudes.md), and
[ADR 0018](0018-uniform-face-normal-generation.md). In particular, ADR 0017's
stability angle supersedes the old tangent-angle wording in ADR 0002.

The current [load conventions](../../docs/methods/load-and-coefficient-conventions.md)
and [frame conventions](../../docs/methods/coordinate-and-attitude-conventions.md)
remain authoritative for signs and reference normalization.

## Authoritative loads and geometry

Use `LocalLoads.traction_coeff_stl`, the model-neutral, unweighted,
nondimensional `(n_faces, 3)` traction vector. Keep the full vector, including
Sentman tangential traction. Do not reconstruct it from `cp` or another scalar.
Traction is constant over each source triangle, including the existing exact
zero on shielded faces. Sectional processing does not rerun shielding or models.

Use the exact SI-scaled mesh and common case from the physical solve. Retain the
global `Aref_m2`, `moment_reference_stl_m`, all three reference lengths, and
`alpha_stability_deg`. Neither component selection nor strip area changes these
references. The section-axis origin is not a new moment reference point.

`PanelMesh.faces` indexes `vertices_stl_m`; component identity belongs to faces
through `face_component_ids`, not to vertices. A vertex can be shared by faces
in different components, and unused vertices need not contribute to the surface.
Core supports nonnegative, sparse component IDs. Normal file loading assigns
zero-based IDs in input-STL order. IDs in this feature use those same identities.

At the baseline, `PanelMesh` validates indexing and alignment but does not prove
that topology-derived areas and centroids agree with `PanelGeometry`. Sectional
geometry requires finite, nondegenerate source triangles and that agreement
within floating-point geometry tolerance. A2 must check this at its geometry
boundary; it must not repair, discard, or rescale inconsistent source faces to
force conservation. This requirement does not change the general `PanelMesh`
constructor or the existing mesh loader as part of this feature.

## Definition, selection, and resolved bins

The numerical definition contains only these user inputs:

| Field | Contract |
|---|---|
| `axis_origin_stl_m` | Finite real vector `(3,)`, STL frame, metres. |
| `axis_direction_stl` | Finite nonzero real vector `(3,)`, dimensionless; normalize internally. |
| `start_m`, `stop_m` | Both `None`, or both finite real values with `start_m < stop_m`. |
| `bin_count` | Required integer, at least 1; booleans and floating values such as `30.0` are invalid Python inputs. |
| `component_ids` | `None` for all, or a nonempty sequence of distinct nonnegative integer IDs. |

Reject numeric booleans, NaN, infinity, invalid shapes, negative IDs, duplicate
IDs, an empty ID sequence, and IDs absent from the case mesh. Do not silently
skip unknown IDs. Normalize selected IDs to ascending order, independently of
input order; include every selected component in the output. An all-components
selection resolves explicitly to the IDs present in that mesh.

For direction `d`, use `h = max(abs(d))`, then normalize `d / h` by its L2 norm.
Reject `h == 0`. Scaling before normalization allows finite extreme magnitudes
and tiny nonzero directions without overflowing or underflowing the raw norm.
For the resulting unit vector `u` and origin `o`, the signed axial coordinate is:

```math
s(\boldsymbol r)=(\boldsymbol r_{\mathrm{STL}}-\boldsymbol o)\cdot\boldsymbol u.
```

`s`, `start_m`, and `stop_m` are in metres. Negative values are valid. Reversing
the direction reverses the coordinate; do not canonicalize away its sign.

### Auto and explicit ranges

Both bounds omitted means auto range. First select faces by their component ID,
then project only the unique vertices referenced by those faces:

```text
selected_vertex_indices = unique(mesh.faces[selected_face_indices].ravel())
start_m = min(projected_selected_vertices)
stop_m = max(projected_selected_vertices)
```

Do not use face centers, every vertex unconditionally, or only faces with
nonzero loads. Shielded faces remain part of the selected geometry.

If the minimum equals the maximum, auto range is invalid: request explicit
bounds rather than inventing a physical width. For example, a plate at `z=0`
with a Z axis has positive surface area but zero projected extent. It can still
be integrated with explicit bounds spanning `s=0`.

Exactly one supplied bound is invalid. Explicit bounds need not cover the
selected geometry. Partial overlap and no overlap are valid; no overlap returns
zero strip integrals. Do not clamp explicit bounds to the geometry or pad auto
bounds. The same auto definition can resolve to different edges on different
case geometries; use explicit bounds for common physical bin locations.

### Uniform bins

For `B = bin_count`, the mathematical definition is:

```math
e_k=start+(stop-start)k/B,\qquad k=0,\ldots,B.
```

Use a numerically safe equivalent computation, retaining the exact supplied or
resolved endpoints. Represent the resolved bins as float64 edges `(B+1,)`, with
widths `e[k+1] - e[k]` and centers halfway between successive edges, each `(B,)`.
Validate finite projections, endpoints, edges, widths, and centers, and require
strictly increasing edges and positive widths. Reject unrepresentable derived
state or a count that produces collapsed float64 edges; do not reduce the count.

Edges are the internal geometry interface, not an arbitrary-edge user input.
Only uniform strips are accepted in this MVP. This representation leaves room
for a later, separately specified extension without adding it now.

## Boundary ownership and degeneracies

Use `[e[k], e[k+1])` for every strip except the last, which includes its upper
endpoint: `[e[B-1], e[B]]`. Thus:

| Contact | Ownership / contribution |
|---|---|
| Whole face on an internal boundary plane | Assign its entire positive area and load to the bin on the right (larger `s`). |
| Whole face on the first or last boundary | Assign to the first or last bin, respectively. |
| Only an edge or vertex on a boundary | The contact itself has zero area and no load; integrate the positive-area portions on their respective sides. |
| Face wholly outside the range | No contribution. |
| Clipping produces only a line or point | Zero contribution. |
| Source triangle is degenerate | Invalid input, not a silently omitted panel. |

The positive-area coplanar-face case needs explicit ownership. Independently
clipping against two closed slabs and counting that face twice is incorrect.
Intermediate polygons may share zero-area edges or vertices, but positive area
must never be counted twice.

Compute a common set of float64 projected coordinates and edges for ownership
decisions. Compare against those values consistently. Do not create an epsilon
band that snaps nearby positive-area geometry into another strip. Exact
boundary values and adjacent representable values have distinct behavior.
Intersection geometry must preserve the shared boundary consistently. Retain
small positive fragments rather than discarding them by a fixed area cutoff;
reject non-finite or unrepresentable numerical state instead of concealing loss.

An empty bin remains in the result with zero area, force, and moment. A
zero-traction fragment still contributes its geometric area. No cumulative or
coefficient-density calculation changes these primitive strip quantities.

## Fragment integration

Split triangles by strip-boundary planes; do not assign a source face according
to its center. For source face `j` and strip `k`, let `P_jk` be their surface
intersection, with area and area first moment:

```math
A_{jk}=\int_{P_{jk}}dA,\qquad
\boldsymbol Q_{jk}=\int_{P_{jk}}\boldsymbol r_{\mathrm{STL}}\,dA.
```

`A_jk` has units m² and `Q_jk` has units m³. When area is positive the equivalent
centroid is `c_jk = Q_jk / A_jk`. For constant source traction `tau_j`:

```math
\Delta\boldsymbol C_{F,jk,\mathrm{STL}}
=\frac{A_{jk}}{A_{\mathrm{ref}}}\boldsymbol\tau_j.
```

Let `T = diag(-1, 1, -1)` be the existing STL-to-body transform and `r_ref` the
case's STL moment reference. The body-frame moment-area coefficient is:

```math
\Delta\overline{\boldsymbol C}_{M,jk,\mathrm{body}}
=\frac{T(\boldsymbol Q_{jk}-A_{jk}\boldsymbol r_{\mathrm{ref}})
\times T\boldsymbol\tau_j}{A_{\mathrm{ref}}}.
```

Equivalently, for a positive-area fragment:

```math
\Delta\overline{\boldsymbol C}_{M,jk,\mathrm{body}}
=T(\boldsymbol c_{jk}-\boldsymbol r_{\mathrm{ref}})
\times T\Delta\boldsymbol C_{F,jk,\mathrm{STL}}.
```

Accumulate first moments relative to a local origin when needed to avoid
cancellation between large absolute coordinates; this is the same integral.
Do not distribute the original face moment by area fraction, because that
loses the fragment's force application point.

Sum fragment contributions by component and bin, and obtain selected-total
distributions from those same contributions. Apply existing transformations:

```math
\boldsymbol C_{F,k,\mathrm{body}}=T\boldsymbol C_{F,k,\mathrm{STL}},
\qquad
\boldsymbol C_{F,k,\mathrm{stability}}=
\begin{bmatrix}
\cos\alpha&0&\sin\alpha\\
0&1&0\\
-\sin\alpha&0&\cos\alpha
\end{bmatrix}
\boldsymbol C_{F,k,\mathrm{body}}.
```

Here `alpha` is the existing `alpha_stability_deg` converted to radians,
including the ADR 0017 lateral-flow fallback. These are stability, not general
wind, axes. Normalize moment components by the existing lengths:

```math
(C_l,C_m,C_n)_k=
\left(
\frac{\overline C_{M,k,X}}{L_{\mathrm{ref},Cl}},
\frac{\overline C_{M,k,Y}}{L_{\mathrm{ref},Cm}},
\frac{\overline C_{M,k,Z}}{L_{\mathrm{ref},Cn}}
\right).
```

The remaining public views retain the current signs:

```math
C_A=-C_{X,\mathrm{body}},\quad
C_Y=C_{Y,\mathrm{body}},\quad
C_N=-C_{Z,\mathrm{body}},\quad
C_D=-C_{X,\mathrm{stability}},\quad
C_L=-C_{Z,\mathrm{stability}}.
```

## Result semantics and coverage

One result contains a resolved definition, a `total` distribution, and one
distribution for every selected component, in ascending ID order. All scopes
share the same edges; do not recompute auto range separately for each component.
Even a single selected component retains both total and component results.

| Quantity in each distribution | Shape / units |
|---|---|
| Wetted surface area | `(B,)`, m² |
| Force coefficient in STL, body, and stability frames | Each `(B, 3)`, dimensionless |
| `moment_area_coeff_body_m` | `(B, 3)`, m |
| `moment_coeff_body` | `(B, 3)`, dimensionless |
| `CA`, `CY`, `CN`, `CD`, `CL`, `Cl`, `Cm`, `Cn` views | Each `(B,)`, dimensionless |

Wetted area means the sum of actual surface fragment areas, not projected area
or an aerodynamic exposure filter. Include shielded surfaces. Distinct
overlapping source faces remain distinct; do not form a surface union.

Retain axis origin and normalized direction, requested and resolved range,
auto/explicit mode, selected IDs, selected geometry projection minimum/maximum,
edges/centers/widths, case identity/signature, and common reference quantities.
Expose whether all mesh components were selected and whether the resolved range
covers all selected geometry. Coverage uses geometric extrema and closed outer
bounds, not nonzero-load extrema or an approximate force match.

`total` always means the sum over the selected components within the range. It
does not unconditionally mean the whole vehicle. Full coverage gives
conservation against the existing selected-component sum; only full coverage
with all components gives conservation against the whole-case total. A partial
range must retain its coverage information even if excluded loads happen to be
zero. A nonintersecting range is valid and has zero area and coefficients.

Use the existing immutable contract conventions: float64 numerical arrays,
int64 indices/IDs, frozen results, read-only buffers and mappings, shape checks
before broadcasting, and no mutable alias to caller-owned data. Coefficient
views derive from primitive vectors rather than becoming independent values.

## Definition CSV and batch semantics

The definition file is separate from the physical solver case table. Its v1
schema is:

```csv
section_id,origin_x_stl_m,origin_y_stl_m,origin_z_stl_m,direction_x_stl,direction_y_stl,direction_z_stl,start_m,stop_m,bin_count,component_ids
right_stab,2.0,0.5,0.0,0.2,0.9,0.4,,,30,2
left_stab,2.0,-0.5,0.0,0.2,-0.9,0.4,,,30,3
body_x,0.0,0.0,0.0,1.0,0.0,0.0,-5.0,0.0,100,
```

These component IDs are examples, not one-based aliases. Each must exist in
every case to which that definition is applied.

- Use UTF-8 with or without BOM, with named columns in any order.
- `start_m`, `stop_m`, and `component_ids` columns may be omitted; omission is
  equivalent to blank. All other columns and their cells are required.
- Trim and Unicode-NFC-normalize `section_id`, preserving it as text (including
  numeric-looking IDs). It must be nonempty and unique after normalization;
  identity comparison is case-sensitive. It is a batch label, not a filename.
- Both range cells blank means auto; only one blank is invalid. Whitespace-only
  optional cells are treated as blank. All coordinates are STL and all lengths
  are metres; direction is dimensionless.
- Blank component IDs means all. Multiple IDs use semicolons, e.g. `1;2;5`,
  consistent with case-table component-list conventions. Trim tokens and reject
  empty tokens, duplicates, negative IDs, and nonintegers.
- Integer cells/tokens use decimal integer notation, not float or exponent
  notation. Do not coerce `30.0` into an accepted count.
- Reject duplicate headers, unknown columns, and files without definitions.
  Validate syntax and numerical values across the file before running cases;
  mesh-dependent ID existence and range resolution occur for each case.
- Diagnostics identify the row, section ID when available, and field. CLI and
  GUI use the same reader/validator and normalized numerical definition.

No sectional columns are added to FMF or Hypersonic solver case tables. The
numerical definition does not require a section ID or know about a CSV row;
the application associates the batch identity with that definition.

Run selected cases times selected definitions. Case filtering and definition
filtering are independent. For each case execute the physical solver exactly
once and apply all selected definitions to that same in-memory execution
result before discarding it. Never rerun the solver per definition or reload
VTP to obtain postprocessing inputs.

### Batch result CSV

Use a separate long-format CSV, not the existing Summary CSV. One row represents
`case_id × section_id × scope × bin`. Required meanings are:

- Case identity and its originating physical case signature.
- Section identity, resolved selection and range/coverage provenance.
- `scope` is `total` or `component`; component ID is blank for total and the
  original nonnegative mesh ID for component rows.
- Zero-based bin index, lower/upper bound, center, and width in metres.
- Wetted area in m² and the primitive strip coefficient values above, with
  explicit frames and units for vector components.

Emit empty bins and individual component rows even for one component. Order
rows by input case order, definition-file order after filtering, total then
ascending component ID, then increasing bin index within each scope. Final
column spelling/order and serialization mechanics belong to A5. Do not add
cumulative columns. The existing Summary CSV schema and its single-component
row omission rule are unchanged.

## API, CLI, and GUI boundaries

Core owns one model-independent implementation of definition resolution,
clipping, integration, and aggregation. It does not import models, app, domains,
or GUI, and does not interpret file formats or concrete model names. Numerical
logic does not belong in command dispatchers or widgets.

### Stable Python surface and retained context

A4 will expose the dedicated stable entry point without adding root exports:

```python
from panelsolver.postprocess import compute_sectional_loads

loads = compute_sectional_loads(
    result,
    axis_origin_stl_m=(2.0, 0.5, 0.0),
    axis_direction_stl=(0.2, 0.9, 0.4),
    start_m=None,
    stop_m=None,
    bin_count=30,
    component_ids=(2,),
)
```

All arguments after the one in-memory `SolveResult` are keyword-only. Origin,
direction, and count are required; bounds and component IDs default to `None`.
The wrapper normalizes into the same numerical definition and calls core; it
does no file I/O or physical solve. Existing root solve functions remain stable.
No wholesale promotion of `core`, `app`, or their constructors is intended.

The baseline `SolveResult` retains per-face geometry and loads but omits mesh
topology and common reference quantities. Internal `CaseExecutionResult` already
has both. A4 must retain the immutable mesh and common-case context from that
same execution in solver-produced `SolveResult` objects, aligned with their
loads, geometry, attitude, and case identity. Do not reread STL files, infer
references from coefficients, or fetch mutable global state. Postprocessing
must still work if source files have since changed or disappeared.

A0 fixes the required context and its origin, not the private field layout or
the exported result-type names. A4 chooses those details and preserves existing
`SolveResult` usage and constructor compatibility. Manually constructed results
without context must fail explicitly rather than trigger file reads or another
solve. Raw `PanelMesh` and `CommonCasePayload` need not become public API types.
Document the callable and returned fields as stable when A4 ships; do not claim
they are available in the A0 release.

### CLI and shared application service

Both flow domains will support a sectional-loads workflow, conceptually:

```text
panelsolver hypersonic sectional-loads -i cases.csv -d sectional_loads.csv -o sectional_loads_result.csv
```

Retain existing case filtering and add independent section filtering. The
application owns shared parsing, selection, batch orchestration, and export;
the dispatcher only routes the command. Preserve the existing solve command.
The baseline final batch projection is not a sufficient postprocessing input:
attach the new workflow to the in-memory execution result before serialization.
No intermediate Summary CSV or VTP is required. Section definitions do not
alter the physical case signature or mesh/shielding cache identities.

### Read-only GUI

Provide only definition CSV open/reload, a read-only list, selection of one or
more definitions, existing case selection, execution of the selected Cartesian
product, and result export. Users edit definitions externally. Use the shared
reader, batch service, and writer rather than widget-specific interpretations.

Freeze the selected definitions as a run snapshot: external edits or reloads
must not change an active calculation. Retain the existing worker-thread,
cancellation, and cleanup boundaries. Detailed widget layout and service
connections belong to A6. There is no create/edit/delete/save definition flow,
3D axis editing, custom axis form, or component-selection writeback.

## Conservation and verification

For full coverage, fragment areas and first moments reproduce those of the
selected source faces. Consequently strip force and moment sums reproduce the
existing selected-component coefficients; with every component selected they
reproduce the whole-case coefficients. Component distributions sum to total in
each bin. These comparisons use the same in-memory traction and common case,
not independently reevaluated physics.

Tests must cover:

- A1: invalid numbers/shapes/types, tiny/large nonzero direction normalization,
  signed ranges, incomplete/reversed bounds, collapsed edges, count validation,
  all/single/multiple/sparse component IDs, empty/duplicate/unknown IDs, unused
  and shared vertices, shielded geometry, zero-extent auto rejection, explicit
  planar ranges, immutable buffers, and deterministic resolution.
- A2: triangles crossing many strips, arbitrary oblique and reversed axes,
  exact and adjacent-representable boundary face/edge/vertex cases, both outer
  boundaries, coplanar faces, empty/tiny fragments, translated/scaled geometry,
  invalid topology-derived geometry, area and local first-moment conservation.
- A3: Hypersonic and Sentman, normal and tangential traction, shielding,
  multiple components, oblique axes, nonzero moment reference, unequal reference
  lengths, body/stability transforms including backward and lateral flow,
  full auto/explicit conservation, partial-range analytic integrals, and
  per-bin component sums.
- A4: retained context, unchanged root surface, explicit missing-context errors,
  multiple definitions on one result, and independence from later STL changes.
- A5: encoding, schema, blank fields, semicolon lists, duplicate identities,
  independent filters, per-case auto edges, shared explicit edges, ordering,
  coverage provenance, export failures, and one solve per case regardless of
  definition count.
- A6: read-only loading, reload failures, shared numerical results, run
  snapshots, selection, cancellation/cleanup, and export failures.

New float64 conservation fixtures use scale-aware error bounds: `1e-11 * scale`
for ordinary representable fixtures. Use source area sums for area, sums of
force contribution norms for force, and sums of lever-arm norms times force
norms for moment; do not use only the possibly canceled resultant. For local
first moments use area times distance from the chosen local origin as the
scale. Apply the corresponding reference-length normalization for normalized
moments. Test empty bins and exact-zero shielded loads exactly. Tiny geometries
must not pass merely because of a large fixed absolute tolerance. Extreme
unrepresentable cases exercise explicit failures instead.

Retain all existing model-specific golden tolerances, expected coefficients,
shielding masks, CSV/VTP semantics, and signatures. Do not loosen golden
tolerances to hide a clipping error. Use the repository validation runner for
implementation PRs, including the authoritative full tests before push/PR and
both shielding backends where applicable. A0 checks document links, strict docs,
and that only the intended developer documentation changed.

## Non-goals

- Cumulative distributions or cumulative CSV columns.
- Pressure/Cp surface sections or surface scalar sections.
- GUI definition editor, custom GUI axis input, or 3D axis editing.
- Writing GUI component selections back into definitions.
- VTP-only standalone postprocessing.
- Arbitrary bin edges, explicit bin width input, or adaptive binning.
- Dimensional force/load in N or N/m.
- Structural cut forces, bending, or torsional internal loads.
- Smoothing/interpolation or pressure section contour construction.
- Unrelated refactoring.

Coefficient density `delta_C / ds` is not an MVP output contract; preserve the
primitive strip integrals instead.

## Delivery boundaries and consequences

| Task | Independently reviewable deliverable |
|---|---|
| A0 | This accepted contract, ADR index, and architecture boundary reference only. |
| A1 | Typed numerical definitions/specs, validation, component selection, auto range, and uniform bins. |
| A2 | Triangle/slab geometry, area/first moments, geometry consistency, and geometric conservation tests. |
| A3 | Model-neutral force/moment integration, distributions, and cross-model conservation tests. |
| A4 | Retained solve context, dedicated stable Python interface, and API documentation/tests. |
| A5 | Shared definition reader, batch service, CLI, and final long-format CSV schema/writer. |
| A6 | Read-only GUI definition loading/selection, shared batch execution, and export. |

### Exact next task: A1

Implement the internal `panelsolver.core.sectional` module with:

- `SectionalLoadDefinition`: numerical inputs and normalized direction, with
  mesh-independent validation under this ADR; no CSV or section identity.
- `ResolvedSectionalLoadSpec`: normalized definition, selected component IDs and
  face indices, geometry projection bounds, resolved edges/centers/widths, and
  selection/coverage metadata.
- `resolve_sectional_load_spec(mesh, definition)`: validate ID existence,
  select referenced vertices, project them, resolve the range and uniform bins,
  and return the immutable spec in deterministic order.
- Focused unit tests for all A1 contracts above, without physical solves.

A1 does not implement clipping, fragment geometry, traction integration,
distribution results, changes to `SolveResult`, public API, CSV, CLI, or GUI.
A2 must be able to consume its resolved spec and triangle topology without
making new axis, range, component, or bin policy decisions.

A4 retains private representation and result-type packaging decisions. A5
retains exact output column names/order, help text, and failure-recovery wiring;
A6 retains widget layout and lifecycle wiring. These tasks do not reopen the
numerical or input semantics accepted here. No production dependency, numerical
value, existing file schema, or current executable behavior changes in A0.
