# Architecture

The completed software ships one distribution with a small canonical CLI and
in-memory API, a shared model-neutral engine/application layer, two independent
physical models, and thin compatibility frontends.

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

fmfsolver / newtsolver command frontends
          |                         |
          +----> panelsolver domains/app/models/core
          +----> panelsolver._compat (artifact signatures only)
```

## Layer ownership

| Layer | Owns |
|---|---|
| `panelsolver` root/API | small stable domain-specific in-memory solve surface and canonical flow-domain command selection |
| `panelsolver.domains` | current FMF/Hypersonic case schemas, adaptation, runtime/projection policies, output validation, and CLI/GUI composition |
| `panelsolver.core` | immutable contracts, geometry, frames, shielding, integration, aggregation, signatures, mesh/shielding caches, scheduler |
| `panelsolver.models` | Sentman and hypersonic case validation, equations, model scalars, model signature payloads |
| `panelsolver.app` | case-table mechanics, product assembly, environment resolution, CLI/GUI orchestration, artifact and CSV serialization |
| `panelsolver._compat` | private D017/D018 legacy artifact-signature reconstruction and historical signature inputs |
| `fmfsolver`, `newtsolver` | legacy command entry points, visible GUI identities, and private legacy signature selection |

Allowed dependency directions are canonical user surfaces to `panelsolver.domains`,
domains to `app/models/core`, `app -> models -> core`, `app -> core`, and
compatibility frontends inward to those layers. Production `panelsolver` code
never imports `fmfsolver` or `newtsolver`. Core cannot import models, app, GUI,
domains, or a compatibility frontend; models cannot import app, GUI, domains, or
a frontend. Physical equations do not belong in domains, GUI, or compatibility
code. Product selection and compatibility environment names are resolved in the
domain/application boundary. Core receives product-neutral configuration values
and does not inspect process environment variables.

`panelsolver._compat` depends inward on app and core. Core, models, app, and the
shared GUI never import `_compat`; canonical runtime therefore does not require
compatibility implementation. The two private GUI frontends import it only for
legacy artifact recognition. Legacy direct-Python APIs are not part of the
architecture.

## Numerical boundary

Every model receives validated `PanelGeometry` and `PanelFlowState` and returns a
`LocalLoads` vector of shape `(n_faces, 3)`. This is deliberately not a universal
pressure coefficient: Sentman has a tangential contribution, while the
hypersonic model returns pressure-only normal traction. Core applies panel area
and reference normalization and integrates forces and moments.

The exact contract and immutability rules are in
[ADR 0002](../adr/0002-panel-load-vector-contract.md). Units, frames, and signs
are in [Numerical conventions](../../docs/reference/numerical-conventions.md).

## Public and lower-level Python boundaries

The package-root objects `FMFCase`, `HypersonicCase`, `ResolvedAttitude`,
`SolveResult`, `resolve_attitude`, `solve_fmf`, and `solve_hypersonic` form the
stable in-memory Python API. They adapt domain cases into the shared numerical
pipeline without serializing artifacts.

`panelsolver.core`, `panelsolver.models`, `panelsolver.app`, and
`panelsolver.domains` are lower-level composition modules. They expose typed
implementation contracts for geometry, flow, models, execution policy, case
tables, and product assembly, but are not re-exported wholesale from the package
root. Direct Python modules under the legacy package names are not public API.

## Execution and artifacts

The one-case engine loads ordered STL components, validates geometry, resolves
shielding, evaluates a registered model, integrates totals/components, and
returns a canonical signature with immutable results. The spawn scheduler wraps
that engine and rebuilds snapshots in input order.

CSV and VTP projections receive explicit domain-owned policy. Shared code does
not branch on a concrete model name to invent a universal schema. Compatibility
frontends supply only model-specific input/output additions; the shared
application records the installed distribution version as artifact provenance.
The in-memory API stops at the common execution result and performs no artifact
serialization.

Canonical GUI artifact matching constructs only the current
`panelsolver.case` v1 signature. Legacy launchers replace only visible identity
and the signature callback so D017/D018 fallbacks remain a compatibility
responsibility.

Canonical selectors and high-level case names use the FMF and Hypersonic flow
domains. Sentman and Newtonian-family names identify physical models or methods;
`fmfsolver` and `newtsolver` identify only legacy compatibility frontends. See
[ADR 0011](../adr/0011-canonical-domain-naming.md).

## Shared convergence

Canonical and legacy command frontends converge on the same application-owned
case-table dispatch, strict geometry and numeric validation, output collision
checks, durable CSV writing, scheduler behavior, and input-ordered result
reconstruction. Domain schemas, physical equations, domain-only artifact fields,
visible legacy identities, and legacy signature fallback inputs remain owned by
their domain or compatibility boundary. Core does not select behavior from a
concrete product name.

## Stable decisions

Architecture changes must respect the accepted [ADRs](../adr/README.md),
especially dependency direction, the load-vector boundary, signatures, mesh
identity, distribution versioning, and supported-domain compatibility.
Historical Phase 1–8 design/evidence is retained under
[History](../history/README.md), but its migration sequencing is no longer the
current development model.
