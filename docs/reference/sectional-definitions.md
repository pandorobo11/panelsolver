# Sectional definition CSV

A sectional definition CSV describes one or more axes along which to slice
each case. Sectional loads and Sectional Cp use separate definition files with
almost the same columns. Keep these files separate from your case tables. See
[Sectional loads and Cp](../guides/sectional.md) for how to run them. From
Python, pass the same values as arguments to
[`compute_sectional_loads`](python-api.md#sectional-aerodynamic-load-distributions)
or [`compute_sectional_cp`](python-api.md#sectional-cp-sections).

## Common columns

| Column | Required | Meaning |
|---|---|---|
| `section_id` | yes | A label for the definition. Labels are case-sensitive. Leading and trailing spaces are removed, and labels must be unique. It is kept as text, so `001` stays `001`. |
| `origin_x_stl_m`, `origin_y_stl_m`, `origin_z_stl_m` | yes | The point where the axis position is zero, in STL coordinates and metres. |
| `direction_x_stl`, `direction_y_stl`, `direction_z_stl` | yes | The axis direction in STL coordinates. Any nonzero length; it is normalized for you, keeping its sign. |
| `start_m`, `stop_m` | no | The range along the axis in metres. Leave both empty to cover the selected geometry automatically, or fill both. |
| `component_ids` | no | Which STL parts to include, as zero-based IDs separated by semicolons, for example `0;2`. Each ID may appear once. Leave empty for all parts. |

The position along the axis is the signed distance
`s = dot(r_stl_m - origin_stl_m, unit_direction_stl)`. The origin only sets
where `s = 0`. It is **not** the moment reference point: the reference area,
moment reference point, reference lengths, and attitude always come from the
case.

**File rules.** Columns can be in any order. The file is UTF-8, with or without
a byte-order mark. Required cells cannot be empty; a cell with only spaces
counts as empty. Duplicate columns, unknown columns, an empty file, duplicate
section IDs, and values such as NaN or infinity are errors. Quote cells that
contain commas or line breaks, as usual in CSV. Do not put case IDs in this
file.

Panel Solver checks the whole file before any case runs, including
definitions you did not select. Errors name the row, the section ID when
known, and the column.

**Automatic range.** With `start_m` and `stop_m` empty, the range covers the
vertices of the selected parts, including shielded panels. It is worked out
again for each case, so different geometries can get different positions. If
the selected geometry has zero length along the axis, give the range
explicitly.

**Explicit range.** The same positions are used in every case. A range that
covers only part of the geometry, or none of it, is allowed.

**Components.** Component IDs are the positions of the parts in each case's own
`stl_path` list. Panel Solver does not try to match parts between different
assemblies. An ID that a case does not have is an error for that case.

## Sectional load definitions

Sectional loads add one column:

| Column | Required | Meaning |
|---|---|---|
| `bin_count` | yes | Number of equal-width strips. A whole number written without a decimal point or exponent: `30` is valid, `30.0` and `3e1` are not. |

```csv
section_id,origin_x_stl_m,origin_y_stl_m,origin_z_stl_m,direction_x_stl,direction_y_stl,direction_z_stl,start_m,stop_m,bin_count,component_ids
span,0,0,0,0,1,0,,,30,
oblique,0,0,0,0.2,0.9,0.4,-1,1,20,0
```

With an explicit range, `start_m` must be less than `stop_m`. A range that
misses the geometry gives zero for every strip, and the result marks that the
range does not cover the geometry. The "total" in the result covers only the
selected parts within the range.

Each strip gives the integrated force and moment coefficients of that strip,
not a value per metre. Running totals, structural internal loads, and pressure
sections are not part of this workflow. The
[sectional load CSV](sectional-loads-csv.md) describes the result.

## Sectional Cp definitions

Sectional Cp uses `section_count` instead of `bin_count`:

| Column | Required | Meaning |
|---|---|---|
| `section_count` | yes | Number of equally spaced cutting planes, a whole number. Both ends of the range get a plane. |

```csv
section_id,origin_x_stl_m,origin_y_stl_m,origin_z_stl_m,direction_x_stl,direction_y_stl,direction_z_stl,start_m,stop_m,section_count,component_ids
span,0,0,0,0,1,0,-0.2,0.2,5,
center,0,0,0,0,1,0,0,0,1,
```

The axis direction is the normal of the cutting planes.

- For several planes, `start_m` must be less than `stop_m`.
- For a single plane at a fixed position, set `start_m` and `stop_m` to the
  same value.
- With an automatic range, several planes are spread over the geometry, and a
  single plane is placed in the middle. Several automatic planes need a
  geometry with nonzero length along the axis.

Sectional Cp records the value of each panel that a plane crosses: `cp` in
Hypersonic, and `normal_traction_coeff` in FMF. It does not integrate loads,
and FMF tangential traction is not included. The
[sectional Cp CSV](sectional-cp-csv.md) describes the result and what happens
when a plane touches a vertex or lies in a panel.
