# Changelog

This file is the source of truth for `panelsolver` release notes. Legacy
migration baselines and runtime artifact version semantics are recorded in ADR
0007 and ADR 0012.

## [Unreleased]

- **Breaking:** Remove the six predecessor-product commands, their two Python
  package trees, compatibility-only tuning-variable aliases, and legacy VTP
  signature reconstruction/fallback before the first Panel Solver release.
  The only console scripts are now `panelsolver` and `panelsolver-gui`, the wheel
  contains only the `panelsolver` package, and automatic VTP loading requires the
  current case ID plus current canonical signature. Generic manual **Open VTP**
  inspection remains available; historical artifacts are unsupported and can be
  regenerated. Numerical results, canonical signature digests, current case-file
  schemas, and current CSV/VTP schemas are unchanged.
- Make manual VTP opening available from both the File menu and the existing
  Viewer control.
- Reduce case-table input latency by deduplicating repeated STL and output path
  resolution within each read, without changing validation or normalized paths.
- **Breaking:** Replace the Hypersonic VTP cell scalar `Cp_n` with `cp`, and
  replace the FMF `Cp_n` scalar with `normal_traction_coeff` and
  `tangential_traction_coeff`, without a compatibility alias. The FMF
  tangential direction is the in-plane projection of the uniform-flow vector.
  Existing VTP files must be regenerated when the new scalars are required.
  `traction_coeff_stl`, pressure and Sentman equations, case-input semantics,
  model algorithm versions, case signatures, and whole-vehicle force and
  moment coefficients are unchanged.
- Restore the offline documentation to the audited MkDocs 1.6.1 built-in
  Read the Docs theme, improving technical tables, navigation, and code
  readability. Add complete license texts and release-gate coverage for the
  newly bundled theme assets; numerical behavior and public APIs are unchanged.
- Allow PySide6 6.9.3 through the Qt 6 series and require PyVistaQt 0.12 or
  newer, removing the obsolete cross-platform PySide6 6.9.3 exact pin.
- Improve GUI file workflows by remembering the last successfully opened input
  directory for the current GUI session, resolving relative Summary CSV, VTP,
  image, and `out_dir` paths from the input table's directory, and adding
  domain-specific `File > New from Example` workspaces copied with packaged
  geometry to a user-selected writable directory before opening.
- Improve batch CLI presentation with Rich, including progress display and
  `--verbose`, `--plain`, and `--debug`, while preserving plain-text output for
  non-interactive use.
- **Breaking:** Rename the CLI checkpoint option from
  `--flush-every-cases` to `--checkpoint-every-cases`, with no compatibility or
  deprecated alias. Unify the CLI, GUI, and runtime API name as
  `checkpoint_every_cases`, change the default from 100 to 2000 cases, expose
  the interval in the GUI, and allow `0` to disable intermediate checkpoints.
- **Breaking:** Remove `PANELSOLVER_SHIELD_CACHE_MAX` and the legacy
  `FMFSOLVER_SHIELD_CACHE_MAX` / `NEWTSOLVER_SHIELD_CACHE_MAX` fallbacks, plus
  `ShieldingConfig.cache_max` and `ResolvedShieldingConfig.cache_max`. Mask,
  mesh, and intersector caches are now fixed internally at one entry;
  `SHIELD_BATCH_SIZE` and `PARALLEL_CHUNK_CASES` remain advanced tuning options.
- Preserve numerical results, algorithm versions, the signature schema, and
  case signatures across these runtime-tuning changes.
- Exact-pin and fail closed on the audited MkDocs and LaTeX-to-MathML versions
  used to generate offline release documentation.
- Harden the first-release gates by accepting only the latest exact-commit
  `main` push CI run, bundling audited offline-documentation asset licenses,
  making US1976 regeneration executable from the sdist, and granting release
  validation only its required GitHub API read permissions.
- Add the first-release foundation: strict offline documentation bundled in the
  wheel, shared GUI Help/About, deterministic documentation and examples ZIPs,
  manifest schema v2, and build-once release verification.
- Unify the canonical repository, distribution, package, and command namespace
  as `panelsolver`; the human-readable product name is Panel Solver.
- Adopt the Apache License 2.0 for project-owned code, documentation, examples,
  and generated material; record author, maintainer, project URLs, PEP 639
  license metadata, and US1976/PDAS/dependency rights boundaries.
- Change Summary CSV and VTP `solver_version` provenance to the installed
  `panelsolver` distribution version for both FMF and Hypersonic; numerical
  results and case signatures are unchanged.
- Add canonical `panelsolver fmf` and `panelsolver hypersonic` batch selectors
  plus `panelsolver-gui fmf` and `panelsolver-gui hypersonic`. Add the small
  domain-specific `FMFCase`/`HypersonicCase` in-memory solve API at the package
  root; it writes no artifacts. Stable API case IDs now share portable NFC
  validation with case tables, and attitude resolution rejects non-text
  selectors and beta-sin alpha values outside the open principal interval.
- **Breaking:** Remove legacy Excel 97–2003 BIFF `.xls` input support and the
  `xlrd` runtime dependency. Convert `.xls` case files to `.xlsx` or CSV before
  using the current release. CSV, XLSX, and XLSM behavior is unchanged, and
  solver numerical results are unaffected.
- **Breaking:** Remove NPZ output, the `save_npz_on` case field, the Summary CSV
  `npz_path` column, and both compatibility frontends' `export_npz` API. Old
  case files must delete the `save_npz_on` column. Existing NPZ files are not
  automatically deleted; use VTP for visualization and panel data, and Summary
  CSV for aggregate results.
- Correct the optional ray-acceleration install hint to use the shared
  `panelsolver[rayaccel]` distribution extra.
- Reject portable summary and planned-artifact path collisions after Unicode NFC
  normalization and casefolding, including existing symlink and hardlink aliases.
- Completed Phase 8 supported-domain compatibility remediation, final-candidate
  audit, release/rollback hardening, and durable acceptance reporting.
