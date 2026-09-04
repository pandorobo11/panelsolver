# Hypersonic input reference

This page defines the Hypersonic case-table schema. Input columns may be in any
order. The standard input columns are written to Summary CSV in the order shown
below, followed by extra input columns in their original relative order.
[Case files](../user-guide/case-files.md) defines accepted formats, path
resolution, case-ID rules, and reserved-field rejection. See
[Columns and defaults](../user-guide/case-files.md#columns-and-defaults) for
omitted-column and empty-cell behavior.

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
| `attitude_input` | no | `beta_tan` | `beta_tan`, `beta_sin`, `bank` | Attitude representation used to interpret the two values |
| `ref_x_m` | yes | — | m | Moment reference X in STL frame |
| `ref_y_m` | yes | — | m | Moment reference Y in STL frame |
| `ref_z_m` | yes | — | m | Moment reference Z in STL frame |
| `Aref_m2` | yes | — | m², > 0 | Reference area |
| `Lref_Cl_m` | yes | — | m, > 0 | Roll-moment reference length |
| `Lref_Cm_m` | yes | — | m, > 0 | Pitch-moment reference length |
| `Lref_Cn_m` | yes | — | m, > 0 | Yaw-moment reference length |
| `shielding_on` | no | `0` | `0` or `1` | Enable the [ray-occlusion shielding method](ray-shielding.md) |
| `ray_backend` | no | `auto` | `auto`, `rtree`, `embree` | [Ray-shielding backend](ray-shielding.md#backend-behavior) |
| `out_dir` | no | `outputs` | path | Per-case VTP directory; resolution and path rules are in [Case files](../user-guide/case-files.md#paths-vtp-destinations-and-components) |
| `save_vtp_on` | no | `1` | `0` or `1` | `1` writes the case VTP; `0` skips it |

Windward values are `newtonian`, `modified_newtonian`, `tangent_wedge`, and
`tangent_cone`. Leeward values are `shield` and `prandtl_meyer`. One value
applies to all STL components; otherwise the number of semicolon-separated
entries must equal the STL count. Modified Newtonian, tangent wedge, tangent
cone, and Prandtl–Meyer require `Mach > 1`.

The leeward `shield` pressure selector and geometry-based ray shielding serve
different purposes. See
[Ray shielding versus `leeward_eq=shield`](ray-shielding.md#ray-shielding-versus-leeward_eqshield).

Every required numeric field must be finite, and numeric booleans are rejected.
Hypersonic and FMF use the same attitude resolver. See
[Case files](../user-guide/case-files.md#attitude-modes) for mode selection and
accepted ranges, and
[Coordinate and attitude conventions](coordinate-and-attitude-conventions.md)
for the axes, signs, and geometric definitions. Path, case-ID, flag, and mesh
rules are in Case files; physical interpretation is in the Hypersonic
[pressure-model equations](../solvers/hypersonic.md#pressure-model-equations).
