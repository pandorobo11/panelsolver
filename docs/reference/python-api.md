# Python API reference

Panel Solver provides a small synchronous API for one-case, in-memory
calculation. It reads the requested STL files but does not serialize result
artifacts.

## Supported imports and scope

The canonical supported Python API is exactly these seven names, imported from
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

`panelsolver.api`, `panelsolver.core`, `panelsolver.app`,
`panelsolver.models`, domain adapters, registries, execution requests,
lower-level solvers and helpers, and predecessor-product modules are not stable
import surfaces. Objects nested inside `SolveResult` are documented below so
callers can use the returned values; their defining module paths and direct
constructors are not part of the supported API.

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
| `beta_tan` | tangent angle of attack | tangent sideslip | both strictly between -90° and 90° |
| `beta_sin` | tangent angle of attack | sine-definition sideslip | first strictly between -90° and 90°; second any finite angle |
| `bank` | included angle | bank angle | both any finite angle |

The resolver converts every mode to the common tangent-angle representation
used by both solve functions. The complete equations, axes, signs, and periodic
behavior are in [Coordinate and attitude conventions](coordinate-and-attitude-conventions.md);
the concise accepted-input rules are also listed in
[Case files](../user-guide/case-files.md#attitude-modes).

### `ResolvedAttitude`

| Field | Type / shape | Unit / values | Meaning |
|---|---|---|---|
| `velocity_hat_stl` | NumPy `float64` vector `(3,)` | unit vector | Resolved direction in which the freestream travels, expressed in STL axes. |
| `alpha_t_deg` | `float` | degrees | Resolved tangent angle of attack. |
| `beta_t_deg` | `float` | degrees | Resolved tangent sideslip. |
| `input_mode` | `str` | `beta_tan`, `beta_sin`, or `bank` | Canonical representation used for the input pair. |

`ResolvedAttitude` is itself part of the package-root API and supports direct
construction:

```text
ResolvedAttitude(
    velocity_hat_stl: np.ndarray,
    alpha_t_deg: float,
    beta_t_deg: float,
    input_mode: str,
)
```

The vector must be a finite, nonzero real vector with shape `(3,)`; construction
normalizes it to a read-only unit vector. Both resolved angles must be finite,
and the mode is normalized with the same rules as `resolve_attitude()`. A solve
also requires the vector and resolved tangent angles to describe the same
direction. Prefer `resolve_attitude()` for ordinary use because it establishes
that relationship from one documented input representation.

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
| `case_id` | `str` | — | portable text | Case identity. It is normalized to Unicode NFC and must satisfy the portable filename rules described under [Shared case requirements](#shared-case-requirements). |
| `stl_paths` | non-empty sequence of `str` or `Path` | — | ordered paths | STL components in component-ID order. A single string or `Path` is not a sequence-of-components value; wrap it in a tuple or list. |
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

The package-root `FMFCase` accepts resolved Sentman **Mode A only**:
`speed_ratio`, `translational_temperature_k`, and `wall_temperature_k`. The
case-table Mode B workflow derives speed ratio and temperature from `Mach` and
`Altitude_km`; it is available through the CLI and GUI, not as another
`FMFCase` constructor mode. See the [FMF input reference](fmf-input.md) and
[FMF solver page](../solvers/fmf.md).

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
| `case_id` | `str` | — | portable text | Case identity, normalized to Unicode NFC. |
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
limits are in [Hypersonic Panel Methods](../solvers/hypersonic.md); the
case-table names and rules are in the
[Hypersonic input reference](hypersonic-input.md).

As with `FMFCase`, `stl_paths` corresponds to ordered `stl_path`, while
`moment_reference_stl_m` combines `ref_x_m`, `ref_y_m`, and `ref_z_m`.

## Shared case requirements

- `case_id` must be non-empty portable Unicode text: not `.` or `..`, not a
  Windows-reserved filename, without path/control or Windows-invalid
  characters, and without a trailing dot or space. It is normalized to NFC.
- `stl_paths` must be a non-empty ordered sequence whose entries are non-empty
  `str` or `pathlib.Path` values. Component ID zero corresponds to the first
  path, ID one to the second, and so on. Relative API paths are resolved from
  the process working directory; unlike case-table paths, there is no
  case-table directory to use as an anchor.
- `stl_scale_m_per_unit`, `Aref_m2`, and all three reference lengths must be
  finite and strictly positive. `moment_reference_stl_m` must contain exactly
  three finite coordinates in metres in the STL frame. Numeric booleans are
  not accepted as real-number inputs.
- `attitude` must be a `ResolvedAttitude`. Its unit vector and resolved tangent
  angles are used by shielding, model evaluation, and integration.
- `shielding` must be boolean. `ray_backend` accepts `auto`, `rtree`, or
  `embree`; `auto` selects an available supported backend when shielding is
  enabled. See [Ray shielding](ray-shielding.md#backend-behavior).
- Model inputs must satisfy the domain-specific ranges in the case tables
  above. Meshes must be readable, non-empty, finite, consistently orientable,
  and free of degenerate faces after applying the STL scale.

The case constructors normalize and validate the portable ID, require a
non-empty path sequence, require a three-value moment reference, and require a
`ResolvedAttitude`. Common numerical, model, backend, and mesh validation can
occur while solving. Treat the validity requirements as the contract; do not
depend on more specific validation timing.

## Solve functions

```text
solve_fmf(case: FMFCase) -> SolveResult
solve_hypersonic(case: HypersonicCase) -> SolveResult
```

Each function accepts only its matching case type and runs synchronously. It
loads the ordered STL sources, uses the same canonical geometry, shielding,
model, integration, component-aggregation, and case-signature pipeline as an
equivalent documented case-table calculation, and returns its result in
memory. Equivalent inputs therefore produce the same numerical result as the
CLI/GUI case-table workflow.

These functions do not expose registry, request, or cache controls.

## `SolveResult`

`SolveResult` contains the complete in-memory result surface returned by either
solve function:

| Field | Type / shape | Unit / values | Meaning |
|---|---|---|---|
| `coefficients` | nested coefficient result | see below | Integrated whole-case force and moment coefficients. |
| `components` | ordered tuple of component results | one per STL | Per-component integrated coefficients and counts, in ascending component-ID/input-STL order. |
| `geometry` | nested per-face geometry | `n_faces` rows | SI-scaled geometry used by the calculation. |
| `flow_state` | nested flow state | `n_faces` mask | Resolved flow direction and geometric shielding mask. |
| `local_loads` | nested model result | `n_faces` rows | Local traction plus model visualization/diagnostic scalars and resolved model metadata. |
| `case_signature` | `str` | 64 lowercase hexadecimal characters | Canonical current case/artifact identity for the evaluated geometry, normalized case, model algorithm, and resolved shielding configuration. |
| `ray_backend_used` | `str` | `not_used`, `rtree`, or `embree` | Effective ray backend. `not_used` means shielding was disabled. |
| `warnings` | tuple of `str` | possibly empty | User-visible warnings produced while loading/executing the case. Exact warning text is not a stable taxonomy, and warnings are not fields in Summary CSV or VTP. |

The nested objects are result values reached through `SolveResult`; callers do
not need to import their private implementation classes.

### Coefficients

`result.coefficients` and every `component.integrated` expose the same fields
and scalar properties:

| Field / property | Type / shape | Unit / frame | Meaning |
|---|---|---|---|
| `force_coeff_stl` | NumPy `float64` vector `(3,)` | dimensionless, STL frame | Integrated force-coefficient vector before frame transformation. |
| `force_coeff_body` | NumPy `float64` vector `(3,)` | dimensionless, body frame | Integrated force coefficient after the fixed STL-to-body transform. |
| `force_coeff_stability` | NumPy `float64` vector `(3,)` | dimensionless, stability frame | Body force rotated using resolved `alpha_t_deg`. |
| `moment_area_coeff_body_m` | NumPy `float64` vector `(3,)` | m, body frame | Area-normalized moment numerator before division by the three reference lengths. |
| `moment_coeff_body` | NumPy `float64` vector `(3,)` | dimensionless, body frame | Roll-, pitch-, and yaw-axis moment coefficients after reference-length division. |
| `CA`, `CY`, `CN` | `float` | dimensionless | Axial, side, and normal force coefficients. |
| `Cl`, `Cm`, `Cn` | `float` | dimensionless | Roll, pitch, and yaw moment coefficients. |
| `CD`, `CL` | `float` | dimensionless | Drag and lift coefficients in stability axes. |

Full transforms, signs, area normalization, and moment definitions are in
[Load and coefficient conventions](load-and-coefficient-conventions.md).

### Components

`result.components` contains one item for each input STL, ordered by ascending
zero-based `component_id`, which is the same as ordered `stl_paths`. Each item
exposes:

| Field | Type | Meaning |
|---|---|---|
| `component_id` | non-negative `int` | Zero-based input-STL identity. |
| `integrated` | nested coefficient result | Coefficients for only this component's faces, using the same global reference area, moment reference, and reference lengths as the total. |
| `face_count` | non-negative `int` | Number of triangular faces in the component. |
| `shielded_face_count` | non-negative `int` | Number of its faces geometrically ray-shielded. |

The high-level solvers do not populate component-specific metadata. That
implementation field is not a separately supported user schema.

### Geometry

| `result.geometry` field | Type / shape | Unit / values | Meaning |
|---|---|---|---|
| `centers_stl_m` | NumPy `float64` array `(n_faces, 3)` | m, STL frame | Triangle centroids used for moments. |
| `normals_out_stl` | NumPy `float64` array `(n_faces, 3)` | outward unit vectors, STL frame | Triangle normals used by shielding and the physical model. |
| `areas_m2` | NumPy `float64` array `(n_faces,)` | m², positive | Triangle areas used by integration. |
| `component_ids` | NumPy `int64` array `(n_faces,)` | non-negative IDs | Per-face input-STL assignment. |
| `n_faces` | `int` | positive count | Number of faces represented by every per-face result. |
| `unique_component_ids` | tuple of `int` | ascending IDs | Component identities present in the geometry. |

This geometry surface does not expose the VTP point array or triangle
connectivity.

### Flow state

| `result.flow_state` field | Type / shape | Unit / values | Meaning |
|---|---|---|---|
| `velocity_hat_stl` | NumPy `float64` vector `(3,)` | unit vector, STL frame | Resolved direction in which the freestream travels. |
| `shielded` | NumPy boolean array `(n_faces,)` | `False` or `True` | Geometric ray-occlusion mask. Shielded faces have exact-zero local traction. |
| `n_faces` | `int` | positive count | Number of entries in `shielded`. |

See [Ray shielding](ray-shielding.md) for the method, backend behavior, and its
distinction from Hypersonic `leeward_equation="shield"`.

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
| FMF | `normal_traction_coeff`, `tangential_traction_coeff`, `theta_deg` | Local normal/tangential Sentman traction projections and the normal-to-flow angle. |
| Hypersonic | `cp`, `theta_deg` | Local pressure coefficient and the normal-to-flow angle. |

Each current scalar array is `float64`. The model-specific scalar definitions
are in the [FMF](../solvers/fmf.md) and
[Hypersonic](../solvers/hypersonic.md) solver pages, while the shared
`theta_deg` definition is in
[Load and coefficient conventions](load-and-coefficient-conventions.md#common-panel-angle).
Their artifact representations are documented separately under VTP
[common cell data](../results/vtp.md#common-cell-data) and
[model-specific cell data](../results/vtp.md#model-specific-cell-data).

FMF metadata contains `mode` (always `A` for this API), `S`, `Ti_K`, and
`Tw_K`. Hypersonic metadata contains `Mach`, `gamma`, `windward_eq`, and
`leeward_eq`; equation values are their canonical one-or-per-component strings.

!!! important "Local traction is not VTP `C_face_stl`"

    `result.local_loads.traction_coeff_stl` is the unweighted local model
    result. The common integrator forms the per-face force-coefficient
    contribution stored in VTP as

    ```text
    C_face_stl = traction_coeff_stl * area_m2 / Aref_m2
    ```

    The package-root `SolveResult` does not directly expose `C_face_stl`. It can
    be derived from `local_loads.traction_coeff_stl` and
    `geometry.areas_m2` when the case's `Aref_m2` is available. Do not treat the
    two arrays as identical and do not apply panel area twice. See
    [Load and coefficient conventions](load-and-coefficient-conventions.md#local-traction-and-panel-contributions).

### Arrays and mutability

Result arrays are C-contiguous, read-only NumPy buffers: central floating arrays
use `float64`, component IDs use `int64`, and the shielding mask uses boolean
dtype. Nested result objects are frozen value objects, and the scalar/metadata
mappings are immutable. Make an explicit copy when mutable working data is
needed, for example `result.geometry.centers_stl_m.copy()`.

These in-memory dtypes differ where an artifact deliberately projects a storage
type, such as VTP `stl_index` (`int32`) or `shielded` (`uint8`). The
[VTP reference](../results/vtp.md) owns artifact dtypes.

## API ↔ Summary CSV / VTP correspondence

This table gives the useful semantic correspondence; the result pages remain
canonical for serialization order, stored dtypes, blank conditions, and
artifact-only metadata.

| In-memory API value | Artifact correspondence |
|---|---|
| `coefficients.CA`, `CY`, `CN`, `Cl`, `Cm`, `Cn`, `CD`, `CL` | Same-named Summary CSV columns on the `total` row. |
| `components[*].integrated` | Same coefficient surface on Summary `component` rows. |
| Component IDs and counts | Summary `component_id`, `faces`, and `shielded_faces`; components use input-STL order. |
| `case_signature` | Summary and VTP `case_signature`. |
| `ray_backend_used` | Summary and VTP `ray_backend_used`. |
| `geometry.areas_m2` | VTP `area_m2`. |
| Columns of `geometry.centers_stl_m` | VTP `center_x_stl_m`, `center_y_stl_m`, and `center_z_stl_m`. |
| `geometry.component_ids` | VTP `stl_index` (with artifact projection dtype). |
| `flow_state.shielded` | VTP `shielded` (with artifact projection dtype). |
| `local_loads.cell_scalars` | Same-named VTP diagnostic/model cell data. |
| `local_loads.traction_coeff_stl` | Not serialized directly; VTP `C_face_stl` is its `area_m2 / Aref_m2` weighted contribution. |

The API does not return artifact paths, timestamps, solver-version provenance,
VTP points/connectivity, or the original case-table row. See the complete
[Summary CSV](../results/summary-csv.md) and [VTP](../results/vtp.md)
references for those surfaces.

## Validation and errors

Passing anything other than an `FMFCase` to `solve_fmf()`, or anything other
than a `HypersonicCase` to `solve_hypersonic()`, raises `TypeError`. Invalid
attitude modes/ranges, case IDs, common physical values, model selectors and
ranges, shielding configuration, missing/unreadable STL sources, and invalid
mesh geometry are rejected with value errors from the relevant validation
boundary.

Some checks happen during case or attitude construction and others require the
loaded geometry and therefore happen during solve. Private exception subclasses,
exact messages, and more specific validation timing are not stable package-root
API. Callers may catch built-in `TypeError` or `ValueError` as appropriate; do
not import lower-level exception classes as part of normal API use.

## Filesystem and side-effect boundary

The solve functions read every path in `stl_paths`; the API is therefore not
file-I/O free. They perform calculation and return `SolveResult` without:

- writing Summary CSV;
- writing VTP;
- writing PNG;
- writing checkpoints;
- creating an output directory; or
- producing other result-artifact side effects.

Use the [CLI](../user-guide/cli.md) or [GUI](../user-guide/gui.md) case-table
workflow when artifacts or atmosphere-derived FMF Mode B are required.

## Minimal examples

Both examples assume that a readable, valid `model.stl` already exists in the
process working directory. They import Panel Solver names only from the package
root.

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