# Environment-variable reference

These settings tune how calculations are grouped for performance. Normally,
leave both unset: the defaults are a suitable starting point. Change one at a
time only when measuring runtime or memory use on a representative workload.
Set variables in the environment that launches Panel Solver; they apply to both
FMF and Hypersonic.

| Variable | Accepted value | Default | What it changes / when to try it |
|---|---|---|---|
| `PANELSOLVER_SHIELD_BATCH_SIZE` | integer ≥ 1 | Embree `64`; rtree `8` | Number of panel rays tested in one shielding query batch, used when `shielding_on=1`. Smaller batches can reduce temporary memory use; larger batches may reduce query overhead. Consider tuning for large meshes. |
| `PANELSOLVER_PARALLEL_CHUNK_CASES` | integer ≥ 1 | `8` | Maximum number of cases grouped into a worker task. Smaller chunks may spread uneven case runtimes more evenly across workers; larger chunks can reduce scheduling overhead and improve reuse for similar cases. Consider tuning for large multi-worker sweeps. Set worker count and checkpoint interval through the CLI or GUI controls. |

Blank or unset variables use the defaults. Other values must be integers of at
least 1; invalid values cause an error when the setting is used. An explicit
configuration argument, where available, takes precedence over the environment.
The stable package-root Python API does not expose these tuning arguments.

For the geometric method and backend choices, see [Ray shielding](../methods/ray-shielding.md).
For worker counts, checkpoints, and result ordering, see
[Batch execution and recovery](../running/batch-execution-and-recovery.md).
