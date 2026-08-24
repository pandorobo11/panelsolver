# Migration plan

Historical record — non-normative for the current product contract. This page records the repository state at the migration phase or audit named below. Statements such as “current”, supported commands, package names, file formats, and future work apply to that recorded point in time. Pinned source identities, golden evidence, tolerance profiles, and audit results may still be referenced by current developer workflows where devdocs/ or tests explicitly do so. Use docs/, devdocs/architecture/, and accepted or superseding ADRs for the present product contract.

## Principles

The migration proceeds through independently reviewable pull requests. Structural
movement and physical changes are never combined. A phase is complete only when
its tests and documented acceptance criteria pass; elapsed work or copied code is
not completion.

The pinned legacy implementations in `MIGRATION_SOURCES.md` remain numerical
oracles for supported inputs. ADR 0008 prevents accidental invalid-input and
Python-internal differences from becoming permanent product contracts. The final
design is one repository, one shared engine/application shell, independent
physical models, and temporary compatibility frontends for both old products.

## Dependency sequence

```text
0 foundation
    -> 1 behavioral baselines
        -> 2 central contracts
            -> 3 low-risk shared core
                -> 4a Sentman model
                -> 4b hypersonic model
                    -> 5 shielding/execution/cache/signatures
                        -> 6 shared GUI
                            -> 7 packaging and compatibility completion
                                -> 8 final audit
```

Only model migrations 4a and 4b are intended for concurrent implementation, and
only after Phase 2 contracts are merged. Changes to the shared core, schemas,
output formats, GUI shell, or `pyproject.toml` are serialized.

## Phase 0 — Repository foundation

**Scope:** Create the neutral repository, package/test directory boundaries,
development instructions, architecture and compatibility documents, ADRs, locked
dependencies, and cross-platform CI. Do not migrate algorithms or expose legacy
commands.

**Acceptance:**

- Python 3.12+ package skeleton imports all three top-level packages.
- `uv sync --locked --extra rayaccel`, unittest, Ruff, and build pass locally.
- CI covers Ubuntu, Windows, and macOS, verifies Embree, and builds/reinstalls the
  wheel.
- Source commits and intentional Phase 0 compatibility gaps are documented.
- Central architecture decisions are recorded, while exact Python contracts and
  numeric tolerances remain deferred to evidence-producing phases.

## Phase 1 — Freeze behavioral and numerical baselines

**Scope:** Execute both pinned legacy suites; inventory public imports, commands,
case schemas/defaults, environment variables, result columns, VTP/NPZ contents,
GUI-visible behavior, caches, scheduler errors, and backend selection. Generate a
small matrix of reproducible golden fixtures for both models and both ray paths.
Document all differing behavior without resolving it incidentally.

**Minimum fixture coverage:** zero and nonzero attitude, sideslip/bank variants,
multi-component geometry, shielded/unshielded panels, moment-reference offset,
backend selection/fallback, valid boundary inputs, invalid inputs, and at least
one canonical validation case per physical model family.

**Acceptance:**

- Every golden fixture names its source commit, generation command, backend, and
  per-quantity tolerance.
- Panel vectors/scalars, shielding masks, total and component coefficients,
  result CSV schema/order, and semantic VTP/NPZ content are captured.
- A legacy-difference ledger classifies each mismatch as intentional, bug,
  unknown, or compatibility decision required.
- Baselines reproduce on a clean environment without editing legacy source.

**Evidence:** `phase1/BEHAVIORAL_INVENTORY.md` records the public surfaces,
`phase1/LEGACY_DIFFERENCES.md` preserves unresolved dual behavior,
`phase1/GOLDEN_BASELINES.md` identifies the case matrix and Phase 2 inputs, and
`phase1/TOLERANCES.md` defines the quantity-specific comparison rules. Executable
captures and their manifest are under `tests/fixtures/phase1`.

## Phase 2 — Define central contracts

