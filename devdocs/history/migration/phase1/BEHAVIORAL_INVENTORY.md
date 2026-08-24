# Phase 1 legacy behavioral inventory

Historical record — non-normative for the current product contract. This page records the repository state at the migration phase or audit named below. Statements such as “current”, supported commands, package names, file formats, and future work apply to that recorded point in time. Pinned source identities, golden evidence, tolerance profiles, and audit results may still be referenced by current developer workflows where devdocs/ or tests explicitly do so. Use docs/, devdocs/architecture/, and accepted or superseding ADRs for the present product contract.

This inventory freezes observable surfaces of the two immutable implementations.
It is evidence for migration, not a design proposal.  Where the implementations
differ, both remain authoritative until a later compatibility decision; see
`LEGACY_DIFFERENCES.md`.

## Evidence and execution context

| Implementation | Commit | Version | Locked suite | Result |
|---|---|---:|---:|---|
| `fmfsolver` | `b62bc844d02a8f5212e62a53dea3238a1414317d` | 1.3.8 | 75 tests | pass |
| `newtsolver` | `dc1357d0d50bbedfdc8b3429cab37e6b98b56c70` | 1.0.3 | 90 tests | pass |

Both local checkouts matched `docs/history/migration/MIGRATION_SOURCES.md`, their `origin` URLs,
and clean tracked status.  Suites and fixtures ran from `git archive` copies, not
from the checkouts.  The baseline environment was Python 3.12, NumPy 2.4.1,
SciPy 1.17.0, pandas 3.0.0, trimesh 4.11.1, rtree 1.4.1, PyVista 0.46.5, and VTK
9.5.2.  The accelerated profile additionally used embreex4 4.4.0.post1.
`golden/*/contracts.json` records the executable help, module paths, dependency
versions, environment behavior, invalid-input errors, and suite counts.
CLI help is captured with a deterministic 80-column terminal width.

## Commands

| Product | GUI commands | Batch command | Entry point |
|---|---|---|---|
| FMF | `fmfsolver`, `fmfsolver-gui` | `fmfsolver-cli` | `fmfsolver.app.gui_app:main`, `fmfsolver.app.cli_app:main` |
| Hypersonic | `newtsolver`, `newtsolver-gui` | `newtsolver-cli` | `newtsolver.app.gui_app:main`, `newtsolver.app.cli_app:main` |

Both CLIs accept:

- required `-i/--input`;
- optional `-o/--output`;
- `-j/--workers`, default 1 and required to be at least 1;
- `--cases`, accepting space- and comma-separated IDs;
- `--flush-every-cases`, default 100, with 0 disabling checkpoints.

The default summary is
`<input-dir>/outputs/<input-stem>_result.csv`.  Selected cases retain input-table
order, not option order.  An unknown ID rejects the whole request.  Checkpoints
rewrite the complete successful snapshot atomically, so rows are not duplicated.
Success prints `[RUN]`, optional `[SAVE]`, then `[OK]` to stdout and exits 0.
`--help` exits 0, argument errors exit 2, and input/solver/worker exceptions are
uncaught and exit 1 with a traceback.

The exact help text is captured under each `contracts.json`.  One syntax differs:
FMF uses `--cases CASES [CASES ...]`; newtsolver uses `--cases [CASES ...]`, so a
value-less newtsolver option means all cases while FMF rejects it at parsing.
README option summaries omit `--flush-every-cases` even though both parsers expose
it.

## Python import surface

Both package roots set `__all__ = []` and document no supported top-level Python
API.  The following importable, tested, or application-used names are therefore
de facto compatibility surfaces, not an endorsement of their architecture.

Common-shaped surfaces:

- `core.solver.run_case`, `run_cases`, and imported alias
  `build_case_signature`;
- `core.mesh_utils.MeshData`, `load_meshes`, `clear_mesh_cache`,
  `mesh_cache_stats`;
- `core.shielding.compute_shield_mask`,
  `compute_shield_mask_with_backend`, `clear_shield_cache`;
