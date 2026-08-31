# Compatibility policy

The current supported product surface consists of:

- canonical batch commands `panelsolver fmf` and
  `panelsolver hypersonic`;
- canonical GUI commands `panelsolver-gui fmf` and
  `panelsolver-gui hypersonic`;
- normal launcher-driven GUI operation;
- the stable package-root API described in [Python API support](python-api.md);
- documented CSV, XLSX, and XLSM case files and their domain schemas/defaults;
- documented Summary CSV and VTP semantics;
- documented numerical values, signs, frames, normalizations, and
  model-specific behavior.

Other package or command identities are not distributed. Invalid-input quirks,
exact exceptions and tracebacks, object identity, pickle globals, cache
internals, and other private implementation details are not compatibility
contracts.

The canonical `fmf` token selects the free-molecular-flow domain and its Sentman
model. `hypersonic` selects the hypersonic panel-method domain and its
Newtonian-family methods.

## Distribution and artifact version

Panel Solver is distributed as `panelsolver`. Summary CSV and VTP
`solver_version` fields record the installed `panelsolver` distribution version
that generated them. Both domains therefore record the same installed version
when artifacts are produced by the same release.

Automatic VTP loading requires both the current case ID and current canonical
case signature. Artifacts produced by predecessor products are unsupported and
should be regenerated with Panel Solver. **Open VTP...** remains a generic
manual inspection path when an artifact satisfies the current viewer's data
requirements, but that does not establish a historical compatibility contract.