**Scope:** Define and test immutable/validated contracts such as `PanelGeometry`,
`PanelFlowState`, `LocalLoads`, `PanelLoadModel`, common/model case payloads, and
common results. Decide frame annotations, mutability, array ownership, scalar
validation, error taxonomy, and model registry. Update ADR 0002 with the exact
accepted API.

**Acceptance:** contracts represent Sentman tangential loads and hypersonic normal
loads without model-name branches; shapes/nonfinite values are validated; core
does not import models/app/frontends; contract tests use synthetic data and do not
change legacy numerical output.

## Phase 3 — Extract low-risk shared core

**Status:** Complete.

**Scope:** Migrate exporters, attitude/frame transforms, mesh data representation,
force/moment integration, component aggregation, and common result types. Initially
call the extracted functions from adapters around legacy pipelines. Choose a
legacy difference only through a dedicated compatibility decision or ADR.

**Acceptance:** affected golden arrays and coefficients match within Phase 1
tolerances; frame/sign edge cases pass; exporter semantic fields and CSV order are
unchanged; no model equation has moved into core.

**Evidence:** `PHASE3_ADAPTERS.md` records the final adapter boundary and retained
dual policies. The complete 15-case semantic matrix runs through the product
adapters in `tests/regression/test_phase3_legacy_adapters.py`, comparing every CSV
cell/order, VTP named array/field, and NPZ array with the selected Phase 1
tolerance profile.

## Phase 4 — Adapt physical models

**Status:** Complete.

### 4a Sentman

**Status:** Complete.

Wrap the existing Sentman equations, atmosphere-derived inputs, case validation,
scalars, metadata, and signature payload behind `PanelLoadModel`. Preserve both
normal and tangential local load contributions.

**Evidence:** `PHASE4_MODELS.md` records the Sentman adapter boundary. Unit tests
retain the independent analytic flat-plate reference; an exact audit covers all
201 pinned US1976 rows. The six FMF Phase 1 cases are recomputed by the model and
routed through the common integrator without changing their goldens or
tolerances.

### 4b Hypersonic

**Status:** Complete.

Wrap Newtonian, modified Newtonian, tangent-wedge, tangent-cone, and
Prandtl–Meyer behavior, including windward/leeward canonicalization and component
overrides, behind the same contract.

**Evidence:** `PHASE4_MODELS.md` records the independent hypersonic boundary.
Unit coverage preserves all five equation families, detached branches, the
Taylor–Maccoll solver settings, safeguarded Prandtl–Meyer iteration, selector
canonicalization, and component overrides. The nine newtsolver Phase 1 cases are
recomputed by the model and compared with their algebraic, root-solve, or
tangent-cone tolerance profiles.

**Acceptance for each:** model-specific validation and scientific reference tests
pass; Phase 1 panel-level and integrated goldens match; no filesystem, GUI,
scheduler, or common integration code lives in the model.

## Phase 5 — Unify geometry execution infrastructure

**Scope:** Unify strict mesh validation, geometry fingerprints, ray shielding,
Embree/rtree adapters, mesh and shielding caches, common case signatures, parallel
scheduler, worker logging, cancellation, progress, partial-result policy, and
failure propagation. Define neutral `PANELSOLVER_*` environment variables while
reading documented legacy variables with explicit precedence.

**Acceptance:** both models execute through one engine; cache keys cannot cross
contaminate geometry/model/algorithm variants; backend goldens match; worker start,
failure, cancellation, and partial-result tests are deterministic; signature
schema/versioning conforms to ADR 0005.

**Status:** Complete. Phase 5a–5e introduced content-safe mesh loading and
fingerprints, explicit rtree/Embree shielding and caches, the ADR 0005 canonical
signature and bounded result cache, one model-neutral execution engine, and the
spawn scheduler. The scheduler requires explicit D015 log and worker-failure
partial-result policies, observes cancellation between cases, propagates remote
tracebacks and unexpected exits, and produces input-ordered successful snapshots.
All 15 Phase 1 cases continue to match their frozen semantic goldens and
tolerances through the common engine; no numerical baseline was changed.

