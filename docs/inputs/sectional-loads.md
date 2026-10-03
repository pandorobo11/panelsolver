# Sectional load definitions

Use a separate UTF-8 CSV to define sectional aerodynamic load distributions for
the [sectional CLI workflow](../running/cli.md#sectional-load-batches) or the
[read-only GUI workflow](../running/gui.md#sectional-load-batches). Solver
case tables remain unchanged. Python callers use
[`compute_sectional_loads`](../running/python-api.md#sectional-aerodynamic-load-distributions)
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

See the [result CSV reference](../results/sectional-loads-csv.md) for coverage,
per-bin quantities and output ordering. These are integrated aerodynamic strip
coefficients; cumulative values, coefficient density, pressure sections and
structural cut loads are outside this workflow.
