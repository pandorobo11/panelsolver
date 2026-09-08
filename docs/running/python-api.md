# Python API reference

Panel Solver provides a small synchronous API for one-case, in-memory
calculation. It reads the requested STL files and returns a `SolveResult` in
memory.

Use this API to work directly with coefficients and per-panel arrays.
The [CLI](cli.md) and [GUI](gui.md) provide case-table
workflows for writing result files.

## Minimal examples

Both examples assume that a readable, valid `model.stl` already exists in the
process working directory. To try them with the supplied geometry, copy
`examples/geometry/plate.stl` from the [Quickstart](../getting-started/quickstart.md)
examples to `model.stl` there. The returned coefficients describe the whole case,
while the scalar arrays provide one value per triangular panel.

### FMF

<!-- python-api-example: fmf -->
```python
from panelsolver import FMFCase, resolve_attitude, solve_fmf

attitude = resolve_attitude(5.0, 0.0, "beta_tan")
case = FMFCase(
    case_id="fmf-example",
    stl_paths=("model.stl",),
    stl_scale_m_per_unit=1.0,
    attitude=attitude,
    Aref_m2=1.0,
    moment_reference_stl_m=(0.0, 0.0, 0.0),
    Lref_Cl_m=1.0,
    Lref_Cm_m=1.0,
    Lref_Cn_m=1.0,
    speed_ratio=7.0,
    translational_temperature_k=1000.0,
    wall_temperature_k=300.0,
)
result = solve_fmf(case)

print(result.coefficients.CD, result.coefficients.CL)
local_traction = result.local_loads.traction_coeff_stl
normal_traction = result.local_loads.cell_scalars["normal_traction_coeff"]
print(local_traction.shape, normal_traction.shape)
```

### Hypersonic

<!-- python-api-example: hypersonic -->
```python
from panelsolver import HypersonicCase, resolve_attitude, solve_hypersonic

attitude = resolve_attitude(10.0, 0.0)
case = HypersonicCase(
    case_id="hypersonic-example",
    stl_paths=("model.stl",),
    stl_scale_m_per_unit=1.0,
    attitude=attitude,
    Aref_m2=1.0,
    moment_reference_stl_m=(0.0, 0.0, 0.0),
    Lref_Cl_m=1.0,
    Lref_Cm_m=1.0,
    Lref_Cn_m=1.0,
    mach=6.0,
    gamma=1.4,
)
result = solve_hypersonic(case)

print(result.coefficients.CA, result.coefficients.Cm)
cp = result.local_loads.cell_scalars["cp"]
shielded = result.flow_state.shielded
print(cp.shape, shielded.shape, result.case_signature)
```

## Supported imports and scope

The supported Python API consists of exactly these seven names, imported from
the package root:

```python
from panelsolver import (
    FMFCase,
    HypersonicCase,
    ResolvedAttitude,
    SolveResult,
    resolve_attitude,
    solve_fmf,
    solve_hypersonic,
)
```

Compatibility covers these package-root imports and the returned fields
documented below. Nested result objects are accessed through `SolveResult`;
their defining modules and direct constructors remain implementation details.
See [Compatibility policy](../product-reference/compatibility.md) for the full support boundary.

## Attitude resolution

```text
resolve_attitude(
    alpha_deg: float,
    beta_or_bank_deg: float,
    attitude_input: str | None = None,
) -> ResolvedAttitude
```

Both input angles are finite real numbers in degrees. `attitude_input` is
trimmed and normalized case-insensitively. `None` and blank text select
`beta_tan`.

| Mode | First value | Second value | Accepted domain |
|---|---|---|---|
| `beta_tan` | tangent angle of attack | tangent sideslip | first any finite periodic angle; second -90° to 90° inclusive; simultaneous tangent poles rejected |
| `beta_sin` | tangent angle of attack | sine-definition sideslip | first any finite periodic angle; second -90° to 90° inclusive |
| `bank` | included angle | bank angle | both any finite angle |

