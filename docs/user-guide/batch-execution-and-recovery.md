# Batch execution and recovery

This page covers how the CLI and GUI handle workers, checkpoints, cancellation,
and recovery from calculation or output-file failures.
Use the [Summary CSV reference](../results/summary-csv.md) and
[VTP reference](../results/vtp.md) to interpret saved result fields.

## Workers and visible ordering

Case execution order is not guaranteed to match input-table order, regardless
of the worker count. `workers=1` is the simplest non-parallel execution setting.
With multiple workers, execution and completion can be further asynchronous.
Progress and diagnostics can therefore mention cases out of order, but every
checkpoint and final Summary CSV presents the completed cases in input-table
order.

The CLI exposes this setting as `--workers`; the GUI exposes it as **Workers**.

## Checkpoints

The CLI `--checkpoint-every-cases N` option and GUI **Checkpoint every** control
set the same interval. The default is `2000`. Each time another `N` cases have
completed, Panel Solver writes a Summary CSV containing all cases
completed so far; it is not a delta from the preceding snapshot. Set the value
to `0` to disable intermediate snapshots. A final Summary CSV is still attempted
after all case calculations finish without cancellation or a calculation
failure.

After a checkpoint is written, it is available at the selected Summary CSV
destination and has the fields and rows described in the
[Summary CSV reference](../results/summary-csv.md). It retains results from
completed cases when a later calculation fails or a run is canceled. A
checkpoint is not restart state: Panel Solver does not resume a calculation
from it. Use CLI `--cases` or a GUI row selection to rerun cases that still need
results.

## Cancellation and calculation failures

Cancellation is cooperative. Panel Solver observes it between cases; an active
[ray-shielding query](../reference/ray-shielding.md) or physical-model solve may
finish before the request is observed.

Summary CSV snapshots and VTP files already written are not rolled back. If the
run is canceled before every case finishes, a new final Summary CSV is not
guaranteed. Use the most recent checkpoint written successfully during this run
and any VTP files written successfully during this run.

A calculation failure, such as a geometry-loading or model-execution error,
stops the batch. Results from cases completed earlier may still be
available in an already-written checkpoint or VTP. This is distinct from an
output-file failure: a calculation can succeed even when one of its files cannot
be written.

## Output-file failures and partial success

Output-directory preparation, VTP write, and Summary CSV write failures are
reported separately from calculation failures. The [CLI guide](cli.md) and
[GUI guide](gui.md) define how their respective run statuses present these
failures.

| Failure | What Panel Solver does | What remains usable |
|---|---|---|
| Per-case output-directory or VTP write failure | Keeps that case's calculated result and continues with later cases. | A later checkpoint or final Summary CSV that is written successfully includes the calculated case. The [Summary CSV reference](../results/summary-csv.md) defines when its `vtp_path` is blank. Other VTP files written successfully during this run remain available. |
| Checkpoint Summary CSV write failure | Records the checkpoint write error and continues calculations, including later checkpoint and final write attempts. | The last Summary CSV written successfully, if any, and VTP files written successfully during this run remain. Do not assume the retained Summary CSV includes cases completed after its last successful write. |
| Final Summary CSV write failure | Leaves the calculations completed but reports that the final Summary CSV could not be saved. | The latest checkpoint written successfully or pre-existing Summary CSV, if any, is left in place, as are VTP files written successfully during this run. Treat the retained Summary CSV according to the run diagnostics; it may not represent the completed batch. |

An older VTP can remain at a case's planned path after this run fails to write a
replacement. That older file is not evidence that this run wrote a VTP and is
not automatically treated by the GUI as the selected case's result.

## Write durability guarantee

A failed new write does not replace an existing completed Summary CSV or VTP
with a partial new file. Summary CSV snapshots and VTP files written
successfully before a later failure or cancellation remain present. This
guarantee protects completed files; it does not make an older retained file
part of this run. Use run diagnostics, Summary CSV paths, and VTP case IDs and
signatures when deciding what to keep or rerun.
