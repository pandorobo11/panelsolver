# Outputs

Each run produces a Summary CSV and can produce per-case VTP files. The canonical
column and array inventory is in [Output formats](../reference/output-formats.md).

## Paths and switches

- If CLI `--output` is omitted, the summary is
  `<input_dir>/outputs/<input_stem>_result.csv`.
- A relative `out_dir` is resolved from `<input_dir>`; an absolute `out_dir` is
  used as specified.
- Per-case artifacts are `<resolved_out_dir>/<case_id>.vtp`.
- `save_vtp_on` defaults to `1`.
- `out_dir` is created even if VTP output is off.

The GUI uses the same base for its default Summary CSV, automatic VTP loading,
and image-export directories.

Both the final summary and checkpoint snapshots are written through a
same-directory temporary file, flushed, synchronized, and atomically replaced.
VTP files already written remain after a later failure or cancellation.

## Summary rows

Every case emits a `total` row. A multi-STL case then emits one component row per
STL in component-ID order. Component rows have blank `vtp_path` because artifacts
belong to the total case. Results remain in input order even when workers finish
out of order.

## Reading artifacts

VTP is intended for visualization and panel-level data. It contains mesh-aligned
cell data plus case metadata. Summary CSV is the aggregate output and the only
output with component summary rows.

Compare VTP artifacts semantically by field name, shape, dtype, metadata, and
appropriate numeric tolerance—not by file bytes.

Current Panel Solver releases do not generate NPZ output. Existing NPZ files
are not automatically deleted.
