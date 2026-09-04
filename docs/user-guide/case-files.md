# Case files

Both domains accept CSV, XLSX, and XLSM. Excel input uses the first worksheet.
Excel 97–2003 BIFF `.xls` is not a supported input format; resave the workbook as
`.xlsx` or export it as CSV. Column names and defaults are defined in the
[FMF input reference](../reference/fmf-input.md) and
[Hypersonic input reference](../reference/hypersonic-input.md).

CSV case tables use UTF-8 with BOM (`utf-8-sig`). The reader also accepts
BOM-less UTF-8 CSV files, so existing UTF-8 inputs remain compatible.

## Adapt an example to your own case

Copy the basic table and geometry from [Quickstart](../getting-started/quickstart.md)
to a working directory, keeping their relative paths intact. Edit the table in a
spreadsheet or text editor, then open it again in the GUI or pass it to CLI
`--input`.

1. Give the case a distinct `case_id` and replace `stl_path` with your STL path
   or component list.
2. Check the STL orientation, normals, and scale as described below.
3. Replace the example's flow conditions and attitude with your analysis
   conditions. For FMF, supply either `S` and `Ti_K` or `Mach` and
   `Altitude_km`, plus `Tw_K`. For Hypersonic, supply `Mach`, `gamma`, and the
   pressure methods appropriate to your surfaces. Check the assumptions on the
   [FMF](../solvers/fmf.md) or [Hypersonic](../solvers/hypersonic.md) method page.
4. Set your reference area, moment reference point, and reference lengths;
   the example's values of 1 and origin reference are not inferred from your STL.
5. Choose whether geometry can block upstream flow to other panels and set
   `shielding_on` accordingly; see [Ray shielding](../reference/ray-shielding.md).
   Choose `out_dir` if you want a separate VTP location. Keep `save_vtp_on=1`
   for surface inspection.
6. Run one case first. Inspect the geometry and surface scalars in the GUI,
   then check the total coefficients in the Summary CSV before adding more rows
   for an attitude or flow-condition sweep.

## Orient and scale the STL

Export the mesh in the coordinate frame you intend to use throughout the case.
At zero attitude, freestream travels along **+X in STL axes**, so an upstream
face has its outward normal pointing toward −X. Body axes are
`(X_body, Y_body, Z_body) = (−X_stl, +Y_stl, −Z_stl)`.
With the default `beta_tan` attitude, positive alpha tilts flow toward +Z_STL
and positive sideslip tilts it toward −Y_STL. Panel Solver uses the exported
coordinates; it does not infer a vehicle nose or automatically align the STL.
See [Coordinate and attitude conventions](../reference/coordinate-and-attitude-conventions.md)
for the full definitions.

STL coordinates carry no reliable unit declaration. Set
`stl_scale_m_per_unit` to the number of metres per exported coordinate unit:
`1` for metres, `0.001` for millimetres, or `0.0254` for inches. All STL
coordinates are multiplied by that value before calculation. Reference inputs
ending in `_m` or `_m2` are already SI quantities and are **not** multiplied by
this scale. Check a known model dimension after conversion; a units mistake
also changes panel areas and moment arms.

Use consistently wound triangles with normals pointing out of the body. Normal
repair is attempted during loading, but it cannot establish the intended loaded
side of an open surface. Check that side explicitly for plates or other open
meshes. Non-watertight geometry is allowed with a warning; degenerate faces,
failed normal repair, or remaining inconsistent winding are rejected.

Export all components in the same assembly frame and units, with their relative
positions already set. Multiple STL files are combined at those coordinates;
there is no per-component translation, rotation, or scale input.

## Choose reference quantities

Use the conventions of the experiment, design, or coefficient data you intend
to compare with, and keep them consistent across the comparison.

| Input | Practical choice and effect |
|---|---|
| `Aref_m2` | The positive reference area for all force and moment coefficients, such as a specified planform or frontal area. Supply it explicitly; it is not computed from the STL or changed with attitude. Doubling it halves every integrated coefficient for the same geometry and conditions. |
| `ref_x_m`, `ref_y_m`, `ref_z_m` | The point about which moments are calculated, in metres in the scaled STL frame; often the center of mass or an experiment's moment reference. Changing it changes moments, while forces stay the same. |
| `Lref_Cl_m`, `Lref_Cm_m`, `Lref_Cn_m` | Positive lengths dividing roll, pitch, and yaw moments respectively, in addition to area normalization. Use the lengths defined by your comparison convention, for example span for roll/yaw and chord for pitch where applicable. They need not be equal. |

