# Examples

Panel Solver comes with small example cases. Each one shows one feature, so
you can see what the inputs look like and what result to expect before you
prepare your own case.

## Open an example

- **In the GUI:** choose **File > New from Example** and pick an example from
  the list below. Select a folder; the GUI copies the case table and its
  geometry there and opens the table. Select the rows and run them.
- **From the CLI:** use the `examples/` folder of a source checkout, or extract
  `panelsolver-examples-v<version>.zip` from the release page. Run the command
  from the folder that contains `examples/`.

For example:

```bash
panelsolver fmf --input examples/fmf/flow_modes.csv
```

The Summary CSV is written to `examples/<domain>/outputs/<table>_result.csv`.
VTP files of the Basic examples go directly into `outputs/`; the others go into
a subfolder named after the example, for example `outputs/shielding/`.

All example geometry is in metres (`stl_scale_m_per_unit=1`). The cases use the
origin as the moment reference point, 1 m reference lengths, and
`Aref_m2=1`, except the sphere-cone examples, which use the cone's maximum
cross-section area, π × (0.5 m)².

## Example list

The **New from Example** menu offers these examples. Most exist in both
domains; **Flow Modes** is FMF only and **Pressure Models** is Hypersonic only.

| Menu item | Case table | Geometry | What it shows |
|---|---|---|---|
| **Basic** | `fmf/basic.csv`, `hypersonic/basic.csv` | Plate | The smallest complete run. Walked through in the [Quickstart](quickstart.md). |
| **Sphere-cone: Angle Effects** | `fmf/sphere_cone.csv`, `hypersonic/sphere_cone.csv` | Sphere-cone | How surface loads and `CL`/`CD` change with angle of attack (0, 15, 30 degrees). |
| **Attitude Modes** | `fmf/attitude_modes.csv`, `hypersonic/attitude_modes.csv` | Cube | One flow direction written in the three attitude modes `beta_sin`, `beta_tan`, and `bank`. All three rows give the same results. |
| **Components** | `fmf/components.csv`, `hypersonic/components.csv` | Cube and offset plate | A case with two STL parts. The Summary CSV has a total row and one row per part, and the parts add up to the total. In Hypersonic, each part has its own pressure method. |
| **Flow Modes** (FMF) | `fmf/flow_modes.csv` | Plate | The same flow given as `S` and `Ti_K` (Mode A) and as `Mach=25` at `Altitude_km=100` (Mode B). Both give the same coefficients. |
| **Pressure Models** (Hypersonic) | `hypersonic/pressure_models.csv` | Plate and cube | The four windward pressure methods side by side, and the Prandtl–Meyer leeward method. |
| **Shielding** | `fmf/shielding.csv`, `hypersonic/shielding.csv` | Two plates, one behind the other | Ray shielding off and on. With shielding on, the rear plate is hidden from the flow, carries no load, and the force is halved. |
| **Sectional Loads** | FMF `flow_modes.csv` or Hypersonic `basic.csv`, with `sectional_loads.csv` | Plate | Strip loads along an axis. Opens the Sectional Loads window. See [Sectional loads and Cp](../guides/sectional.md). |
| **Sectional Cp** | FMF `flow_modes.csv` or Hypersonic `basic.csv`, with `sectional_cp.csv` | Plate | Panel values along cutting planes. Opens the Sectional Cp window. |

The sectional examples can also be run from the CLI, as shown in
[Sectional loads and Cp](../guides/sectional.md#sectional-loads-from-the-cli).

## What to look for

- **Basic:** one `total` row; read `CA`, `CD`, and `CL`. In the Viewer, look at
  `Cp` (Hypersonic) or the normal and tangential traction (FMF).
- **Sphere-cone:** at zero angle of attack, `CL` and `CY` are almost zero. As
  the angle grows, the load on the windward side increases. Keep the same
  camera and color range when you compare the three cases.
- **Attitude Modes, Flow Modes:** the rows describe the same physical condition,
  so their coefficients agree within a very small numerical tolerance. These examples
  are a good way to check that you understand the input conventions.
- **Components:** compare the `component` rows with the `total` row, and check
  `component_stl_path` to see which row is which part.
- **Shielding:** compare `shielded_faces` and the coefficients between the two
  rows. In the Viewer, color by **Shielded** to see the hidden panels.

`examples/README.md`, included in the checkout and in the examples archive,
lists the exact inputs of every case.
