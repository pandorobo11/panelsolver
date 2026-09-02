# Summary CSV reference

This page is the canonical contract for the result portion of Panel Solver
Summary CSV files. The case-table columns that precede these results are defined
in the [FMF input reference](../reference/fmf-input.md), the
[Hypersonic input reference](../reference/hypersonic-input.md), and
[Case files](../user-guide/case-files.md). The [CLI guide](../user-guide/cli.md)
defines the CLI Summary destination, while
[Batch execution and recovery](../user-guide/batch-execution-and-recovery.md)
defines checkpoint and write-failure behavior.

## Serialization and column order

Summary CSV uses UTF-8 with a byte-order mark (`utf-8-sig`). Treat the parsed
columns and values as the contract; temporary-file and replacement mechanics are
not part of this result reference.

Columns are written in this order:

1. canonical input columns for the selected domain;
2. accepted non-reserved extra input columns, in their source-table order;
3. the domain result columns below.

### FMF result columns

```text
solver_version, case_signature, run_started_at_utc, run_finished_at_utc,
run_elapsed_s, mode, out_S, out_Ti_K, out_attitude_input,
alpha_t_deg_resolved, beta_t_deg_resolved, scope, component_id,
component_stl_path, ray_backend_used, CA, CY, CN, Cl, Cm, Cn, CD, CL,
faces, shielded_faces, vtp_path
```

### Hypersonic result columns

```text
solver_version, case_signature, run_started_at_utc, run_finished_at_utc,
run_elapsed_s, out_attitude_input, alpha_t_deg_resolved,
beta_t_deg_resolved, scope, component_id, component_stl_path,
ray_backend_used, CA, CY, CN, Cl, Cm, Cn, CD, CL, faces,
shielded_faces, vtp_path
```

A result field listed for one domain is absent from the other domain's schema; it
is not emitted as an empty placeholder.

## Row structure

Every calculated case emits one `total` row. A case with multiple ordered STL
components then emits one `component` row per component in ascending zero-based
component-ID order. A single-STL case emits only its `total` row. Across a batch,
cases remain in input-table order even when workers complete them in another
order.

Input cells and case-level run fields are repeated on component rows. Coefficients,
face counts, shielding counts, `component_id`, and `component_stl_path` describe
the row's selected scope. Component coefficients use the same global reference
area, moment reference point, and three reference lengths as the total, so a
component row is not independently renormalized.

In the tables below, **blank** means an empty CSV field. The semantic types describe
values after CSV parsing rather than a required textual formatting of each
number.

## Provenance and timing fields

| Column | Domain | Type / format | Unit | Rows | Blank when | Meaning |
|---|---|---|---|---|---|---|
| `solver_version` | common | text | — | all | never | Installed `panelsolver` distribution version that generated the result. |
| `case_signature` | common | 64-character lowercase hexadecimal SHA-256 | — | all | never | Canonical current case/artifact identity. It incorporates the numerical geometry, normalized common and model case, model algorithm version, and shielding configuration including the effective backend. The GUI uses it with `case_id` to match a VTP to a current case. It is not a complete-result cache key. |
| `run_started_at_utc` | common | ISO 8601 UTC timestamp ending in `Z` | — | all | never | Time at which this case began execution. It is a per-case timestamp, not the batch start. |
| `run_finished_at_utc` | common | ISO 8601 UTC timestamp ending in `Z` | — | all | never | Time after calculation and the case's optional VTP write attempt completed. It is a per-case timestamp, not the final Summary CSV write time. |
| `run_elapsed_s` | common | floating-point number | s | all | never | Monotonic elapsed time over the same per-case interval, including optional VTP handling and excluding final batch Summary CSV serialization. |

The same provenance and timing values are repeated on every component row for a
case; they are not component timings.

## FMF resolved-state fields

These columns exist only in FMF Summary CSV.

| Column | Type / format | Unit / values | Rows | Blank when | Meaning |
|---|---|---|---|---|---|
| `mode` | text | `A` or `B` | all | never | Resolved Sentman input mode. Mode A uses supplied `S` and `Ti_K`; Mode B derives them from `Mach` and `Altitude_km`. |
| `out_S` | floating-point number | dimensionless | all | never | Molecular speed ratio actually used by the Sentman calculation, whether supplied in Mode A or derived in Mode B. |
| `out_Ti_K` | floating-point number | K | all | never | Incident free-stream translational static temperature actually used, whether supplied in Mode A or obtained from the bundled atmosphere in Mode B. |

`Tw_K` remains an input column. FMF's resolved mode, speed ratio, and incident
temperature are not stored in VTP field data; use the Summary CSV when they are
needed for provenance.

## Attitude and row-identity fields

| Column | Domain | Type / format | Unit / values | Rows | Blank when | Meaning |
|---|---|---|---|---|---|---|
| `out_attitude_input` | common | text | `beta_tan`, `beta_sin`, or `bank` | all | never | Canonical attitude representation used to interpret the two input angles. The corresponding VTP field is `attitude_input_used`. |
| `alpha_t_deg_resolved` | common | floating-point number | degrees | all | never | Resolved tangent angle of attack used by integration and stability-frame conversion. |
| `beta_t_deg_resolved` | common | floating-point number | degrees | all | never | Resolved tangent sideslip angle associated with the evaluated flow direction. |
| `scope` | common | text | `total` or `component` | all | never | Identifies whether the row covers the complete case geometry or one STL component. |
| `component_id` | common | non-negative integer | zero-based STL index | component | `scope=total` | Component identifier in input `stl_path` order. |
| `component_stl_path` | common | absolute path text | — | component | `scope=total` | Resolved STL source path used to load this component. |

The exact axes, angle transformations, coefficient signs, and moment reference
conventions are defined in
[Numerical conventions](../reference/numerical-conventions.md).

## Execution and artifact fields

| Column | Domain | Type / format | Unit / values | Rows | Blank when | Meaning |
|---|---|---|---|---|---|---|
| `ray_backend_used` | common | text | `not_used`, `rtree`, or `embree` | all | never | Effective ray backend for the evaluated case. It is `not_used` when ray shielding is disabled; for input `auto`, it records the backend actually selected. |
| `faces` | common | non-negative integer | panel count | all | never | Number of triangular panels represented by the row's scope. |
| `shielded_faces` | common | non-negative integer | panel count | all | never | Number of panels in the row's scope marked geometrically occluded by ray shielding. A Hypersonic leeward `shield` pressure selector does not increment this count. |
| `vtp_path` | common | absolute path text | — | total | VTP saving was disabled, output-directory preparation failed, or the current VTP write failed | VTP successfully written for this case during the current run. Component rows are always blank because one case VTP contains every component. |

A blank `vtp_path` never claims that an older file at the planned path represents
the current result. See the [VTP reference](vtp.md) for that file's complete
semantic contract.

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
body-to-stability rotation, signs, and moment calculation are canonical in
[Numerical conventions](../reference/numerical-conventions.md#loads-and-normalization).
Per-panel contributions from which these coefficients are integrated are stored
as `C_face_stl` in the [VTP reference](vtp.md).
