# Architecture

The software ships one distribution with a small top-level CLI and in-memory
API, a shared model-neutral engine/application layer, and two independent
physical models.

```text
panelsolver CLI / panelsolver-gui / stable in-memory API
                    |
                    v
        panelsolver.domains
          /             \
        FMF          Hypersonic
          \             /
           panelsolver.app
             /       \
panelsolver.models   panelsolver.core
          |
    panelsolver.core
```

## Layer ownership

| Layer | Owns |
|---|---|
| `panelsolver` root/API | small stable domain-specific in-memory solve surface and top-level flow-domain command selection |
| `panelsolver.domains` | current FMF/Hypersonic case schemas, adaptation, runtime/projection policies, output validation, and CLI/GUI composition |
| `panelsolver.core` | immutable contracts, geometry, frames, shielding, integration, aggregation, signatures, mesh/shielding caches, scheduler |
| `panelsolver.models` | Sentman and hypersonic case validation, equations, model scalars, model signature payloads |
| `panelsolver.app` | case-table mechanics, product assembly, environment resolution, CLI/GUI orchestration, artifact and CSV serialization |

Allowed dependency directions are public user surfaces to `panelsolver.domains`,
domains to `app/models/core`, `app -> models -> core`, and `app -> core`. Core
cannot import models, app, GUI, or domains; models cannot import app, GUI, or
domains. Physical equations do not belong in domains or GUI code. Product
selection and Panel Solver environment-variable names are resolved in the domain/application
boundary. Core receives product-neutral configuration values and does not inspect
process environment variables.

## Numerical boundary

Every model receives validated `PanelGeometry` and `PanelFlowState` and returns a
`LocalLoads` vector of shape `(n_faces, 3)`. This is deliberately not a universal
pressure coefficient: Sentman has a tangential contribution, while the
hypersonic model returns pressure-only normal traction. Core applies panel area
and reference normalization and integrates forces and moments.

The exact contract and immutability rules are in
[ADR 0002](../adr/0002-panel-load-vector-contract.md). Frames, attitude, signs,
and normalization are in
[Coordinate and attitude conventions](../../docs/methods/coordinate-and-attitude-conventions.md)
and [Load and coefficient conventions](../../docs/methods/load-and-coefficient-conventions.md).

## Public and lower-level Python boundaries

The package root provides a small stable in-memory Python API that adapts domain
cases into the shared numerical pipeline without serializing artifacts. The
exact supported exports and their user-facing contract are defined in the
[Python API reference](../../docs/running/python-api.md).

`panelsolver.core`, `panelsolver.models`, `panelsolver.app`, and
`panelsolver.domains` are lower-level composition modules. They expose typed
implementation contracts for geometry, flow, models, execution policy, case
tables, and product assembly, but are not re-exported wholesale from the package
root. The package-root solve API and dedicated sectional postprocessing API are
the supported Python integration surfaces.

[ADR 0019](../adr/0019-sectional-aerodynamic-load-distributions.md) accepts a
dedicated `panelsolver.postprocess` stable surface for sectional aerodynamic
loads, implemented by A4 without adding root exports. Its numerical
definition, geometry, and integration belong to core; the public wrapper adapts
retained solve context into that core boundary. The CLI and GUI use the same
application-owned definition reader, batch service, and export path. The
`SolveResult` retains the immutable mesh and common case privately from the same
execution, without rereading STL or rerunning physics. The retained field is not
a constructor argument, so manually constructed or `dataclasses.replace` results
cannot attach stale context to substituted loads, geometry, attitude, or identity.
Deep copying a solver-produced result retains its immutable buffers/context.
The public `SectionalLoads` result reuses the A3 spec, case, total, and component
distributions, adding only the originating case signature. Documented returned
fields are public; raw numerical constructors remain internal.

The internal A1 boundary is `panelsolver.core.sectional`:
`SectionalLoadDefinition` validates and freezes numerical inputs and normalizes
the STL axis; `resolve_sectional_load_spec(mesh, definition)` returns an immutable
`ResolvedSectionalLoadSpec`. Requested bounds remain in `spec.definition`;
resolved bounds, selected geometry extrema, and closed-bound coverage are
separate. A2 consumes the same `PanelMesh` topology with
`spec.selected_face_indices`, `spec.axis_origin_stl_m`,
`spec.axis_direction_hat_stl`, and `spec.bin_edges_m`. Selected component IDs are
ascending, face indices retain mesh order, and bins are uniform. This boundary
does not implement clipping, load integration, or any public/file/UI surface.

