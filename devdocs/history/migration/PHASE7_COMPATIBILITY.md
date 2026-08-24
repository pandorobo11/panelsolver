# Phase 7 packaging and public compatibility

Historical record — non-normative for the current product contract. This page records the repository state at the migration phase or audit named below. Statements such as “current”, supported commands, package names, file formats, and future work apply to that recorded point in time. Pinned source identities, golden evidence, tolerance profiles, and audit results may still be referenced by current developer workflows where devdocs/ or tests explicitly do so. Use docs/, devdocs/architecture/, and accepted or superseding ADRs for the present product contract.

Phase 7 turns the accepted shared engine and GUI into the two runnable legacy
product surfaces. It preserves numerical behavior and each product's public
contract while removing duplicated common implementation from the compatibility
packages. It does not perform the independent Phase 8 audit or archive either
legacy repository.

This document also records Phase 7's historical decisions. ADR 0008 supersedes
the assumption that every legacy discrepancy is a permanent product contract;
its supported-domain policy governs Phase 8 remediation and close-out.

## Dependency sequence

Implementation is serialized through one issue, one worktree, and one draft PR
per slice:

1. #47 decides the single-distribution and compatibility-version mechanics;
2. #48 adds product case readers, attitude adaptation, and primary/legacy
   signature candidates;
3. #49 composes shared execution, CSV/VTP/NPZ serialization, and real GUI
   adapters;
4. #50 registers all six commands and preserves the two CLI contracts;
5. #51 forwards the frozen Python module and callable surfaces;
6. #52 completes user/release documentation, installed samples, both macOS GUI
   smokes, and Phase 7 acceptance.

Every slice starts from the latest accepted `origin/main`. It is made ready and
merged only after the complete unittest suite, unchanged Phase 1 goldens, Ruff,
build, and Ubuntu/Windows/macOS CI pass. Packaging slices additionally reinstall
and exercise the built wheel outside the repository.

## Distribution and versions

ADR 0007 selects one `panel-solvers` distribution containing all three packages
and both command families. Repository tags follow only `project.version`.

The frozen product-facing version values remain independent adapter contracts:

- FMF compatibility version: `1.3.8`;
- newtsolver compatibility version: `1.0.3`.

They remain visible only on legacy-compatible result, artifact, signature, and
Python surfaces. `importlib.metadata.version("panel-solvers")` reports the shared
distribution release. Canonical numerical signatures continue to use explicit
model and shielding algorithm versions, never an application version.

## Phase 7 retained dual contracts

Phase 7 implements product policy rather than choosing a universal behavior:

- D004-D008 were retained in Phase 7, then superseded by ADR 0008 and converged
  in Phase 8: common CSV/Excel format dispatch, portable Unicode case IDs,
  casefold collision rejection, attitude domains, and `--cases` cardinality;
- D009/D010 were retained in Phase 7, then superseded by ADR 0008 and converged
  in Phase 8 to shared destructive-collision rejection and durable atomic CSV;
- D015 was retained as an explicit scheduler-policy difference in Phase 7:
  when a later case raised a caught Python exception, FMF forwarded worker logs
  and discarded completed results from that chunk, while newtsolver dropped
  worker logs and yielded those completed results before reporting the error.
  This historical behavior is superseded by ADR 0008; both products now use
  `FORWARD`/`YIELD_COMPLETED`;
- D017/D018: the ADR 0005 signature is primary and ordered legacy hashes remain
  opaque fallbacks, including distinct direct/file variants;
- D019/D020/D029: VTP, NPZ, and result CSV model fields remain separate;
- D022/D023/D024/D027: exact titles, close policies, and manual stale-artifact
  inspection remain as accepted in Phase 6;
- D025: the de facto Python surfaces are forwarded independently rather than
  replaced with a cross-product union.

ADR 0006 recorded D011 mesh-repair policy during migration. Phase 8 applies ADR
0008 strict mesh safety to both frontends: repair exceptions and unresolved
winding are rejected together with non-finite and degenerate geometry. Phase 5
already defines neutral environment-variable precedence while reading one
explicitly selected legacy prefix.

