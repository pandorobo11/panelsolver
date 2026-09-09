# CI performance measurements

## Decision

Retain the independent scheduler matrix (option 1) and the revised option 2:
GUI tests serial, all other tests on two file-scoped workers. Keep the
installed-wheel smoke serial. The selected combination completed both controlled
CI attempts in 186-191 seconds versus 229 seconds for the successful baseline,
an observed reduction of 38-43 seconds (17-19%). This is a small-sample result,
not a guaranteed speedup.

The retained change moves the existing ten-iteration scheduler probe to three
independent OS runners and adds it to the required `artifact` gate. Probe
deadlines, all existing test cases, OS coverage, Embree verification, golden
tolerances, packaging checks, and installed-command checks are unchanged. The
local standard runner still runs the unfiltered serial suite. Only the CI
invocation is split into two complementary selections.

## Method

Measurements were collected on GitHub-hosted Ubuntu, Windows, and macOS runners
with Python 3.12. Each reported elapsed time runs from the first non-skipped
job start to the last non-skipped job completion. It includes downstream
scheduling and artifact-transfer waits but excludes the initial workflow queue.
This avoids counting time between rerun attempts in GitHub's original
`createdAt`. Runner seconds are the sum of job elapsed times, not CPU time or
billed cost.

Initial screening used base `9505800`. During the experiment, main advanced to
`ac720271e9f867ce8706d54eeff95770b944c741` (PR #291), adding the approved face-normal
change and two tests. The hybrid option-2 runs already used that base. The PR
was temporarily retargeted to a frozen branch at `ac720271` for subsequent
measurements, and the baseline and option 1 were measured again on that same
source. Screening and controlled results are kept separate in the
[measurement data](ci-performance.json).

Final integration validation also includes main's later presentation update
`83d4b8f` (PR #293). It is not included in the controlled timing sample.

These are small samples from shared hosted infrastructure, not a statistical
guarantee. Do not attribute every difference in total duration to the code
change: pytest and runner setup times also varied. Failed or interrupted suites
are not counted as successful speedups.

## Controlled CI results

| Configuration | Successful CI seconds | Successful runner seconds | Successes / attempts |
| --- | --- | --- | --- |
| [Unchanged CI](https://github.com/pandorobo11/panelsolver/actions/runs/34352066173/attempts/2) | 229 | 1044 | 1 / 2 |
| [1: independent scheduler](https://github.com/pandorobo11/panelsolver/actions/runs/34352996912/attempts/2) | — | — | 0 / 2 |
| [1 + 2: GUI serial, non-GUI parallel](https://github.com/pandorobo11/panelsolver/actions/runs/34350294905/attempts/2) | 186, 191 | 1047, 1050 | 2 / 2 |
| [1 + 2 + 3: bounded smoke concurrency](https://github.com/pandorobo11/panelsolver/actions/runs/34351289607/attempts/2) | 190, 193 | 1053, 1057 | 2 / 2 |

Excluded failed controlled attempts took 234 seconds for the baseline and
197/210 seconds for option 1. Both option-1 macOS pytest steps crashed after
33 seconds. Their shorter incomplete durations are not evidence of a successful
whole-workflow speedup.

## Effect versus implementation cost

| Option | Incremental implementation | Assessment |
| --- | --- | --- |
| 1: independent scheduler | 2 files, +42/-5 lines; 3 runner jobs; no dependency | Retain. Removes the serial probe wait and preserves the required failure gate. Extra runner setup increases aggregate runner time. |
| 2: GUI serial, other tests on two workers | 4 files, +39/-2 lines including lockfile; pytest-xdist and execnet are development-only | Retain the conservative split. It completed both controlled attempts; option 1 alone did not complete either controlled macOS suite. The incremental end-to-end speed benefit is uncertain, but the split substantially reduces Windows test time without omitting tests. |
| 3: bounded smoke concurrency | 3 files, +171/-34 lines including five test cases; standard-library executor | Reject for now. Windows and Linux improved, macOS did not, and complete CI did not improve. |

Documentation and captured measurement data are excluded from those change
counts. No production dependency or change to numerical behavior is introduced.
Option 1 alone had the smallest implementation, but its two controlled attempts
reproduced the existing native GUI crash. The revised option 2 completed both
attempts and is the selected working configuration. This observation does not
establish that changing test process boundaries fixes the underlying GUI defect.

## Option 2: complete coverage and GUI ordering

The first experiment ran the complete suite with
`pytest -n 2 --dist loadfile --max-worker-restart=0`. Windows and macOS completed,
but Linux crashed in `GuiBootstrapTests.test_run_gui_sets_icon_when_reusing_existing_application`.
Only 357 tests passed before termination; its short duration is not a speedup.
See the [failed run](https://github.com/pandorobo11/panelsolver/actions/runs/34349663801).

The revised experiment preserved GUI order with `pytest tests/gui` and ran
`pytest --ignore=tests/gui -n 2 --dist loadfile --max-worker-restart=0` for the
remainder. Both CI attempts completed on all three OSes. Local JUnit test IDs
were checked against full collection: 153 GUI plus 414 non-GUI IDs equalled all
567 collected IDs, with no omission or duplication. That local checkout also
contained the five experimental smoke tests and preceded PR #291; the hosted
hybrid runs collected 564 IDs per OS, with the existing non-macOS skip retained.

Local screening measured full serial pytest at 59.13 seconds and unrestricted
two-worker pytest at 36.66 seconds, both completing 562 tests. This improvement
did not justify ignoring the subsequently observed Linux GUI worker crash.

## Option 3: command isolation and cache reuse

The experiment parallelized six help commands and eight release-example
commands, bounded at two concurrent children. GUI construction and dependent
CSV/VTP validations remained serial. Each example used a private copy of the
archive, preserving its relative paths; worker caches could be reused without
concurrent writers. Nonzero exit results and worker exceptions remained fatal.

A fresh installed-wheel environment with locked dependencies was used for local
comparisons outside the checkout. Baseline and candidate order was reversed
between batches. Audit wrappers verified the same 30 Panel Solver commands and
three OS/font-discovery commands in every run; command fingerprints are saved
in the measurement data. All existing semantic checks passed.

| Local smoke experiment | Baseline seconds | Parallel seconds |
| --- | --- | --- |
| Initial, fully isolated command caches | 75.919, 33.851 | 46.566, 45.927 |
| Warm, reverse-order repeat | 33.660, 33.691 | 46.174, 46.055 |
| Reuse isolated caches per worker | 33.411, 33.658 | 37.560, 38.035 |

The first cold baseline would have overstated the improvement. Reusing caches
per worker reduced the prototype's overhead, but it was still about 13% slower
than the warm baseline locally. In controlled CI, the revised candidate reduced
Windows wheel smoke from 75-80 to 62-67 seconds, but macOS went from 76 to 80-86
seconds. Workflow duration stayed at 190-193 seconds versus 186-191 without it.

## Validation and limitations

The [final integration run](https://github.com/pandorobo11/panelsolver/actions/runs/34354439120)
on the later `83d4b8f` main source passed every test, scheduler, and artifact job,
but took 281 seconds. Its clean-install step took 147 seconds: uv reported
106 seconds preparing downloaded dependencies, dominated by VTK, despite a
setup-uv cache hit. The clean-install gate intentionally installs wheel runtime
dependencies into an empty environment; it can resolve newer versions than the
development lock. The remaining installed-smoke execution took about 40 seconds.
This integration run is retained separately in the data and is not hidden by
the faster controlled samples. Network/download variability can outweigh the
pytest improvement. A separate follow-up could investigate download-cache
reuse while preserving the empty-environment installation check.

The retained option passed the standard local runner: locked dependency sync,
formatting, lint, scoped typing, the complete pytest suite, generated-source and
plot checks, strict documentation, and distribution builds. The experimental
smoke also passed full local packaging/installed-wheel validation and explicit
parallel smoke runs. New gate tests execute the real gate body for failure,
cancellation, and skip results, including the new scheduler prerequisite.

Baseline and screening runs reproduced an existing macOS segmentation fault in
`RunLifecycleTests.test_vtp_output_failures_complete_once_with_bounded_summary_and_recover_ui`.
It also occurred without any optimization, including main's pre-experiment CI.
No automatic retry, new skip, timeout reduction, assertion relaxation, or GUI fix is included
in the retained change. The observed failure counts are recorded per attempt;
they are not estimates of long-run failure probability.

The final PR diff against main consists of CI orchestration, its regression
tests, development dependencies, and developer documentation/evidence. Product
code, runtime dependencies, numeric expectations, supported file/API contracts,
and installed smoke code have no final diff. Follow-up work is to resolve the
native GUI lifecycle crash separately, continue running the unfiltered local
gate, and revisit smoke concurrency only when a repeatable end-to-end benefit
is available.
