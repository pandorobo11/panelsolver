# Phase 8 execution record

Historical record — non-normative for the current product contract. This page records the repository state at the migration phase or audit named below. Statements such as “current”, supported commands, package names, file formats, and future work apply to that recorded point in time. Pinned source identities, golden evidence, tolerance profiles, and audit results may still be referenced by current developer workflows where devdocs/ or tests explicitly do so. Use docs/, devdocs/architecture/, and accepted or superseding ADRs for the present product contract.

## Scope, baselines, and working discipline

Phase 8 was the independent final audit of the Phase 7 migration. It started
from the Phase 7 acceptance merge
`64658432bcae7eb642e2ab07167a8d32993315a1` and ended with the accepted product
candidate `0674fbb0ad8c20e203624d1be76d52c3b66090cc`. The audit used the policy in
ADR 0008 and the disposition in `PHASE8_ISSUE_DISPOSITION.md`. It did not treat
invalid-input accidents or Python implementation identity as product contracts.

The immutable references in `../migration/MIGRATION_SOURCES.md` remained clean and
read-only throughout:

- FMF commit `b62bc844d02a8f5212e62a53dea3238a1414317d`, tree
  `52e5b876544d90323fa04468fc22ea0fbbf559c3`;
- newtsolver commit `dc1357d0d50bbedfdc8b3429cab37e6b98b56c70`, tree
  `48e3782dd27056e716884a30e72a2ed758e6c8e4`.

Every implementation used a new worktree from the latest accepted
`origin/main`, one scoped branch, and one reviewable PR. No implementation was
pushed directly to `main`. Audit-only Issues used clean detached worktrees and
did not create product changes. The final report uses the same rule through
Issue #66 and a dedicated report-only worktree.

## Issue, worktree, PR, and merge order

The branch column identifies the corresponding worktree branch. Temporary
worktree paths were disposable; the branch and merge commit are the durable
identity of each slice.

| Order | Issue / PR | Worktree branch | Merge commit | Decision or result |
|---:|---|---|---|---|
| 1 | #67 / #68 | `codex/issue-67-phase8-provenance` | `6be91c7` | Correct the Phase 7 legacy provenance SHAs. |
| 2 | #74 / #81 | `codex/issue-74-scheduler-lifecycle` | `a4d6d07` | Harden spawn, transport, shutdown, and cleanup. |
| 3 | #75 / #84 | `codex/issue-75-failed-chunk-policy` | `4658ab6` | Restore the measured legacy failed-chunk policies before policy review. |
| 4 | #82 / #85 | `codex/issue-82-result-cache-flow` | `70de1b6` | Isolate result-cache entries by exact flow direction. |
| 5 | #83 / #87 | `codex/issue-83-shield-cache-direction` | `24f07f7` | Prevent shielding-direction cache collisions. |
| 6 | #69 / #88 | `codex/issue-69-exporter-contract` | `603cf78` | Restore supported exporter behavior. |
| 7 | #70 / #91 | `codex/issue-70-direct-result-types` | `29c7f07` | Restore direct result blanks and types. |
| 8 | #86 / #92 | `codex/issue-86-component-row-schema` | `e1c3306` | Restore component-row schema and order. |
| 9 | #73 / #101 | `codex/issue-73-direct-solver-errors` | `25dfbbc` | Restore direct solver failure and cancellation behavior. |
| 10 | #98 / #102 | `codex/issue-98-direct-solver-logging` | `b739920` | Restore direct solver logging side effects. |
| 11 | #59–#62 / #103 | `codex/phase8-supported-domain-policy` | `aeaf85a` | Accept ADR 0008 and dispose every then-open Issue. |
| 12 | #104 / #105 | `codex/issue-104-d015-convergence` | `1831d93` | Converge both schedulers on `FORWARD / YIELD_COMPLETED`. |
| 13 | #93 / #106 | `codex/issue-93-array-coercion` | `361220e` | Normalize ragged common-array errors. |
| 14 | #99 / #107 | `codex/issue-99-shielding-coercion` | `402bd0e` | Normalize ragged shielding errors. |
| 15 | #94 / #108 | `codex/issue-94-speed-ratio-overflow` | `d60f1f4` | Reject overflowed derived Sentman speed ratio. |
| 16 | #95 / #109 | `codex/issue-95-attitude-invariants` | `c1c63fb` | Enforce finite, overflow-safe `ResolvedAttitude` invariants. |
| 17 | #96 / #110 | `codex/issue-96-sentman-helper-validation` | `705a2dc` | Validate shared Sentman helper inputs. |
| 18 | #76 / #111 | `codex/issue-76-shared-reader-cli` | `93314df` | Converge file readers, case IDs, attitudes, and CLI selection. |
| 19 | #100 / #112 | `codex/issue-100-validation-matrix` | `32410c9` | Freeze the common reader accept/reject matrix. |
| 20 | #113 / #114 | `codex/issue-113-output-safety` | `379b271` | Add path-collision safety and durable atomic CSV writes. |
| 21 | #115 / #116 | `codex/issue-115-mesh-safety` | `33043ae` | Converge strict finite, nondegenerate, consistent mesh safety. |
| 22 | #117 / #118 | `codex/issue-117-gui-lifecycle` | `7934e6a` | Unify active-run cancel, deferred close, and cleanup. |
| 23 | #78 / #119 | `codex/issue-78-architecture-graph` | `d39f80a` | Enforce the complete dependency graph and justify `networkx`. |
| 24 | #71 / #120 | `codex/issue-71-version-independent-wheel` | `b376e62` | Make wheel verification version-independent and complete release checks. |
| 25 | #72 / #121 | `codex/issue-72-reproducible-rollback` | `e6e38b7` | Make exact pinned rollback and return reproducible. |
| 26 | #122 / #128 | `agent/issue-122-case-id-nfc` | `8be3cc6` | Normalize accepted case IDs to Unicode NFC. |
| 27 | #123 / #129 | `agent/issue-123-numeric-booleans` | `67d9e7a` | Reject booleans in numeric case fields. |
| 28 | #124 / #130 | `agent/issue-124-attitude-overflow` | `6ffe235` | Make attitude normalization overflow-safe. |
| 29 | #125 / #131 | `agent/issue-125-cache-warnings` | `5a0e5b2` | Replay mesh warnings on cache hits. |
| 30 | #126 / #132 | `agent/issue-126-d015-docs` | `a97be07` | Align D015 documentation with ADR 0008. |
| 31 | #127 / #133 | `agent/issue-127-release-tag` | `6635a41` | Verify annotated release tags and protected-main targets. |
| 32 | #134 / #135 | `agent/issue-134-release-provenance` | `4043855` | Bind every release consumer to one verified distribution set. |
| 33 | #136 / #137 | `agent/issue-136-selector-attitude-types` | `0674fbb` | Harden selector and attitude-vector type boundaries. |