- `core.parallel_scheduler.iter_case_results_parallel`,
  `resolve_parallel_chunk_cases`;
- `io.io_cases.read_cases`, `InputValidationError`, `ValidationIssue`;
- `io.csv_out.write_results_csv`, `append_results_csv`;
- `io.exporters.export_vtp`, `export_npz`;
- GUI `MainWindow`, `CasesPanel`, and `ViewerPanel` classes.

FMF-specific callable imports include:

- `core.sentman_core.resolve_attitude_to_vhat`,
  `sentman_dC_dA_vector`, `sentman_dC_dA_vectors`, `stl_to_body`, `rot_y`;
- `physics.us1976.load_us1976_tables`, `altitude_range_km`,
  `sample_at_altitude_km`, `mean_to_most_probable_speed`.

newtsolver explicitly re-exports a compatibility surface from
`core.panel_core`, including `panel_force_density`, attitude/frame helpers,
modified-Newtonian, tangent-wedge, tangent-cone, and Prandtl-Meyer functions.
`core.pressure_models` also has an explicit `__all__`.  Some underscore helpers
are intentionally present in `panel_core.__all__` and are used by legacy tests.

Direct `run_case` calls bypass `read_cases`.  They can therefore observe different
validation/default behavior from CLI and GUI calls.  Neither contract may be
silently inferred from the other.

## Case input

Both readers accept CSV, XLSX, XLSM, and an advertised XLS suffix, use the first
worksheet, fill blank optional cells with defaults, preserve unknown columns after
canonical columns, retain textual `case_id` values, resolve `~`, and resolve
relative `stl_path` and `out_dir` from the input file directory.  Multiple STL
paths use `;` and become an absolute semicolon-separated string.

Common required geometry, attitude, and reference columns are:

```text
case_id, stl_path, stl_scale_m_per_unit,
alpha_deg, beta_or_bank_deg,
ref_x_m, ref_y_m, ref_z_m, Aref_m2,
Lref_Cl_m, Lref_Cm_m, Lref_Cn_m
```

FMF additionally requires `Tw_K` and exactly one complete flow pair:

- Mode A: `S`, `Ti_K`;
- Mode B: `Mach`, `Altitude_km`.

newtsolver instead requires `Mach`, `gamma`; optional selectors are
`windward_eq` and `leeward_eq`.  A selector can be one value broadcast to every
STL or exactly one value per STL.

| Optional column | FMF default | newtsolver default |
|---|---|---|
| `attitude_input` | `beta_tan` | `beta_tan` |
| `shielding_on` | 0 | 0 |
| `ray_backend` | `auto` | `auto` |
| `out_dir` | `outputs` | `outputs` |
| `save_vtp_on` | 1 | 1 |
| `save_npz_on` | 0 | 0 |
| `windward_eq` | not applicable | `newtonian` |
| `leeward_eq` | not applicable | `shield` |

Shared validation makes required numbers finite; scale, area, and three reference
lengths positive; flags numeric 0 or 1; backend one of `auto`, `rtree`, `embree`;
and attitude mode one of `beta_tan`, `beta_sin`, `bank`.  STL existence is checked
before mesh content.  Errors are aggregated into `InputValidationError.issues`
with spreadsheet row number, case ID, field, and message.

FMF also requires positive `Tw_K` and positive specified Mode values, constrains
altitude to `[0, 1000] km`, and rejects `beta_tan` angles at or outside ±90°.
newtsolver requires `gamma > 1`; supersonic-only equation paths require Mach > 1,
but Newtonian/shield accepts any positive Mach.  It does not constrain attitude
angle domains in `read_cases`.

FMF validates portable file names but treats duplicate IDs case-sensitively.
newtsolver restricts IDs to an ASCII portable pattern and treats duplicates
case-insensitively.  FMF selects `xlrd` for `.xls`; newtsolver sends all Excel
suffixes to `openpyxl`, which cannot read legacy BIFF `.xls` files despite the
advertised suffix.

