# Batch runs and recovery

This page explains the settings for runs with many cases, and what you can
still use after a run is cancelled or something fails. It applies to both the
CLI and the GUI. Sectional batches follow their own rules, described in
[Sectional loads and Cp](sectional.md) and the
[sectional load CSV reference](../reference/sectional-loads-csv.md#failures-and-repeated-export).

## Workers and result order

**Workers** (GUI) or `--workers` (CLI) sets how many cases run at the same time.
With `1`, cases run one after another. With more workers, cases can finish in
any order, so progress messages and Diagnostics may not follow the table
order. The final Summary CSV is always in case-table order.

## Checkpoints

During a long run, Panel Solver can save finished results to the Summary CSV
before the whole run is done. Set the interval with **Checkpoint** (GUI, under
**Show advanced**) or `--checkpoint-every-cases` (CLI). The default is `2000`.

- Every time another N cases finish, the results not yet saved are written to
  the Summary CSV. The first checkpoint replaces any older file at that path;
  later checkpoints add rows to the end.
- While the run is in progress, rows appear in the order the cases finished.
- When all cases are done, the file is rewritten once more in case-table order.
- `0` turns checkpoints off. The final Summary CSV is still written.
- Cancelling or a failed case does not trigger an extra save.

A checkpoint file is an ordinary Summary CSV that you can open at any time. It
contains results only; a run cannot be resumed from it. To fill in cases that
are missing, rerun just those cases with `--cases` (CLI) or by selecting their
rows (GUI).

## Cancellation and calculation failures

Cancellation is checked between cases. A case that is already running, for
example one doing a large [ray-shielding](../methods/ray-shielding.md) query,
finishes first.

After you cancel:

- the Summary CSV contains the cases saved by the last checkpoint;
- cases finished after that checkpoint are not saved;
- VTP files written so far remain;
- a complete final Summary CSV is not written.

If a case fails to calculate, for example because its geometry cannot be
loaded, the batch stops. Results already saved remain, as described above.

## When a result file cannot be written

File-writing problems are reported separately from calculation failures. The
calculations themselves are not lost.

| Problem | What Panel Solver does | What you can still use |
|---|---|---|
| A VTP file or its folder cannot be written | Keeps that case's coefficients and continues with the next case. | The case still appears in the Summary CSV, with an empty `vtp_path`. Other VTP files from the run remain. |
| A checkpoint cannot be written | Reports the error, keeps calculating, and tries again at the next checkpoint. | The previous checkpoint usually stays intact. If Diagnostics reports that the file end may be incomplete, check it before use. |
| The final Summary CSV cannot be written | Reports that the final file could not be saved. | The last checkpoint (or an older file) stays in place, but it may not contain every case and may not be in table order. In the GUI, use **Retry Save...** to save the complete result without recalculating. |

If a VTP write fails, an older file with the same name may still exist. Use
Diagnostics and the Summary CSV `vtp_path` column to see which files this run
wrote. The GUI does not load the older file automatically.

**Retry Save...** in the GUI is available only after the final save fails, and
only until you close the window. It is not available in the CLI. See
[Using the GUI](gui.md#if-the-summary-csv-cannot-be-saved).

## Write durability guarantee

- The first checkpoint, the final Summary CSV, and each VTP are written to a
  temporary file first and then moved into place. If writing fails, the old
  file is left unchanged.
- Later checkpoints add rows directly to the end of the file. If the computer
  loses power or the process is killed during that write, the last row or case
  may be incomplete. Check the file before using it after such an interruption.
- Files written before a cancellation or failure remain. To tell them apart
  from older files, use Diagnostics, the Summary CSV `vtp_path` column, and the
  case ID and `case_signature` stored in each VTP. A Summary CSV from an earlier
  run stays at the path until the first checkpoint of the new run replaces it.
