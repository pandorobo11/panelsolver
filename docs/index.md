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
geometry, continue with [Case files](inputs/case-files.md).

## Choosing a solver

| Choice | FMF | Hypersonic |
|---|---|---|
| Physical applicability | Free-molecular flow, where intermolecular collisions near the body can be neglected | Hypersonic flow suited to a local, inviscid pressure approximation |
| Surface/model assumptions | Sentman with complete diffuse reflection and complete thermal accommodation | Newtonian-family pressure methods; constant specific-heat ratio, no viscous shear or heat transfer |
| Model input | `S` + `Ti_K`, or `Mach` + `Altitude_km`; always `Tw_K` | `Mach`, `gamma`, and surface equations |
| Panel load | Sentman normal and tangential traction | Pressure-only normal traction |
| Input/method choices | Two ways to specify the same Sentman model: Mode A or atmosphere-derived Mode B | Per-component windward/leeward equations |
| Read next | [FMF](methods/fmf.md) | [Hypersonic](methods/hypersonic.md) |

Choose a model whose assumptions match your flow regime and geometry. Each
solver page explains its equations and applicability.

## Choose a path by task

### Understand the method

Use **Methods and conventions** for the definitions that govern both domains:
[coordinate and attitude](methods/coordinate-and-attitude-conventions.md),
[panel loads and coefficients](methods/load-and-coefficient-conventions.md),
and [ray shielding](methods/ray-shielding.md). Then read the
[FMF / Sentman model](methods/fmf.md) or
[Hypersonic pressure methods](methods/hypersonic.md) for domain-specific
equations, assumptions, and limits.

### Prepare inputs

Start with [Case tables and geometry](inputs/case-files.md) for file,
path, component, attitude-input, and common validation rules. Continue with the
[FMF input reference](inputs/fmf-input.md) or
[Hypersonic input reference](inputs/hypersonic-input.md) for the selected
domain's accepted columns, defaults, and validation.

### Run calculations

Choose the [GUI](running/gui.md), [CLI](running/cli.md), or stable
[Python API](running/python-api.md) workflow. For multiple cases, workers,
checkpoints, cancellation, or partial failures, use
[Batch execution and recovery](running/batch-execution-and-recovery.md).

### Interpret results

Use the [Summary CSV reference](results/summary-csv.md) for integrated total
and component rows, and the [VTP reference](results/vtp.md) for mesh,
per-panel, and provenance data.

### Diagnose a problem or check support

Start with [Troubleshooting](running/troubleshooting.md) for operational
problems. Use **Product reference** for
[environment variables](product-reference/environment-variables.md) and the
[compatibility and versioning policy](product-reference/compatibility.md), including
the supported commands, files, artifacts, and Python surface.
