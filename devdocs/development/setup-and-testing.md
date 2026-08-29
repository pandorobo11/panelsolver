# Development setup and testing

## Set up

Python 3.12 or newer and `uv` are required for the repository workflow.

```bash
uv sync --locked --extra rayaccel --group docs
```

`uv.lock` is authoritative for local development and CI. The `rayaccel` extra
installs the platform-specific Embree binding; rtree remains a supported backend
and must stay testable.

## Documentation plots

Install the documentation-only plotting dependency, regenerate the committed
SVG plots, or verify that they are synchronized with the current models:

```bash
uv sync --locked --extra rayaccel --group docs
uv run --no-sync mkdocs build --strict
uv run --no-sync python scripts/generate_docs_angle_response_plots.py
uv run --no-sync python scripts/generate_docs_angle_response_plots.py --check
```

When ray-acceleration development dependencies are also needed, combine the
options as `uv sync --locked --extra rayaccel --group docs`.

## Change discipline

1. Read `AGENTS.md`, the current task, the architecture and compatibility pages,
   numerical conventions, and relevant ADRs.
2. Keep one independently reviewable concern per change.
3. Do not combine a physical-formula change with structural work.
4. Add focused tests, then run the standard gates.
5. Inspect the diff for unintended API, schema, artifact, or golden changes.
6. Report numerical deltas, compatibility impact, risks, and follow-up work.

The Phase 1 legacy repositories and golden captures remain read-only evidence.
Their exact source commits are in
[Migration sources](../history/migration/MIGRATION_SOURCES.md). Do not regenerate
or change expected values merely to make tests pass.

## Canonical local quality gates

```bash
python scripts/check.py --quick  # during development
python scripts/check.py          # before push or pull request
python scripts/check.py --full   # deeper local validation
```

The Python runner is canonical and resolves the repository root independently
of the caller's current directory. It works on Windows, macOS, and Linux. POSIX
users may invoke `scripts/check.sh` with the same flags; the shell script is only
a thin argument-forwarding wrapper. Every mode performs
`uv sync --locked --extra rayaccel --group docs` first, uses `--no-sync` for
subsequent `uv run` commands, reports step and total elapsed times, and stops at
the first failure.

The modes contain:

- **quick:** Ruff format check, Ruff lint, the six-file mypy boundary, and
  `pytest -m "not slow"`;
- **standard (default):** the same quality checks, the unfiltered pytest suite,
  generated US1976 and documentation-plot checks, strict MkDocs, and `uv build`;
- **full:** standard plus the scheduler lifecycle stress probe, wheel/sdist and
  isolated sdist-rebuild verification, and the installed-wheel smoke in a
  temporary clean virtual environment.

The documentation-plot check compares generated SVG bytes. The generator fixes
metadata and hash salt, renders bundled DejaVu glyphs as paths, rounds serialized
plot values, and normalizes line endings to make that comparison suitable for
the cross-platform standard gate.

Full mode does not modify the active development environment when testing the
built wheel. It creates a temporary Python 3.12 environment, installs the wheel
with its dependencies, invokes the existing installed-wheel helper outside the
checkout, and removes the temporary environment even after failure.

GitHub Actions remains responsible for the multi-OS matrix, protected-main and
release-tag state, exact legacy rollback, release archive/manifest orchestration,
artifact transfer, and GitHub Release publication. The local runner does not
attempt to reproduce those CI/release-only operations.

For targeted troubleshooting, use the individual checks directly:

```bash
uv run --no-sync pytest -m "not slow"
uv run --no-sync pytest
uv run --no-sync ruff format --check src tests scripts hatch_build.py
uv run --no-sync ruff check src tests scripts hatch_build.py
uv run --no-sync mypy src/panelsolver/core/contracts.py src/panelsolver/core/execution.py src/panelsolver/models/registry.py src/panelsolver/app/execution.py src/panelsolver/api.py src/panelsolver/__init__.py
uv run --no-sync python scripts/generate_us1976_sentman_table.py --check
uv run --no-sync python scripts/generate_docs_angle_response_plots.py --check
uv run --no-sync mkdocs build --strict
uv build
```

The mypy invocation deliberately names the initial coherent six-file typing
boundary: the shared model contract, registry-to-execution wiring, and stable
in-memory solve API. It does not check all of `panelsolver.core`, model
implementations, the GUI, or compatibility frontends, and it is not a
repository-wide typing claim.

Most existing tests remain written with `unittest`; pytest is the standard test
runner and collects that suite without requiring a test-style rewrite.

The `slow` marker identifies real process/subprocess lifecycle and other
high-wall-time integration tests. The fast suite supplements rather than
replaces the authoritative unfiltered pytest suite. Run the full suite before a
push or pull request through the standard runner; CI continues to run it on
every supported operating system.

For installed-interface or packaging changes, install the built wheel into a
clean environment and test imports, canonical `panelsolver` and subcommand help,
canonical `panelsolver-gui` dispatch and construction, plus both compatibility
CLI `--help` commands outside the checkout. For GUI
changes, add headless-safe tests where practical and record a manual smoke test.
For shielding or numerical work, run the applicable golden cases with both
supported ray paths.

## Test layout

- `tests/unit`: contracts, models, and utilities;
- `tests/regression`: semantic numerical golden comparisons;
- `tests/compatibility`: command, Python, case, and artifact compatibility;
- `tests/gui`: shared GUI/viewer behavior;
- `tests/fixtures`: compact inputs and generated expectations.

Artifact regression checks compare named semantic arrays and metadata rather
than file bytes. Per-quantity tolerances and provenance live in
[Phase 1 history](../history/migration/phase1/TOLERANCES.md).

Phase 1 fixtures and goldens and the Phase 3 adapter regressions are historical,
read-only inputs to compatibility decisions. A changed implementation must be
compared using the recorded quantity-specific tolerance profile. Do not update a
golden or tolerance merely to make a test pass; document the intended numerical
change, evidence, effect, and accepted compatibility decision first.

## Versions

`pyproject.toml` owns the single distribution version.
Summary CSV and VTP retrieve that installed `panelsolver` version from
distribution metadata for both domains. FMF `1.3.8` and newtsolver `1.0.3` are
historical migration baselines retained only for legacy signature
reconstruction. Release and rollback procedures are in
[Release and rollback](release-and-rollback.md).
