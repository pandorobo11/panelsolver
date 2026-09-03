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
python scripts/check.py --quick  # during development
python scripts/check.py          # before push or pull request
python scripts/check.py --full   # deeper packaging/process validation
```

`scripts/check.py` is the cross-platform local validation runner. On POSIX systems,
`scripts/check.sh` forwards the same arguments. All modes perform the locked
dependency sync first and stop at the first failed step.

For targeted troubleshooting, the individual commands remain available:

```bash
uv run --no-sync pytest -m "not slow"
uv run --no-sync pytest
uv run --no-sync ruff format --check src tests scripts hatch_build.py
uv run --no-sync ruff check src tests scripts hatch_build.py
uv run --no-sync mypy src/panelsolver/core/contracts.py src/panelsolver/core/execution.py src/panelsolver/models/registry.py src/panelsolver/app/execution.py src/panelsolver/api.py src/panelsolver/__init__.py
```

The explicit mypy paths are the current six-file checked boundary: the model
contracts, typed registry/execution wiring, and stable package-root solve API.
Other modules are not claimed to be mypy-clean.

Most existing tests remain written with `unittest`; pytest is the standard test
runner for the repository.

Quick mode uses the fast suite, which excludes real process/subprocess and other
high-wall-time integration tests. Standard and full modes run only the
unfiltered authoritative suite; they do not repeat the fast suite. CI also runs
the full suite on all supported operating systems.

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
