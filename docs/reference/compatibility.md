# Compatibility policy

The current supported product surface consists of:

- canonical batch commands `panelsolver fmf` and
  `panelsolver hypersonic`;
- canonical GUI commands `panelsolver-gui fmf` and
  `panelsolver-gui hypersonic`;
- all six legacy compatibility commands: `fmfsolver`, `fmfsolver-gui`,
  `fmfsolver-cli`, `newtsolver`, `newtsolver-gui`, and `newtsolver-cli`;
- normal launcher-driven GUI operation;
- the stable package-root API described in [Python API support](python-api.md);
- documented CSV, XLSX, and XLSM case files and their domain schemas/defaults;
- documented Summary CSV and VTP semantics;
- documented numerical values, signs, frames, normalizations, and
  model-specific behavior.

Python modules and attributes under `fmfsolver.*` and `newtsolver.*` are not
supported direct-Python APIs. Invalid-input quirks, exact exceptions and
tracebacks, object identity, pickle globals, cache internals, and other private
implementation details are not compatibility contracts.

The canonical `fmf` token selects the free-molecular-flow domain and its Sentman
model. `hypersonic` selects the hypersonic panel-method domain and its
Newtonian-family methods. The `fmfsolver` and `newtsolver` names identify only
legacy compatibility commands, not canonical analysis domains.

## Distribution and artifact version

Panel Solver is distributed as `panelsolver`. Summary CSV and VTP
`solver_version` fields record the installed `panelsolver` distribution version
that generated them. Both domains therefore record the same installed version
when artifacts are produced by the same release.

Do not install `panelsolver` in the same environment as the separate legacy
`fmfsolver` or `newtsolver` distributions. They provide overlapping package and
command names. Uninstall the legacy distributions before installing
`panelsolver`, as shown in [Installation](../getting-started/installation.md).

## Current shared behavior

Canonical and legacy commands use the same strict mesh and numeric validation,
portable case IDs, case-table dispatch, output-collision checks, durable Summary
CSV writes, and input-ordered result reconstruction. Physical model inputs and
equations, domain-only output fields, and visible legacy command identities
remain distinct where required by the documented product surface.
