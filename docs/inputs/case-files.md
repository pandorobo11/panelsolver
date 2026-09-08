# Case files

Both domains accept CSV, XLSX, and XLSM. Excel input uses the first worksheet.
Convert Excel 97–2003 BIFF `.xls` files to `.xlsx` or CSV before opening them.
Column names and defaults are defined in the
[FMF input reference](fmf-input.md) and
[Hypersonic input reference](hypersonic-input.md).

CSV case tables use UTF-8, with or without a byte-order mark (BOM).

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
   [FMF](../methods/fmf.md) or [Hypersonic](../methods/hypersonic.md) method page.
4. Set your reference area, moment reference point, and reference lengths;
   use values appropriate to your geometry and comparison convention.
5. Choose whether geometry can block upstream flow to other panels and set
   `shielding_on` accordingly; see [Ray shielding](../methods/ray-shielding.md).
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
Near zero attitude in the default `beta_tan` mode, increasing alpha tilts flow
toward +Z_STL and increasing sideslip tilts it toward −Y_STL. Panel Solver uses the exported
coordinates and orientation as supplied.
See [Coordinate and attitude conventions](../methods/coordinate-and-attitude-conventions.md)
for the full definitions.

STL coordinates carry no reliable unit declaration. Set
`stl_scale_m_per_unit` to the number of metres per exported coordinate unit:
`1` for metres, `0.001` for millimetres, or `0.0254` for inches. All STL
coordinates are multiplied by that value before calculation. Reference inputs
ending in `_m` or `_m2` are used directly as SI quantities. Check a known model
dimension after conversion; a units mistake also changes panel areas and moment
arms.

Use consistently wound triangles with normals pointing out of the body. Normal
repair is attempted during loading, but it cannot establish the intended loaded
side of an open surface. Check that side explicitly for plates or other open
meshes. Non-watertight geometry is allowed with a warning; degenerate faces,
failed normal repair, or remaining inconsistent winding are rejected.

Export all components in the same assembly frame and units, with their relative
positions already set. Multiple STL files are combined at those coordinates
using the single case-wide scale.

## Choose reference quantities

Use the conventions of the experiment, design, or coefficient data you intend
to compare with, and keep them consistent across the comparison.

| Input | Practical choice and effect |
|---|---|
| `Aref_m2` | The positive reference area for all force and moment coefficients, such as a specified planform or frontal area. Supply a fixed value for the case, independent of attitude. Doubling it halves every integrated coefficient for the same geometry and conditions. |
| `ref_x_m`, `ref_y_m`, `ref_z_m` | The point about which moments are calculated, in metres in the scaled STL frame; often the center of mass or an experiment's moment reference. Changing it changes moments, while forces stay the same. |
| `Lref_Cl_m`, `Lref_Cm_m`, `Lref_Cn_m` | Positive lengths dividing roll, pitch, and yaw moments respectively, in addition to area normalization. Use the lengths defined by your comparison convention, for example span for roll/yaw and chord for pitch where applicable. They need not be equal. |

Component coefficients use these same global references, so they add to the
total within numerical tolerance. The exact equations and signs are in
[Load and coefficient conventions](../methods/load-and-coefficient-conventions.md).

## Columns and defaults

Input columns may appear in any order: headers identify the fields. Use the
exact names in the [FMF](fmf-input.md) or
[Hypersonic](hypersonic-input.md) input reference. The order shown
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
[Batch execution and recovery](../running/batch-execution-and-recovery.md) explains write
failures.

Use semicolons to list multiple STL components in input order:

```text
geometry/body.stl;geometry/fin.stl
```

Every STL in a case is scaled by that row's `stl_scale_m_per_unit`. Component
IDs are zero-based positions in that list.

For Hypersonic, a surface-equation cell may contain one selector applied to all
components or exactly one semicolon-separated selector per STL. See
[Hypersonic](../methods/hypersonic.md).

## Attitude modes

Angles in case files are degrees. `attitude_input` controls the meaning of
`alpha_deg` and `beta_or_bank_deg`:

| Mode | `alpha_deg` | `beta_or_bank_deg` |
|---|---|---|
| `beta_tan` | angle of attack; any finite periodic angle | absolute-X tangent sideslip; -90° to 90° inclusive |
| `beta_sin` | angle of attack; any finite periodic angle | sine-definition sideslip; -90° to 90° inclusive |
| `bank` | included angle; any finite angle | bank angle; any finite angle |

Use `beta_tan` for two tangent-angle inputs, `beta_sin` when the sideslip source
uses the sine definition, and `bank` when attitude is expressed as an included
angle plus a circumferential orientation. All modes use the same resolver for
FMF and Hypersonic and become a unit STL-frame freestream vector plus a separately derived
stability angle. The beta_tan pair with alpha an odd multiple of 90° and
beta = ±90° is rejected because the flow direction is undetermined. The table above lists the accepted
ranges; the coordinate axes, signs, reference directions, periodicity, and
transformations are defined in
[Coordinate and attitude conventions](../methods/coordinate-and-attitude-conventions.md).

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
updating an older case file.
