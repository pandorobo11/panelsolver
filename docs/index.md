# Panel Solver documentation

Panel Solver estimates the aerodynamic forces and moments on a vehicle whose
surface is given as a triangle mesh (STL). You describe each flight condition
as one row of a case table. For each case, Panel Solver gives you:

- force and moment coefficients for the whole vehicle and for each STL part, in
  a Summary CSV file;
- the load on every surface panel, in a VTP file that you can view in the
  Panel Solver GUI or in ParaView.

New users should start with [Installation](getting-started/installation.md) and
the [Quickstart](getting-started/quickstart.md), which runs a supplied example.
When you are ready to use your own geometry, continue with
[Preparing cases](guides/preparing-cases.md).

## Choosing a solver

Panel Solver has two flow domains. Pick the one that matches your flight
regime.

| | FMF | Hypersonic |
|---|---|---|
| Use it for | Very low-density flow, such as orbital altitudes, where gas molecules rarely collide with each other near the vehicle | High-Mach flow in a continuum gas, where a simple local pressure estimate per panel is good enough |
| Model | Sentman free-molecular flow, with molecules re-emitted diffusely at the wall temperature | Newtonian-family pressure methods that you choose per surface |
| Main inputs | Speed ratio `S` and temperature `Ti_K`, **or** `Mach` and `Altitude_km`; plus wall temperature `Tw_K` | `Mach`, `gamma`, and optional pressure methods |
| Panel load | Pressure (normal) and shear (tangential) | Pressure only |
| Not included | Specular reflection, partial accommodation | Viscosity, heat transfer, real-gas effects |
| Read more | [FMF / Sentman model](methods/fmf.md) | [Hypersonic pressure methods](methods/hypersonic.md) |

Both domains use the same case-table layout, attitude inputs, reference
quantities, and result files. Only the flow-condition columns differ.

## How this documentation is organized

### Getting started

[Installation](getting-started/installation.md) and the
[Quickstart](getting-started/quickstart.md) take you from installing Panel Solver
to running a supplied example and reading its first results.
[Examples](getting-started/examples.md) lists the other supplied examples and
what each one shows.

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
- [Glossary](reference/glossary.md) of the terms used in this documentation.

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
