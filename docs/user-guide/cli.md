# CLI guide

Select a physical flow domain with:

```text
panelsolver fmf --input PATH [--output PATH] [--workers N]
                [--cases ID [ID ...]] [--checkpoint-every-cases N]
                [--verbose] [--plain] [--debug]
panelsolver hypersonic --input PATH [--output PATH] [--workers N]
                       [--cases ID [ID ...]] [--checkpoint-every-cases N]
                       [--verbose] [--plain] [--debug]
```

Here `fmf` means the free-molecular-flow domain selector. The selected physical
model is Sentman; the stable Python API names the domain as `FMFCase` and
`solve_fmf()`.

| Selector | Flow-domain identity | Physical model identity | Reused case schema |
|---|---|---|---|
| `fmf` | free molecular flow | Sentman | FMF case table |
| `hypersonic` | hypersonic pressure approximation | Newtonian-family methods | Hypersonic case table |

The final column describes schema/application-service reuse; it does not change
the command identity.

Both batch forms use the same case-table reader and application service. They
accept CSV, XLSX, and XLSM. Summary CSV and optional per-case VTP are the only
formal outputs; Excel 97–2003 BIFF `.xls` and NPZ are not supported. Their
complete field contracts are in the
[Summary CSV reference](../results/summary-csv.md) and
[VTP reference](../results/vtp.md).

| Option | Meaning | Default |
|---|---|---|
| `-i`, `--input` | CSV/XLSX/XLSM case table | required |
| `-o`, `--output` | Summary CSV destination | `<input_dir>/outputs/<input_stem>_result.csv` |
| `-j`, `--workers` | Spawn workers; must be at least 1 | `1` |
| `--cases` | Space- or comma-separated case IDs | all cases |
| `--checkpoint-every-cases` | Rewrite a complete checkpoint after N completed cases; `0` disables | `2000` |
| `--verbose` | Show case-level runtime messages in Rich mode | off |
| `--plain` | Disable Rich run/progress output | off |
| `--debug` | Show a Python traceback for CLI errors | off |

Examples:

```bash
panelsolver fmf -i cases.csv --cases mode_a,mode_b -j 2
panelsolver hypersonic -i cases.xlsx -o results.csv --cases baseline -j 1
```

Selected rows retain input-table order. Unknown case IDs reject the request.
`--cases` requires at least one value. On an interactive TTY, the default display
uses a Rich summary and live progress while suppressing case-level `[RUN]` and
`[OK]` messages; `--verbose` shows those messages. Use `--plain` for plain-text
run output. Redirected or piped stdout and CI environments automatically use
plain output. Validation and calculation failures normally show a concise error
and return a nonzero exit status; `--debug` shows the Python traceback. Artifact
failures are also reported with a nonzero exit status after the runtime has
applied its documented continuation and recovery rules. See
[Batch execution and recovery](batch-execution-and-recovery.md).

Output-path validation rejects collisions with the input table, any STL, and
any planned VTP before execution, even when that case has VTP saving disabled.
The check also rejects portable case/Unicode variants and aliases of an existing
protected file. See [Case files](case-files.md) for per-case VTP destinations
and [Ray shielding](../reference/ray-shielding.md) for the geometry-occlusion
method.
