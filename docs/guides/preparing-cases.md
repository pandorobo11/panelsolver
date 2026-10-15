# Preparing cases

A **case** is one calculation: one geometry, one flow condition, and one
attitude. You list cases as rows of a **case table**, which can be a CSV, XLSX,
or XLSM file. Excel files use their first worksheet. Save CSV files as UTF-8
(with or without a byte-order mark). Old Excel `.xls` files are not supported;
save them as `.xlsx` or CSV first.

This page explains how to prepare a case table and geometry. The exact columns
for each domain are in the [FMF case table](../reference/fmf-case-table.md) and
[Hypersonic case table](../reference/hypersonic-case-table.md) references.

## Adapt an example to your own case

The easiest start is to copy the Basic example from the
[Quickstart](../getting-started/quickstart.md) into a working folder, keeping the
table and its `geometry/` folder together. Edit the table in a spreadsheet or
text editor, then open it in the GUI or pass it to the CLI with `--input`.

1. Give the case a new `case_id`, and set `stl_path` to your STL file (or to a
   list of STL parts, described below).
2. Check the STL orientation, normals, and units as described in
   [Orient and scale the STL](#orient-and-scale-the-stl).
3. Enter your flow condition and attitude. For FMF, give either `S` and
   `Ti_K`, or `Mach` and `Altitude_km`, and always `Tw_K`. For Hypersonic, give
   `Mach`, `gamma`, and the pressure methods for your surfaces. Check that the
   model suits your flow; see the [FMF](../methods/fmf.md) or
   [Hypersonic](../methods/hypersonic.md) method page.
4. Set the reference area, moment reference point, and reference lengths (see
   [Choose reference quantities](#choose-reference-quantities)).
5. Decide whether parts of the vehicle can hide other parts from the flow. If
   they can, set `shielding_on=1`; see [Ray shielding](../methods/ray-shielding.md).
   Set `out_dir` if you want the VTP files in a different folder. Keep
   `save_vtp_on=1` so you can view the surface result.
6. Run this one case first. Check the geometry and surface colors in the GUI,
   and the total coefficients in the Summary CSV. Then add more rows for your
   attitude or flow-condition sweep.

## Orient and scale the STL

**Direction.** With zero attitude, the flow travels along **+X of the STL
file**. A surface that faces the oncoming flow therefore has its outward normal
pointing toward −X. Increasing `alpha_deg` tilts the flow toward +Z, and
increasing sideslip tilts it toward −Y (in the default `beta_sin` mode, near
zero attitude). Panel Solver uses the STL coordinates exactly as exported, so
export the mesh in the frame you want to use.

Body axes, used for `CA`, `CN`, and the moments, are related to STL axes by
`(X_body, Y_body, Z_body) = (−X_stl, +Y_stl, −Z_stl)`. See
[Coordinate and attitude conventions](../methods/coordinate-and-attitude-conventions.md)
for the full definitions.

**Units.** STL files do not record their length unit. Set
`stl_scale_m_per_unit` to the number of metres in one STL unit: `1` for metres,
`0.001` for millimetres, or `0.0254` for inches. Every coordinate is multiplied
by this value. Columns ending in `_m` or `_m2` are always in metres and square
metres. After a run, check one known dimension of your model; a wrong scale
also changes panel areas and moment arms.

**Normals.** Triangles should be wound consistently, with normals pointing out
of the body. Panel Solver tries to repair inconsistent winding when it loads
the mesh, but it cannot guess which side of an open surface (such as a plate)
should carry the load. Check that side yourself. A mesh that is not watertight
is allowed with a warning. Degenerate triangles, or winding that cannot be
repaired, stop the case with an error.

**Multiple parts.** Export every part in the same assembly frame and units,
already in their correct positions. Panel Solver combines them as they are,
using one scale for the whole case.

## Choose reference quantities

Use the same reference conventions as the data you want to compare with, and
keep them the same across all cases in the comparison.

| Input | How to choose it |
|---|---|
| `Aref_m2` | The reference area for integrated force and moment coefficients, for example a planform or frontal area. Use a fixed value that does not change with attitude. Doubling it halves those coefficients for the same geometry and flow, but does not change local Cp or traction coefficients. |
| `ref_x_m`, `ref_y_m`, `ref_z_m` | The point about which moments are calculated, in metres in the (scaled) STL frame. Often the center of mass or the moment reference of a test. Moving it changes the moments but not the forces. |
| `Lref_Cl_m`, `Lref_Cm_m`, `Lref_Cn_m` | Reference lengths for the roll, pitch, and yaw moments. For example, span for roll and yaw, and chord for pitch. They do not need to be equal. |

Results for each STL part use the same references as the total, so the parts
add up to the total. The exact equations and signs are in
[Load and coefficient conventions](../methods/load-and-coefficient-conventions.md).

## Columns and defaults

- Columns can be in any order; the header names identify them. Use the exact
  names from the [FMF](../reference/fmf-case-table.md) or
  [Hypersonic](../reference/hypersonic-case-table.md) reference.
- Required columns must be present, and their cells filled.
- A column with a default can be left out. An empty cell in that column also
  uses the default. Leave unused cells truly empty, without spaces or
  placeholder text. For example, leaving out `save_vtp_on` still saves the VTP;
  set it to `0` to skip the VTP.
- In FMF, fill exactly one complete pair per row: `S` and `Ti_K`, **or**
  `Mach` and `Altitude_km`. A table can mix both kinds of rows if it has all
  four columns.
- You can add your own columns, such as notes. They are copied to the Summary
  CSV after the standard input columns.

## Paths, VTP destinations, and components

Relative paths in `stl_path` and `out_dir` are relative to the folder that
contains the case table, not to the folder you run the command from. Absolute
paths are used as written, and `~` means your home folder.

When VTP saving is on, each case is saved as `<out_dir>/<case_id>.vtp`. The
[VTP reference](../reference/vtp.md) describes its contents, and
[Batch runs and recovery](batch-runs.md) explains what happens if a file
cannot be written.

To build a case from several STL parts (components), separate their paths
with semicolons:

```text
geometry/body.stl;geometry/fin.stl
```

All parts use the same `stl_scale_m_per_unit`. Parts are numbered from zero in
the order listed (component IDs `0`, `1`, ...). The Summary CSV reports each
part separately as well as the total.

In Hypersonic, each pressure-method cell can hold one method for all parts, or
one method per part separated by semicolons. See
[Hypersonic pressure methods](../methods/hypersonic.md).

## Attitude modes

Angles in case tables are in degrees. `attitude_input` sets how `alpha_deg` and
`beta_or_bank_deg` are read:

| Mode | `alpha_deg` | `beta_or_bank_deg` | Use it when |
|---|---|---|---|
| `beta_sin` (default) | angle of attack; any angle | sideslip, sine definition; −90° to 90° | your sideslip data uses the sine definition |
| `beta_tan` | angle of attack; any angle | sideslip, tangent definition; −90° to 90° | your data gives two tangent angles |
| `bank` | total angle between flow and +X; any angle | bank (roll) angle of that flow direction; any angle | your data gives a total angle plus a roll orientation |

If `attitude_input` is missing or blank, `beta_sin` is used, including for
older case files. Earlier versions used `beta_tan` as the default; set
`attitude_input=beta_tan` explicitly to reproduce their results.

In `beta_tan` mode, an angle of attack of ±90° (or 270°, and so on) together
with a sideslip of ±90° does not define a direction, so that combination is
rejected. The exact formulas for each mode are in
[Coordinate and attitude conventions](../methods/coordinate-and-attitude-conventions.md).

## Common validation

Panel Solver checks the table when it opens it and reports the row, case ID,
and column of each problem. Mesh problems are reported when that case runs.

- `case_id` is also the VTP file name, so it must be a valid file name on
  every common operating system: not empty; no path separators or control
  characters; no Windows reserved names such as `CON`; no trailing dot or
  space; and not `.` or `..`.
- Case IDs must be unique, ignoring upper and lower case.
- Numbers must be finite. `TRUE`/`FALSE` values are not accepted as numbers.
- The STL scale, reference area, and the three reference lengths must be
  greater than zero.
- `shielding_on` and `save_vtp_on` are `0` or `1`.
- `ray_backend` is `auto`, `rtree`, or `embree`.
- The mesh must not be empty, must have finite coordinates, and must not
  contain degenerate triangles or winding that cannot be repaired.
- The `save_npz_on` column from older versions is no longer accepted. Remove it
  from old tables.
