# Hypersonic input reference

This page is the canonical Hypersonic case-table schema, also used by the legacy
`newtsolver` compatibility commands. Columns appear in the order shown; accepted
non-reserved unknown columns are retained after them in Summary CSV output.
Common formats, paths, case IDs, and reserved-field rejection are defined in
[Case files](../user-guide/case-files.md).

| Column | Required | Default | Unit / values | Meaning |
|---|---:|---|---|---|
| `case_id` | yes | — | portable text | Unique case and artifact basename |
| `stl_path` | yes | — | path; `;` separates components | Ordered STL sources |
| `stl_scale_m_per_unit` | yes | — | m / STL unit, > 0 | Geometry scale |
| `Mach` | yes | — | dimensionless, > 0 | Freestream Mach number |
| `gamma` | yes | — | dimensionless, > 1 | Specific-heat ratio |
| `windward_eq` | no | `newtonian` | see below | Windward pressure equation(s) |
| `leeward_eq` | no | `shield` | see below | Leeward pressure equation(s) |
| `alpha_deg` | yes | — | degrees | First attitude value |
| `beta_or_bank_deg` | yes | — | degrees | Second attitude value |
| `attitude_input` | no | `beta_tan` | `beta_tan`, `beta_sin`, `bank` | Attitude interpretation |
| `ref_x_m` | yes | — | m | Moment reference X in STL frame |
| `ref_y_m` | yes | — | m | Moment reference Y in STL frame |
| `ref_z_m` | yes | — | m | Moment reference Z in STL frame |
| `Aref_m2` | yes | — | m², > 0 | Reference area |
| `Lref_Cl_m` | yes | — | m, > 0 | Roll-moment reference length |
| `Lref_Cm_m` | yes | — | m, > 0 | Pitch-moment reference length |
| `Lref_Cn_m` | yes | — | m, > 0 | Yaw-moment reference length |
| `shielding_on` | no | `0` | `0` or `1` | Ray-occlusion shielding |
| `ray_backend` | no | `auto` | `auto`, `rtree`, `embree` | Shielding backend |
| `out_dir` | no | `outputs` | path | Per-case artifact directory |
| `save_vtp_on` | no | `1` | `0` or `1` | Save VTP |

Windward values are `newtonian`, `modified_newtonian`, `tangent_wedge`, and
`tangent_cone`. Leeward values are `shield` and `prandtl_meyer`. One value is
broadcast to all STL components; otherwise the number of semicolon-separated
entries must equal the STL count. Modified Newtonian, tangent wedge, tangent
cone, and Prandtl–Meyer require `Mach > 1`.

Every required numeric field must be finite, and numeric booleans are rejected.
Common rules are in [Case files](../user-guide/case-files.md); physical
interpretation is in the Hypersonic
[pressure-model equations](../solvers/hypersonic.md#pressure-model-equations).
