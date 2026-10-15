# Sectional loads and Cp

Sectional workflows show how the load is distributed along an axis of the
vehicle, for example along the span or the length. You define the axis in a
separate [definition CSV](../reference/sectional-definitions.md), so your case
tables do not change.

| | Sectional loads | Sectional Cp |
|---|---|---|
| What it does | Splits the surface into equal-width strips along the axis and adds up the force and moment coefficients of each strip. | Cuts the surface with parallel planes and records the panel value along each cut line. |
| Typical use | Spanwise or lengthwise load distribution. | Pressure distribution around a cross-section. |
| Value | `delta_CA` … `delta_CL` for each strip | Hypersonic `cp`, or FMF `normal_traction_coeff` |
| Result file | [Sectional load CSV](../reference/sectional-loads-csv.md) | [Sectional Cp CSV](../reference/sectional-cp-csv.md) |

FMF Sectional Cp uses the normal traction coefficient, which is the
free-molecular pressure-like load on each panel. It is not the same quantity as
a continuum pressure coefficient, and it leaves out the tangential (shear) load.

Both workflows solve each selected case once, then apply every selected
definition to that result. They do not need or create a Summary CSV or VTP
file.

## Sectional loads in the GUI

**Try the example.** Choose **File > New from Example > Sectional Loads** and
pick a folder. The GUI copies a case table (FMF **Flow Modes** or Hypersonic
**Basic**), its geometry, and `sectional_loads.csv`, then opens the table and
the **Sectional Loads** window with the definitions loaded. Files you have
already changed are not overwritten.

**Use your own files:**

1. Open a case table in the main window. Select the cases to run, or select
   none to run all of them.
2. Choose **File > Sectional Loads...** and open your
   [definition CSV](../reference/sectional-definitions.md#sectional-load-definitions).
3. In the Sectional Loads window, select the definitions to run, or select none
   to run all of them. The run scope shows how many cases and definitions will
   run.
4. Choose **Run All Cases × Sections** (or **Run Selected Cases × Sections**),
   then choose where to save the result. The suggested file is
   `<input folder>/outputs/<input name>_sectional_loads.csv`.
5. When the run finishes, the result is saved automatically. The window shows
   the status, the number of completed case–section pairs, and the saved path.
   Open the CSV to see the numbers; the window does not show a result table.

The window only opens definition files; it does not edit them. Edit the CSV in
another program, then choose **Reload**. The selections and definitions are
fixed when a run starts, so changing them during a run does not affect that
run.

**Cancelling and errors.** **Cancel** stops the run after the cases in progress
finish. Any case–section pairs that finished are still saved, and the CSV
records whether the run was `completed`, `failed`, or `cancelled`. If nothing
finished, no file is written. If the result cannot be saved, use **Retry** in
the error message or **Retry Save...** later; nothing is calculated again. If
you close the window with unsaved results, you are asked whether to **Save**,
**Discard**, or **Cancel**.

Ordinary runs, Sectional Loads, and Sectional Cp cannot run at the same time.

## Sectional Cp in the GUI

Sectional Cp works like Sectional Loads, using **File > Sectional Cp...** and a
[Cp definition CSV](../reference/sectional-definitions.md#sectional-cp-definitions).
The suggested output file is `<input name>_sectional_cp.csv`.

To try it, choose **File > New from Example > Sectional Cp**. The GUI copies
the example files, opens the case table, and opens the **Sectional Cp** window
with `sectional_cp.csv` loaded. The calculation starts only when you choose
Run and an output file.

Each result row is one straight line segment across one panel, with both end
points and that panel's value. The window does not plot the result; use the
CSV.

## Sectional loads from the CLI

Add the `sectional-loads` subcommand after the domain:

```bash
panelsolver fmf sectional-loads -i examples/fmf/flow_modes.csv -d examples/sectional_loads.csv -o outputs/fmf_sections.csv
panelsolver hypersonic sectional-loads -i examples/hypersonic/basic.csv -d examples/sectional_loads.csv -o outputs/hypersonic_sections.csv
```

These commands work from the repository root (or the extracted examples
archive).

| Option | What it does |
|---|---|
| `-i`, `--input` | Case table (required). |
| `-d`, `--definitions` | Sectional load definition CSV (required). |
| `-o`, `--output` | Result CSV (required). |
| `--cases ID [ID ...]` | Run only these cases (spaces or commas). Default: all. |
| `--sections ID [ID ...]` | Run only these definitions, by exact `section_id`. Quote IDs that contain spaces. Use `--sections=--label` for an ID that starts with `-`. Default: all. |
| `-j`, `--workers` | Number of cases to run in parallel. Default: 1. |
| `--plain`, `--verbose`, `--debug` | Same as for ordinary runs. |

CSV results follow case-table order and then definition-file order. Case
execution and progress messages can follow a different order, even with one
worker. An unknown case or section ID is an error. The whole definition file
is checked before any case runs.

If a definition cannot be applied to a case's geometry, the batch stops and the
pairs that already finished are saved. Press Ctrl-C to cancel; work already in
progress may finish first. Failed pairs are never written as zero results.

| Exit code | Meaning |
|---|---|
| `0` | Every pair finished and the result was saved. |
| `1` | A validation, calculation, or save error occurred. Pairs that finished are still saved when possible. |
| `2` | The command-line arguments are invalid. |
| `130` | The run was cancelled and the finished pairs were saved. |

If no pair finished, the output file is not created or changed.

## Sectional Cp from the CLI

Use the `sectional-cp` subcommand with a
[Cp definition CSV](../reference/sectional-definitions.md#sectional-cp-definitions):

```bash
panelsolver hypersonic sectional-cp -i examples/hypersonic/basic.csv -d examples/sectional_cp.csv -o outputs/hypersonic_sectional_cp.csv
panelsolver fmf sectional-cp -i examples/fmf/basic.csv -d examples/sectional_cp.csv -o outputs/fmf_sectional_cp.csv
```

The options are the same as for `sectional-loads`. The result contains
[line segments and panel values](../reference/sectional-cp-csv.md). If one cut
plane fails, the other planes and definitions still run and the command exits
with `1`. Cancelling exits with `130`.
