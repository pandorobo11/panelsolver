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
geometry, continue with [Case files](guides/preparing-cases.md).

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

## How this documentation is organized

### Getting started

[Installation](getting-started/installation.md) and the
[Quickstart](getting-started/quickstart.md) take you from installing Panel Solver
to running a supplied example and reading its first results.

### Guides

Task-based instructions for everyday use:

- [Preparing cases](guides/preparing-cases.md): set up a case table and STL
  geometry for your own vehicle.
- [Using the GUI](guides/gui.md) and
  [viewing results in the GUI](guides/gui-viewer.md).
- [Using the CLI](guides/cli.md) for scripted or batch runs.
- [Sectional loads and Cp](guides/sectional.md): load and pressure
  distributions along an axis.
- [Batch runs and recovery](guides/batch-runs.md): workers, checkpoints,
  cancellation, and what remains after a failure.
- [Troubleshooting](guides/troubleshooting.md) for common problems.

### Reference

Look up exact columns, fields, and options:

- Case tables: [FMF](reference/fmf-case-table.md),
  [Hypersonic](reference/hypersonic-case-table.md), and
  [sectional definitions](reference/sectional-definitions.md).
- Results: [Summary CSV](reference/summary-csv.md), [VTP](reference/vtp.md),
  [sectional load CSV](reference/sectional-loads-csv.md), and
  [sectional Cp CSV](reference/sectional-cp-csv.md).
- [Python API](reference/python-api.md) and
  [environment variables](reference/environment-variables.md).

### Methods

The definitions and equations behind the results:
[coordinate and attitude conventions](methods/coordinate-and-attitude-conventions.md),
[load and coefficient conventions](methods/load-and-coefficient-conventions.md),
the [FMF / Sentman model](methods/fmf.md), the
[Hypersonic pressure methods](methods/hypersonic.md), and
[ray shielding](methods/ray-shielding.md).

### About

The [compatibility and versioning policy](about/compatibility.md) lists what is
supported between releases. Data sources and licenses are in
[US1976 data provenance](about/us1976-data-provenance.md) and
[License and third-party notices](about/license-and-third-party-notices.md).
