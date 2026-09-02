# Batch execution and recovery

This page covers the run lifecycle shared by the CLI and GUI: workers,
checkpoints, cancellation, and recovery from calculation or artifact failures.
Use the [Summary CSV reference](../results/summary-csv.md) and
[VTP reference](../results/vtp.md) to interpret saved result fields.

## Workers and visible ordering

`workers=1` is the simplest deterministic execution setting. With multiple
workers, calculations may finish in a different order from the selected input
rows. Progress and diagnostics can therefore mention cases out of order, but
every checkpoint and final Summary CSV presents the completed cases in input-
table order.

The CLI exposes this setting as `--workers`; the GUI exposes it as **Workers**.

## Checkpoints

The CLI `--checkpoint-every-cases N` option and GUI **Checkpoint every** control
set the same interval. The default is `2000`. Each time another `N` cases have
completed, Panel Solver writes a complete Summary CSV snapshot of all cases
completed so far; it is not a delta from the preceding snapshot. Set the value
to `0` to disable intermediate snapshots. A final Summary CSV is still attempted
after a normally completed run.

A successful checkpoint uses the selected Summary CSV destination and can be
read with the normal [Summary CSV contract](../results/summary-csv.md). It is
useful for retaining aggregate results when a later calculation fails or a run
is canceled. A checkpoint is not restart state: Panel Solver does not resume a
calculation from it. Use CLI `--cases` or a GUI row selection to rerun cases that
still need results.

## Cancellation and calculation failures

Cancellation is cooperative. Panel Solver observes it between cases; an active
ray query or physical-model solve may finish before the request is observed.
Artifacts already saved are not rolled back. If cancellation prevents normal
completion, a new final aggregate Summary CSV is not guaranteed, so use the
latest successfully written checkpoint and any successfully written VTP files.

A calculation failure, such as a geometry-loading or model-execution error,
ends normal batch completion. Results from cases completed earlier may still be
available in an already-written checkpoint or VTP. This is distinct from an
artifact failure: a calculation can succeed even when one of its files cannot
be written.

## Artifact failures and partial success

Artifact failures are reported separately from calculation failures. The
[CLI guide](cli.md) and [GUI guide](gui.md) define how their respective run
statuses present these failures.

| Failure | What Panel Solver does | What remains usable |
|---|---|---|
| Per-case output-directory or VTP write failure | Keeps that case's calculated result and continues with later cases. | A later successfully written checkpoint or final Summary CSV includes the calculated case. Its `vtp_path` representation is defined only in the [Summary CSV reference](../results/summary-csv.md). Other successfully written VTP files remain available. |
| Checkpoint Summary CSV write failure | Records the artifact error and continues calculations, including later checkpoint and final write attempts. | The last successfully written Summary CSV, if any, and successfully written VTP files remain. Do not assume the retained Summary CSV includes cases completed after its last successful write. |
| Final Summary CSV write failure | Leaves the calculations completed but reports that the final aggregate could not be saved. | The latest successful checkpoint or pre-existing Summary CSV, if any, is left in place, as are successfully written VTP files. Treat the retained Summary CSV according to the run diagnostics; it may not represent the completed batch. |

An older VTP can remain at a case's planned path after the current run fails to
write a replacement. That older file is not evidence of a current successful
VTP write and is not automatically treated by the GUI as the current case
result.

## Write durability guarantee

A failed new write does not replace an existing completed Summary CSV or VTP
with a partial new artifact. Artifacts successfully written before a later
failure or cancellation remain present. This guarantee protects completed
files; it does not make an older retained file part of the current run. Use run
diagnostics, Summary CSV paths, and VTP case identity when deciding what to keep
or rerun.
