# Hypersonic case table

This page lists every column of a Hypersonic case table. Columns can be in any order.
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
| `Mach` | yes | — | dimensionless, > 0 | Freestream Mach number |
| `gamma` | yes | — | dimensionless, > 1 | Specific-heat ratio |
| `windward_eq` | no | `newtonian` | see below | Windward pressure equation(s) |
| `leeward_eq` | no | `shield` | see below | Leeward pressure equation(s) |
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
| `out_dir` | no | `outputs` | path | Per-case VTP directory; resolution and path rules are in [Preparing cases](../guides/preparing-cases.md#paths-vtp-destinations-and-components) |
| `save_vtp_on` | no | `1` | `0` or `1` | `1` writes the case VTP; `0` skips it |

**Pressure methods.** A *windward* panel faces the oncoming flow; a *leeward*
panel faces away from it.

| Column | Accepted values |
|---|---|
| `windward_eq` | `newtonian`, `modified_newtonian`, `tangent_wedge`, `tangent_cone` |
| `leeward_eq` | `shield` (`Cp = 0`), `prandtl_meyer` |

Write one value to use it for every STL part, or one value per part separated
by semicolons, in the same order as `stl_path`. All methods except
`newtonian` and `shield` need `Mach > 1`. The
[Hypersonic method page](../methods/hypersonic.md#pressure-model-equations)
explains each method and when it applies.

For attitude modes and their ranges, see
[Preparing cases](../guides/preparing-cases.md#attitude-modes). Axes and signs
are defined in
[Coordinate and attitude conventions](../methods/coordinate-and-attitude-conventions.md).
