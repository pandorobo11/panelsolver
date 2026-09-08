# VTP reference

A VTP is the mesh and surface-distribution result for one case. Open it in the
[Panel Solver GUI](../running/gui.md#view-and-export), ParaView, or another
VTK-capable tool to see where the surface load acts. The GUI normally loads a
selected case's matching result automatically; **Open VTP...** also allows
manual inspection.

<a id="relating-vtp-to-summary-csv"></a>

For Hypersonic, start with `cp`, the local pressure coefficient. For FMF, inspect
`normal_traction_coeff` and `tangential_traction_coeff`, the local Sentman
traction components. These surface scalars describe individual panels; use the
[Summary CSV](summary-csv.md) for integrated force and moment coefficients.

Each `.vtp` is VTK XML PolyData containing the SI-scaled mesh, one result value
per triangle for each cell array, and case-level provenance. The tables below
define every supported field. Per-case paths are in
[Case files](../inputs/case-files.md#paths-vtp-destinations-and-components),
and write failures are covered by
[Batch execution and recovery](../running/batch-execution-and-recovery.md).

## Guaranteed VTP contents

Panel Solver's compatibility guarantee covers the mesh, cell-data arrays, and
field-data arrays described below, including their names, associations, shapes,
stored dtypes, units, meanings, and roles in integration. Numeric values are
compared with the tolerance appropriate to the selected physical model. The
guarantee does not cover XML element order, binary encoding details,
compression, temporary files, or byte-for-byte equality.

There are no Panel Solver-defined point-data arrays. Every cell-data array is
aligned with the VTP triangle-cell order. Array names are case-sensitive.

## PolyData mesh

The VTP contains the loaded, validated, SI-scaled panel mesh used by the
calculation.

| Element | Association | Shape | Stored dtype | Unit | Meaning |
|---|---|---:|---|---|---|
| Points | point coordinates | `(n_vertices, 3)` | `float64` | m | Vertex coordinates in the STL frame after applying `stl_scale_m_per_unit`. |
| Triangle connectivity | polygon cells | `n_faces` triangles of 3 vertex indices | `int64` VTK IDs | — | Face topology and face order used by geometry, shielding, model evaluation, and every cell-data array. |

Before writing, each triangle is stored in the flattened VTK connectivity array
as `[3, i0, i1, i2]`. Ordinary VTK/PyVista readers expose the same values as
triangle cells.

## Common cell data

| Array | Shape | Stored dtype | Unit | Meaning | Role in integration |
|---|---:|---|---|---|---|
| `C_face_stl` | `(n_faces, 3)` | `float64` | dimensionless | Per-face force-coefficient contribution in STL axes after multiplying local traction by `area_m2 / Aref_m2`. | **Integrated value.** Summing all rows gives the total STL-frame force coefficient; summing one `stl_index` subset gives that component's force coefficient. Moments use the same face force with the configured lever arm. |
| `area_m2` | `(n_faces,)` | `float64` | m² | Triangle area used by the calculation. | Supplies the area factor incorporated into `C_face_stl`. |
| `center_x_stl_m` | `(n_faces,)` | `float64` | m | Face-centroid X coordinate in the STL frame. | Geometry/provenance; the three center arrays define the moment lever arm with the configured reference point. |
| `center_y_stl_m` | `(n_faces,)` | `float64` | m | Face-centroid Y coordinate in the STL frame. | Geometry/provenance; used with the other center coordinates for moments. |
| `center_z_stl_m` | `(n_faces,)` | `float64` | m | Face-centroid Z coordinate in the STL frame. | Geometry/provenance; used with the other center coordinates for moments. |
| `shielded` | `(n_faces,)` | `uint8` | `0` or `1` | [Ray-occlusion](../methods/ray-shielding.md) mask. `1` means the panel was geometrically shielded for this case. | Shielded panels have exact-zero local traction and therefore exact-zero `C_face_stl`. A Hypersonic leeward `shield` selector is a different pressure rule and does not set this mask. |
| `stl_index` | `(n_faces,)` | `int32` | zero-based component ID | Input-STL/component assignment in ordered `stl_path` order. | Selects the faces used for each component row in the Summary CSV. |
| `theta_deg` | `(n_faces,)` | `float64` | degrees | Angle `acos(n_out_stl · Vhat_stl)` between the outward panel normal and the resolved flow direction, in the range 0–180 degrees. | Diagnostic/model geometry scalar. |

The relationship between `C_face_stl`, whole-case coefficients, frames, signs,
and moments is defined in
[Load and coefficient conventions](../methods/load-and-coefficient-conventions.md).

## Model-specific cell data

### Hypersonic

| Array | Shape | Stored dtype | Unit | Meaning | Role in integration |
|---|---:|---|---|---|---|
| `cp` | `(n_faces,)` | `float64` | dimensionless | Local pressure coefficient selected by the panel's windward or leeward pressure method. It may be negative for Prandtl–Meyer expansion and is zero on ray-shielded faces. | Pressure-load input used to calculate `C_face_stl`. |

See [Hypersonic Panel Methods](../methods/hypersonic.md) for each pressure
equation and its limits.

### FMF

| Array | Shape | Stored dtype | Unit | Meaning | Role in integration |
|---|---:|---|---|---|---|
| `normal_traction_coeff` | `(n_faces,)` | `float64` | dimensionless | Component of the local Sentman traction opposite the outward normal, `-tau · n_out_stl`, before multiplying by panel area or dividing by reference area. | Visualization/diagnostic scalar derived from local traction. |
| `tangential_traction_coeff` | `(n_faces,)` | `float64` | dimensionless | Component of local Sentman traction along the resolved flow direction projected into the panel plane, before area/reference-area scaling. It is exactly zero where that in-plane direction is undefined at normal incidence. | Visualization/diagnostic scalar derived from local traction. |

See [Free Molecular Flow](../methods/fmf.md) for the Sentman equation and the
exact normal and tangential components.

## Common field data

Every common field-data array has shape `(1,)`.

| Field | Stored dtype / format | Unit / values | Meaning |
|---|---|---|---|
| `alpha_stability_deg` | `float64` | degrees | Common stability angle used for coefficient conversion, including the documented zero fallback. It matches the Summary CSV field of the same name. |
| `attitude_input_used` | string | `beta_tan`, `beta_sin`, or `bank` | Normalized attitude representation used to interpret the two input angles. The corresponding Summary CSV field is `out_attitude_input`. |
| `velocity_hat_x_stl` | `float64` | dimensionless | X component of the evaluated unit STL flow direction; matches Summary CSV. |
| `velocity_hat_y_stl` | `float64` | dimensionless | Y component of the evaluated unit STL flow direction; matches Summary CSV. |
| `velocity_hat_z_stl` | `float64` | dimensionless | Z component of the evaluated unit STL flow direction; matches Summary CSV. |
| `alpha_deg` | `float64` | degrees | Original first input value before periodic reduction. |
| `beta_or_bank_deg` | `float64` | degrees | Original second input value before periodic reduction. |
| `case_id` | string | portable case text | Case identifier and planned VTP basename. |
| `case_signature` | string; 64-character lowercase hexadecimal SHA-256 | — | SHA-256 value that identifies the current case and associates its output files. It corresponds to the Summary CSV value, and the GUI compares it with the currently loaded case for automatic display. |
| `ray_backend_used` | string | `not_used`, `rtree`, or `embree` | Effective [ray-shielding backend](../methods/ray-shielding.md#backend-behavior). `not_used` means ray shielding was disabled. |
| `solver_version` | string | installed version | `panelsolver` distribution version that generated the VTP file. |
| `stl_count` | `int64` | positive component count | Number of ordered STL sources represented in the VTP file. |
| `stl_paths_json` | JSON string containing a list of strings | resolved absolute paths | Ordered STL source paths corresponding to `stl_index=0,1,...`. JSON non-ASCII characters are escaped for VTK portability; parse the JSON to recover the original Unicode paths. |

Other string field data is stored in VTK string arrays and round-trips Unicode
through supported readers. Reader-library in-memory types are not part of the
VTP file specification.

## Hypersonic field data

Each Hypersonic-only field has shape `(1,)` and string storage.

| Field | Values | Meaning |
|---|---|---|
| `windward_eq_used` | normalized selector or semicolon-separated selectors | Normalized windward pressure-method specification used by the model. One selector applies to all components; otherwise entries correspond to components in `stl_index` order. |
| `leeward_eq_used` | normalized selector or semicolon-separated selectors | Normalized leeward pressure-method specification used by the model, with the same one-or-per-component rule. |

FMF records its resolved `mode`, `out_S`, and `out_Ti_K` in the
[Summary CSV reference](summary-csv.md#fmf-resolved-state-fields).

The original numeric angle inputs are retained before periodic reduction.
No stability-angle source flag or resolved sine-sideslip field is exported.
See [attitude conventions](../methods/coordinate-and-attitude-conventions.md#stability-angle-and-numerical-boundaries)
for the common fallback threshold. The former `alpha_t_deg_resolved` and
`beta_t_deg_resolved` fields have been replaced; consumers must use the direction
and stability-angle fields above. Signatures now use `panelsolver.case` v2;
old artifacts are available for manual inspection but do not automatically match.