Issues #63, #65, and #64 then re-audited performance, distribution/release,
and both real macOS GUIs on `0674fbb`; all three closed without another product
change. Issue #66 is the report-only close-out.

## Changed files and design decisions

From the Phase 7 acceptance merge through the accepted Phase 8 product
candidate, 85 files changed (8,882 insertions and 947 deletions). The complete
name list is available from:

```bash
git diff --name-only \
  64658432bcae7eb642e2ab07167a8d32993315a1 \
  0674fbb0ad8c20e203624d1be76d52c3b66090cc
```

The changes are grouped as follows:

- release and provenance: `.github/workflows/ci.yml`, `CHANGELOG.md`,
  `scripts/release_tools.py`, `scripts/smoke_installed_wheel.py`, and
  `scripts/probe_legacy_rollback.py`;
- common safety and execution: `src/panelsolver/app/{attitude,case_io,cli,
  csv_writer,legacy_results,legacy_scheduler,main_window,runtime,solver_spec}.py`
  and `src/panelsolver/core/{_validation,execution,mesh_loading,result_cache,
  scheduler,shielding}.py`;
- physical-model boundary: `src/panelsolver/models/sentman.py`, with formulas
  unchanged for supported inputs;
- thin compatibility frontends: the touched `src/fmfsolver` and
  `src/newtsolver` adapters, readers, runtime, CLI, GUI specification, and
  exporters;
- documentation and policy: AGENTS, architecture, compatibility, development,
  migration, numerical, Phase 3/5/6/7 records, ADRs 0004–0006 and 0008, and the
  Phase 8 disposition;
- regression coverage: compatibility, GUI, cache/signature, architecture,
  scheduler, release, rollback, mesh, shielding, Sentman, attitude, CSV, and
  execution tests.

The central decisions were:

1. Preserve numerical correctness and documented commands/files/GUI semantics,
   while converging invalid-input safety and excluded Python internals under ADR
   0008.
2. Use one shared `FORWARD / YIELD_COMPLETED` scheduler policy while retaining
   successful cases, ordering, diagnostics, and remote failure visibility.
