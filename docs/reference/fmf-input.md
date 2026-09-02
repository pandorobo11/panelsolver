# FMF input reference

This page is the canonical FMF case-table schema. Columns appear in the order
shown; accepted non-reserved unknown columns are retained after them in Summary
CSV output. Common formats, paths, case IDs, and reserved-field rejection are
defined in [Case files](../user-guide/case-files.md).

| Column | Required | Default | Unit / values | Meaning |
|---|---:|---|---|---|
| `case_id` | yes | — | portable text | Unique case and artifact basename |
| `stl_path` | yes | — | path; `;` separates components | Ordered STL sources |
| `stl_scale_m_per_unit` | yes | — | m / STL unit, > 0 | Geometry scale |
| `S` | Mode A | blank | dimensionless, > 0 | Molecular speed ratio, `V_inf / sqrt(2 R Ti)` |
| `Ti_K` | Mode A | blank | K, > 0 | Free-stream incident translational (static) temperature; not total/stagnation temperature |
| `Mach` | Mode B | blank | dimensionless, > 0 | Mach used to derive `S` |
| `Altitude_km` | Mode B | blank | km, 0–1000 inclusive | Geometric altitude for the bundled-atmosphere lookup |
| `Tw_K` | yes | — | K, > 0 | Wall temperature, used as the diffusely reflected molecular temperature |
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
| `shielding_on` | no | `0` | `0` or `1` | Ray-occlusion shielding |
| `ray_backend` | no | `auto` | `auto`, `rtree`, `embree` | Shielding backend |
| `out_dir` | no | `outputs` | path | Per-case VTP directory; resolution and path rules are in [Case files](../user-guide/case-files.md#paths-artifact-destinations-and-components) |
| `save_vtp_on` | no | `1` | `0` or `1` | `1` writes the case VTP; `0` skips it |

Mode A requires both `S` and `Ti_K`; Mode B requires both `Mach` and
`Altitude_km`. Specify exactly one complete pair. Every required or specified
numeric field must be finite, and numeric booleans are rejected.

For Mode A, `Ti_K` is the static translational temperature of the incident
free-stream molecular population. Directed flow energy is represented
separately by `S`, so do not supply total or stagnation temperature. The caller
must ensure that `S` and `Ti_K` describe the same free-stream state. Here `R` in
the speed-ratio definition is the specific gas constant of that incident gas.

For Mode B, the solver obtains `Ti_K` directly from the bundled atmosphere's
temperature column at `Altitude_km`, computes `V_inf = Mach * c`, converts the
tabulated mean molecular speed to the most-probable speed as
`V_mp = sqrt(pi) / 2 * V_mean`, and resolves `S = V_inf / V_mp`. No total-
temperature conversion is performed.

The Sentman reflected term uses `sqrt(Tw_K / Ti_K)`. Because the input schema has
no separate reflected-gas temperature or accommodation coefficient, the model
uses `Tw_K` as the diffusely reflected molecular temperature (`T_r = T_w`).

FMF uses the common attitude resolver also used by Hypersonic. See
[Case files](../user-guide/case-files.md#attitude-modes) for mode selection and
accepted ranges, and
[Coordinate and attitude conventions](coordinate-and-attitude-conventions.md)
for the canonical axes, signs, and geometric definitions. Common path, case-ID,
flag, and mesh rules are also in Case files. Model interpretation is in
[Sentman local-load equation](../solvers/fmf.md#sentman-local-load-equation).
