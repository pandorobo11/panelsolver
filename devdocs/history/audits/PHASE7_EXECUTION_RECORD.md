# Phase 7 execution record

Historical record — non-normative. This page records the repository state at the migration phase or audit named below. Statements such as “current”, supported commands, package names, file formats, and future work apply to that recorded point in time. Use docs/, devdocs/architecture/, and accepted or superseding ADRs for the present contract.

## Starting point and scope

Phase 7 started from Phase 6-complete `origin/main` commit
`a8266681f0405328a3fbf079ccca9ba6287571c5`. AGENTS.md, DEVELOPMENT,
MIGRATION_PLAN, ARCHITECTURE, COMPATIBILITY, NUMERICAL_CONVENTIONS, the Phase 6
execution record, related ADRs, and both pinned legacy implementations were read
before editing. The references matched `../migration/MIGRATION_SOURCES.md` and remained
read-only and clean:

- FMF: `b62bc844d02a8f5212e62a53dea3238a1414317d`;
- newtsolver: `dc1357d0d50bbedfdc8b3429cab37e6b98b56c70`.

Phase 7 was split in dependency order. Every slice used one Issue, one new
worktree from the latest accepted `origin/main`, and one draft PR. Each draft was
made ready and squash-merged only after local full tests, Ruff, build, and both
push- and PR-event Ubuntu/Windows/macOS/artifact CI succeeded.

| Slice | Issue / PR | Main merge | Local full suite |
|---|---|---|---:|
| distribution/version decision | #47 / [#53](https://github.com/pandorobo11/panel-solvers/pull/53) | `1da7375` | 175 |
| case I/O and signatures | #48 / [#54](https://github.com/pandorobo11/panel-solvers/pull/54) | `8aec1c0` | 175 |
| runtime, serializers, GUI adapters | #49 / [#55](https://github.com/pandorobo11/panel-solvers/pull/55) | `78c6c36` | 183 |
| six commands and installed samples | #50 / [#56](https://github.com/pandorobo11/panel-solvers/pull/56) | `b474507` | 196 |
| frozen Python surfaces | #51 / [#57](https://github.com/pandorobo11/panel-solvers/pull/57) | `57a4cfb` | 202 |
| docs and final acceptance | #52 / [#58](https://github.com/pandorobo11/panel-solvers/pull/58) | linked PR records final merge | 202 source + 202 installed wheel |

All recorded Ubuntu, Windows, macOS, and artifact jobs for PRs #53–#57 ended in
`SUCCESS`. PR #56's PR-event macOS job was rerun after an infrastructure stall
while the exact push-event job had already passed; the rerun passed. No test or
expected result was changed to obtain a green job.

## Numerical and compatibility evidence

- All 15 Phase 1 cases continue through the common engine and compare against
  the original CSV/VTP/NPZ semantic goldens with the original tolerance
  profiles.
- No golden, tolerance, physical formula, sign, axis, frame, normalization,
  shielding mask, case signature schema, CSV column, or artifact field was
  updated.
- The clean installed wheel imports the frozen 22 FMF and 29 newtsolver module
  paths, retains exact product roots/versions and D025 exports, registers all six
  entry points, compares both help texts exactly, and runs both unchanged sample
  tables from outside the checkout.
- Direct public numerical anchors remain product-specific; for the pinned flat
  plate checks FMF `CA=2.3944907701811076` and newtsolver `CA=2.0`.
- Selected pinned-legacy suites for Sentman, mesh/cache, hypersonic panel core,
  direct solver shapes/signatures, serializers, and atmosphere helpers passed.
  Obsolete tests that patch replaced private implementation points were not
  treated as public failures.
- This Phase 7 record originally and incorrectly stated that Issue #52 had fixed
  the failed-chunk pairing to FMF `FORWARD`/`YIELD_COMPLETED` and newtsolver
  `DROP`/`DISCARD_CHUNK`. Phase 8's independent audit re-read the pinned worker
  envelopes and forced two cases into one good-then-failing chunk. Issue #75
  corrects both code and documentation to the actual legacy contracts: FMF
  `FORWARD`/`DISCARD_CHUNK`, newtsolver `DROP`/`YIELD_COMPLETED`. Successful
  case numerical values and all-success runs are unchanged; failed-run result,
  progress, and checkpoint visibility now match the pinned policies. Ordering
  rules, cancellation, signatures, and cache identity are unchanged.

ADR 0008 later classified that failed-chunk difference as transitional rather
than a permanent compatibility requirement and adopted common
`FORWARD`/`YIELD_COMPLETED` as the next specification. This execution record
continues to describe the code and evidence at each historical point.

## Manual macOS GUI smoke

Date: 2026-08-12, correct logged-in macOS user session, built from main
`57a4cfb`. Computer Use initially returned `cgWindowNotFound` during screen
acquisition, so no pass was inferred. After the service recovered, both apps
were recognized and fully operated; no manual item remained unverified.

FMF:

- recognized `Sentman FMF Solver (GUI)` and the shared cases/viewer controls;
- loaded all 6 unchanged FMF sample rows with FMF schema and STL display names;
- selected and ran `fmf_zero_plate` through the real adapter, observed `1/1`,
  wrote result CSV/NPZ/VTP, and automatically loaded the signature-matching VTP;
- confirmed initial `Cp_n`, changed to `shielded`, applied `+X`, exported and
  opened `phase7-fmf.png`, and verified overlay, geometry, axes, and colorbar;
- closed normally; the product-specific active-run defer/cancel path remains
  covered by native QThread GUI tests.

newtsolver:

- recognized `newtsolver (GUI)` and the shared cases/viewer controls;
- loaded all 9 unchanged newtsolver sample rows with its independent schema;
- selected and ran `newt_zero_newtonian`, observed `1/1`, wrote result
  CSV/NPZ/VTP, and automatically loaded the signature-matching VTP;
- confirmed initial `Cp_n`, changed to `shielded`, applied `+X`, exported and
  opened `phase7-newtsolver.png`, and verified its product overlay, geometry,
  axes, and colorbar;
- closed normally; the distinct active-run close policy remains covered by
  native QThread GUI tests.

## Final gate and remaining boundary

The Issue #52 candidate repeated `uv sync --locked --extra rayaccel`, all 202
tests, Ruff, build, clean built-wheel reinstall/import/sample smoke outside the
checkout, and all 202 tests again against the installed wheel. PR #58's Ubuntu,
Windows, macOS, and artifact check rollup is the authoritative CI record; it must
be completely successful before merge.

Remaining risks are the subjects of Phase 8: an independent numerical and
architecture audit, performance/memory comparison, and broader lifecycle audit.
At the Phase 7 handoff Phase 8 had not started. It is now in progress under ADR
0008; no legacy repository has been archived and no release tag was created.
