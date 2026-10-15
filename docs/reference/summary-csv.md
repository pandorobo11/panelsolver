# Summary CSV reference

The Summary CSV holds the force and moment coefficients of each case. Open it in
a spreadsheet, find your `case_id`, and read the row with `scope` = `total` for
the whole vehicle. Cases with several STL parts also have one `scope` =
`component` row per part. Part rows use the same reference quantities, so they
add up to the total.

The coefficients to start with:

| Columns | Meaning |
|---|---|
| `CA`, `CY`, `CN` | Axial, side, and normal force, in body axes. |
| `Cl`, `Cm`, `Cn` | Roll, pitch, and yaw moment about your moment reference point. |
| `CD`, `CL` | Drag and lift, in stability axes. |

All coefficients are dimensionless. Their axes and signs are defined in
[Load and coefficient conventions](../methods/load-and-coefficient-conventions.md#stability-axis-force-coefficients).
For the load on each panel, use the [VTP file](vtp.md) instead.

## File format and column order

The file is UTF-8 with a byte-order mark, which spreadsheet programs use to
detect the encoding. The columns and values described on this page are
guaranteed; exact number formatting is not.

Columns are written in this order:

1. the standard input columns of the domain, in the order listed in the
   [FMF](fmf-case-table.md) or [Hypersonic](hypersonic-case-table.md) case
   table reference;
2. your own extra input columns, in their order in the case table;
3. the result columns below.

### FMF result columns

```text
solver_version, case_signature, run_started_at_utc, run_finished_at_utc,
run_elapsed_s, mode, out_S, out_Ti_K, out_attitude_input,
alpha_stability_deg, velocity_hat_x_stl, velocity_hat_y_stl, velocity_hat_z_stl, scope, component_id,
component_stl_path, ray_backend_used, CA, CY, CN, Cl, Cm, Cn, CD, CL,
faces, shielded_faces, vtp_path
```

### Hypersonic result columns

```text
solver_version, case_signature, run_started_at_utc, run_finished_at_utc,
run_elapsed_s, out_attitude_input, alpha_stability_deg,
velocity_hat_x_stl, velocity_hat_y_stl, velocity_hat_z_stl, scope, component_id, component_stl_path,
ray_backend_used, CA, CY, CN, Cl, Cm, Cn, CD, CL, faces,
shielded_faces, vtp_path
```

Each domain writes exactly its listed result columns.

## Row structure

- Each case has one `total` row.
- A case with several STL parts then has one `component` row per part, in
  `stl_path` order (component ID `0`, `1`, ...). A single-part case has only
  the `total` row.
- The rows of one case always stay together.
- In the final file, cases are in case-table order. While a run is still
  writing checkpoints, cases appear in the order they finished.
- Component rows repeat the case's input values and run times. Their
  coefficients, panel counts, `component_id`, and `component_stl_path` describe
  only that part. Part coefficients add up to the total, apart from rounding.

In the tables below, **blank** means an empty cell. The type column describes
the value, not its exact text formatting.

## Provenance and timing fields

| Column | Domain | Type / format | Unit | Rows | Blank when | Meaning |
|---|---|---|---|---|---|---|
| `solver_version` | common | text | — | all | never | Installed `panelsolver` distribution version that generated the result. |
| `case_signature` | common | 64-character lowercase hexadecimal SHA-256 | — | all | never | A fingerprint of the case. It changes when the geometry, the case inputs, the model version, or the shielding settings change. The GUI compares it, together with `case_id`, to decide whether a VTP belongs to the current case. |
| `run_started_at_utc` | common | ISO 8601 UTC timestamp ending in `Z` | — | all | never | Time at which this case began execution. |
| `run_finished_at_utc` | common | ISO 8601 UTC timestamp ending in `Z` | — | all | never | Time after this case's calculation and optional VTP write attempt completed. |
| `run_elapsed_s` | common | floating-point number | s | all | never | Monotonic elapsed time over the same per-case interval, including optional VTP handling and excluding the final batch Summary CSV write. |

## FMF resolved-state fields

| Column | Type / format | Unit / values | Rows | Blank when | Meaning |
|---|---|---|---|---|---|
| `mode` | text | `A` or `B` | all | never | Resolved Sentman input mode. Mode A uses supplied `S` and `Ti_K`; Mode B derives them from `Mach` and `Altitude_km`. |
| `out_S` | floating-point number | dimensionless | all | never | Molecular speed ratio actually used by the Sentman calculation, whether supplied in Mode A or derived in Mode B. |
| `out_Ti_K` | floating-point number | K | all | never | Incident free-stream translational static temperature actually used, whether supplied in Mode A or obtained from the bundled atmosphere in Mode B. |

`Tw_K` remains an input column. Summary CSV is the file source for FMF's
resolved mode, speed ratio, and incident temperature.

## Attitude and row fields

| Column | Domain | Type / format | Unit / values | Rows | Blank when | Meaning |
|---|---|---|---|---|---|---|
| `out_attitude_input` | common | text | `beta_sin`, `beta_tan`, or `bank` | all | never | Normalized attitude input mode used to interpret the two input angles. The corresponding VTP field is `attitude_input_used`. |
| `alpha_stability_deg` | common | floating-point number | degrees | all | never | Common stability angle in (-180°, 180°], including the documented zero fallback. |
| `velocity_hat_x_stl` | common | floating-point number | dimensionless | all | never | X component of the evaluated unit STL flow direction. |
| `velocity_hat_y_stl` | common | floating-point number | dimensionless | all | never | Y component of the evaluated unit STL flow direction. |
| `velocity_hat_z_stl` | common | floating-point number | dimensionless | all | never | Z component of the evaluated unit STL flow direction. |
| `scope` | common | text | `total` or `component` | all | never | Identifies whether the row covers the complete case geometry or one STL component. |
| `component_id` | common | non-negative integer | zero-based STL index | component | `scope=total` | Component identifier in input `stl_path` order. |
| `component_stl_path` | common | absolute path text | — | component | `scope=total` | Resolved STL source path used to load this component. |

The exact axes and angle transformations are defined in
[Coordinate and attitude conventions](../methods/coordinate-and-attitude-conventions.md).

## Execution and output fields

| Column | Domain | Type / format | Unit / values | Rows | Blank when | Meaning |
|---|---|---|---|---|---|---|
| `ray_backend_used` | common | text | `not_used`, `rtree`, or `embree` | all | never | Effective backend for the [ray-shielding method](../methods/ray-shielding.md). It is `not_used` when ray shielding was disabled; for input `auto`, it records the backend actually selected. |
| `faces` | common | non-negative integer | panel count | all | never | Number of triangular panels represented by the row's scope. |
| `shielded_faces` | common | non-negative integer | panel count | all | never | Number of panels in the row's scope marked geometrically occluded by [ray shielding](../methods/ray-shielding.md). |
| `vtp_path` | common | absolute path text | — | total | VTP saving was disabled, output-directory preparation failed, or the current VTP write failed | VTP successfully written for this case during the current run. Component rows are always blank because one case VTP contains every component. |

Use `vtp_path` to identify files written by the current run. For handling older
retained files, checkpoints, and write failures, see
[Batch execution and recovery](../guides/batch-runs.md).

## Force and moment coefficient fields

All coefficient columns are floating-point, dimensionless, present on both
`total` and `component` rows, and never blank for a successful calculation.

| Column | Frame / axis | Meaning |
|---|---|---|
| `CA` | body X | Axial-force coefficient, `-C_X_body`. |
| `CY` | body Y | Side-force coefficient, `C_Y_body`. |
| `CN` | body Z | Normal-force coefficient, `-C_Z_body`. |
| `Cl` | body X | Roll-moment coefficient about the configured moment reference, divided by `Lref_Cl_m`. |
| `Cm` | body Y | Pitch-moment coefficient about the configured moment reference, divided by `Lref_Cm_m`. |
| `Cn` | body Z | Yaw-moment coefficient about the configured moment reference, divided by `Lref_Cn_m`. |
| `CD` | stability X | Drag coefficient, `-C_X_stability`. |
| `CL` | stability Z | Lift coefficient, `-C_Z_stability`. |

Panel-area/reference-area normalization, the STL-to-body mapping, the
body-to-stability rotation, signs, and moment calculation are defined in
[Load and coefficient conventions](../methods/load-and-coefficient-conventions.md).
Per-panel contributions from which these coefficients are integrated are stored
as `C_face_stl` in the [VTP reference](vtp.md).

The `alpha_deg` and `beta_or_bank_deg` input columns keep the values you
entered, even if they include full turns (for example 460°). See
[Coordinate and attitude conventions](../methods/coordinate-and-attitude-conventions.md#stability-angle-and-numerical-boundaries)
for when `alpha_stability_deg` falls back to 0°.
