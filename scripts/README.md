# Scripts

Repository maintenance and reproducible fixture-generation scripts belong here.
Scripts must not become an alternate implementation of production logic.

`check.py` is the canonical cross-platform local validation runner:

```bash
python scripts/check.py --quick  # development feedback
python scripts/check.py          # push / pull-request gate
python scripts/check.py --full   # deep packaging and process validation
```

It resolves the repository root from its own path, performs one locked dependency
sync, runs explicit argument-list commands without a shell, fails fast, and
reports step and total elapsed times. Quick runs Ruff format/lint, the exact
six-file mypy boundary, and fast pytest. Standard substitutes full pytest and
adds generated US1976/plot checks, strict docs, and the distribution build. Full
adds scheduler lifecycle stress, existing distribution verification, and the
existing installed-wheel smoke from a temporary clean virtual environment.

`check.sh` is a POSIX convenience wrapper with no validation logic; it forwards
all arguments to `check.py`. Windows users invoke the Python runner directly.
Multi-OS matrices, protected-main/tag/GitHub state, legacy rollback, and release
artifact publication remain CI/release-only checks.

`generate_phase1_goldens.py` archives and runs the pinned read-only legacy
sources, then captures historical artifact meaning into reviewable JSON. Use `--check` for
a non-mutating clean regeneration. `compare_phase1_goldens.py` compares two
already generated capture trees with the manifest's case/quantity tolerances.

`generate_us1976_sentman_table.py` uses the pinned, development-only PDAS
`bigtables.py` calculation snapshot to regenerate the single package-internal
Sentman atmosphere table. Its `--check` mode prevents manual generated-data
drift without network access.

`generate_docs_angle_response_plots.py` produces the committed SVG figures
directly from Panel Solver model output. The script and generated figures are
project material distributed under Apache-2.0.
