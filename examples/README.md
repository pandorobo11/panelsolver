# Examples

Start with `basic.csv` for your chosen flow domain, then run the table for the
feature you want to inspect. The [Quickstart](../docs/getting-started/quickstart.md)
walks through a basic run, its first results, and an attitude change. This page
collects the inputs and expected relationships for the remaining examples.

All paths are relative to the case table. Every example saves VTP for GUI
inspection: the basic tables use the `save_vtp_on=1` default, and the feature
tables set it explicitly.

The example STL coordinates are in metres (`stl_scale_m_per_unit=1`). Cases use
an origin moment reference and 1 m moment reference lengths. Reference area
is `Aref_m2=1`, except for the sphere-cone examples, which use the fixed maximum
circular cross-section area, `pi * (0.5 m)^2`.
Components use the same global references, so component rows add to the total
for all eight coefficients. When adapting an example, choose your own
[reference quantities](../docs/inputs/case-files.md#choose-reference-quantities).
The five meshes in `geometry/` and the case tables are project material
distributed under Apache-2.0.

The examples archive is named `panelsolver-examples-v<version>.zip`. It preserves
this `examples/fmf/`, `examples/hypersonic/`, and `examples/geometry/` layout
and includes `LICENSE` and `THIRD_PARTY_NOTICES.md` at the archive root.

For the complete schemas, see the
[FMF input reference](../docs/inputs/fmf-input.md),
[Hypersonic input reference](../docs/inputs/hypersonic-input.md),
[Summary CSV reference](../docs/results/summary-csv.md), and
[VTP reference](../docs/results/vtp.md).

## Running and opening results

Run a table from the repository root with the command below. To inspect FMF
results, launch `panelsolver-gui fmf`; for Hypersonic results, launch
`panelsolver-gui hypersonic`. Open the listed CSV, select a row, and choose
**Run Selected Cases**. The GUI loads the saved VTP for the selected case.

The CLI summary for a table is
`examples/<domain>/outputs/<table>_result.csv`. Additional examples keep their
VTP files in `examples/<domain>/outputs/<category>/<case_id>.vtp`; basic VTPs
remain directly under `outputs/`.

## Choosing an example

| Example | Geometry | What it demonstrates |
|---|---|---|
| Basic | Plate | Minimal input, execution and result inspection |
| Sphere-cone: Angle Effects | Sphere-cone | Different flow directions: surface loads and CL/CD change with angle of attack |
| Attitude Modes | Cube | The same flow direction expressed through beta_sin, beta_tan and bank gives matching results |
| Components | Cube and offset plate | Ordered multi-STL inputs and total/component loads |
| Flow Modes (FMF) | Plate | Mode A and atmosphere-resolved Mode B give matching coefficients |
| Pressure Models (Hypersonic) | Plate and cube | Windward equations and leeward Prandtl–Meyer expansion |
| Shielding | Double plate | Ray shielding off and on |
| Sectional Loads, Sectional Cp | Plate | GUI-only: sectional definitions applied to the Basic (Hypersonic) or Flow Modes (FMF) table; see [GUI operation](../docs/running/gui.md) |

Both domains offer **File > New from Example > Sphere-cone: Angle Effects**.
It copies the selected domain's three-case table and the shared STL to your
workspace; select all three rows and run them normally.

## FMF

### `fmf/basic.csv`

- Purpose: a minimal first run for Sentman Mode A.
- Run: `panelsolver fmf --input examples/fmf/basic.csv`
- GUI file: `examples/fmf/basic.csv`
- Main inputs: `plate.stl`, `S=5`, `Ti_K=Tw_K=300`, and 10-degree alpha.
- Observe: one total row and `outputs/fmf_basic.vtp` are produced. Read `CA`,
  `CD`, and `CL`; inspect normal and tangential traction in the Viewer.
- Output: `examples/fmf/outputs/`.

### `fmf/sphere_cone.csv`

- Purpose: inspect curved-surface normal and tangential loads as alpha changes.
- Run: `panelsolver fmf --input examples/fmf/sphere_cone.csv`
- GUI file: `examples/fmf/sphere_cone.csv`.
- Main inputs: shared `sphere_cone.stl`, Sentman Mode A, `S=5`,
  `Ti_K=Tw_K=300`, alpha = 0, 15, 30 degrees and beta = 0.
- Observe: nearly zero CL/CY at zero alpha; changing alpha produces asymmetric
  normal and tangential traction and changes CL/CD. Inspect both
  `normal_traction_coeff` and `tangential_traction_coeff`; FMF does not output Cp.
- Output: `examples/fmf/outputs/sphere_cone/` for VTP and
  `examples/fmf/outputs/sphere_cone_result.csv` for the summary.

### `fmf/flow_modes.csv`

- Purpose: compare FMF Mode A and atmosphere-resolved Mode B at the same
  freestream state.
- Run: `panelsolver fmf --input examples/fmf/flow_modes.csv`
- GUI file: `examples/fmf/flow_modes.csv`
- Main inputs: `plate.stl`, `Tw_K=300`, 5-degree alpha; Mode A uses
  `S=20.711805563427` and `Ti_K=195.081`, while Mode B uses `Mach=25` and
  `Altitude_km=100`.
- Observe: `mode` is respectively `A` and `B`; resolved `out_S`, `out_Ti_K`,
  and all eight coefficients agree within an absolute
  tolerance (`1e-10`). This is an equivalence-within-tolerance example, not an
  exact decimal identity requirement.
- Output: `examples/fmf/outputs/flow_modes/`.

### `fmf/shielding.csv`

- Purpose: compare unshielded and rtree ray-shielded loads.
- Run: `panelsolver fmf --input examples/fmf/shielding.csv`
- GUI file: `examples/fmf/shielding.csv`
- Main inputs: two aligned plates in `double_plate.stl`, `S=5`,
  `Ti_K=Tw_K=300`, zero attitude, and `ray_backend=rtree`.
- Observe: shielding off has 0 shielded faces. Shielding on marks the rear two
  of four faces as shielded, sets their complete Sentman traction to zero, and
  halves the resultant force (`CA` and `CD` are halved here).
- Output: `examples/fmf/outputs/shielding/`.

### `fmf/components.csv`

- Purpose: show ordered multi-STL input and total/component summary rows.
- Run: `panelsolver fmf --input examples/fmf/components.csv`
- GUI file: `examples/fmf/components.csv`
- Main inputs: `cube.stl;plate_offset_x2.stl`, `S=5`, `Ti_K=Tw_K=300`,
  `alpha_deg=15`, and `beta_or_bank_deg=10`.
- Observe: the summary contains one total followed by two component rows.
  `component_stl_path` follows the input STL order, and each of the eight total
  coefficients equals the sum of the two component values within the Sentman
  tolerance.
- Output: `examples/fmf/outputs/components/`.

### `fmf/attitude_modes.csv`

- Purpose: express one freestream direction through `beta_sin`, `beta_tan`,
  and `bank` inputs.
- Run: `panelsolver fmf --input examples/fmf/attitude_modes.csv`
- GUI file: `examples/fmf/attitude_modes.csv`
- Main inputs: `cube.stl`; `(alpha, second angle, mode)` is `(0,10,beta_sin)`,
  `(0,10,beta_tan)`, and `(10,90,bank)` with otherwise identical FMF inputs.
- Observe: the resolved freestream direction and all eight coefficients agree
  within the Sentman tolerance.
- Output: `examples/fmf/outputs/attitude_modes/`.

## Hypersonic

### `hypersonic/basic.csv`

- Purpose: a minimal first run using the default pressure selectors.
- Run: `panelsolver hypersonic --input examples/hypersonic/basic.csv`
- GUI file: `examples/hypersonic/basic.csv`
- Main inputs: `plate.stl`, `Mach=6`, `gamma=1.4`, and 10-degree alpha; omitted
  selectors default to windward Newtonian and leeward `shield`.
- Observe: one total row and `outputs/hypersonic_basic.vtp` are produced. Read
  `CA`, `CD`, and `CL`; inspect `cp` in the Viewer.
- Output: `examples/hypersonic/outputs/`.

### `hypersonic/sphere_cone.csv`

- Purpose: inspect curved-surface pressure as alpha changes.
- Run: `panelsolver hypersonic --input examples/hypersonic/sphere_cone.csv`
- GUI file: `examples/hypersonic/sphere_cone.csv`.
- Main inputs: shared `sphere_cone.stl`, `Mach=6`, `gamma=1.4`,
  `modified_newtonian` windward and `shield` leeward, alpha = 0, 15, 30 degrees
  and beta = 0; ray shielding is off.
- Observe: nearly zero CL/CY at zero alpha, high nose Cp, and stronger windward
  cone pressure with increasing alpha. Compare Cp and CL/CD between cases.
- Output: `examples/hypersonic/outputs/sphere_cone/` for VTP and
  `examples/hypersonic/outputs/sphere_cone_result.csv` for the summary.

### `hypersonic/pressure_models.csv`

- Purpose: compare all four windward equations and exercise leeward
  Prandtl–Meyer expansion.
- Run: `panelsolver hypersonic --input examples/hypersonic/pressure_models.csv`
- GUI file: `examples/hypersonic/pressure_models.csv`
- Main inputs: the four windward cases use `plate.stl`, `Mach=6`, `gamma=1.4`,
  leeward `shield`, and whole-vehicle `alpha_deg=75`. With this plate orientation,
  VTP `theta_deg=105`, so the implemented relation
  `local turning = theta_deg - 90` gives 15 degrees in the attached comparison
  region. The fifth case uses a cube, nonzero alpha/beta, Newtonian windward,
  and Prandtl–Meyer leeward behavior.
- Naming: the `newt_*` case IDs here denote Newtonian-family or
  Newtonian/Prandtl–Meyer physical-method combinations.
- Observe: Newtonian, Modified Newtonian, Tangent Wedge, and Tangent Cone all
  return finite but distinct `cp` values. The `newt_pm.vtp` cube has negative
  `cp` on at least one leeward panel.
- Output: `examples/hypersonic/outputs/pressure_models/`.

### `hypersonic/shielding.csv`

- Purpose: compare Newtonian loads with ray shielding off and on.
- Run: `panelsolver hypersonic --input examples/hypersonic/shielding.csv`
- GUI file: `examples/hypersonic/shielding.csv`
- Main inputs: `double_plate.stl`, `Mach=6`, `gamma=1.4`, Newtonian windward,
  leeward `shield`, zero attitude, and `ray_backend=rtree`.
- Observe: ray shielding on marks the rear two of four faces, removes their
  load, and halves the resultant force (`CA` and `CD` are halved here).
- Output: `examples/hypersonic/outputs/shielding/`.

`leeward_eq=shield` and `shielding_on=1` are different features. The former is
a pressure-model choice that assigns zero `cp` to active leeward panels. The
latter performs geometric ray-occlusion testing and zeros any hidden panel,
regardless of its windward/leeward pressure selector. See the
[Ray shielding reference](../docs/methods/ray-shielding.md) for the common
method and its exact-zero load consequence.

### `hypersonic/components.csv`

- Purpose: combine multi-STL output with per-component pressure selectors.
- Run: `panelsolver hypersonic --input examples/hypersonic/components.csv`
- GUI file: `examples/hypersonic/components.csv`
- Main inputs: `cube.stl;plate_offset_x2.stl`, `Mach=6`, `gamma=1.4`, nonzero
  alpha/beta, `modified_newtonian;newtonian`, and
  `prandtl_meyer;shield`.
- Observe: both selector lists apply in STL order. The summary contains two
  component rows in the same order, and each total coefficient equals the
  component sum within the applicable hypersonic tolerance.
- Output: `examples/hypersonic/outputs/components/`.

### `hypersonic/attitude_modes.csv`

- Purpose: express one freestream direction through `beta_sin`, `beta_tan`,
  and `bank` inputs.
- Run: `panelsolver hypersonic --input examples/hypersonic/attitude_modes.csv`
- GUI file: `examples/hypersonic/attitude_modes.csv`
- Main inputs: `cube.stl`, `Mach=6`, `gamma=1.4`, Newtonian windward, leeward
  `shield`; the three attitude tuples are the same as in the FMF example.
- Observe: the resolved freestream direction and all eight coefficients agree
  within the algebraic hypersonic tolerance (`1e-10`).
- Output: `examples/hypersonic/outputs/attitude_modes/`.

## Sphere-cone geometry and comparison

The shared `geometry/sphere_cone.stl` is an original idealized convex body with
9,216 outward-oriented triangles (binary STL, 460,884 bytes). It has a spherical
nose of radius 0.2 m tangent to a 15-degree half-angle cone, a base radius of
0.5 m and a flat rear closure. Total length is approximately 1.293285 m.
The nose is the origin and the body extends along +X_STL; zero-attitude flow
travels along +X_STL. Moment reference is the nose, reference lengths are 1 m,
and the fixed reference area is pi/4 m² at every attitude.

Use the same camera and fixed color range between angles: 0–2 for Hypersonic
Cp, 0–3 for FMF normal traction, and 0–1.5 for FMF tangential traction. These are
separate domain examples at different flow regimes, not matched physical states
or a physical validation comparison. The Hypersonic model does not resolve a
shock layer, viscosity or wake; FMF includes both normal and tangential traction.
The default mesh supports visualization and is not a discretization-error bound.

In a source checkout, regenerate the supplied STL and both CSVs, then run them:

```bash
uv sync --locked
uv run --no-sync python scripts/generate_sphere_cone_example.py
uv run --no-sync panelsolver fmf -i examples/fmf/sphere_cone.csv
uv run --no-sync panelsolver hypersonic -i examples/hypersonic/sphere_cone.csv
```

Generated VTPs and summaries are excluded from distribution archives and the
wheel. The geometry generator is a source-checkout/sdist tool, not required to
run the bundled examples. Generate a finer mesh in a separate tree with
`--destination PATH --refinement 2`.
