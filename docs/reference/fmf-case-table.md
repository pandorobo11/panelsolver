# FMF case table

This page lists every column of an FMF case table. Columns can be in any order.
In the Summary CSV, these input columns are written in the order shown here,
followed by any extra columns of your own. For file formats, paths, and the
checks that apply to every table, see [Preparing cases](../guides/preparing-cases.md)
and its [common validation](../guides/preparing-cases.md#common-validation) list.
Leaving out a column with a default, or leaving its cell empty, uses the default
(see [Columns and defaults](../guides/preparing-cases.md#columns-and-defaults)).

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
| `save_vtp_on` | no | `1` | `0` or `1` | `1` writes the case VTP; `0` skips it |

**Flow input modes.** Fill exactly one complete pair on each row:

- **Mode A:** `S` and `Ti_K`, the molecular speed ratio and gas temperature.
- **Mode B:** `Mach` and `Altitude_km`. Panel Solver looks up the gas
  temperature and speed at that altitude in the bundled US Standard Atmosphere
  1976 table and works out `S` and `Ti_K` from them.

The Summary CSV records which mode was used and the `S` and `Ti_K` values
actually used. The [FMF method page](../methods/fmf.md#flow-inputs) gives the
conversion and explains how the wall temperature is used.

For attitude modes and their ranges, see
[Preparing cases](../guides/preparing-cases.md#attitude-modes). Axes and signs
are defined in
[Coordinate and attitude conventions](../methods/coordinate-and-attitude-conventions.md).
