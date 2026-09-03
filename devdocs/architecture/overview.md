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
[Coordinate and attitude conventions](../../docs/reference/coordinate-and-attitude-conventions.md)
and [Load and coefficient conventions](../../docs/reference/load-and-coefficient-conventions.md).

## Public and lower-level Python boundaries

The package root provides a small stable in-memory Python API that adapts domain
cases into the shared numerical pipeline without serializing artifacts. The
exact supported exports and their user-facing contract are defined in the
[Python API reference](../../docs/reference/python-api.md).

`panelsolver.core`, `panelsolver.models`, `panelsolver.app`, and
`panelsolver.domains` are lower-level composition modules. They expose typed
implementation contracts for geometry, flow, models, execution policy, case
tables, and product assembly, but are not re-exported wholesale from the package
root. Only the package-root API is a supported Python integration surface.

## Execution and artifacts

The one-case engine loads ordered STL components, validates geometry, resolves
shielding, evaluates a registered model, integrates totals/components, and
returns a canonical signature with immutable results. The spawn scheduler wraps
that engine and rebuilds snapshots in input order.

CSV and VTP projections receive explicit domain-owned policy. Shared code does
not branch on a concrete model name to invent a universal schema. The shared
application records the installed distribution version as artifact provenance.
The in-memory API stops at the common execution result and performs no artifact
serialization.

GUI artifact matching constructs the current `panelsolver.case` v1 signature and
requires both that signature and the current case ID for automatic display.
Manual **Open VTP...** remains a generic inspection path and does not establish a
historical artifact compatibility contract.

Flow-domain selectors and high-level case names use the FMF and Hypersonic flow
domains. Sentman and Newtonian-family names identify physical models or methods.
See [ADR 0011](../adr/0011-canonical-domain-naming.md).

## Shared convergence

Both domain selectors use the same application-owned case-table
dispatch, strict geometry and numeric validation, output collision checks,
durable CSV writing, scheduler behavior, and input-ordered result reconstruction.
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
