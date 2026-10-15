# Sectional definition CSV

Sectional loads and Sectional Cp each read their own definition CSV. Both
files use the same origin, direction and component columns. See
[Sectional loads and Cp](../guides/sectional.md) to run them.

## Sectional load definitions

Use a separate UTF-8 CSV to define sectional aerodynamic load distributions for
the [sectional CLI workflow](../guides/sectional.md#sectional-loads-from-the-cli) or the
[read-only GUI workflow](../guides/sectional.md#sectional-loads-in-the-gui). Solver
case tables remain unchanged. Python callers use
[`compute_sectional_loads`](python-api.md#sectional-aerodynamic-load-distributions)
arguments directly.

```csv
section_id,origin_x_stl_m,origin_y_stl_m,origin_z_stl_m,direction_x_stl,direction_y_stl,direction_z_stl,start_m,stop_m,bin_count,component_ids
span,0,0,0,0,1,0,,,30,
oblique,0,0,0,0.2,0.9,0.4,-1,1,20,0
```

| Column | Required | Meaning |
|---|---|---|
| `section_id` | yes | Case-sensitive label. Trimmed and Unicode NFC normalized; unique after normalization. Kept as text, so `001` stays `001`. |
| `origin_x_stl_m`, `origin_y_stl_m`, `origin_z_stl_m` | yes | Finite point defining axis coordinate zero, in STL coordinates and metres. |
| `direction_x_stl`, `direction_y_stl`, `direction_z_stl` | yes | Finite, nonzero dimensionless vector. Normalized internally while preserving direction. |
| `start_m`, `stop_m` | no | Both blank/omitted for automatic range, or both finite signed metre distances with start less than stop. |
| `bin_count` | yes | Positive decimal integer count of equal-width bins. `30.0` and `3e1` are invalid. |
| `component_ids` | no | Blank/omitted for all components, or distinct nonnegative decimal integer IDs separated by semicolons, for example `0;2`. |

Columns may appear in any order. A UTF-8 BOM is accepted. Required cells cannot
be blank; whitespace-only optional cells are blank. Duplicate headers, unknown
columns, empty files, duplicate normalized section IDs, empty component tokens,
noninteger IDs, NaN and infinity are errors. Section IDs are labels, not
filenames: quote CSV fields containing commas or newlines in the usual CSV way.
Case IDs do not belong in this file. Diagnostics identify the row, section ID
when available, and field. The whole file is validated before any case starts,
including definitions excluded by a selection filter.

The signed axis coordinate is
`s = dot(r_stl_m - origin_stl_m, normalized_direction_stl)`.
The origin is not the moment reference; reference area, moment reference,
reference lengths and stability angle always come from the physical case.

Auto range uses the vertices referenced by selected component faces, including
shielded faces. It resolves separately for each case, so different geometries
can have different bin locations. A zero projected extent is invalid for auto
range; supply explicit bounds for a plane perpendicular to the axis. Explicit
bounds use the same requested physical locations in every case. Partial and
nonintersecting ranges are valid; a nonintersecting range yields normal zero
integrals with coverage marked false.

Component IDs are original zero-based positions in each case's STL list. The
reader does not infer correspondence between different assemblies. Unknown IDs
fail when the definition is resolved against that case's mesh. Selected IDs
are sorted for output. The selected total covers only the selected components
within the requested range.

See the [result CSV reference](sectional-loads-csv.md) for coverage,
per-bin quantities and output ordering. These are integrated aerodynamic strip
coefficients; cumulative values, coefficient density, pressure sections and
structural cut loads are outside this workflow.

## Sectional Cp definitions

Sectional Cp extracts constant panel values on parallel cutting planes. It does
not integrate strip loads. Hypersonic uses `cp`; FMF uses
`normal_traction_coeff`, the local Sentman normal traction coefficient, not a
renamed pressure coefficient. Tangential traction is not included.

Use a separate UTF-8 CSV, with the same origin, direction, identity and component
selection conventions as [sectional loads](#sectional-load-definitions), replacing
`bin_count` with `section_count`:

```csv
section_id,origin_x_stl_m,origin_y_stl_m,origin_z_stl_m,direction_x_stl,direction_y_stl,direction_z_stl,start_m,stop_m,section_count,component_ids
span,0,0,0,0,1,0,-0.2,0.2,5,
center,0,0,0,0,1,0,0,0,1,
```

`section_count` is a positive decimal integer. For multiple planes, `start_m`
must be less than `stop_m`; both endpoints are included. For one plane, supply
equal start and stop. Omit both bounds to use the selected geometry's projected
extrema; one automatic plane uses their midpoint. Multiple automatic planes
require a nonzero projected extent. The normalized direction defines the plane
normal and increasing signed position. All coordinates and distances are STL
metres. Component IDs are original zero-based STL positions, separated by
semicolons; blank selects all.

The entire file is validated before selection or solving. Duplicate IDs,
unknown columns, nonfinite values, zero direction, malformed integer fields and
partial bounds are errors. Mesh-dependent failures are reported per case and
definition. Keep these definitions separate from physical case tables.

See [sectional Cp CSV](sectional-cp-csv.md) for contact rules and output.
