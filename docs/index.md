# Panel Solver documentation

`panelsolver` provides a shared geometry, execution, shielding, integration,
output, CLI, and GUI platform for two independent panel-load models. Start with
[installation](getting-started/installation.md), then run the
[quickstart](getting-started/quickstart.md).

## Choosing a solver

| Question | FMF | Hypersonic |
|---|---|---|
| Flow regime | Free molecular / rarefied | Hypersonic pressure approximation |
| Model input | `S` + `Ti_K`, or `Mach` + `Altitude_km`; always `Tw_K` | `Mach`, `gamma`, and surface equations |
| Panel load | Sentman normal and tangential traction | Pressure-only normal traction |
| Equation selection | Sentman Mode A or Mode B | Per-component windward/leeward equations |
| Read next | [FMF](solvers/fmf.md) | [Hypersonic](solvers/hypersonic.md) |

These are engineering panel methods, not general-purpose CFD. Confirm that the
assumptions documented on the solver page match the intended flow regime and
geometry before interpreting coefficients.

## Choose a path by task

### Understand the method

Use **Methods and conventions** for the definitions that govern both domains:
[coordinate and attitude](reference/coordinate-and-attitude-conventions.md),
[panel loads and coefficients](reference/load-and-coefficient-conventions.md),
and [ray shielding](reference/ray-shielding.md). Then read the
[FMF / Sentman model](solvers/fmf.md) or
[Hypersonic pressure methods](solvers/hypersonic.md) for domain-specific
equations, assumptions, and limits.

### Prepare inputs

Start with [Case tables and geometry](user-guide/case-files.md) for file,
path, component, attitude-input, and common validation rules. Continue with the
[FMF input reference](reference/fmf-input.md) or
[Hypersonic input reference](reference/hypersonic-input.md) for the selected
domain's accepted columns, defaults, and validation.

### Run calculations

Choose the [GUI](user-guide/gui.md), [CLI](user-guide/cli.md), or stable
[Python API](reference/python-api.md) workflow. For multiple cases, workers,
checkpoints, cancellation, or partial failures, use
[Batch execution and recovery](user-guide/batch-execution-and-recovery.md).

### Interpret results

Use the [Summary CSV reference](results/summary-csv.md) for integrated total
and component rows, and the [VTP reference](results/vtp.md) for mesh,
per-panel, and provenance data. Those result pages link back to the canonical
method and convention definitions when a field requires its equation, frame,
sign, or normalization.

### Diagnose a problem or check support

Start with [Troubleshooting](user-guide/troubleshooting.md) for operational
problems. Use **Product reference** for
[environment variables](reference/environment-variables.md) and the
[compatibility and versioning policy](reference/compatibility.md), including
the supported commands, files, artifacts, and Python surface.
