# Examples

These examples are small, portable feature demonstrations. Start with
`basic.csv`, then run only the table for the feature you want to inspect. They
are intentionally separate from the Phase 1 fixtures and are not numerical
goldens.

All paths are relative to the case table. The added tables explicitly set
`save_vtp_on=1`; the two minimal `basic.csv` tables obtain the same value from
the documented default. Every case therefore writes a VTP for GUI inspection.
NPZ output and the former `save_npz_on` field are not part of the current case
schema; Summary CSV and VTP are the supported outputs.

The examples use a 1 m scale, an origin moment reference, `Aref_m2=1`, and 1 m
moment reference lengths. These simple global references make component rows
add directly to the total row for all eight coefficients. The four meshes in
`geometry/` are simple geometric fixtures carried forward byte-identically from
the small Phase 1 inputs. The current example CSVs were created for Panel Solver;
they do not copy the historical sample matrices. These files are project
material distributed under Apache-2.0. Examples exercise the current canonical
readers, defaults, validation, and output semantics.

The first-release examples archive is named
`panelsolver-examples-v<version>.zip`. It preserves this `examples/` layout and
adds `LICENSE` and `THIRD_PARTY_NOTICES.md` at the archive root. Generated
outputs, caches, NPZ, legacy `.xls`, test fixtures, and migration inputs are not
release examples.

The current example directories use the canonical flow-domain names
`examples/fmf/` and `examples/hypersonic/`.

For the complete schemas, see the
[FMF input reference](../docs/reference/fmf-input.md),
[Hypersonic input reference](../docs/reference/hypersonic-input.md),
[Summary CSV reference](../docs/results/summary-csv.md), and
[VTP reference](../docs/results/vtp.md).

## Running and opening results

Run a table from the repository root with its canonical command below. To
inspect FMF results, launch `panelsolver-gui fmf`; for Hypersonic results,
launch `panelsolver-gui hypersonic`. Open the listed CSV, select a row, and
choose **Run Selected Cases**. The GUI loads the saved VTP for the selected case.

The CLI summary for a table is
`examples/<domain>/outputs/<table>_result.csv`. Additional examples keep their
VTP files in `examples/<domain>/outputs/<category>/<case_id>.vtp`; basic VTPs
remain directly under `outputs/`.

## FMF

### `fmf/basic.csv`

- Purpose: a minimal first run for Sentman Mode A.
- Run: `panelsolver fmf --input examples/fmf/basic.csv --workers 1 --checkpoint-every-cases 0`
- GUI file: `examples/fmf/basic.csv`
- Main inputs: `plate.stl`, `S=5`, `Ti_K=Tw_K=300`, and 10-degree alpha.
- Observe: one total row and `outputs/fmf_basic.vtp` are produced.
- Output: `examples/fmf/outputs/`.

### `fmf/flow_modes.csv`

- Purpose: compare FMF Mode A and atmosphere-resolved Mode B at the same
  freestream state.
- Run: `panelsolver fmf --input examples/fmf/flow_modes.csv --workers 1 --checkpoint-every-cases 0`
- GUI file: `examples/fmf/flow_modes.csv`
- Main inputs: `plate.stl`, `Tw_K=300`, 5-degree alpha; Mode A uses
  `S=20.711805563427` and `Ti_K=195.081`, while Mode B uses `Mach=25` and
  `Altitude_km=100`.
- Observe: `mode` is respectively `A` and `B`; resolved `out_S`, `out_Ti_K`,
  and all eight coefficients agree within the existing Sentman absolute
  tolerance (`1e-10`). This is an equivalence-within-tolerance example, not an
  exact decimal identity requirement.
- Output: `examples/fmf/outputs/flow_modes/`.

### `fmf/shielding.csv`

- Purpose: compare unshielded and rtree ray-shielded loads.
- Run: `panelsolver fmf --input examples/fmf/shielding.csv --workers 1 --checkpoint-every-cases 0`
- GUI file: `examples/fmf/shielding.csv`
- Main inputs: two aligned plates in `double_plate.stl`, `S=5`,
  `Ti_K=Tw_K=300`, zero attitude, and `ray_backend=rtree`.
- Observe: shielding off has 0 shielded faces. Shielding on marks the rear two
  of four faces as shielded, sets their complete Sentman traction to zero, and
  halves the resultant force (`CA` and `CD` are halved here).
- Output: `examples/fmf/outputs/shielding/`.

### `fmf/components.csv`

