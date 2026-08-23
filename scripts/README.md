# Scripts

Repository maintenance and reproducible fixture-generation scripts belong here.
Scripts must not become an alternate implementation of production logic.

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
