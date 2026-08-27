# Contributing

This project prioritizes numerical correctness and compatibility over code
deduplication. Before starting, read `AGENTS.md`,
[Developer documentation](devdocs/README.md),
[Development setup and testing](devdocs/development/setup-and-testing.md), the
relevant [ADRs](devdocs/adr/README.md), and the current issue or task.

## Change scope

- Keep one independently reviewable concern per branch/worktree and pull request.
- Do not combine physical-equation changes with structural refactoring.
- Do not silently resolve a supported numerical or file-contract conflict.
- Keep changes minimal and avoid unrelated renames or formatting.
- Do not push directly to or merge `main` as part of an implementation task.

## Required checks

```bash
uv sync --locked --extra rayaccel --group docs
uv run --no-sync pytest
uv run --no-sync ruff format --check src tests scripts hatch_build.py
uv run --no-sync ruff check src tests scripts hatch_build.py
uv build
```

Most existing tests remain written with `unittest`; pytest is the standard test
runner for the repository.

During development, `uv run --no-sync pytest -m "not slow"` provides fast
feedback by excluding real process/subprocess and other high-wall-time
integration tests. The unfiltered pytest suite remains authoritative; run it
before pushing or opening a pull request. CI also runs the full suite.

Installed-interface changes also require a built-wheel smoke test. Changes to a
physical model, shielding, geometry, integration, caching, or signatures require
the applicable golden regression suite and a report of observed numeric
differences.

## Pull request description

Include:

1. issue and scope;
2. design choices and relevant ADRs;
3. commands run and results;
4. numerical deltas and tolerances, or an explicit statement that no numerical
   code changed;
5. compatibility impact;
6. remaining risks and follow-up work.

Golden data must identify the pinned legacy repository and commit that generated
it. Updating expected values merely to make tests pass is prohibited. The
current workflow is in
[Development setup and testing](devdocs/development/setup-and-testing.md).

## Contribution license

Unless you explicitly state otherwise, contributions intentionally submitted
for inclusion in Panel Solver are provided under the project's
[Apache License 2.0](LICENSE), consistent with section 5 of that license. This
project does not require a Contributor License Agreement.
