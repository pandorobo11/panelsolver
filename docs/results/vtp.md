# VTP reference

This page is the canonical semantic contract for Panel Solver VTP artifacts.
Each saved `.vtp` is VTK XML PolyData containing the validated case mesh,
face-aligned result arrays, and case-level provenance. The
[Summary CSV reference](summary-csv.md) defines integrated and component rows;
per-case path rules are in [Case files](../user-guide/case-files.md), and write-
failure behavior is in
[Batch execution and recovery](../user-guide/batch-execution-and-recovery.md).

## What is contractual

The supported contract is the named mesh, cell-data, and field-data content
described below. Numeric values are compared with the tolerance appropriate to
the selected physical model. XML element order, binary encoding details,
compression, temporary files, and byte-for-byte file identity are not
compatibility contracts.

There are no Panel Solver-defined point-data arrays. Every cell-data array is
aligned with the VTP triangle-cell order. Array names are case-sensitive.

## PolyData mesh

The VTP contains the loaded, validated, SI-scaled panel mesh used by the
calculation.

| Element | Association | Semantic shape | Projection dtype | Unit | Meaning |
|---|---|---:|---|---|---|
| Points | point coordinates | `(n_vertices, 3)` | `float64` | m | Vertex coordinates in the STL frame after applying `stl_scale_m_per_unit`. |
| Triangle connectivity | polygon cells | `n_faces` triangles of 3 vertex indices | `int64` VTK-ID projection | — | Face topology and face order used by geometry, shielding, model evaluation, and every cell-data array. |

The in-memory VTP projection represents each triangle as flattened VTK
connectivity `[3, i0, i1, i2]`; ordinary VTK/PyVista readers expose the same
content as triangle cells.

## Common cell data

| Array | Shape | Stored dtype | Unit | Meaning | Role in integration |
|---|---:|---|---|---|---|
| `C_face_stl` | `(n_faces, 3)` | `float64` | dimensionless | Per-face force-coefficient contribution in STL axes after multiplying local traction by `area_m2 / Aref_m2`. | **Integrated value.** Summing all rows gives the total STL-frame force coefficient; summing one `stl_index` subset gives that component's force coefficient. Moments use the same face force with the configured lever arm. |
| `area_m2` | `(n_faces,)` | `float64` | m² | Triangle area used by the calculation. | Supplies the area factor already incorporated into `C_face_stl`; do not multiply `C_face_stl` by area again. |
| `center_x_stl_m` | `(n_faces,)` | `float64` | m | Face-centroid X coordinate in the STL frame. | Geometry/provenance; the three center arrays define the moment lever arm with the configured reference point. |
| `center_y_stl_m` | `(n_faces,)` | `float64` | m | Face-centroid Y coordinate in the STL frame. | Geometry/provenance; used with the other center coordinates for moments. |
| `center_z_stl_m` | `(n_faces,)` | `float64` | m | Face-centroid Z coordinate in the STL frame. | Geometry/provenance; used with the other center coordinates for moments. |
| `shielded` | `(n_faces,)` | `uint8` | `0` or `1` | Ray-occlusion mask. `1` means the panel was geometrically shielded for this case. | Shielded panels have exact-zero local traction and therefore exact-zero `C_face_stl`. A Hypersonic leeward `shield` selector is a different pressure rule and does not set this mask. |
| `stl_index` | `(n_faces,)` | `int32` | zero-based component ID | Input-STL/component assignment in ordered `stl_path` order. | Selects the faces used for each component row in the Summary CSV. |
| `theta_deg` | `(n_faces,)` | `float64` | degrees | Angle `acos(n_out_stl · Vhat_stl)` between the outward panel normal and the resolved flow direction, in the range 0–180 degrees. | Diagnostic/model geometry scalar. It is not summed or separately integrated. |