## Compatibility boundaries

Shared case mechanics, orchestration, serialization, CLI flow, and GUI behavior
belong in `panelsolver.app` or `panelsolver.core`. Physical equations remain in
the independent model packages. `fmfsolver` and `newtsolver` may define schemas,
policies, legacy signatures, and call-shape translation, but may not duplicate
common numerical or application implementation.

No existing command, field, module, or callable is deprecated in Phase 7. A
future removal needs its own accepted transition. The legacy repositories remain
read-only numerical references through Phase 8.

## Case input and artifact identity

The compatibility readers keep separate FMF and newtsolver schemas, defaults,
model-field validation callbacks, and model fields over one table-reading
mechanism. Common format dispatch, case-ID safety, duplicate detection, and
attitude domains are owned by that shared boundary. Rows are adapted to
`CaseExecutionRequest` through product policies that select the model, mesh
validation rule, and legacy environment prefix.

The ADR 0005 execution signature is prepared through the same mesh and
shielding-resolution path used by execution, without evaluating physical panel
loads. Ordered pinned legacy hashes remain product-owned fallback identities.
They use the frozen `1.3.8` and `1.0.3` compatibility versions and are neither
interpreted by core nor treated as interchangeable with the primary signature.

Phase 8 preserves that public signature while separating internal result-cache
entries by the exact accepted flow vector. FMF/newtsolver adapters
deterministically resolve the vector and tangent angles together from each
product-specific public attitude mode. Equivalent attitudes expressed through
different modes can retain last-bit-distinct vectors while sharing the frozen
resolved-angle public signature. A custom direct-core caller may likewise supply
a tolerance-distinct vector that is evaluated under the same public signature.
The `ResultCache` API remains public and unchanged, but an instance passed to
`execute_case` contains engine-owned entries addressed by the private identity,
not by the returned public signature. User paths and limitations are recorded in
`PHASE7_USER_GUIDE.md`.

## Execution, serialization, and GUI adapters

The shared runtime executes adapted requests serially or through the Phase 5
spawn scheduler. Phase 7 selected FMF `FORWARD`/`DISCARD_CHUNK` and newtsolver
`DROP`/`YIELD_COMPLETED`. Phase 8
independently found that the original Phase 7 policy wiring and documentation had
the partial-result choices reversed, then restored the pinned same-chunk failure
behavior. ADR 0008 subsequently adopted and Phase 8 implemented common
`FORWARD`/`YIELD_COMPLETED`. Per-case
numerical values and all-success runs are unchanged. Shielding reuse may change execution
order, but every
checkpoint and final summary is reconstructed in input order. Cancellation is
observed at case boundaries and worker failures retain their remote traceback.

Each complete case projects and writes VTP/NPZ according to its flags, including
the retained output-directory side effect when both flags are off. Summary CSV
snapshots use the existing product schemas and D010 atomic-write policies. FMF
adds only `mode`, resolved `S`/`Ti_K`, and its NPZ physical values; newtsolver
adds only its canonical equation VTP metadata. Both artifacts and CSV carry the
primary ADR 0005 signature and frozen product-facing version.

Both default GUI specifications now contain real readers, signature builders,
execution, collision validation, and wind-direction adapters. The non-calculating
fallback remains only for an explicitly adapter-free specification and is not
used by either normal product launcher.

## Commands and CLI behavior

The distribution registers both GUI aliases and the batch command for each
product. The two batch entry modules select one shared CLI flow while retaining
their program names and descriptions. Both use `--cases CASES [CASES ...]`;
omitting the option runs every case and an explicit option with no value exits 2.
Case selection remains comma/space aware and input ordered, while reader, solver,
and worker exceptions remain uncaught command failures. Checkpoints rewrite the
complete successful snapshot and final output uses the same product-selected
atomic CSV policy.

CI builds and reinstalls the wheel on Ubuntu, Windows, and macOS, verifies all
six entry-point targets, validates the common CLI semantics, and runs both
unchanged Phase 1 input tables from a temporary directory outside the checkout.

## Python compatibility surface

