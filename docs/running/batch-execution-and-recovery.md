# Batch execution and recovery

This page covers how the CLI and GUI handle workers, checkpoints, cancellation,
and recovery from calculation or output-file failures.
Use the [Summary CSV reference](../results/summary-csv.md) and
[VTP reference](../results/vtp.md) to interpret saved result fields.

## Workers and visible ordering

`workers=1` runs cases without parallel execution; larger values allow multiple
cases to run concurrently. With any worker count, execution, progress, and
diagnostics may follow a different order from the input table. Every checkpoint
and final Summary CSV presents completed cases in input-table order.

The CLI exposes this setting as `--workers`; the GUI exposes it as **Workers**.

## Checkpoints

The CLI `--checkpoint-every-cases N` option and GUI **Checkpoint every** control
set the same interval. The default is `2000`. Each time another `N` cases have
completed, Panel Solver writes a Summary CSV containing all cases completed so
far. Set the value to `0` to disable intermediate snapshots. A final Summary CSV is still attempted
after all case calculations finish without cancellation or a calculation
failure.

After a checkpoint is written, it is available at the selected Summary CSV
destination and has the fields and rows described in the
[Summary CSV reference](../results/summary-csv.md). It retains results from
completed cases when a later calculation fails or a run is canceled. A
checkpoint stores results rather than resumable calculation state. Use CLI
`--cases` or a GUI row selection to rerun cases that still need results.

## Cancellation and calculation failures

Cancellation is cooperative. Panel Solver observes it between cases; an active
[ray-shielding query](../methods/ray-shielding.md) or physical-model solve may
finish before the request is observed.

After cancellation, use the most recent successful checkpoint and VTP files
from this run. A new final Summary CSV is not guaranteed when cancellation
occurs before every case finishes.

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
| Checkpoint Summary CSV write failure | Records the checkpoint write error and continues calculations, including later checkpoint and final write attempts. | The last Summary CSV written successfully, if any, and VTP files written successfully during this run remain. Do not assume the retained Summary CSV includes cases completed after its last successful write. |
| Final Summary CSV write failure | Leaves the calculations completed but reports that the final Summary CSV could not be saved. | The latest checkpoint written successfully or pre-existing Summary CSV, if any, is left in place, as are VTP files written successfully during this run. Treat the retained Summary CSV according to the run diagnostics; it may not represent the completed batch. |

If a VTP write fails, an older file can remain at the planned path. Check the
current run's diagnostics and Summary `vtp_path` to identify successful writes.
The GUI suppresses automatic loading of the older file after that failure.

## Write durability guarantee

Summary CSV and VTP writes preserve the existing completed file if a new write
fails. Files written successfully before a later failure or cancellation remain
present. Use run diagnostics, Summary CSV paths, and VTP case IDs and signatures
to distinguish current-run results from older retained files.