The internal A2 boundary is
`panelsolver.core._sectional_geometry.compute_sectional_fragment_geometry(mesh, spec)`.
It validates selected topology against stored geometry and returns immutable
`SectionalFragmentGeometry` rows in source-face/bin order. Each row retains its
source index, bin index, surface area, source-local first moment, and STL origin.
[Sectional geometry](sectional-geometry.md) explains exact boundary ownership,
analytic strip clipping, rounding bounds, and the geometry-only A3 handoff.
No aerodynamic integration or public sectional feature is implemented by A2.

The internal A3 boundary is
`panelsolver.core._sectional_integration.integrate_sectional_loads(mesh, spec, local_loads, case)`.
It integrates full model-neutral traction over A2 fragments and returns immutable
strip wetted area, force/moment vectors, and coefficient views for the selected
total and every selected component. [Sectional integration](sectional-integration.md)
describes the A4 handoff, stable reductions, and separate local-conservation and
stored-representation checks. No public API or artifact surface is added by A3.

The A5 application boundary is `app.sectional_definitions` plus
`app.sectional_batch`. The reader owns CSV syntax and normalized batch labels;
A1 owns numerical validation. `run_sectional_cases` reuses product case
adaptation and the existing case scheduler, evaluates physics once per case,
and projects every selected definition before releasing the full execution.
Only compact CSV rows, counts and failure identities cross the worker boundary.
The final projection follows input case/definition order, and records terminal
batch status and completion counts. Cancellation and observed failures request
a cooperative stop and drain already-dispatched work at case boundaries.
Export reuses protected-path validation and atomic CSV writing. There is no
Summary/VTP round trip, new cache, checkpoint system or physical signature.
`app.sectional_cli` owns selection and presentation; the top-level dispatcher
only routes the new subcommand.

The A6 `app.sectional_dialog` is a persistent modeless, read-only selection and
results surface. Domain adapters bind the same batch service to the current
runtime policy. A concrete Qt worker executes frozen case/definition snapshots;
only compact results survive completion. Normal and sectional runs exclude each
other until thread cleanup. The case scope reuses ordinary selection semantics:
selected cases or all loaded cases when none are selected; definitions still
require explicit selection. Run chooses and validates the output destination
before solving. Calculation cleanup hands off successful pairs to the existing
export worker without releasing the run guard or notifying completion between
phases. Cooperative cancellation retains and saves successful pairs with their
actual terminal status. The export worker uses the retained
result and protected input paths, so a save failure can be retried without a
solve. The viewer's VTP and ordinary solve results are never sectional inputs.

## Execution and artifacts

The one-case engine loads ordered STL components, validates geometry, resolves
shielding, evaluates a registered model, integrates totals/components, and
returns a canonical signature with immutable results. The spawn scheduler wraps
that engine. The application retains input-indexed results for the final CSV and
optional in-memory snapshots. Normal CSV checkpoint output uses a separate
completed-case callback and a pending delta buffer, avoiding cumulative snapshot
construction. It initializes one CSV atomically, appends unsaved cases in
completion order, and atomically replaces it with the input-ordered final CSV.
See [ADR 0016](../adr/0016-append-csv-checkpoints.md) for write failure handling.

CSV and VTP projections receive explicit domain-owned policy. Shared code does
not branch on a concrete model name to invent a universal schema. The shared
application records the installed distribution version as artifact provenance.
The in-memory API stops at the common execution result and performs no artifact
serialization.

GUI artifact matching constructs the current `panelsolver.case` v2 signature and
requires both that signature and the current case ID for automatic display.
Manual **Open VTP...** remains a generic inspection path and does not establish a
historical artifact compatibility contract.

Flow-domain selectors and high-level case names use the FMF and Hypersonic flow
domains. Sentman and Newtonian-family names identify physical models or methods.
See [ADR 0011](../adr/0011-canonical-domain-naming.md).

## Shared convergence

Both domain selectors use the same application-owned case-table
dispatch, strict geometry and numeric validation, output collision checks,
CSV checkpoint and final writing, scheduler behavior, and input-ordered final
result reconstruction.
Domain schemas, physical equations, and domain-only artifact fields remain owned
by their domain boundary. Core does not select behavior from a concrete product
name.

## Stable decisions

Architecture changes must respect the accepted [ADRs](../adr/README.md),
especially dependency direction, the load-vector boundary, signatures, mesh
identity, distribution versioning, and supported-domain compatibility.
Historical Phase 1–8 design/evidence is retained under
[History](../history/README.md), but its migration sequencing is no longer the
current development model.