3. Keep model schemas, formulas, compatibility versions, and product metadata
   independent behind the common engine.
4. Build a release distribution once, bind every test/rollback/release consumer
   to its manifest, and require an annotated tag at protected `origin/main`.
5. Keep rollback reproducible from the exact recorded legacy commits rather
   than from older release-tag artifacts.

No Phase 1 golden array, golden record, manifest, quantity-specific tolerance,
physical formula, sign, axis, frame, normalization, shielding mask, CSV schema,
VTP/NPZ semantic field, or case-signature schema was changed. Two BIFF XLS
inputs were added only to test the already-supported legacy workbook path.

## Final source, distribution, and CI gates

The final candidate was fetched and tested in a clean detached worktree:

- `git diff --check`: pass;
- `uv sync --locked --extra rayaccel`: pass on CPython 3.12.12;
- source full suite: 311/311 pass;
- `uv run ruff check src tests scripts`: pass;
- `uv build`: pass;
- clean extracted sdist running the installed downloaded wheel: 311/311 pass;
- installed-wheel smoke from outside the checkout: pass;
- all six commands, both real sample tables, serial/parallel execution,
  rtree/Embree, CSV/VTP/NPZ semantics, direct compatibility surfaces, scheduler,
  GUI, packaging, release, and rollback probes: pass.

