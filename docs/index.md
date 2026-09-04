# Panel Solver documentation

Panel Solver estimates aerodynamic forces and moments on a triangulated STL
surface. Supply one or more STL files and a case table of flow conditions,
attitudes, and reference quantities. It calculates total and component force
and moment coefficients, plus surface load distributions for inspection in
the GUI or another VTK-capable viewer.

Choose the flow domain below, follow
[Installation](getting-started/installation.md), then use the
[Quickstart](getting-started/quickstart.md) to run a supplied plate example,
read its results, and change its attitude. When you are ready to use your own
geometry, continue with [Case files](user-guide/case-files.md).

## Choosing a solver

| Choice | FMF | Hypersonic |
|---|---|---|
| Physical applicability | Free-molecular flow, where intermolecular collisions near the body can be neglected | Hypersonic flow suited to a local, inviscid pressure approximation |
| Surface/model assumptions | Sentman with complete diffuse reflection and complete thermal accommodation | Newtonian-family pressure methods; constant specific-heat ratio, no viscous shear or heat transfer |
| Model input | `S` + `Ti_K`, or `Mach` + `Altitude_km`; always `Tw_K` | `Mach`, `gamma`, and surface equations |
| Panel load | Sentman normal and tangential traction | Pressure-only normal traction |
| Input/method choices | Two ways to specify the same Sentman model: Mode A or atmosphere-derived Mode B | Per-component windward/leeward equations |
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
per-panel, and provenance data. Those result pages link to the applicable
method and convention definitions when a field requires its equation, frame,
sign, or normalization.

### Diagnose a problem or check support

Start with [Troubleshooting](user-guide/troubleshooting.md) for operational
problems. Use **Product reference** for
[environment variables](reference/environment-variables.md) and the
[compatibility and versioning policy](reference/compatibility.md), including
the supported commands, files, artifacts, and Python surface.
