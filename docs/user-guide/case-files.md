# Case files

Both domains accept CSV, XLSX, and XLSM. Excel input uses the first worksheet.
Excel 97–2003 BIFF `.xls` is not a supported input format; resave the workbook as
`.xlsx` or export it as CSV. Exact columns and defaults are defined in the
[FMF input reference](../reference/fmf-input.md) and
[Hypersonic input reference](../reference/hypersonic-input.md).

CSV case tables use UTF-8 with BOM (`utf-8-sig`). The reader also accepts
BOM-less UTF-8 CSV files, so existing UTF-8 inputs remain compatible.

## Paths and components

Relative `stl_path` and `out_dir` values are resolved from the case table's
directory, not the process working directory. `~` is expanded. Use semicolons to
list multiple STL components in input order:

```text
geometry/body.stl;geometry/fin.stl
```

Every STL is scaled by the common `stl_scale_m_per_unit`. Component IDs are
zero-based positions in that list. Component rows use the global reference area,
moment reference point, and reference lengths.

For Hypersonic, a surface-equation cell may contain one selector applied to all
components or exactly one semicolon-separated selector per STL. See
[Hypersonic](../solvers/hypersonic.md).

## Attitude modes

Angles in case files are degrees. `attitude_input` controls the meaning of
`alpha_deg` and `beta_or_bank_deg`:

| Mode | `alpha_deg` | `beta_or_bank_deg` | Reader domain |
|---|---|---|---|
| `beta_tan` | tangent angle of attack | tangent sideslip | both strictly between -90° and 90° |
| `beta_sin` | tangent angle of attack | sine-definition sideslip | `abs(alpha_deg) < 90°`; second angle finite |
| `bank` | included angle | bank angle | both finite; bank is periodic |

All modes resolve to a unit STL-frame freestream vector and resolved tangent
angles before panel calculation. The exact signs and transform are in
[Numerical conventions](../reference/numerical-conventions.md).

## Common validation

- `case_id` must be a portable Unicode filename: no empty values, path/control
  characters, Windows reserved names, trailing dot/space, `.` or `..`.
- Case IDs must be unique after Unicode case-folding.
- Required numbers must be finite; numeric booleans are rejected.
- STL scale, reference area, and all three reference lengths must be positive.
- `shielding_on` and `save_vtp_on` are `0` or `1`.
- `ray_backend` is `auto`, `rtree`, or `embree`.
- Empty, non-finite, degenerate, or unrepaired inconsistently wound meshes are
  rejected by the shared strict geometry boundary.

Accepted non-reserved unknown input columns are preserved after the canonical
input columns in the Summary CSV. `save_npz_on` is a reserved field that the
CSV, XLSX, and XLSM readers explicitly reject; remove it when updating an older
case file. The documented case file plus CLI/GUI path is the supported file
interface.
