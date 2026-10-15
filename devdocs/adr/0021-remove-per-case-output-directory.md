# ADR 0021: Remove the per-case output directory

- Status: Accepted
- Date: 2026-10-15
- Supersedes: only the `out_dir` case-file column portion of ADR 0008

## Context

Both legacy products accepted an `out_dir` column, so each case row could name
its own VTP directory. The current product inherited it, together with its
`outputs` default, input-table-relative resolution, per-row blank validation,
and a GUI table column.

In practice the column described a table-level choice. Every bundled example
set one value for a whole table, and it did so only to keep VTPs from tables in
the same directory apart. A per-row setting added cost without a supported use:
per-row path resolution and caching, per-row directory preparation, a batch
image-export fallback for tables with mixed directories, and one more path
column in the Cases table. The Summary CSV destination is already a run-level
choice. Placing VTPs per row was the only exception to that.

This is an intentional input-compatibility change, not a numerical-model change.
Phase 1 inputs, goldens, provenance, and migration records that contain
`out_dir` remain historical evidence of the pinned legacy products.

## Decision

Remove `out_dir` immediately, without a deprecation period, compatibility
no-op, or replacement option. Every case VTP is written to
`<input_dir>/outputs/<case_id>.vtp`, where `<input_dir>` is the case table's
directory. This is the previous default location, so tables that omitted the
column, or left it blank, keep their VTP paths. The CLI `--output` option and
the GUI save dialog still choose only the Summary CSV.

A case table whose header contains `out_dir` is rejected with a field-aware
message telling the user to delete it, whatever its values are. Runtime calls
given a row that contains `out_dir` reject it in the same way. The Summary CSV
loses only the echoed `out_dir` input column. Every other column keeps its
value, order, blank semantics, and total/component ordering. VTP content is
unchanged.

The GUI's automatic VTP loading, current-run validity tracking, Summary CSV
collision checks, and image-export defaults all use the same input-relative
directory. Images default to `<input_dir>/outputs/images`.

Existing VTP files in previously configured directories are not moved or
deleted. Historical goldens and fixtures are not edited. Current-versus-historical
regression comparisons exclude only the retired `out_dir` input field.

This decision does not change numerical formulas, coordinate systems, signs,
normalization, VTP semantics, or the case-signature schema or values, because
`out_dir` was never part of the case signature. The other supported-domain
portions of ADR 0008 are not superseded.

## Consequences

Users must delete `out_dir` from old case tables. A table that used a non-default
`out_dir` now writes its VTPs to `outputs/` beside the table. Tables whose
`case_id` values overlap must be kept in separate directories so that their
VTPs do not replace each other. Collisions with the input table, STL files, and
the Summary CSV are still rejected before execution.

The runtime receives the VTP directory once per run as an explicit argument.
Workers no longer derive it from each row.
