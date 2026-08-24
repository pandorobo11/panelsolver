# Phase 8 final audit and acceptance report

Historical record — non-normative for the current product contract. This page records the repository state at the migration phase or audit named below. Statements such as “current”, supported commands, package names, file formats, and future work apply to that recorded point in time. Pinned source identities, golden evidence, tolerance profiles, and audit results may still be referenced by current developer workflows where devdocs/ or tests explicitly do so. Use docs/, devdocs/architecture/, and accepted or superseding ADRs for the present product contract.

## Verdict

**Accepted.** Phase 8 found no unexplained supported-domain numerical delta,
compatibility exception, performance or peak-memory regression at the defined
threshold, architecture violation, unresolved GUI lifecycle risk, distribution
drift, release-provenance gap, rollback failure, or cross-platform CI failure.

The final audited product commit is
`0674fbb0ad8c20e203624d1be76d52c3b66090cc`. It was the fetched protected
`origin/main` HEAD, the manifest commit, and the exact head of final-candidate CI
run [31761090153](https://github.com/pandorobo11/panel-solvers/actions/runs/31761090153).
The report PR changes documentation only. Its post-merge `origin/main` SHA and
exact-main CI are recorded on Issue #66 after merge.

## Acceptance matrix

| Area | Evidence | Result |
|---|---|---|
| prerequisites | #59–#65 accepted and closed; every remediation merged in dependency order | pass |
| clean candidate | exact fetched main, clean detached worktree, Open PR 0 before report | pass |
| frozen baseline | no Phase 1 golden, manifest, or tolerance change after ADR 0008 | pass |
| source | diff check, locked rayaccel sync, 311/311 unittest, Ruff, build | pass |
| installed distribution | clean outside-checkout smoke; extracted-sdist full 311/311 against installed exact wheel | pass |
| commands and formats | six commands; CSV/XLSX/XLSM/XLS; documented CSV/VTP/NPZ semantics | pass |
| numerical/backend | 15 cases, direct anchors, serial/parallel, cache, exact rtree/Embree masks | pass |
| architecture | complete import graph, no prohibited edge/cycle, thin compatibility frontends | pass |
| lifecycle | scheduler failure/cancel/cleanup and both real macOS GUI lifecycles | pass |
| performance/RSS | five-run medians, fresh/cold/warm, serial/parallel; maxima 1.156 wall and 1.043 RSS | pass |
| release | single build, manifest binding, tag-target rejection, no rebuild in release | pass |
| rollback | exact pinned FMF/newtsolver wheels, six commands, samples, exact return | pass |
| CI | artifact plus Ubuntu, Windows, macOS exact-main jobs | pass |
| non-effects | no benchmark optimization, numerical change, release, tag, or legacy modification | pass |

## Exact distribution evidence

- wheel `panel_solvers-0.1.0-py3-none-any.whl`:
  `8c5a0ae908da78e51f9dc5f7b097204baa5684cb23c1a802795fbad718530081`;
- sdist `panel_solvers-0.1.0.tar.gz`:
  `c2c20b2c2237d3adaf7f6632ed04692e3b103f17e432893bc960f7991cd43ed3`;
- `manifest.json`:
  `64f8dbff6e7881e061a7548e09ee68299b27fe6916ec59a3e8780e337d417f12`;
- rollback record:
  `f0106e786d571b6498c02dc16fc13aeedca8e9d2a7015e6be20bb678538cd5a2`.

The workflow builds once in `artifact`. All three OS jobs, installed smoke,
artifact inspection, rollback/return, and release publication consume that same
verified distribution set. The release job has no build step.

## Numerical, performance, and compatibility conclusions

The final performance comparison used FMF Mode B, newtsolver algebraic and
tangent-cone cases, both products with forced rtree and Embree shielding,
serial/two-worker spawn, fresh processes, same-process cold/warm caches, peak
process-tree RSS, and five repetitions per cell. The maximum fresh end-to-end
ratio was 1.156 and maximum peak-RSS ratio was 1.043. Across 6,720 coefficient
comparisons the maximum absolute difference was
`5.551115123125783e-17`, inside the unchanged tolerances.

FMF and newtsolver intentionally retain different physical models, case fields,
formula selections, compatibility versions, and product-only artifact metadata.
ADR 0008 intentionally excludes Python introspection/identity, exact invalid
exception details, and direct GUI internals. The documented commands, normal GUI
operation, case formats, CSV columns, and VTP/NPZ semantics remain supported.

## GUI, release, and rollback conclusions

The exact installed wheel was manually operated in an unlocked macOS session.
Both titled GUIs loaded their real committed tables, ran a real case, showed
progress/logs, wrote CSV/VTP/NPZ, automatically loaded the matching artifact,
changed scalar and camera, exported PNG, closed/restarted normally, canceled an
active workload, deferred active-run close through cleanup, exited, and restarted
cleanly.

The hypothetical release and annotated-tag tests passed, including rejection
when a tag does not target current protected `origin/main`. No actual tag or
GitHub Release exists. Exact pinned rollback used FMF wheel
`bb42ef01f1af0ac8821ee70f239db7f53b7355dcb674567620ed8f6d618e1933`
and newtsolver wheel
`6bc2bb436eea3b246549f78493edaab8679947b31c0702de8df278a02ab3939c`,
then returned to the byte-identical candidate wheel.

## Remaining operating boundaries

No audit item remains unverified. Cancellation remains cooperative at a case
boundary while an individual model/ray call is active. The pinned legacy
repositories remain unarchived read-only references. A future release remains a
deliberate operator action and must use the verified annotated-tag and manifest
procedure.

The detailed evidence, merge order, changed-file groups, raw performance hashes,
and design decisions are in `PHASE8_EXECUTION_RECORD.md`.