## Numerical conventions observed

The semantic fixtures verify these operations without changing them:

- STL to body axes is `(-x_stl, +y_stl, -z_stl)`;
- `C_face_stl = dC/dA * area_m2` and total force is its face sum;
- `CA=-Fx_body`, `CY=Fy_body`, `CN=-Fz_body`;
- `CD` and `CL` use a body-to-stability Y rotation by resolved `alpha_t`;
- the body moment numerator is
  `(center_body - ref_body) × C_face_body`, followed by axis-specific Lref;
- component IDs are zero-based input-STL indices and use the global Aref,
  reference point, and reference lengths;
- `theta_deg = acos(n_out_stl · Vhat_stl)`; a head-on windward plate has 180°;
- `Cp_n = -(Aref/area) * dot(C_face_stl, n_out_stl)`;
- a ray-shielded panel has an exact zero load vector.

FMF returns Sentman normal and tangential load contributions.  Mode B linearly
samples the bundled US1976 tables and derives `S` and `Ti_K`.  newtsolver returns
normal pressure load from Newtonian, modified Newtonian, tangent wedge, or tangent
cone on windward panels, and either zero (`shield`) or Prandtl-Meyer suction on
leeward panels.  `leeward_eq=shield` is a pressure-model choice and is distinct
from ray `shielding_on`.

FMF repairs normals per watertight body and explicitly rejects inconsistent
winding, degenerate/nonfinite faces, and failed repair.  newtsolver repairs
disconnected body orientation but has weaker explicit degenerate-face checks.
Both warn and continue for non-watertight fixture plates.

## Summary CSV

The writer places canonical normalized input columns first, then unknown input
columns, then result columns.  A multi-STL case emits one `total` row followed by
component rows in component-ID order.  Component rows repeat case/run metadata but
blank `vtp_path` and `npz_path`.  Output order is independent of worker completion
order.  Summary replacement is atomic; VTP and NPZ writes are not.

FMF canonical input order has 23 columns and its result portion is:

```text
solver_version, case_signature, run_started_at_utc, run_finished_at_utc,
run_elapsed_s, mode, out_S, out_Ti_K, out_attitude_input,
alpha_t_deg_resolved, beta_t_deg_resolved, scope, component_id,
component_stl_path, ray_backend_used, CA, CY, CN, Cl, Cm, Cn, CD, CL,
faces, shielded_faces, vtp_path, npz_path
```

newtsolver canonical input order has 22 columns and omits the FMF
`mode/out_S/out_Ti_K` fields.  The fixture tables add one unknown `fixture_note`
column deliberately, freezing the rule that extras appear after canonical input
columns and before result columns.  Exact generated column order is in every case
and in `contracts.json`.

## VTP and NPZ

Both VTP files have the following cell arrays in face order:

```text
area_m2, shielded, Cp_n, theta_deg, C_face_stl,
center_x_stl_m, center_y_stl_m, center_z_stl_m, stl_index
```

Common field metadata is:

```text
case_id, case_signature, solver_version, stl_count, ray_backend_used,
attitude_input_used, alpha_t_deg_resolved, beta_t_deg_resolved,
stl_paths_json
```

newtsolver additionally stores `windward_eq_used` and `leeward_eq_used`.

Common NPZ names are:

```text
vertices, faces, centers_stl_m, normals_out_stl, areas_m2, shielded,
Vhat_stl, Aref_m2, attitude_input, alpha_t_deg_resolved,
beta_t_deg_resolved, C_force_stl, C_force_body, C_M_body,
CA, CY, CN, Cl, Cm, Cn, CD, CL, Cp_n,
face_stl_index, stl_paths, ray_backend_used
```

FMF additionally stores `S`, `Ti_K`, and `Tw_K`.  NPZ omits `C_face_stl` and
`theta_deg`; VTP omits integrated vectors and coefficients; CSV alone has
component results.  The three outputs must therefore be joined semantically.
Legacy `stl_paths` is an object array requiring trusted `allow_pickle=True` load.
NPZ lacks case ID, signature, and version; newtsolver NPZ also lacks equation
metadata.  These omissions are frozen, not repaired in Phase 1.

