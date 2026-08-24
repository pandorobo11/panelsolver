# ADR 0002: Put a local load vector at the model boundary

- Status: Accepted (exact Phase 2 API adopted)
- Date: 2026-08-12

## Context

Hypersonic models can often express panel traction as pressure coefficient times
the outward normal. The Sentman model also contains a freestream/tangential load
component. A common interface returning only `Cp` cannot represent both without
discarding physics or smuggling model-specific reconstruction into core.

Phase 1 confirmed that both legacy pipelines integrate a per-face vector, that a
shielded panel has an exact-zero vector, and that common results must retain
STL, body, and stability-frame data plus all eight public coefficients. It also
confirmed that the two products' case fields and result metadata cannot be
collapsed into one physical-model schema.

## Decision

The exact central API is exported from `panelsolver.core`:

```python
PanelGeometry(
    centers_stl_m,       # float64 (n_faces, 3)
    normals_out_stl,     # float64 (n_faces, 3), unit vectors
    areas_m2,            # float64 (n_faces,), strictly positive
    component_ids,       # int64 (n_faces,), non-negative
)

PanelFlowState(
    velocity_hat_stl,    # float64 (3,), unit vector
    shielded,            # bool (n_faces,)
)

LocalLoads(
    traction_coeff_stl,  # float64 (n_faces, 3)
    cell_scalars={},     # name -> real/bool (n_faces,)
    metadata={},         # immutable JSON-shaped model metadata
)
```

`traction_coeff_stl` is a local nondimensional traction coefficient. The Phase 3
integrator will apply the already-approved semantic relation

```text
C_face_stl = traction_coeff_stl * (area_m2 / Aref_m2)
```

and will own force/moment integration. Model-specific visualization scalars are
derived from this vector: Hypersonic exposes `cp`, while Sentman exposes
`normal_traction_coeff` and `tangential_traction_coeff`. None of these scalars is
the universal computational value.

Models implement this structural protocol:

```python
class PanelLoadModel(Protocol):
    model_id: str
    algorithm_version: str

    def validate_case(self, case: ModelCasePayload) -> None: ...

    def evaluate(
        self,
        geometry: PanelGeometry,
        flow_state: PanelFlowState,
        case: ModelCasePayload,
    ) -> LocalLoads: ...
```

`CommonCasePayload` contains the resolved, model-independent numerical inputs:
case identity, `Aref_m2`, moment reference point in STL coordinates, the three
axis-specific reference lengths, and resolved tangent angles in degrees.
`ModelCasePayload(model_id, payload)` is an opaque mapping; a model owns its keys
and validation. This keeps Sentman Mode A/B and thermal fields separate from the
hypersonic Mach/gamma/equation selectors. Payload canonical serialization remains
deferred to Phase 5 under ADR 0005.

`IntegratedCoefficients` retains force coefficients in STL, body, and stability
frames, the body-frame area-normalized moment vector before reference-length
division, and the normalized body moment vector. It exposes `CA`, `CY`, `CN`,
`Cl`, `Cm`, `Cn`, `CD`, and `CL` using the Phase 1 verified sign convention.
`ComponentResult` retains a non-negative component identity and counts.
`CommonResults` binds the common/model cases, geometry, flow, local loads, total,
all component results, and common metadata while validating panel and component
alignment.

`panelsolver.models.ModelRegistry` is an explicit, intentionally mutable
assembly-time registry; the value contracts themselves remain immutable.
Registration order is deterministic, registered model identities must remain
stable, and duplicate or unknown IDs are errors. Dispatch calls the same protocol
for every model, verifies the returned type and panel count, and rejects nonzero
traction on a shielded panel. Neither core nor the registry contains a branch on
a concrete model name.

## Validation and ownership

- Contract dataclasses are frozen and slotted; array-bearing dataclasses use
  identity equality rather than NumPy's ambiguous elementwise equality.
- Every input array is defensively copied into a C-contiguous buffer that shares
  no memory with caller data. Exposed arrays are read-only and backed by
  immutable storage, including after pickling; callers must explicitly create a
  mutable copy for working data.
- Central floating arrays use `float64`, component IDs use `int64`, and shielding
  masks require actual boolean dtype. Visualization scalars retain their real or
  boolean dtype.
- Shapes are checked before any operation that could broadcast. All numerical
  arrays and scalar floats reject NaN and infinity. Geometry areas and common
  reference area/lengths are strictly positive.
- Geometry normals and the freestream vector must be unit length within the
  Phase 1 geometry absolute tolerance of `1e-12`.
- Metadata/payload keys are non-empty strings. Values may contain only JSON
  scalars, mappings, lists, or tuples; lists become tuples, mappings become
  immutable insertion-ordered mappings, reference cycles are rejected, and all
  floating values must be finite. Per-panel arrays belong in explicit array
  fields, not metadata.
- The shared case contract requires a non-empty ID but deliberately does not
  choose either legacy product's character-set, duplicate-ID, or angle-boundary
  behavior.

The stable core exception hierarchy is `PanelSolverError -> ContractError ->`
`ShapeError | NonFiniteError | ContractValueError`. Registry failures use
`ModelRegistryError` with `DuplicateModelError`, `UnknownModelError`,
`ModelCaseMismatchError`, and `ModelOutputError`. Model-specific physical-domain
errors remain owned by each model and are not silently wrapped or normalized.

## Consequences

Sentman can return a vector with a tangential component, while Newton-family
models can return a normal-only vector through the identical API. Core can later
integrate both without knowing the selected model. Models cannot mutate geometry
or flow data retained by common execution, and caller mutation cannot corrupt a
contract or cache input.

This ADR does not implement or select a physical formula, mesh repair policy,
attitude boundary, exporter schema, integration routine, signature encoding,
scheduler, GUI, or compatibility frontend. Those remain in their planned phases,
and the unresolved Phase 1 dual behaviors remain unchanged.
