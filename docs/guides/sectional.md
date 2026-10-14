# Sectional loads and Cp

Sectional workflows slice each solved case along an axis that you define in a
separate [definition CSV](../reference/sectional-definitions.md). Your case
tables do not change.

- **Sectional loads** split the surface into equal-width strips and integrate
  the aerodynamic coefficients of each strip. See the
  [sectional load CSV](../reference/sectional-loads-csv.md).
- **Sectional Cp** cuts the surface with parallel planes and saves the panel
  value along each cut. See the [sectional Cp CSV](../reference/sectional-cp-csv.md).

## Sectional loads in the GUI

To start with a complete example, choose **File > New from Example > Sectional
Loads** and select a workspace directory. This copies the current domain's case
table (FMF Flow Modes or Hypersonic Basic), its STL geometry, and
`sectional_loads.csv`. The case table and the Sectional Loads dialog open with
those copied inputs, ready to run. Existing modified files are not overwritten.
Edit the copied definition CSV externally and use **Reload** to try changes.

For your own files:

1. Open a case table. Select case rows to run a subset, or leave the case selection
   empty to run all loaded cases, as with ordinary calculation.
2. Choose **File > Sectional Loads...** and open a separate
   [sectional definition CSV](../reference/sectional-definitions.md#sectional-load-definitions).
3. Select definitions in the read-only table to run a subset, or leave the
   selection empty to run all loaded definitions. Case and definition selections
   are independent; the run scope shows both effective counts and lists the
   target case IDs.
4. Choose **Run All Cases × Sections** or **Run Selected Cases × Sections**, then
   select the [sectional result CSV](../reference/sectional-loads-csv.md) destination.
   The suggested path is `<input_dir>/outputs/<input_stem>_sectional_loads.csv`.
   Cancelling the file dialog does not start a calculation or change retained results.
5. Each target case is solved once and all selected definitions use that same
   in-memory execution. Results are saved automatically to the chosen path.
   The dialog shows completion/save status, pair counts and the saved path;
   inspect numerical results in the CSV. There is no result table or separate
   Export action. The Viewer VTP is not an input.

The definition table supports opening and reloading files, not definition
editing. Edit the CSV externally and reload it before starting a new batch.
A failed reload clears the runnable definitions and reports the error.
The open definition CSV is protected from ordinary Summary CSV output as well
as sectional output, including while the Sectional Loads window is hidden.
Opening or reloading definitions is disabled during ordinary calculation.

Starting a run freezes both selections and definitions. Later selection/file
changes do not relabel completed results. Run and export status are separate:
cancelled or failed batches save any successful pairs to the chosen destination,
with their actual terminal status. If no pair succeeds, the output is unchanged.
A save failure retains the calculation and offers **Retry** in the error
dialog. It opens the save chooser after the export worker has finished cleanup.
**Close** dismisses that message; **Retry Save...** remains available to select a
destination and save without rerunning physics. These actions also save retained
partial results with their original failed or cancelled batch status. The button is hidden after
successful saving and never substitutes current selections for the failed-save
snapshot.
Result rows include their actual case signatures, section IDs and terminal
batch status, including partial results.

Normal case solving and sectional solving cannot run simultaneously. Cancel
requests stop at safe boundaries; already-running parallel cases can finish.
Closing during a run requests cancellation and waits for calculation, automatic
export of successful pairs, and worker cleanup. Ordinary runs remain disabled
until both calculation and saving finish.
If saving fails while a close request is waiting, the window remains open so
you can use **Retry Save...**. Closing the Sectional dialog (including Esc) or
the main window while a failed-save result is retained offers **Save**,
**Discard**, and **Cancel**. Save closes only after a successful export; cancelling
the file chooser or another save failure keeps the window and results available.
Discard releases that dialog's unsaved result, and Cancel keeps it open.
Main-window close also checks hidden Sectional dialogs and checks Loads and Cp
independently when both hold unsaved results. Results are held only in the current
application session.
No intermediate Summary CSV or VTP is required or created by sectional runs.

For an FMF example, open `examples/fmf/flow_modes.csv`; for Hypersonic, open
`examples/hypersonic/basic.csv`. Both work with `examples/sectional_loads.csv`.


## Sectional Cp in the GUI

Choose **File > New from Example > Sectional Cp** for a complete sample.
After selecting a workspace folder, the application copies the case CSV, STL,
and Cp definitions, replaces the displayed case table with the sample cases,
and opens the Sectional Cp dialog with its definitions loaded. This follows the
same flow and logging as other examples, with no extra confirmation dialog.
Calculation starts only when you choose Run and an output CSV destination.

Choose **File > Sectional Cp...**, open a [Cp definition CSV](../reference/sectional-definitions.md#sectional-cp-definitions),
select cases and definitions (empty selection means all), and run. Try
`examples/sectional_cp.csv` with either domain's basic example. The read-only
workflow, frozen selections, cancellation, automatic CSV saving, and **Retry
Save...** follow Sectional Loads. The suggested output is
`<input_stem>_sectional_cp.csv`.

Each row saves both endpoints and the source panel's constant scalar. Hypersonic
extracts Cp; FMF extracts its normal traction coefficient. The dialog explains
this distinction; it does not plot or interpolate the result. Ordinary solving,
Sectional Loads and Sectional Cp cannot run concurrently. Both definition files
remain protected against overwriting while their dialogs are hidden.

## Sectional loads from the CLI

Both domains can calculate finite-width sectional loads from a separate
[definition CSV](../reference/sectional-definitions.md#sectional-load-definitions):

```bash
panelsolver fmf sectional-loads -i examples/fmf/flow_modes.csv -d examples/sectional_loads.csv -o outputs/fmf_sections.csv
panelsolver hypersonic sectional-loads -i examples/hypersonic/basic.csv -d examples/sectional_loads.csv -o outputs/hypersonic_sections.csv
```

These commands work from the repository root with the supplied examples.
Use `--cases ID [ID ...]` and `--sections ID [ID ...]` independently; omitted
filters select all. Cases keep input-table order; sections keep definition-file
order. Unknown IDs are errors. Case selectors accept comma-separated IDs as in
ordinary solve. Section selectors use exact labels (quote labels with spaces
or commas); `--sections=--label` selects a label beginning with hyphens.

`-i/--input`, `-d/--definitions` and `-o/--output` are required.
`-j/--workers` defaults to one and parallelizes cases through the existing
scheduler. `--plain`, `--verbose` and `--debug` have the usual meanings.
The help describes STL coordinates, metre units, auto range and component IDs.
Axes and ranges are specified only in the definition file.

Each case executes physics once, then applies all selected definitions to that
same in-memory execution. Mode B and other domain case inputs remain supported.
No Summary CSV or VTP is required or generated, regardless of `save_vtp_on`.
The [dedicated result CSV](../reference/sectional-loads-csv.md) includes all bins,
total and component scopes, coverage, references and the physical signature.

The complete definition file is validated before solving. Mesh-dependent
definition failures stop the batch, retaining earlier successful pairs. Ctrl-C
requests cooperative cancellation: serial runs check case/definition boundaries;
parallel workers finish at case boundaries. Already-dispatched work may finish.
Partial results are saved with `batch_status` and completion counts; failed pairs
are never emitted as zero results. Exit codes are 0 for complete success, 1 for
validation/calculation/save failure, 2 for command argument errors, and 130 for
cancellation when any requested partial save succeeds. If no pair succeeds,
the output remains untouched. Save failure is reported independently and returns 1.

## Sectional Cp from the CLI

Use [Cp definitions](../reference/sectional-definitions.md#sectional-cp-definitions) to extract surface sections:

```bash
panelsolver hypersonic sectional-cp -i examples/hypersonic/basic.csv -d examples/sectional_cp.csv -o /tmp/hypersonic_sectional_cp.csv
panelsolver fmf sectional-cp -i examples/fmf/basic.csv -d examples/sectional_cp.csv -o /tmp/fmf_sectional_cp.csv
```

The `--cases`, `--sections`, `--workers`, `--plain`, `--verbose` and `--debug`
options follow `sectional-loads`. Each selected case is solved once. Outputs
contain [panel segments and scalar values](../reference/sectional-cp-csv.md), with
no intermediate VTP or Summary CSV. A failed plane yields exit code 1 while other
planes/definitions continue; cancellation returns 130.