## Phase 6 — Share the GUI and viewer

**Scope:** Implement one `SolverSpec`-driven main window, cases panel, and viewer.
Discover VTP cell arrays dynamically while prioritizing model-preferred scalars.
Preserve selection, progress, cancel/close, image export, camera controls, and
case-signature matching.

**Acceptance:** each compatibility launcher opens the shared shell with the right
model/schema/title; GUI and viewer compatibility tests pass; neither GUI nor
frontend contains physics; headless numerical use remains testable.

**Status:** Complete. Phase 6a–6g introduced the immutable product-selected
`SolverSpec`, shared exact artifact matching and dynamic scalar discovery, one
viewer, one cases panel, QThread progress/cancellation lifecycle, independently
selected D023 close behavior, image export, one shared bootstrap, and two thin
GUI selector modules. Both launchers preserve their exact titles, schemas,
overlays, model identities, and close policies. All Phase 1 numerical goldens
remain unchanged. The modules are included in the built wheel, but none of the
six legacy commands is registered.

## Phase 7 — Finish packaging, CLI, and public compatibility

**Scope:** Register all legacy command names, forward supported public imports,
complete CSV/Excel and artifact compatibility, decide single-versus-multiple
distribution release mechanics, and write user migration/release documentation.
Do not archive legacy repositories yet.

**Acceptance:** existing samples run unchanged; all six commands and their
`--help` contracts work from an installed wheel; result schemas and artifacts
match; Windows/macOS/Linux CI covers both models; no common implementation remains
duplicated in the compatibility packages.

**Status:** Complete. ADR 0007 selects one `panel-solvers` distribution while
retaining independent FMF/newtsolver compatibility versions on their frozen
public surfaces. Issues #47–#52 were implemented serially as one worktree and
one draft PR each. Case readers, execution and serialization adapters, all six
commands, the complete frozen import inventories, clean-wheel sample runs, and
both manual macOS GUI smokes are accepted. Every Phase 1 golden and tolerance is
unchanged. `PHASE7_COMPATIBILITY.md`, `PHASE7_USER_GUIDE.md`, and
`../audits/PHASE7_EXECUTION_RECORD.md` record the contracts and evidence.

## Phase 8 — Independent final audit

**Status:** Complete. ADR 0008 established the supported-domain compatibility
policy. Every remediation and final-candidate audit is accepted; the durable
evidence is in `../audits/PHASE8_EXECUTION_RECORD.md` and
`../audits/PHASE8_FINAL_AUDIT.md`.

**Scope:** Audit numerical correctness, architecture/dependencies, compatibility,
parallelism/caching, performance, GUI lifecycle, tests, and installed artifacts.
Run the complete baseline on clean environments and compare performance/memory
without changing algorithms to improve benchmark optics.

**Acceptance:** no unexplained supported-domain numerical delta; all retained
compatibility exceptions have an accepted record and user path; shared
invalid-input safety and infrastructure conform to ADR 0008; performance
regressions are understood and accepted or fixed; release/rollback instructions
are complete. Only then may the legacy repositories be marked read-only.

**Outcome:** Accepted at audited product commit
`0674fbb0ad8c20e203624d1be76d52c3b66090cc`. Source, installed wheel, extracted
sdist, numerical/artifact semantics, performance/RSS, both macOS GUI lifecycles,
Ubuntu/Windows/macOS/artifact CI, single-build release provenance, annotated-tag
target safety, and exact pinned rollback/return all passed. No golden or
tolerance changed. The legacy repositories remain unarchived read-only
references; no release or tag was created by the audit.

## Decision and risk log

Open questions must be recorded in the relevant issue or a new ADR. Highest-risk
areas are load-vector signs/frames, mesh normal repair, shielding backend parity,
signature/cache invalidation, multiprocessing errors/cancellation, CSV order, and
VTP/NPZ metadata. These receive panel-level regression coverage before refactoring.