## Ray backend, cache, scheduler, and environment

`auto` uses the intersector selected by trimesh: rtree in the locked base profile
and Embree in the rayaccel profile.  Explicit `rtree` always constructs the
triangle intersector.  Explicit unavailable `embree` raises `ValueError`; it does
not fall back.  Shielding off records `ray_backend_used=not_used`.

Each product has three prefix-specific variables with otherwise matching rules:

| FMF | newtsolver | Rule |
|---|---|---|
| `FMFSOLVER_SHIELD_CACHE_MAX` | `NEWTSOLVER_SHIELD_CACHE_MAX` | default 1, 0 disables mask cache; read at module import for the effective global |
| `FMFSOLVER_SHIELD_BATCH_SIZE` | `NEWTSOLVER_SHIELD_BATCH_SIZE` | explicit argument > env > Embree 64 / rtree 8 |
| `FMFSOLVER_PARALLEL_CHUNK_CASES` | `NEWTSOLVER_PARALLEL_CHUNK_CASES` | explicit scheduler argument > env > 8 |

Invalid variable values raise `ValueError`; an invalid cache-max value can make
even CLI `--help` fail during import.  `contracts.json` executes unset, valid,
invalid, explicit-precedence, base-auto, accelerated-auto, and forced probes.

Both have process-local one-entry mesh caches, mask/intersector caches, shielding
reuse scheduling, spawn-based workers, cooperative case-boundary cancellation,
remote traceback propagation, unexpected-worker-exit detection, ordered final
results, and checkpoint snapshots.  The precise cache keys differ.  As a
historical Phase 1 observation, FMF forwarded worker logs while newtsolver
dropped them; that product difference is superseded by ADR 0008 and both current
frontends forward worker logs.  Cancellation does not interrupt a ray query or
ODE already executing.

## GUI-visible behavior

Common visible behavior:

- 1480×900 split window with case controls/log/progress on the left and VTP
  viewer on the right;
- CSV/XLSX/XLSM/XLS picker, read-only multi-select table, workers from 1 through
  CPU count, selection-or-all execution, cooperative Cancel;
- validation failure clears old input/table state and shows structured issues;
- result chooser defaults beside the input under `outputs` (the directory can be
  created even if the dialog is cancelled);
- case selection auto-loads `<out_dir>/<case_id>.vtp` only when the stored
  signature matches; missing/stale artifacts clear the current view;
- manual Open VTP can display a signature-mismatched file;
- scalar choices are `Cp_n`, `shielded`, `theta_deg`, `area_m2`, three STL center
  coordinates, and `stl_index`;
- default jet map, edges, shield transparency, information overlay, parallel
  projection, axis/ISO/Wind camera buttons;
- PNG/JPEG/TIFF single-image export and selected-case PNG batch export; missing
  or stale batch VTPs are skipped and logged.

FMF title is `Sentman FMF Solver (GUI)` and it defers window close while an active
run is cancelled and joined.  newtsolver title is `newtsolver (GUI)` and has no
equivalent close-event deferral.  This lifecycle difference remains unresolved.

## Values normalized only for golden comparison

Case signatures include absolute STL paths and installed version, so their
literal hashes change across clean locations.  Generated captures first verify
that CSV, VTP, and a recomputation agree and that the value is lowercase SHA-256,
then replace it with a marker.  Absolute staging paths, valid UTC timestamps,
finite nonnegative elapsed time, and NumPy fixed string width are likewise
validated then normalized. The rayaccel distribution is `embreex` or `embreex4`
depending on platform, so its name/version is normalized only after Embree
availability and effective selection are proven. Backend identity, solver
version, case ID, schemas, array names/order/shape/logical dtype, and all
numerical values are not normalized. Explicit CSV nonfinite values remain
distinct markers and numerical artifact arrays must be finite.
