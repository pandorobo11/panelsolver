# Glossary

**Attitude** — The direction of the flow relative to the vehicle, given by `alpha_deg`,
`beta_or_bank_deg`, and `attitude_input`. See
[Preparing cases](../guides/preparing-cases.md#attitude-modes).

**Body axes** — The axes used for `CA`, `CY`, `CN`, and the moments:
`(X_body, Y_body, Z_body) = (−X_stl, +Y_stl, −Z_stl)`. See
[Coordinate and attitude conventions](../methods/coordinate-and-attitude-conventions.md).

**Case** — One calculation: a geometry, a flow condition, an attitude, and reference
quantities. One row of a case table.

**Case ID** (`case_id`) — The unique name of a case. It is also the name of the case's VTP file.

**Case signature** (`case_signature`) — A fingerprint of a case, stored in the Summary CSV and VTP. It changes
when the geometry or an input that affects the calculation changes. The GUI uses it to check that a
VTP file belongs to the current case.

**Case table** — A CSV, XLSX, or XLSM file with one case per row.

**Checkpoint** — An intermediate save of the Summary CSV during a long run. See
[Batch runs and recovery](../guides/batch-runs.md#checkpoints).

**Component** — One STL file of a case that has several. Components are numbered from zero
in `stl_path` order, and the Summary CSV reports each one separately.

**Domain** (flow domain) — FMF or Hypersonic. The domain decides which physical model is used and which
flow-condition columns the case table has. See
[Choosing a solver](../index.md#choosing-a-solver).

**FMF** — Free-molecular flow: very low-density flow in which gas molecules rarely
collide with each other near the vehicle. Panel Solver uses the Sentman model.
See [FMF / Sentman model](../methods/fmf.md).

**Leeward panel** — A panel that faces away from the oncoming flow.

**Mode A / Mode B** — The two ways of giving the FMF flow condition: `S` and `Ti_K` (Mode A), or
`Mach` and `Altitude_km` (Mode B). See the
[FMF case table](fmf-case-table.md).

**Moment reference point** — The point (`ref_x_m`, `ref_y_m`, `ref_z_m`) about which moments are
calculated.

**Panel** — One triangle of the STL mesh. Panel Solver calculates the load on each panel
separately and then adds them up.

**Ray shielding** — An option (`shielding_on=1`) that finds panels hidden from the flow by other
parts of the geometry and sets their load to zero. See
[Ray shielding](../methods/ray-shielding.md).

**Reference area and lengths** — `Aref_m2` and `Lref_Cl_m`, `Lref_Cm_m`, `Lref_Cn_m`, used to turn forces and
moments into dimensionless coefficients. See
[Choose reference quantities](../guides/preparing-cases.md#choose-reference-quantities).

**Scalar** — A value stored for each panel in the VTP file, such as `cp`, that the Viewer
can color by.

**Sectional loads / Sectional Cp** — Load or panel-value distributions along an axis. See
[Sectional loads and Cp](../guides/sectional.md).

**Stability axes** — The axes used for `CD` and `CL`. They are body axes rotated by the stability
angle `alpha_stability_deg`. See
[Load and coefficient conventions](../methods/load-and-coefficient-conventions.md#stability-axis-force-coefficients).

**STL frame** — The coordinate system of your STL file. With zero attitude, the flow travels
along +X of this frame.

**Summary CSV** — The result file with the force and moment coefficients of every case. See
the [Summary CSV reference](summary-csv.md).

**Traction (normal and tangential)** — The load per unit area on a panel. The normal part acts like pressure; the
tangential part acts like shear (friction). Hypersonic methods give only the
normal part; FMF gives both.

**VTP** — The VTK file format used for the surface result of each case. See the
[VTP reference](vtp.md).

**Windward panel** — A panel that faces the oncoming flow.

**Workers** — The number of cases calculated at the same time. See
[Batch runs and recovery](../guides/batch-runs.md#workers-and-result-order).