The relationship between `C_face_stl`, whole-case coefficients, frames, signs,
and moments is defined in
[Numerical conventions](../reference/numerical-conventions.md#loads-and-normalization).

## Model-specific cell data

### Hypersonic

| Array | Shape | Stored dtype | Unit | Meaning | Role in integration |
|---|---:|---|---|---|---|
| `cp` | `(n_faces,)` | `float64` | dimensionless | Local pressure coefficient selected by the panel's windward or leeward pressure method. It may be negative for Prandtl–Meyer expansion and is zero on ray-shielded faces. | Source diagnostic for the pressure-only local traction `-cp * n_out_stl`. The engine integrates the resulting traction vector, not this scalar directly. |

See [Hypersonic Panel Methods](../solvers/hypersonic.md) for each pressure
equation and its limits.

### FMF

| Array | Shape | Stored dtype | Unit | Meaning | Role in integration |
|---|---:|---|---|---|---|
| `normal_traction_coeff` | `(n_faces,)` | `float64` | dimensionless | Component of the local Sentman traction opposite the outward normal, `-tau · n_out_stl`, before multiplying by panel area or dividing by reference area. | Visualization/diagnostic scalar derived from the local `traction_coeff_stl` before area/reference-area weighting. It is not independently integrated. |
| `tangential_traction_coeff` | `(n_faces,)` | `float64` | dimensionless | Component of local Sentman traction along the resolved flow direction projected into the panel plane, before area/reference-area scaling. It is exactly zero where that in-plane direction is undefined at normal incidence. | Visualization/diagnostic scalar derived from the local `traction_coeff_stl` before area/reference-area weighting. It is not independently integrated. |

See [Free Molecular Flow](../solvers/fmf.md) for the Sentman equation and the
exact normal and tangential projections.

`Cp_n` is not emitted by either domain.

## Common field data

Every common field-data array has semantic shape `(1,)`.

| Field | Stored dtype / format | Unit / values | Meaning |
|---|---|---|---|
| `alpha_t_deg_resolved` | `float64` | degrees | Resolved tangent angle of attack used for this calculation. It matches the Summary CSV field of the same name. |
| `attitude_input_used` | string | `beta_tan`, `beta_sin`, or `bank` | Canonical attitude representation used to interpret the two input angles. The corresponding Summary CSV field is `out_attitude_input`. |
| `beta_t_deg_resolved` | `float64` | degrees | Resolved tangent sideslip angle used for this calculation. It matches the Summary CSV field of the same name. |
| `case_id` | string | portable case text | Case identifier and planned artifact basename. |
| `case_signature` | string; 64-character lowercase hexadecimal SHA-256 | — | Canonical current case/artifact identity. It corresponds to the Summary CSV value, and the GUI compares it with the currently loaded case for automatic display. |
| `ray_backend_used` | string | `not_used`, `rtree`, or `embree` | Effective ray backend. `not_used` means ray shielding was disabled. |
| `solver_version` | string | installed version | `panelsolver` distribution version that generated the artifact. |
| `stl_count` | `int64` | positive component count | Number of ordered STL sources represented in the artifact. |
| `stl_paths_json` | JSON string containing a list of strings | resolved absolute paths | Ordered STL source paths corresponding to `stl_index=0,1,...`. JSON non-ASCII characters are escaped for VTK portability; parse the JSON to recover the original Unicode paths. |

Other string field data is stored as semantic VTK text and round-trips Unicode
through supported readers; its internal bridge representation is not a
user-facing type distinction.

## Hypersonic field data

Each Hypersonic-only field has semantic shape `(1,)` and string storage.

| Field | Values | Meaning |
|---|---|---|
| `windward_eq_used` | canonical selector or semicolon-separated selectors | Normalized windward pressure-method specification used by the model. One selector applies to all components; otherwise entries correspond to components in `stl_index` order. |
| `leeward_eq_used` | canonical selector or semicolon-separated selectors | Normalized leeward pressure-method specification used by the model, with the same one-or-per-component rule. |

FMF does not add model-specific VTP field data. Its resolved `mode`, `out_S`,
and `out_Ti_K` are recorded in the
[Summary CSV reference](summary-csv.md#fmf-resolved-state-fields).

## Relating VTP to Summary CSV

For a current saved artifact:

- VTP `case_id`, `case_signature`, `solver_version`,
  `alpha_t_deg_resolved`, `beta_t_deg_resolved`, and `ray_backend_used`
  correspond to the case's Summary CSV values.
- Summary `vtp_path` points to the VTP only on the `total` row.
- `stl_index` partitions `C_face_stl` into the Summary component scopes.
- Summing `C_face_stl` over every face produces the STL-frame force coefficient
  from which `CA`, `CY`, `CN`, `CD`, and `CL` are transformed. The moment
  coefficients additionally use face centers, the moment reference, and the
  three reference lengths.
- A blank Summary `vtp_path` means no VTP was successfully written for that case
  during the current run, even if an older file exists at the planned path.

The GUI automatically displays an existing VTP for a selected case only when
both `case_id` and `case_signature` match. Manual **Open VTP...** remains a
generic inspection path; see the [GUI guide](../user-guide/gui.md).