The resolver converts every mode directly to a unit flow vector and a common
stability angle used by both solve functions. The equations, axes, signs, and periodic
behavior are in [Coordinate and attitude conventions](../methods/coordinate-and-attitude-conventions.md).

### `ResolvedAttitude`

| Field | Type / shape | Unit / values | Meaning |
|---|---|---|---|
| `velocity_hat_stl` | NumPy `float64` vector `(3,)` | unit vector | Resolved direction in which the freestream travels, expressed in STL axes. |
| `alpha_deg` | `float` | degrees | Original first input value before periodic reduction. |
| `alpha_stability_deg` | `float` | degrees | Derived stability angle; read-only constructor result. |
| `beta_or_bank_deg` | `float` | degrees | Original second input value before periodic reduction. |
| `input_mode` | `str` | `beta_tan`, `beta_sin`, or `bank` | Normalized representation used for the input pair. |

`ResolvedAttitude` also supports direct construction:

```text
ResolvedAttitude(
    velocity_hat_stl: np.ndarray,
    alpha_deg: float,
    beta_or_bank_deg: float,
    input_mode: str,
)
```

The vector must be a finite, nonzero real vector with shape `(3,)`; construction
normalizes it to a read-only unit vector. Both original angle fields must be
finite and provide provenance; the mode is normalized. The supplied vector is
authoritative for direct construction, and alpha_stability_deg is always derived
from it using the common fallback rule. Prefer resolve_attitude() to construct
the vector from validated input angles and preserve their relationship.

## `FMFCase`

```text
FMFCase(
    case_id: str,
    stl_paths: Sequence[str | Path],
    stl_scale_m_per_unit: float,
    attitude: ResolvedAttitude,
    Aref_m2: float,
    moment_reference_stl_m: Sequence[float],
    Lref_Cl_m: float,
    Lref_Cm_m: float,
    Lref_Cn_m: float,
    speed_ratio: float,
    translational_temperature_k: float,
    wall_temperature_k: float,
    shielding: bool = False,
    ray_backend: str = "auto",
)
```

Fields appear below in constructor order. A dash in **Default** means the field
is required.

