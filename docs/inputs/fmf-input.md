# FMF input reference

This page defines the FMF case-table schema. Input columns may be in any
order. The standard input columns are written to Summary CSV in the order shown
below, followed by extra input columns in their original relative order.
[Case files](case-files.md) defines accepted formats, path
resolution, and [common validation](case-files.md#common-validation).
See [Columns and defaults](case-files.md#columns-and-defaults) for
omitted-column and empty-cell behavior.

| Column | Required | Default | Unit / values | Meaning |
|---|---:|---|---|---|
| `case_id` | yes | — | portable text | Unique case ID and VTP filename stem |
| `stl_path` | yes | — | path; `;` separates components | Ordered STL sources |
| `stl_scale_m_per_unit` | yes | — | m / STL unit, > 0 | Geometry scale |
| `S` | Mode A | blank | dimensionless, > 0 | Molecular speed ratio, `V_inf / sqrt(2 R Ti)`; `R` is the incident gas's specific gas constant |
| `Ti_K` | Mode A | blank | K, > 0 | Free-stream incident translational (static) temperature; not total/stagnation temperature |
| `Mach` | Mode B | blank | dimensionless, > 0 | Mach used to derive `S` |
| `Altitude_km` | Mode B | blank | km, 0–1000 inclusive | Geometric altitude for the bundled-atmosphere lookup |
| `Tw_K` | yes | — | K, > 0 | Wall temperature, used as the diffusely reflected molecular temperature |
| `alpha_deg` | yes | — | degrees | First attitude value; interpretation depends on `attitude_input` |
| `beta_or_bank_deg` | yes | — | degrees | Second attitude value; interpretation depends on `attitude_input` |
| `attitude_input` | no | `beta_sin` | `beta_sin`, `beta_tan`, `bank` | Attitude representation used to interpret the two values |
| `ref_x_m` | yes | — | m | Moment reference X in STL frame |
| `ref_y_m` | yes | — | m | Moment reference Y in STL frame |
| `ref_z_m` | yes | — | m | Moment reference Z in STL frame |
| `Aref_m2` | yes | — | m², > 0 | Reference area |
| `Lref_Cl_m` | yes | — | m, > 0 | Roll-moment reference length |
| `Lref_Cm_m` | yes | — | m, > 0 | Pitch-moment reference length |
| `Lref_Cn_m` | yes | — | m, > 0 | Yaw-moment reference length |
| `shielding_on` | no | `0` | `0` or `1` | Enable the [ray-occlusion shielding method](../methods/ray-shielding.md) |
| `ray_backend` | no | `auto` | `auto`, `rtree`, `embree` | [Ray-shielding backend](../methods/ray-shielding.md#backend-behavior) |
| `out_dir` | no | `outputs` | path | Per-case VTP directory; resolution and path rules are in [Case files](case-files.md#paths-vtp-destinations-and-components) |
| `save_vtp_on` | no | `1` | `0` or `1` | `1` writes the case VTP; `0` skips it |

Mode A requires both `S` and `Ti_K`; Mode B requires both `Mach` and
`Altitude_km`. Specify exactly one complete pair.

The [FMF solver page](../methods/fmf.md#flow-inputs) explains the Mode B
atmosphere conversion and the wall-temperature assumption.

See [Case files](case-files.md#attitude-modes) for attitude mode
selection and accepted ranges, and
[Coordinate and attitude conventions](../methods/coordinate-and-attitude-conventions.md)
for axes, signs, and geometric definitions.
