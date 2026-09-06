# Batch execution and recovery

This page covers how the CLI and GUI handle workers, checkpoints, cancellation,
and recovery from calculation or output-file failures.
Use the [Summary CSV reference](../results/summary-csv.md) and
[VTP reference](../results/vtp.md) to interpret saved result fields.

## Workers and visible ordering

`workers=1` runs cases without parallel execution; larger values allow multiple
cases to run concurrently. With any worker count, execution, progress, and
diagnostics may follow a different order from the input table. Checkpoints append
cases in the order their completed results are accepted by the application.
The final Summary CSV presents all cases in input-table order.

The CLI exposes this setting as `--workers`; the GUI exposes it as **Workers**.

## Checkpoints

The CLI `--checkpoint-every-cases N` option and GUI **Checkpoint every** control
set the same interval. The default is `2000`. Each time another `N` cases have
completed, Panel Solver saves the cases not yet saved successfully. The first
checkpoint atomically replaces any previous run's Summary CSV; later checkpoints
append only new results to that same file, without repeating its header. A failed
checkpoint is retried with all unsaved cases after another `N` cases complete.

After all calculations finish, any remaining unsaved cases are checkpointed,
then the complete Summary CSV is atomically rewritten in input-table order.
Set the interval to `0` to disable all intermediate saves, including the last
partial checkpoint; the final Summary CSV is still attempted. Cancellation or
a calculation failure does not trigger an additional save.

After a checkpoint is written, it is available at the selected Summary CSV
destination and has the fields and rows described in the
[Summary CSV reference](../results/summary-csv.md). It retains results from
completed cases when a later calculation fails or a run is canceled. A
checkpoint can be opened directly as a CSV and stores results rather than
resumable calculation state. Use CLI
`--cases` or a GUI row selection to rerun cases that still need results.

## Cancellation and calculation failures

Cancellation is cooperative. Panel Solver observes it between cases; an active
[ray-shielding query](../methods/ray-shielding.md) or physical-model solve may
finish before the request is observed.

After cancellation, use the retained checkpoint CSV and VTP files from this
run, subject to the write guarantees below. Cases accepted since the last
successful checkpoint are not saved. A new final Summary CSV is not guaranteed
when cancellation occurs before every case finishes.

A calculation failure, such as a geometry-loading or model-execution error,
stops the batch. Previously saved results remain available under the
[write durability guarantee](#write-durability-guarantee).

## Output-file failures and partial success

Output-directory preparation, VTP write, and Summary CSV write failures are
reported separately from calculation failures. The [CLI guide](cli.md) and
[GUI guide](gui.md) define how their respective run statuses present these
failures.

| Failure | What Panel Solver does | What remains usable |
|---|---|---|
| Per-case output-directory or VTP write failure | Keeps that case's calculated result and continues with later cases. | A later checkpoint or final Summary CSV that is written successfully includes the calculated case. The [Summary CSV reference](../results/summary-csv.md) defines when its `vtp_path` is blank. Other VTP files written successfully during this run remain available. |
| Checkpoint Summary CSV write failure | Records the error and continues calculations. A failed append is rolled back to the previous file length and synchronized before retrying at a later checkpoint. If rollback fails, further appends are disabled; the final atomic write is still attempted. | After a successful rollback, the previous checkpoint remains usable. If rollback fails, the CSV tail may be incomplete. An initial atomic checkpoint failure leaves a pre-existing CSV unchanged. VTP files written successfully remain. |
| Final Summary CSV write failure | Leaves the calculations completed but reports that the final Summary CSV could not be saved. | The latest checkpoint written successfully or pre-existing Summary CSV, if any, is left in place, as are VTP files written successfully during this run. Treat the retained Summary CSV according to the run diagnostics; it may not represent the completed batch. |

If a VTP write fails, an older file can remain at the planned path. Check the
current run's diagnostics and Summary `vtp_path` to identify successful writes.
The GUI suppresses automatic loading of the older file after that failure.

## Write durability guarantee

Initial checkpoint, final Summary CSV, and VTP writes use a temporary file and
atomic replacement, preserving the existing file if the new write fails.
Checkpoint appends synchronize new rows to disk and attempt to restore the
previous file length on a caught write failure. A rollback failure is reported
explicitly and disables further appends.

Direct append is not atomic: forced termination or power loss can leave an
incomplete trailing CSV record or partially written case. Automatic repair and
calculation resumption are not provided. Inspect the retained CSV before using
it after such an interruption or a reported rollback failure.

Files written before a later calculation failure or cooperative cancellation
remain present. Use run diagnostics, Summary CSV paths, and VTP case IDs and
signatures to distinguish current-run results from older retained files. Until
the first checkpoint succeeds, a pre-existing Summary CSV still belongs to the
previous run. A failed final write leaves the retained checkpoint in completion
order, which may contain all calculated cases but is not a finalized Summary CSV.