Component coefficients use these same global references, so they add to the
total within numerical tolerance. The exact equations and signs are in
[Load and coefficient conventions](../reference/load-and-coefficient-conventions.md).

## Columns and defaults

Input columns may appear in any order: headers identify the fields. Use the
exact names in the [FMF](../reference/fmf-input.md) or
[Hypersonic](../reference/hypersonic-input.md) input reference. The order shown
there is the order of the standard input columns in the **Summary CSV**, not an
input ordering requirement.

Required columns must be present and required cells filled. A column with a
listed default may be omitted; an empty cell in that column also uses the
default. Leave cells truly empty rather than entering spaces or placeholder
text. For example, omitting `save_vtp_on` still saves VTP; set it to `0` to
turn saving off. In FMF, fill exactly one complete Mode A/B pair per row and
leave the unused pair empty or omit those columns. A table may mix modes when
it includes both pairs of columns.

## Paths, VTP destinations, and components

Relative `stl_path` and `out_dir` values are resolved from the case table's
directory, not the process working directory. Absolute paths are used as
specified, and `~` is expanded. When VTP saving is enabled, the per-case path is
`<resolved_out_dir>/<case_id>.vtp`. The domain input references define the
`out_dir` and `save_vtp_on` defaults and accepted values; the
[VTP reference](../results/vtp.md) defines the saved content, and
[Batch execution and recovery](batch-execution-and-recovery.md) explains write
failures.

Use semicolons to list multiple STL components in input order:

```text
geometry/body.stl;geometry/fin.stl
```

Every STL in a case is scaled by that row's `stl_scale_m_per_unit`. Component
IDs are zero-based positions in that list. Component rows use the global
reference area, moment reference point, and reference lengths.

For Hypersonic, a surface-equation cell may contain one selector applied to all
components or exactly one semicolon-separated selector per STL. See
[Hypersonic](../solvers/hypersonic.md).

## Attitude modes

Angles in case files are degrees. `attitude_input` controls the meaning of
`alpha_deg` and `beta_or_bank_deg`:

| Mode | `alpha_deg` | `beta_or_bank_deg` |
|---|---|---|
| `beta_tan` | tangent angle of attack; strictly between -90° and 90° | tangent sideslip; strictly between -90° and 90° |
| `beta_sin` | tangent angle of attack; strictly between -90° and 90° | sine-definition sideslip; any finite angle |
| `bank` | included angle; any finite angle | bank angle; any finite angle |

Use `beta_tan` for two tangent-angle inputs, `beta_sin` when the sideslip source
uses the sine definition, and `bank` when attitude is expressed as an included
angle plus a circumferential orientation. All modes use the same resolver for
FMF and Hypersonic and become a unit STL-frame freestream vector and resolved
tangent angles before panel calculation. The table above lists the accepted
ranges; the coordinate axes, signs, reference directions, periodicity, and
transformations are defined in
[Coordinate and attitude conventions](../reference/coordinate-and-attitude-conventions.md).

## Common validation

- `case_id` must be a portable Unicode filename: no empty values, path/control
  characters, Windows reserved names, trailing dot/space, `.` or `..`.
- Case IDs must be unique after Unicode case-folding.
- Required numbers must be finite; numeric booleans are rejected.
- STL scale, reference area, and all three reference lengths must be positive.
- `shielding_on` and `save_vtp_on` are `0` or `1`.
- `ray_backend` is `auto`, `rtree`, or `embree`.
- Empty, non-finite, degenerate, or unrepaired inconsistently wound meshes are
  rejected by mesh validation.

Extra input columns, such as your own notes, are preserved after the
standard input columns in the Summary CSV, in their original relative order.
`save_npz_on` is a reserved
field that the CSV, XLSX, and XLSM readers explicitly reject; remove it when
updating an older case file. Panel Solver accepts the documented CSV, XLSX, and
XLSM case tables through both the CLI and GUI.