The complete Phase 1 module inventories now import from the unified
distribution. Compatibility modules translate legacy DataFrame, dictionary,
mutable-mesh, serializer, scheduler, and no-argument GUI constructor shapes to
shared implementations. The roots retain exact empty-list `__all__` values and
expose product-facing `__version__` values of `1.3.8` and `1.0.3` independently
of the `panel-solvers` distribution version.

FMF forwards its Sentman vector and US1976 helpers only. newtsolver retains the
exact ordered `panel_core.__all__` and `pressure_models.__all__` lists, including
the recorded underscore exports. It forwards the independent pressure-model,
selector, attitude, and panel-force helpers without adding them to FMF. Direct
solver calls return the pinned legacy signature while normal Phase 7 runtime
artifacts continue to carry the primary ADR 0005 identity and accept ordered
legacy identities as fallbacks.

Phase 8 restored the pinned direct-solver failure boundary while retaining the
typed shared exception surface used by the CLI and GUI. For both products, a true
`run_cases()` cancellation callback is observed even for an empty table and
raises the exact built-in `RuntimeError("Canceled by user.")`. During parallel
work the compatibility callback is polled while spawn workers report readiness
as well as during execution, and raises immediately, so active results are not
accepted into progress or checkpoint snapshots after the request. Empty input
still validates `flush_every_cases` before cancellation, matching the non-empty
runtime. Phase 8 Issue #98 separately restored the pinned logging boundary:
direct `run_case()` skips the one-time ray-backend hint and batch-owned `[RUN]`
and `[OK]` messages, while retaining case-owned mesh/model warnings, and does not
consume the product's hint state. A non-cancel empty `run_cases()` emits only the
same product-specific hint as a non-empty batch and returns an empty DataFrame;
the hint becomes silent after its callback succeeds. FMF and newtsolver retain
independent one-time state and rtree installation text. Flush validation and
initial cancellation precede the empty hint, and a caller exception from the
hint leaves it retryable. As in the pinned callables, the required direct logger
is checked lazily only when a message is emitted. CLI, GUI, non-empty batch,
worker-log, and partial-result orchestration remain unchanged. Serial missing-STL
failures expose the original built-in `FileNotFoundError`; parallel
Python failures expose a built-in `RuntimeError` whose first line is
`[WorkerError]` plus the legacy cause wording. The full shared remote traceback
is retained, including the underlying `FileNotFoundError` evidence when mesh
loading supplied it.

Spawn-callable serialization and `Process.start()` failures again expose their
original built-in exception at the compatibility scheduler boundary. An
unexpected exit retains the independent product grammar: FMF uses
`Worker exited unexpectedly: worker N exitcode=X`, while newtsolver uses
`worker N (exit code X) exited without returning a result.` Direct probes at the
authoritative FMF `b62bc844d02a8f5212e62a53dea3238a1414317d` and newtsolver
`dc1357d0d50bbedfdc8b3429cab37e6b98b56c70` commits also observed exact
`cause=None`, `_queue.Empty` context, and `suppress_context=False`: the legacy
exception was raised inside its empty-Queue polling handler. The Pipe scheduler
does not naturally retain that Queue implementation detail, so the compatibility
adapter restores a synthetic empty `_queue.Empty` context only for this frozen
polling case. If an unexpected exit instead carries an EOF/OSError chain from a
broken Pipe frame, the adapter retains that transport cause/context rather than
overwriting it with `_queue.Empty`. Other translated legacy exceptions have no
synthetic cause/context chain.

A worker that exits before its readiness frame is classified by the same
unexpected-exit contract once a bounded join establishes its exit code. This
removes the platform-dependent poll-versus-EOF distinction: both paths reach the
FMF/newtsolver product grammar and pinned empty-Queue context. If the process is
still alive or its status remains unknown, the shared startup error retains the
underlying EOF/OSError chain as a Phase 8 transport diagnostic.

