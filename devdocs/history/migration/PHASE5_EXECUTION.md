# Phase 5 shared execution infrastructure

Historical record — non-normative for the current product contract. This page records the repository state at the migration phase or audit named below. Statements such as “current”, supported commands, package names, file formats, and future work apply to that recorded point in time. Pinned source identities, golden evidence, tolerance profiles, and audit results may still be referenced by current developer workflows where devdocs/ or tests explicitly do so. Use docs/, devdocs/architecture/, and accepted or superseding ADRs for the present product contract.

Phase 5 composes the already-accepted contracts and physical models into a
single model-neutral execution path. It does not add a CLI, GUI, artifact
serializer, or compatibility import surface.

## Geometry and shielding

The Phase 5a loader snapshots source STL bytes, applies SI scale and an explicit
normal-repair policy, then constructs immutable `PanelMesh` and `PanelGeometry`
contracts. ADR 0006 records retained D011 behavior and the content-safe D012
cache identity. The versioned numerical geometry fingerprint excludes paths and
timestamps but includes ordered topology, derived geometry, and component IDs.

Phase 5b casts one upstream ray from each face center with the pinned epsilon and
first-hit rule. Forced rtree and Embree never silently fall back. Cache identity
includes geometry, direction, effective backend, batch size, and shielding
algorithm version. `PANELSOLVER_SHIELD_*` takes precedence over one adapter-
selected legacy prefix; core never chooses between both legacy prefixes.

Phase 8 makes the mask-cache direction identity the exact normalized float64
direction supplied to the ray backend. Both pinned legacy implementations and
the original shared implementation rounded direction components to 12 decimal
places. Distinct grazing directions can cross a panel boundary below that scale,
so a warm cache could return a mask that disagreed with the same cold ray query.
The correction changes only a private process-local cache key: the ray algorithm,
backend selection, public case signatures, artifact metadata, and shielding
algorithm version remain unchanged.

## Signature and result cache

ADR 0005 defines the exact schema. The signature binds common resolved inputs,
geometry, model identity/algorithm/payload, and requested/effective shielding
configuration. Application version and cache capacity are excluded. The result
cache stores only immutable `CommonResults`, so equivalent numerical geometry at
a different source path cannot reuse stale component-source metadata.

Phase 8 retains every public ADR 0005 digest and adds an internal execution-cache
identity. It combines that public digest with the exact accepted float64
`velocity_hat_stl` evaluated by the model. This closes a wrong-hit path for
last-bit-distinct accepted flow states, including equivalent legacy attitude
modes and tolerance-distinct direct-core requests, without changing the
angle-consistency tolerance, model equations, artifacts, or signature matching.

Phase 5 signatures match first. Product adapters may supply opaque ordered
legacy fallbacks; core does not normalize D017/D018 differences.

## One-case engine

`execute_case` accepts `CaseExecutionRequest`, whose model must implement the
Phase 2 `PanelLoadModel` and provide its normalized signature payload. The engine
validates model identity, loads geometry, computes shielding, constructs
`PanelFlowState`, builds the public and private cache signatures, checks the
result cache, evaluates the model, and routes the local vector through common
integration and component aggregation.

The engine has no concrete-model branch. `panelsolver.app` assembles the registry
containing `SentmanModel` and `HypersonicModel` and selects by stable model ID.
Models receive immutable geometry/flow contracts and never access files,
artifacts, GUI state, or scheduling.

The returned `CaseExecutionResult` contains the current mesh/source metadata,
exact shielding result, immutable `CommonResults`, canonical signature, warnings,
and cache-hit state. Artifact projection remains a separate Phase 3 operation;
serialization remains outside this engine.

## Spawn scheduler

`iter_execution_results_parallel` runs the same one-case engine in spawn
workers. Cache-aware bucket keys are scheduling hints; the versioned mesh,
shielding, signature, and result-cache identities still decide every reuse.
Results are delivered with stable input indices as workers finish.
`ordered_success_snapshot` reconstructs input-ordered, checkpoint-ready
successful snapshots, while `SchedulerProgress` counts accepted completions.

Cancellation sets a process-shared event. Workers observe it only between cases,
so an active ray query, root solve, or ODE is allowed to finish before the worker
reports cancellation. No new chunks are dispatched after the request. Worker
startup failure, a remote Python exception and traceback, and an unexpected
process exit have distinct scheduler errors and always trigger cleanup.

At this historical Phase 5/Phase 7 point, the two pinned D015 logging behaviors
were `WorkerLogPolicy.FORWARD` and `WorkerLogPolicy.DROP`. The differing
worker-failure behavior was
`PartialResultPolicy.DISCARD_CHUNK` and
`PartialResultPolicy.YIELD_COMPLETED`. Both were required arguments; core did not
choose one product's behavior for the other. The migrated product adapters
retained the pinned pairing: FMF selected `FORWARD`/`DISCARD_CHUNK`, while
newtsolver selected `DROP`/`YIELD_COMPLETED`.

Those historical choices are superseded by ADR 0008. The current implementation
uses `FORWARD`/`YIELD_COMPLETED` for both products without altering
successful-run numerical results, cancellation, worker lifecycle, signatures,
or caches.

Phase 8's independent audit corrected the pairing in this paragraph. A Phase 7
edit had reversed the two partial-result policies; same-bucket
good-then-failing probes and the pinned worker envelopes establish the pairing
above. No scheduler algorithm or per-case numerical value changed with this
correction. All-success runs remain unchanged; only whether an earlier completed
case from a later-failing chunk becomes parent-visible is corrected.

`PANELSOLVER_PARALLEL_CHUNK_CASES` has precedence over exactly one explicitly
selected `FMFSOLVER_PARALLEL_CHUNK_CASES` or
`NEWTSOLVER_PARALLEL_CHUNK_CASES`; an explicit function argument has highest
precedence and the default remains 8.

Phase 5 deliberately adds no CLI, GUI lifecycle, or artifact writer. Those
remain later-phase application and compatibility work.
