# Environment-variable reference

An explicit API/configuration argument has highest precedence. The neutral name
then wins over the prefix for the selected product. The application or
compatibility boundary resolves only that selected prefix and passes
product-neutral values into core.

| Neutral variable | Selected-product fallback | Domain | Default |
|---|---|---|---:|
| `PANELSOLVER_SHIELD_BATCH_SIZE` | `FMFSOLVER_SHIELD_BATCH_SIZE` or `NEWTSOLVER_SHIELD_BATCH_SIZE` | integer ≥ 1 | Embree `64`; rtree `8` |
| `PANELSOLVER_PARALLEL_CHUNK_CASES` | `FMFSOLVER_PARALLEL_CHUNK_CASES` or `NEWTSOLVER_PARALLEL_CHUNK_CASES` | integer ≥ 1 | `8` |

Invalid or blank-domain values are errors; blank/unset variables are ignored.
The batch variable matters only when ray shielding is used. Chunk size is a
scheduling/reuse hint and does not change the input-ordered final result schema.

## GUI input-load profiling

Set `PANELSOLVER_GUI_PROFILE=1` before launching a GUI to append detailed timing
records to its log panel for each selected case file. Records cover pandas input,
normalization and validation stages, repeated STL path filesystem calls, case
table construction, and the synchronous input/viewer signal handlers. Unset the
variable or set it to `0`, `false`, `no`, or `off` to disable these records.

This diagnostic switch does not cache paths, skip validation, or change the
synchronous GUI load flow. Leave it disabled for normal use because the
per-filesystem-call timers add profiling overhead.
