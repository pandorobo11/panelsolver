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

## Standard quality gates

```bash
uv run --no-sync python -m unittest discover -s tests -p "test_*.py" -v
uv run --no-sync ruff format --check src tests scripts hatch_build.py
uv run --no-sync ruff check src tests scripts hatch_build.py
uv build
```

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