New bounded failures introduced by the Phase 8 Pipe/termination safety
correction, such as an unencodable worker result or broken IPC frame, have no
finite pinned legacy outcome because the old Queue path could hang or leak. They
surface as a built-in `RuntimeError` with the safety diagnostic while preserving
bounded kill/reap cleanup. Exceptions raised by caller-owned `logfn`,
`progress_cb`, `cancel_cb`, or `chunk_cb` callbacks are not runtime failures and
pass through by object identity with their type, message, cause, context, and
attached traceback evidence retained. A cleanup failure detected while such a
callback exception is active is copied to that original exception's notes rather
than being lost with the private boundary marker. For a parent-side progress,
checkpoint, or `[OK]` callback after a parallel result is yielded, the shared
runtime explicitly closes the active scheduler iterator during that unwind so
worker cleanup finishes before the callback exception crosses the public
boundary. This documented safety difference does not change D015 worker logs,
same-chunk partial results, execution order, numerical values, or artifact
schemas.

Phase 8 also restored the pinned direct-solver values before compatibility
DataFrame construction. Total rows expose `component_id` and
`component_stl_path` as exact empty strings; component rows expose Python `int`
IDs in source-STL order and empty `vtp_path`/`npz_path` strings. Disabled total
artifact paths are empty strings as well. This normalization is limited to the
four compatibility fields: the immutable neutral `CsvProjection`, numerical
values, result columns, summary CSV projection, and artifact contents are
unchanged.

The nested `component_rows` records returned by direct `run_case()` calls are
also projected back to the pinned 15 fields and insertion order: `scope`,
`component_id`, `component_stl_path`, `CA`, `CY`, `CN`, `Cl`, `Cm`, `Cn`, `CD`,
`CL`, `faces`, `shielded_faces`, `vtp_path`, and `npz_path`. Shared case IDs,
versions, signatures, timing fields, and backend metadata remain available on
the full `run_cases()` DataFrame and summary CSV; they are excluded only from
the nested compatibility records. Numerical values and artifact schemas are
unchanged.

Shared compatibility adapters own call-shape translation, mutable views of the
immutable mesh contract, DataFrame result reconstruction, and direct-array
serialization. The compatibility packages do not import NumPy, SciPy, trimesh,
or PyVista from their computational forwarding modules and contain no physical
formula, geometry, cache, shielding, scheduler, or serializer implementation.
Installed-wheel smoke testing imports every frozen module and checks the exact
root/version/D025 export contracts before exercising both command families.

Phase 8 restored the pinned direct-exporter call shape in both compatibility
packages. `fmfsolver.io.exporters` and `newtsolver.io.exporters` independently
define `export_vtp(out_path, vertices, faces, cell_data, field_data=None)` and
`export_npz(out_path, **arrays)` under their product module/name identities. The
functions write the requested artifact and return `None`, while the shared
internal serializers retain their `path` parameter and `Path` return for
application use. This correction changes no VTP/NPZ semantic array, metadata,
path, numerical value, or artifact schema.

## Final acceptance evidence

Phase 7 can be marked complete only when:

- unchanged legacy samples run from a clean installed wheel;
- all six commands and exact CLI help contracts work on the installed wheel;
- the frozen module inventories and representative public calls work outside the
  source tree;
- CSV schemas/cells and semantic VTP/NPZ arrays/metadata match the Phase 1
  profiles without updated goldens or tolerances;
- both model paths pass on Ubuntu, Windows, and macOS with required Embree and
  supported rtree fallback coverage;
- both GUIs are manually smoked in the correct macOS user session, or any
  Computer Use visibility limitation is explicitly recorded as unverified with
  alternative evidence;
- numerical deltas, compatibility effects, remaining risks, release, and
  rollback instructions are documented.

These checks are migration acceptance, not the independent correctness,
architecture, performance, and lifecycle audit reserved for Phase 8.

**Status:** Complete. Issues #47–#52 and their dependent draft PRs passed the
listed gates and merged serially. `PHASE7_USER_GUIDE.md` is the user/release
handoff and `../audits/PHASE7_EXECUTION_RECORD.md` records the exact CI, installed-wheel,
numerical, and manual GUI evidence. Phase 8 is now in progress under ADR 0008.
