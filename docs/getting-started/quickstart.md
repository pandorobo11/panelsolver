# Quickstart

This page runs a small supplied example, shows where the results are, and
then changes the attitude and runs it again. Pick the
[flow domain](../index.md#choosing-a-solver) you plan to use. Both domains use
the same plate, so the steps are the same.

## Get the examples

- From a source checkout, the examples are in the `examples/` folder.
- From a wheel installation, download `panelsolver-examples-v<version>.zip`
  from the release page and extract it.
- In the GUI, **File > New from Example** copies an example to a folder you
  choose, so you do not need the archive.

Run the CLI commands below from the folder that contains `examples/`.

## The basic example

`examples/geometry/plate.stl` is a flat 1 m × 1 m plate in the STL Y/Z plane,
centered at the origin. It has two triangles, both facing −X. With zero
attitude the flow travels along +X, straight into the plate.

Both basic cases use an angle of attack of `alpha_deg=10`, no sideslip, a
reference area of `Aref_m2=1`, the origin as the moment reference point, and
1 m reference lengths. Ray shielding is off.

The plate is an open surface, so you will see a “Mesh is not watertight”
warning. This is expected and does not stop the calculation.

## Run FMF

```bash
panelsolver fmf --input examples/fmf/basic.csv
```

This case gives the flow as a molecular speed ratio `S=5` and a gas temperature
`Ti_K=300`, with a wall temperature `Tw_K=300`. FMF calculates both the
pressure (normal) and shear (tangential) load on each panel.

## Run Hypersonic

```bash
panelsolver hypersonic --input examples/hypersonic/basic.csv
```

This case uses `Mach=6` and `gamma=1.4`. The table does not set pressure
methods, so the defaults apply: Newtonian on panels that face the flow and
`Cp = 0` on panels that face away from it.

## Use the GUI

Start the GUI for your domain:

```bash
panelsolver-gui fmf
panelsolver-gui hypersonic
```

1. Choose **File > New from Example > Basic** and pick an empty folder. The
   GUI copies the example there and opens it. (Or use **File > Open Input
   File...** to open `basic.csv` directly.)
2. Select the case row and choose **Run Selected Cases**.
3. Accept the suggested Summary CSV location. Keep the other run settings as
   they are.

When the run finishes, the surface result appears in the Viewer.

## Read the first results

A run writes these files to `examples/<domain>/outputs/`, or to the
`outputs/` folder of your GUI workspace:

| File | What to look at first |
|---|---|
| `basic_result.csv` | Open it in a spreadsheet. Find the row with `scope` = `total`, then read `CA`, `CD`, and `CL`. |
| `fmf_basic.vtp` (FMF) | In the Viewer, select **Normal traction coeff.**, then **Tangential traction coeff.** |
| `hypersonic_basic.vtp` (Hypersonic) | In the Viewer, select **Cp**, the local pressure coefficient. |

What you should see:

- One `total` row with finite coefficients, and a VTP with two panels.
- Positive `CA` (axial force) and `CD` (drag), and negative `CL` (lift) at
  this attitude.
- Moment coefficients `Cl`, `Cm`, and `Cn` close to zero, because the load is
  spread evenly around the moment reference point.
- Both panels have the same color, because they carry the same load.
- In Hypersonic, `Cp` is about 1.94.

All coefficients are dimensionless. The
[Summary CSV reference](../reference/summary-csv.md) and
[VTP reference](../reference/vtp.md) describe every field, and
[Load and coefficient conventions](../methods/load-and-coefficient-conventions.md)
defines the axes and signs.

## Change the attitude and run again

1. Copy `basic.csv` to `alpha20.csv` in the same folder, so the STL path in
   the table still works.
2. Open `alpha20.csv` in a text editor or spreadsheet. Change `case_id` to
   `alpha20` and `alpha_deg` from `10` to `20`. Leave the other cells as they
   are.
3. Run it with the same command, using `alpha20.csv` as the input, or open it
   in the GUI and run its row.

Compare `outputs/alpha20_result.csv` with `outputs/basic_result.csv`, and look
at `outputs/alpha20.vtp`. `CD` and `CL` change. In Hypersonic, `Cp` drops to
about 1.77, because the flow now hits the plate less directly. Because the
case ID is new, the first VTP is kept for comparison.

To use your own geometry and conditions, continue with
[Preparing cases](../guides/preparing-cases.md#adapt-an-example-to-your-own-case).

## Try more examples

`examples/README.md` (in the checkout and in the examples archive) describes
every example and what it shows: the two FMF input modes, the Hypersonic
pressure methods, shielding, multi-part geometry, attitude inputs, and
sphere-cone angle effects. For runs with many cases, see
[Batch runs and recovery](../guides/batch-runs.md).

### Sphere-cone: angle effects

In either domain, choose **File > New from Example > Sphere-cone: Angle
Effects**, select all three rows, and run them. From the CLI:

```bash
panelsolver fmf --input examples/fmf/sphere_cone.csv
panelsolver hypersonic --input examples/hypersonic/sphere_cone.csv
```

Both tables use the same closed sphere-cone with 9,216 panels. Only the angle
of attack changes (0, 15, and 30 degrees), with no sideslip. FMF uses `S=5`
and `Ti_K=Tw_K=300`. Hypersonic uses Mach 6, gamma 1.4, Modified Newtonian on
windward panels, and `Cp = 0` on leeward panels.

Look at the normal and tangential traction in FMF, or `Cp` in Hypersonic, and
compare `CL` and `CD` in the Summary CSV. Keep the same camera and color range
between cases so the pictures are comparable.

The two domains model different flow regimes. These are idealized examples,
not validation data. `examples/README.md` lists the geometry, reference
quantities, and how the mesh was generated.

The Cube **Attitude Modes** example is different: it shows several ways of
writing the same flow direction. The sphere-cone example changes the actual
direction to show how surface loads respond.