- Purpose: show ordered multi-STL input and total/component summary rows.
- Run: `panelsolver fmf --input examples/fmf/components.csv --workers 1 --checkpoint-every-cases 0`
- GUI file: `examples/fmf/components.csv`
- Main inputs: `cube.stl;plate_offset_x2.stl`, `S=5`, `Ti_K=Tw_K=300`,
  `alpha_deg=15`, and `beta_or_bank_deg=10`.
- Observe: the summary contains one total followed by two component rows.
  `component_stl_path` follows the input STL order, and each of the eight total
  coefficients equals the sum of the two component values within the Sentman
  tolerance.
- Output: `examples/fmf/outputs/components/`.

### `fmf/attitude_modes.csv`

- Purpose: express one freestream direction through `beta_tan`, `beta_sin`,
  and `bank` inputs.
- Run: `panelsolver fmf --input examples/fmf/attitude_modes.csv --workers 1 --checkpoint-every-cases 0`
- GUI file: `examples/fmf/attitude_modes.csv`
- Main inputs: `cube.stl`; `(alpha, second angle, mode)` is `(0,10,beta_tan)`,
  `(0,10,beta_sin)`, and `(10,90,bank)` with otherwise identical FMF inputs.
- Observe: the resolved freestream direction and all eight coefficients agree
  within the Sentman tolerance.
- Output: `examples/fmf/outputs/attitude_modes/`.

## Hypersonic

### `hypersonic/basic.csv`

- Purpose: a minimal first run using the default pressure selectors.
- Run: `panelsolver hypersonic --input examples/hypersonic/basic.csv --workers 1 --checkpoint-every-cases 0`
- GUI file: `examples/hypersonic/basic.csv`
- Main inputs: `plate.stl`, `Mach=6`, `gamma=1.4`, and 10-degree alpha; omitted
  selectors default to windward Newtonian and leeward `shield`.
- Observe: one total row and `outputs/hypersonic_basic.vtp` are produced.
- Output: `examples/hypersonic/outputs/`.

### `hypersonic/pressure_models.csv`

- Purpose: compare all four windward equations and exercise leeward
  Prandtl–Meyer expansion.
- Run: `panelsolver hypersonic --input examples/hypersonic/pressure_models.csv --workers 1 --checkpoint-every-cases 0`
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
- Run: `panelsolver hypersonic --input examples/hypersonic/shielding.csv --workers 1 --checkpoint-every-cases 0`
- GUI file: `examples/hypersonic/shielding.csv`
- Main inputs: `double_plate.stl`, `Mach=6`, `gamma=1.4`, Newtonian windward,
  leeward `shield`, zero attitude, and `ray_backend=rtree`.
- Observe: ray shielding on marks the rear two of four faces, removes their
  load, and halves the resultant force (`CA` and `CD` are halved here).
- Output: `examples/hypersonic/outputs/shielding/`.

`leeward_eq=shield` and `shielding_on=1` are different features. The former is
a pressure-model choice that assigns zero `cp` to active leeward panels. The
latter performs geometric ray-occlusion testing and zeros any hidden panel,
regardless of its windward/leeward pressure selector.

### `hypersonic/components.csv`

- Purpose: combine multi-STL output with per-component pressure selectors.
- Run: `panelsolver hypersonic --input examples/hypersonic/components.csv --workers 1 --checkpoint-every-cases 0`
- GUI file: `examples/hypersonic/components.csv`
- Main inputs: `cube.stl;plate_offset_x2.stl`, `Mach=6`, `gamma=1.4`, nonzero
  alpha/beta, `modified_newtonian;newtonian`, and
  `prandtl_meyer;shield`.
- Observe: both selector lists apply in STL order. The summary contains two
  component rows in the same order, and each total coefficient equals the
  component sum within the applicable hypersonic tolerance.
- Output: `examples/hypersonic/outputs/components/`.

### `hypersonic/attitude_modes.csv`

- Purpose: express one freestream direction through `beta_tan`, `beta_sin`,
  and `bank` inputs.
- Run: `panelsolver hypersonic --input examples/hypersonic/attitude_modes.csv --workers 1 --checkpoint-every-cases 0`
- GUI file: `examples/hypersonic/attitude_modes.csv`
- Main inputs: `cube.stl`, `Mach=6`, `gamma=1.4`, Newtonian windward, leeward
  `shield`; the three attitude tuples are the same as in the FMF example.
- Observe: the resolved freestream direction and all eight coefficients agree
  within the algebraic hypersonic tolerance (`1e-10`).
- Output: `examples/hypersonic/outputs/attitude_modes/`.
