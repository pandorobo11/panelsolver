# Quickstart

After [installation](installation.md), choose the
[flow domain](../index.md#choosing-a-solver) appropriate to your analysis and
run its basic example below. Both examples use the same small plate, so you can
learn the input and result workflow before preparing your own geometry.

For the CLI, use a checkout or extract `panelsolver-examples-v<version>.zip`.
Run commands from the directory containing the `examples/` folder. The GUI can
also copy its bundled examples to a workspace.

## What the basic case represents

`examples/geometry/plate.stl` is a 1 m × 1 m square in the STL Y/Z plane,
centered at the origin, with two triangular panels facing −X. At zero attitude
the flow travels along +X, directly into that face. Both basic cases use
`alpha_deg=10`, zero sideslip, `Aref_m2=1`, an origin moment reference, and
1 m moment reference lengths. Ray shielding is off.

This is an open, single-sided plate. A “Mesh is not watertight” warning is
expected for this example and does not prevent calculation.

## Run FMF

```bash
panelsolver fmf --input examples/fmf/basic.csv
```

This Sentman Mode A case uses molecular speed ratio `S=5`, incident static
temperature `Ti_K=300 K`, and wall temperature `Tw_K=300 K`. It calculates both
normal and tangential surface traction.

## Run Hypersonic

```bash
panelsolver hypersonic --input examples/hypersonic/basic.csv
```

This case uses `Mach=6` and `gamma=1.4`. Omitted equation columns select
Newtonian on windward panels and `Cp = 0` (`shield`) on leeward panels.
Zero pressure coefficient means pressure equal to freestream pressure; see the
[pressure convention](../solvers/hypersonic.md#panel-geometry-and-local-pressure-convention).

## Use the GUI

Launch the GUI for your chosen domain:

```bash
panelsolver-gui fmf
panelsolver-gui hypersonic
```

Use **File > New from Example > Basic** to copy the table and geometry to a
workspace, or **File > Open Input File...** to open the matching `basic.csv`.
Select its row, choose **Run Selected Cases**, and accept the suggested Summary
CSV destination. Leave the run settings at their defaults. After a successful
run, the matching VTP appears in the Viewer. If you already ran the CLI example,
opening that input table and selecting its row also loads the matching VTP.

## Read the first results

A successful basic run writes these files under `examples/<domain>/outputs/`
(or the corresponding directory in your GUI workspace):

| File | First inspection |
|---|---|
| `basic_result.csv` | Open in a spreadsheet or CSV reader. Find `case_id` and the row with `scope=total`; read `CA`, `CD`, and `CL`. |
| `fmf_basic.vtp` (FMF) | In the Viewer select **Normal traction coeff.**, then **Tangential traction coeff.** |
| `hypersonic_basic.vtp` (Hypersonic) | In the Viewer select **Cp**, the local pressure coefficient. |

Each basic case produces one total row with finite coefficients and a VTP with
two faces. `CA` is the body-axis axial coefficient; `CD` and `CL` are drag and
lift in the documented stability axes. Both cases have positive `CA` and `CD`
and negative `CL` for this attitude. They have near-zero moment coefficients (`Cl`, `Cm`, `Cn`) because the uniform plate
load is centered on the moment reference. The two triangles have the same scalar
values, so uniform coloring is expected. Hypersonic `cp` is about 1.94 for this
orientation; FMF also has tangential traction.

These are dimensionless coefficients. Reference quantities and signs are
defined in [Load and coefficient conventions](../reference/load-and-coefficient-conventions.md).
Use the [Summary CSV reference](../results/summary-csv.md) and
[VTP reference](../results/vtp.md) when you need every field's meaning.

## Change the attitude and rerun

Copy `basic.csv` to `alpha20.csv` in the same directory, so its relative STL
path still works. In a text editor or spreadsheet, change `case_id` to
`alpha20` and `alpha_deg` from `10` to `20`; keep the other cells unchanged.
Save it, then run the same command with `alpha20.csv` as the input, or open
that file in the GUI and run its row.

Compare `outputs/alpha20_result.csv` with `outputs/basic_result.csv` and inspect
`outputs/alpha20.vtp`. The changed angle changes `CD` and `CL`; in the
Hypersonic case `cp` decreases to about 1.77 as the flow becomes less normal to
the plate. The distinct case ID keeps the original VTP available for comparison.

Next, follow [Case files](../user-guide/case-files.md#adapt-an-example-to-your-own-case)
to replace the plate with your STL, flow conditions, and reference quantities.

## Try the feature examples next

The repository and examples archive include `examples/README.md`, which collects
commands, main inputs, and expected relationships for each feature example:
FMF flow modes, Hypersonic pressure methods, shielding, components, and attitude
representations. Use those examples for the feature you need. For larger runs,
see [Batch execution and recovery](../user-guide/batch-execution-and-recovery.md).