| Field | Type | Default | Unit / values | Meaning |
|---|---|---|---|---|
| `case_id` | `str` | — | portable text | Case ID. It is normalized to Unicode NFC and must satisfy the portable filename rules described under [Shared case requirements](#shared-case-requirements). |
| `stl_paths` | non-empty sequence of `str` or `Path` | — | ordered paths | STL components in component-ID order. Supply a tuple or list even for one component. |
| `stl_scale_m_per_unit` | real number | — | m / STL unit, > 0 | Scale applied to every input STL coordinate. |
| `attitude` | `ResolvedAttitude` | — | — | Resolved flow direction and tangent angles used by the calculation. |
| `Aref_m2` | real number | — | m², > 0 | Global reference area used for total and component integration. |
| `moment_reference_stl_m` | sequence of 3 real numbers | — | m, STL frame | Moment reference point `(x, y, z)`. |
| `Lref_Cl_m` | real number | — | m, > 0 | Roll-moment reference length. |
| `Lref_Cm_m` | real number | — | m, > 0 | Pitch-moment reference length. |
| `Lref_Cn_m` | real number | — | m, > 0 | Yaw-moment reference length. |
| `speed_ratio` | real number | — | dimensionless, > 0 | Sentman molecular speed ratio; corresponds to case-table `S`. |
| `translational_temperature_k` | real number | — | K, > 0 | Incident freestream translational static temperature; corresponds to `Ti_K`. |
| `wall_temperature_k` | real number | — | K, > 0 | Wall/diffusely reflected molecular temperature; corresponds to `Tw_K`. |
| `shielding` | `bool` | `False` | `False` or `True` | Enables the common ray-occlusion shielding calculation. Corresponds to `shielding_on`. |
| `ray_backend` | `str` | `"auto"` | `auto`, `rtree`, or `embree` | Requested shielding backend. It is still validated when shielding is disabled. |

`FMFCase` accepts resolved Sentman **Mode A** inputs: speed ratio, incident
static temperature, and wall temperature. For Mode B (`Mach` and `Altitude_km`),
use a CLI or GUI case table. See the [FMF solver page](../methods/fmf.md#flow-inputs)
for the physical meaning of both modes.

For comparison with a case table, `stl_paths` is the ordered in-memory form of
semicolon-separated `stl_path`, and `moment_reference_stl_m` combines
`ref_x_m`, `ref_y_m`, and `ref_z_m`.

## `HypersonicCase`

```text
HypersonicCase(
    case_id: str,
    stl_paths: Sequence[str | Path],
    stl_scale_m_per_unit: float,
    attitude: ResolvedAttitude,
    Aref_m2: float,
    moment_reference_stl_m: Sequence[float],
    Lref_Cl_m: float,
    Lref_Cm_m: float,
    Lref_Cn_m: float,
    mach: float,
    gamma: float,
    windward_equation: str = "newtonian",
    leeward_equation: str = "shield",
    shielding: bool = False,
    ray_backend: str = "auto",
)
```

| Field | Type | Default | Unit / values | Meaning |
|---|---|---|---|---|
| `case_id` | `str` | — | portable text | Case ID, normalized to Unicode NFC. |
| `stl_paths` | non-empty sequence of `str` or `Path` | — | ordered paths | STL components in component-ID order. |
| `stl_scale_m_per_unit` | real number | — | m / STL unit, > 0 | Scale applied to every input STL coordinate. |
| `attitude` | `ResolvedAttitude` | — | — | Resolved flow direction and tangent angles used by the calculation. |
| `Aref_m2` | real number | — | m², > 0 | Global reference area used for total and component integration. |
| `moment_reference_stl_m` | sequence of 3 real numbers | — | m, STL frame | Moment reference point `(x, y, z)`. |
| `Lref_Cl_m` | real number | — | m, > 0 | Roll-moment reference length. |
| `Lref_Cm_m` | real number | — | m, > 0 | Pitch-moment reference length. |
| `Lref_Cn_m` | real number | — | m, > 0 | Yaw-moment reference length. |
| `mach` | real number | — | dimensionless, > 0 | Freestream Mach number; corresponds to case-table `Mach`. |
| `gamma` | real number | — | dimensionless, > 1 | Specific-heat ratio; corresponds to case-table `gamma`. |
| `windward_equation` | `str` | `"newtonian"` | `newtonian`, `modified_newtonian`, `tangent_wedge`, or `tangent_cone` | Windward equation selection; corresponds to `windward_eq`. |
| `leeward_equation` | `str` | `"shield"` | `shield` or `prandtl_meyer` | Leeward equation selection; corresponds to `leeward_eq`. |
| `shielding` | `bool` | `False` | `False` or `True` | Enables common geometric ray shielding. This is distinct from the leeward `shield` pressure rule. |
| `ray_backend` | `str` | `"auto"` | `auto`, `rtree`, or `embree` | Requested shielding backend. |

Each equation field accepts either one selector applied to every component or
exactly one semicolon-separated selector per ordered STL component. Entries are
trimmed and normalized case-insensitively; empty entries and mismatched counts
are invalid. `modified_newtonian`, `tangent_wedge`, `tangent_cone`, and
`prandtl_meyer` require `mach > 1`. The equations and physical applicability
limits are in [Hypersonic Panel Methods](../methods/hypersonic.md); the
case-table names and rules are in the
[Hypersonic input reference](../inputs/hypersonic-input.md).

As with `FMFCase`, `stl_paths` corresponds to ordered `stl_path`, while
`moment_reference_stl_m` combines `ref_x_m`, `ref_y_m`, and `ref_z_m`.

## Shared case requirements

- `case_id` must be non-empty portable Unicode text: not `.` or `..`, not a
  Windows-reserved filename, without path/control or Windows-invalid
  characters, and without a trailing dot or space. It is normalized to NFC.
- `stl_paths` must be a non-empty ordered sequence whose entries are non-empty
  `str` or `pathlib.Path` values. Component ID zero corresponds to the first
  path, ID one to the second, and so on. Relative API paths are resolved from
  the process working directory.
- `stl_scale_m_per_unit`, `Aref_m2`, and all three reference lengths must be
  finite and strictly positive. `moment_reference_stl_m` must contain exactly
  three finite coordinates in metres in the STL frame. Numeric booleans are
  not accepted as real-number inputs.
- `attitude` must be a `ResolvedAttitude`. Its unit vector and resolved tangent
  angles are used by shielding, model evaluation, and integration.
- `shielding` must be boolean. `ray_backend` accepts `auto`, `rtree`, or
  `embree`; `auto` selects an available supported backend when shielding is
  enabled. See [Ray shielding](../methods/ray-shielding.md#backend-behavior).
- Model inputs must satisfy the domain-specific ranges in the case tables
  above. Meshes must be readable, non-empty, finite, consistently orientable,
  and free of degenerate faces after applying the STL scale.

Validation occurs during construction and solving as described under
[Validation and errors](#validation-and-errors).

## Solve functions

```text
solve_fmf(case: FMFCase) -> SolveResult
solve_hypersonic(case: HypersonicCase) -> SolveResult
```

Each function accepts only its matching case type and runs synchronously. It
loads the ordered STL sources and uses the same geometry loading, shielding,
model, integration, component aggregation, and case-signature pipeline as an
equivalent documented case-table calculation. It returns the result in memory,
so equivalent inputs produce the same numerical result as the CLI/GUI
case-table workflow.

## `SolveResult`

Either solve function returns a `SolveResult` with the following fields:

| Field | Type / shape | Unit / values | Meaning |
|---|---|---|---|
| `attitude` | `ResolvedAttitude` | original inputs and resolved state | Original numeric angles, normalized mode, unit direction and stability angle. |
| `coefficients` | nested coefficient result | see below | Integrated whole-case force and moment coefficients. |
| `components` | ordered tuple of component results | one per STL | Per-component integrated coefficients and counts, in ascending component-ID/input-STL order. |
| `geometry` | nested per-face geometry | `n_faces` rows | SI-scaled geometry used by the calculation. |
| `flow_state` | nested flow state | `n_faces` mask | Resolved flow direction and geometric shielding mask. |
| `local_loads` | nested model result | `n_faces` rows | Local traction plus model visualization/diagnostic scalars and resolved model metadata. |
| `case_signature` | `str` | 64 lowercase hexadecimal characters | SHA-256 value that identifies the evaluated geometry, normalized case, model algorithm, and resolved shielding configuration. |
| `ray_backend_used` | `str` | `not_used`, `rtree`, or `embree` | Effective ray backend. `not_used` means shielding was disabled. |
| `warnings` | tuple of `str` | possibly empty | User-visible warnings produced while loading/executing the case. Exact warning text is not a stable taxonomy, and warnings are not fields in Summary CSV or VTP. |

### Coefficients

`result.coefficients` and every `component.integrated` expose the same fields
and scalar properties:

| Field / property | Type / shape | Unit / frame | Meaning |
|---|---|---|---|
| `force_coeff_stl` | NumPy `float64` vector `(3,)` | dimensionless, STL frame | Integrated force-coefficient vector before frame transformation. |
| `force_coeff_body` | NumPy `float64` vector `(3,)` | dimensionless, body frame | Integrated force coefficient after the fixed STL-to-body transform. |
| `force_coeff_stability` | NumPy `float64` vector `(3,)` | dimensionless, stability frame | Body force rotated using derived `alpha_stability_deg`. |
| `moment_area_coeff_body_m` | NumPy `float64` vector `(3,)` | m, body frame | Area-normalized moment numerator before division by the three reference lengths. |
| `moment_coeff_body` | NumPy `float64` vector `(3,)` | dimensionless, body frame | Roll-, pitch-, and yaw-axis moment coefficients after reference-length division. |
| `CA`, `CY`, `CN` | `float` | dimensionless | Axial, side, and normal force coefficients. |
| `Cl`, `Cm`, `Cn` | `float` | dimensionless | Roll, pitch, and yaw moment coefficients. |
| `CD`, `CL` | `float` | dimensionless | Drag and lift coefficients in stability axes. |

Full transforms, signs, area normalization, and moment definitions are in
[Load and coefficient conventions](../methods/load-and-coefficient-conventions.md).

### Components

`result.components` contains one item for each input STL, ordered by ascending
zero-based `component_id`, which is the same as ordered `stl_paths`. Each item
exposes:

| Field | Type | Meaning |
|---|---|---|
| `component_id` | non-negative `int` | Zero-based input-STL ID. |
| `integrated` | nested coefficient result | Coefficients for only this component's faces, using the same global reference area, moment reference, and reference lengths as the total. |
| `face_count` | non-negative `int` | Number of triangular faces in the component. |
| `shielded_face_count` | non-negative `int` | Number of its faces geometrically ray-shielded. |

### Geometry

| `result.geometry` field | Type / shape | Unit / values | Meaning |
|---|---|---|---|
| `centers_stl_m` | NumPy `float64` array `(n_faces, 3)` | m, STL frame | Triangle centroids used for moments. |
| `normals_out_stl` | NumPy `float64` array `(n_faces, 3)` | outward unit vectors, STL frame | Triangle normals used by shielding and the physical model. |
| `areas_m2` | NumPy `float64` array `(n_faces,)` | m², positive | Triangle areas used by integration. |
| `component_ids` | NumPy `int64` array `(n_faces,)` | non-negative IDs | Per-face input-STL assignment. |
| `n_faces` | `int` | positive count | Number of faces represented by every per-face result. |
| `unique_component_ids` | tuple of `int` | ascending IDs | Component IDs present in the geometry. |

### Flow state

| `result.flow_state` field | Type / shape | Unit / values | Meaning |
|---|---|---|---|
| `velocity_hat_stl` | NumPy `float64` vector `(3,)` | unit vector, STL frame | Resolved direction in which the freestream travels. |
| `shielded` | NumPy boolean array `(n_faces,)` | `False` or `True` | Geometric ray-occlusion mask. Shielded faces have exact-zero local traction. |
| `n_faces` | `int` | positive count | Number of entries in `shielded`. |

See [Ray shielding](../methods/ray-shielding.md) for the geometric method and backend
behavior.

### Local loads

| `result.local_loads` field | Type / shape | Unit / values | Meaning |
|---|---|---|---|
| `traction_coeff_stl` | NumPy `float64` array `(n_faces, 3)` | dimensionless, STL frame | Model-returned local traction coefficient **before** panel-area/reference-area weighting. |
| `cell_scalars` | immutable mapping from `str` to per-face NumPy arrays `(n_faces,)` | model-specific | Visualization/diagnostic values described below. |
| `metadata` | immutable mapping | model-specific finite scalar/text values | Resolved model inputs actually used, described below. |
| `n_faces` | `int` | positive count | Number of local traction rows and entries in every cell scalar. |

The current scalar mappings are:

| Domain | `cell_scalars` keys | Meaning |
|---|---|---|
| FMF | `normal_traction_coeff`, `tangential_traction_coeff`, `theta_deg` | Local normal/tangential Sentman traction components and the normal-to-flow angle. |
| Hypersonic | `cp`, `theta_deg` | Local pressure coefficient and the normal-to-flow angle. |

Each current scalar array is `float64`. The model-specific scalar definitions
are in the [FMF](../methods/fmf.md) and
[Hypersonic](../methods/hypersonic.md) solver pages, while the shared
`theta_deg` definition is in
[Load and coefficient conventions](../methods/load-and-coefficient-conventions.md#common-panel-angle).
The corresponding VTP arrays are documented under
[common cell data](../results/vtp.md#common-cell-data) and
[model-specific cell data](../results/vtp.md#model-specific-cell-data).

FMF metadata contains `mode` (always `A` for this API), `S`, `Ti_K`, and
`Tw_K`. Hypersonic metadata contains `Mach`, `gamma`, `windward_eq`, and
`leeward_eq`; equation values are their normalized one-or-per-component
strings.

To obtain the per-face force-coefficient contribution stored as VTP
`C_face_stl`, apply panel-area/reference-area weighting to the local traction:

```python
C_face_stl = (
    result.local_loads.traction_coeff_stl
    * result.geometry.areas_m2[:, None]
    / case.Aref_m2
)
```

Use the resulting `C_face_stl` for force summation and moment integration, as
specified in [Load and coefficient conventions](../methods/load-and-coefficient-conventions.md#local-traction-and-panel-contributions).

### Arrays and mutability

Result arrays are C-contiguous, read-only NumPy buffers: central floating arrays
use `float64`, component IDs use `int64`, and the shielding mask uses boolean
dtype. Nested result objects and scalar/metadata mappings are also read-only.
Make an explicit copy when mutable working data is needed, for example `result.geometry.centers_stl_m.copy()`.

## API ↔ Summary CSV / VTP correspondence

This table maps API fields to Summary CSV columns and VTP arrays. The result
pages define output order, stored dtypes, blank conditions, and metadata
that exists only in output files.

| In-memory API value | Output-file field |
|---|---|
| `coefficients.CA`, `CY`, `CN`, `Cl`, `Cm`, `Cn`, `CD`, `CL` | Same-named Summary CSV columns on the `total` row. |
| `components[*].integrated` | Same coefficient fields on Summary `component` rows. |
| Component IDs and counts | Summary `component_id`, `faces`, and `shielded_faces`; components use input-STL order. |
| `case_signature` | Summary and VTP `case_signature`. |
| `ray_backend_used` | Summary and VTP `ray_backend_used`. |
| `geometry.areas_m2` | VTP `area_m2`. |
| Columns of `geometry.centers_stl_m` | VTP `center_x_stl_m`, `center_y_stl_m`, and `center_z_stl_m`. |
| `geometry.component_ids` | VTP `stl_index` (stored as `int32`). |
| `flow_state.shielded` | VTP `shielded` (stored as `uint8`). |
| `local_loads.cell_scalars` | Same-named VTP diagnostic/model cell data. |
| `local_loads.traction_coeff_stl` | Not written directly; VTP `C_face_stl` is its `area_m2 / Aref_m2` weighted contribution. |

The API does not return output paths, timestamps, solver-version provenance,
VTP points/connectivity, or the original case-table row. See the
[Summary CSV](../results/summary-csv.md) and [VTP](../results/vtp.md)
references for those fields.

## Validation and errors

Passing anything other than an `FMFCase` to `solve_fmf()`, or anything other
than a `HypersonicCase` to `solve_hypersonic()`, raises `TypeError`. Invalid
attitude modes/ranges, case IDs, common physical values, model selectors and
ranges, shielding configuration, missing/unreadable STL sources, and invalid
mesh geometry are rejected with value errors from the relevant validation
boundary.

Case construction normalizes and validates the portable ID, path sequence,
three-value moment reference, and `ResolvedAttitude` type. Numerical, model,
backend, and mesh checks can occur during solving. Callers should handle
built-in `TypeError` and `ValueError` around both stages; finer validation timing,
private exception subclasses, and exact messages are outside the stable API.

## Filesystem and side-effect boundary

The solve functions read every path in `stl_paths` and return their results in
memory. They create no output directories or result files (Summary CSV, VTP,
PNG, or checkpoints). Use the [CLI](cli.md) or
[GUI](gui.md) to write calculation outputs.
