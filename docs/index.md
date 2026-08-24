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

## User guides

- [GUI](user-guide/gui.md)
- [CLI](user-guide/cli.md)
- [Case files, attitude, and STL components](user-guide/case-files.md)
- [Outputs](user-guide/outputs.md)
- [Shielding and parallel execution](user-guide/shielding-and-parallel.md)
- [Troubleshooting](user-guide/troubleshooting.md)

## Reference

- [FMF input columns](reference/fmf-input.md)
- [Hypersonic input columns](reference/hypersonic-input.md)
- [Output formats](reference/output-formats.md)
- [Environment variables](reference/environment-variables.md)
- [Numerical conventions](reference/numerical-conventions.md)
- [Compatibility policy](reference/compatibility.md)
- [Python API policy](reference/python-api.md)
- [License and third-party notices](reference/license-and-third-party-notices.md)
