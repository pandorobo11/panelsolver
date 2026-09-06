# ADR 0016: Append CSV checkpoints

- Status: Accepted
- Date: 2026-09-06

## Context

Rewriting all completed results at every checkpoint repeatedly serializes and
writes the same rows. With 100,000 equally sized cases and a 2,000-case interval,
the cumulative snapshots write 2,550,000 case-equivalents. Users need one CSV
that can be opened during a run, without split checkpoint files or a recovery
command. The approved change accepts completion-order intermediate output and
the reduced failure guarantees inherent in direct append.

## Decision

Both domains use the same application-owned delta checkpoint path. Accepted
case results are buffered in completion order. Every N newly completed cases
triggers a save of all unsaved cases. The first successful checkpoint atomically
replaces any older CSV. Later checkpoints append complete case projections with
matching columns, without another header or BOM, and synchronize the file.
Buffers are cleared only after successful writes. Failed saves are retried after
another N completions, including all pending cases.

An append records the original byte length. On a caught write failure it
truncates to that length and synchronizes the rollback. If rollback fails,
further appends are disabled and the error reports that the tail may be
incomplete. Calculations continue and final atomic serialization is still
attempted. Forced termination and power loss may leave partial records or cases;
automatic repair and calculation resumption are outside this change.

After successful calculation of the batch, remaining pending cases are saved,
then the complete input-ordered result is atomically written once. A complete
checkpoint does not substitute for this final save. The default interval remains
2,000 cases; zero disables all checkpoint writes. Calculation failure and
cooperative cancellation do not trigger additional saves. Captured output errors
remain visible even if a subsequent save succeeds.

This supersedes only ADR 0008's input-order checkpoint behavior and the prior
unconditional preservation guarantee for checkpoint write failures. Final CSV
columns, values, encoding, total/component ordering, and input-case ordering
are unchanged. Numerical calculations, signatures, VTP semantics, execution
ordering, and the public in-memory Python API are unchanged.

## Consequences and evidence

Successful runs with checkpoints serialize/write each result once across all
checkpoints and once for the final CSV: 200,000 case-equivalents in the example.
Checkpoint I/O is linear in result volume; failed retries can add work. The
application still retains results in memory for final input ordering.

Tests cover delta write volume and projection construction, both domains,
out-of-order completion, multi-component rows, Unicode/quoted cells, rollback
and retry without duplicate rows, rollback failure, final failure, and
cancellation. Existing numerical and artifact regressions remain authoritative;
no numeric tolerance or golden coefficient changes are required.