Exact distributions from exact-main CI run
[31761090153](https://github.com/pandorobo11/panel-solvers/actions/runs/31761090153):

| Artifact | Filename | SHA-256 | Contents |
|---|---|---|---:|
| wheel | `panel_solvers-0.1.0-py3-none-any.whl` | `8c5a0ae908da78e51f9dc5f7b097204baa5684cb23c1a802795fbad718530081` | 118 entries |
| sdist | `panel_solvers-0.1.0.tar.gz` | `c2c20b2c2237d3adaf7f6632ed04692e3b103f17e432893bc960f7991cd43ed3` | 255 entries |
| manifest | `manifest.json` | `64f8dbff6e7881e061a7548e09ee68299b27fe6916ec59a3e8780e337d417f12` | exact commit, filenames, hashes, METADATA |

The manifest commit is exactly
`0674fbb0ad8c20e203624d1be76d52c3b66090cc`. Wheel METADATA reports
`Name: panel-solvers`, `Version: 0.1.0`, and `Requires-Python: >=3.12`; runtime
dependencies, `rayaccel` markers, and exactly six console scripts were checked.
The local rebuild was byte-identical to both downloaded distributions.

The workflow contains exactly one `uv build`, in `artifact`. Ubuntu, Windows,
and macOS download and reinstall the same verified wheel. The artifact job uses
that wheel for installed smoke and rollback/return. The release job contains no
build and can publish only the same verified wheel, sdist, manifest, and matching
changelog section. In run 31761090153 the four required checks passed:

- `artifact`;
- `test (ubuntu-latest)`;
- `test (windows-latest)`;
- `test (macos-15)`.

The non-tag `release` job skipped as designed. Branch protection was re-read as
strict, with those exact four contexts, conversation resolution, admin
enforcement, no force pushes, and no deletion.

## Numerical and compatibility result

The complete supported semantic matrix passed without an unexplained delta.
The maximum coefficient difference in the final performance audit was
`5.551115123125783e-17`, within the original quantity-specific tolerances. The
15 committed Phase 1 cases, direct anchors, serial/parallel paths, rtree/Embree
masks, cache identity, summary CSV, and VTP/NPZ named arrays and metadata all
matched.

The retained differences are intentional:

- FMF remains the Sentman model and retains Mode A/Mode B fields, tangential
  panel loads, FMF schemas, FMF metadata, and compatibility version 1.3.8;
- newtsolver retains Mach/gamma, independent windward/leeward equations,
  Newton-family normal loads, newtsolver schemas/metadata, and compatibility
  version 1.0.3;
- the shared distribution version remains 0.1.0;
- exact direct-Python keyword names, defining modules, object identity, pickle
  globals, cache internals, GUI methods, and exact invalid-input exception
  details remain outside the supported contract unless another ADR promotes
  them.

No command, normal launcher-driven GUI flow, documented case format, result
column, or documented CSV/VTP/NPZ semantic field was removed.

## Performance and peak memory

Issue #63 compared the exact candidate wheel with both exact legacy pins on an
Apple M4, macOS 15.6 arm64, CPython 3.12.12, and one locked dependency set. It
used seven representative scenarios: FMF Mode B, newtsolver algebraic and
tangent-cone, and both products forced through rtree and Embree shielding.
Every scenario ran serial and two-worker spawn, with five repetitions, fresh
processes, and same-process cold/warm cache measurements.

| Measurement | Final maximum candidate/legacy ratio |
|---|---:|
| fresh-process end-to-end wall time | 1.156 |
| parallel cold solver path | 1.148 |
| parallel warm solver path | 1.134 |
| two-run process wall time | 1.192 |
| fresh-process peak RSS | 1.042 |
| cold/warm process-tree peak RSS | 1.043 |

The audit covered 420 solver-batch executions, 840 semantic record pairs, and
6,720 coefficient comparisons. Forced backend identity matched for all 840
records. Very short serial solver-only calls retain a measured fixed common
validation/projection overhead, but no reproducible 50% end-to-end or peak-RSS
regression exists. No benchmark-specific optimization or numerical change was
made.

Raw evidence SHA-256:

- fresh process: `480145cc74fe961e5d9de19dc173daf225c1da11af0a941bc0bfaccf20220915`;
- cache/parallel/RSS: `29819e7e6592b22418a000867c8cf5d83637d0b4e7de31a5b71675b78d202add`;
- summary: `cbf3ee79e6c92cb4101da5fd7fe9b07f44a8238e0ba21c37aec4de8445b9741b`.

## Manual macOS GUI evidence

Issue #64 ran both launchers from an isolated installation of the exact final
wheel in the correct unlocked macOS GUI session. Temporary application bundles
only supplied native Accessibility identities; they called the installed entry
points and did not alter the repository or package.

FMF `Sentman FMF Solver (GUI)` loaded the six-row FMF schema, selected and ran
`fmf_zero_plate`, showed progress and logs, wrote CSV/VTP/NPZ, automatically
matched the selected VTP, changed `Cp_n` to `shielded`, exercised `+X` and
`Wind +`, and exported PNG. newtsolver `newtsolver (GUI)` completed the same
flow with its nine-row independent schema and `newt_zero_newtonian`.

Both products passed normal close, quit cleanup, and restart. Cold large-mesh
workloads proved active Cancel, case-boundary completion, `Run canceled`,
deferred close, worker/thread cleanup, application exit, and clean restart. No
manual item remains unverified.

## Release and exact rollback audit

The hypothetical `0.1.1.dev0` release dry-run passed in a temporary copy and
fresh environment. Annotated-tag temporary-repository tests accepted the exact
protected-main target and rejected an old protected-main target and a side
branch. Version, lock, changelog, tag form, manifest cardinality, manifest
tampering, filename, hash, and METADATA mismatch tests passed. No repository tag
or GitHub Release was created.

Rollback record SHA-256:
`f0106e786d571b6498c02dc16fc13aeedca8e9d2a7015e6be20bb678538cd5a2`.

| Distribution | Exact source commit | Wheel SHA-256 |
|---|---|---|
| FMF 1.3.8 | `b62bc844d02a8f5212e62a53dea3238a1414317d` | `bb42ef01f1af0ac8821ee70f239db7f53b7355dcb674567620ed8f6d618e1933` |
| newtsolver 1.0.3 | `dc1357d0d50bbedfdc8b3429cab37e6b98b56c70` | `6bc2bb436eea3b246549f78493edaab8679947b31c0702de8df278a02ab3939c` |

The sequence panel-solvers -> uninstall -> exact pinned legacy pair ->
uninstall -> exact candidate wheel passed. All six commands worked before,
during, and after rollback; real samples and eight-coefficient semantic records
passed under both products; the returned wheel hash was the exact candidate
hash. The legacy sources remained unchanged.

## Residual risks and final disposition

There are no unverified acceptance items and no remaining remediation decision.
The following are explicit operating boundaries, not blockers:

- cancellation of a currently executing model/ray call is cooperative at the
  next case boundary; active-run close remains deferred until cleanup;
- no real release or tag was created, so publishing remains a future operator
  action governed by the verified procedure;
- the exact pinned legacy repositories remain unarchived, read-only behavioral
  references;
- fixed overhead is visible in millisecond-scale direct calls but is not a 50%
  end-to-end or memory regression.

The accepted final product candidate is
`0674fbb0ad8c20e203624d1be76d52c3b66090cc`. The Issue #66 report merge is
documentation-only; its post-merge `origin/main` SHA and exact-main CI run are
recorded on #66 because a document cannot contain the hash of its own merge.
