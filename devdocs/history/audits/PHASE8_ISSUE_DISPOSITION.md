# Phase 8 open-Issue disposition

Historical record — non-normative for the current product contract. This page records the repository state at the migration phase or audit named below. Statements such as “current”, supported commands, package names, file formats, and future work apply to that recorded point in time. Pinned source identities, golden evidence, tolerance profiles, and audit results may still be referenced by current developer workflows where devdocs/ or tests explicitly do so. Use docs/, devdocs/architecture/, and accepted or superseding ADRs for the present product contract.

> Completion note: this document is the historical planning disposition. The
> plan is complete; results and final acceptance are recorded in
> `PHASE8_EXECUTION_RECORD.md` and `PHASE8_FINAL_AUDIT.md`.

This record applies ADR 0008 to every Issue open on 2026-08-14. It is a planning
and close-out record, not authorization to combine the listed implementations.
Each implementation remains one latest-main worktree and one independently
reviewable PR. This policy PR closes no Issue and creates no remediation Issue.

## Disposition

| Issue | Classification | Recommendation after ADR 0008 merges |
|---|---|---|
| #59 | audit close-out | Record that #67 corrected the provenance conflict, then close. |
| #60 | audit close-out | Map the numerical findings to their remediation Issues, then close the audit-only parent. |
| #61 | audit close-out | Record ADR 0008's supported-domain decision and the remaining implementation map, then close. |
| #62 | audit close-out | Correct D015's current facts and target, keep open until the next run creates the dedicated D015 remediation, then close. |
| #63 | manual verification | Keep open for final-candidate performance and peak-memory measurement. |
| #64 | manual verification | Keep open for final-wheel macOS GUI lifecycle verification. |
| #65 | audit close-out | Keep open for post-remediation wheel/sdist, CI, release, and rollback evidence. |
| #66 | audit close-out | Keep open until every preceding audit, remediation, and manual verification is accepted. |
| #71 | implementation required | Keep open; make wheel reinstall/version checks independent of the current version and complete the release procedure. |
| #72 | implementation required | Keep open; make rollback to both exact pinned legacy commits reproducible. |
| #76 | implementation required | Keep open but rescope: both products accept `.xls` through the shared reader; document CLI/file validation as the supported path and direct Python calls as best effort. |
| #77 | accepted convergence / no code change | Close after merge; exact Python keyword, introspection, and pickle behavior are outside the supported surface. Do not merge `codex/issue-77-public-keyword`. |
| #78 | implementation required | Keep open; enforce the architecture graph and remove or justify the unused production dependency. |
| #79 | accepted convergence / no code change | Close after merge; normal launcher-driven GUI operation remains supported, but direct legacy GUI methods are not frozen Python API. |
| #80 | accepted convergence / no code change | Close after merge; retain legacy environment names as aliases while using common validation, exception categories, and timing. |
| #89 | accepted convergence / no code change | Close after merge; both frontends may re-export the same shared mesh result classes. |
| #90 | accepted convergence / no code change | Close after merge; both frontends may re-export the same shared validation and exception classes. |
| #93 | implementation required | Keep open; normalize ragged common-contract inputs to the shared contract error taxonomy without exact cause/message compatibility. |
| #94 | implementation required | Keep open; reject overflowed derived Sentman speed ratio at its field boundary. |
| #95 | implementation required | Keep open; enforce finite angles and overflow-safe vector normalization in `ResolvedAttitude`. |
| #96 | implementation required | Keep open but rescope: reject invalid Sentman helper normalization inputs instead of restoring a shielded early return that bypasses validation. |
| #97 | accepted convergence / no code change | Record the owner decision and close after ADR 0008 merges. Semantic atmosphere values are retained without freezing storage dtype; common shape/finite/bool validation governs transforms and attitudes. |
| #99 | implementation required | Keep open; normalize ragged shielding inputs to the shared shielding error boundary without exact cause/message compatibility. |
| #100 | implementation required | Keep open but compare common accept/reject and field attribution, not product-specific exact message/order for invalid values. |

## Next-run order

1. Create a dedicated D015 remediation Issue and implement common
   `FORWARD / YIELD_COMPLETED` in an independent PR.
2. Implement #93, then #99; continue with #94, #95, #96, and #100.
3. Implement #76, #78, #71, and #72 from the latest accepted main in that order.
4. Close the accepted-convergence Issues and audit-only parents when their
   conditions above are met.
5. Run #63, #65, and #64 on the final candidate, then publish #66. Any finding
   that changes the candidate repeats the affected final-candidate gates.

The D015 remediation must prove serial and parallel successful results are
unchanged; a same-chunk success/success/failure sequence retains the first two
cases; logs and warnings are forwarded; progress, checkpoints, and summary CSV
contain those successes in input order; the remote failure remains visible; and
cancellation, startup failure, unexpected exit, cleanup, VTP/NPZ, signatures,
caches, formulas, and numerical goldens are unchanged.
