# Environment-variable reference

An explicit API/configuration argument has highest precedence. The application
resolves the canonical variable and passes product-neutral values into core.

| Variable | Domain | Default |
|---|---|---:|
| `PANELSOLVER_SHIELD_BATCH_SIZE` | integer ≥ 1 | Embree `64`; rtree `8` |
| `PANELSOLVER_PARALLEL_CHUNK_CASES` | integer ≥ 1 | `8` |

Invalid or blank-domain values are errors; blank/unset variables are ignored.
The batch variable matters only when ray shielding is used. Chunk size is a
scheduling/reuse hint and does not change the input-ordered final result schema.
