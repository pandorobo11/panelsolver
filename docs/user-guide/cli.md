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

| Selector | Flow regime | Method | Input table |
|---|---|---|---|
| `fmf` | free molecular flow | Sentman | FMF case table |
| `hypersonic` | hypersonic pressure approximation | Newtonian-family methods | Hypersonic case table |

Both commands read CSV, XLSX, and XLSM case tables and write
[Summary CSV](../results/summary-csv.md) and optional per-case
[VTP](../results/vtp.md).

| Option | Meaning | Default |
|---|---|---|
| `-i`, `--input` | CSV/XLSX/XLSM case table | required |
| `-o`, `--output` | Summary CSV destination | `<input_dir>/outputs/<input_stem>_result.csv` |
| `-j`, `--workers` | Spawn workers; must be at least 1 | `1` |
| `--cases` | Space- or comma-separated case IDs | all cases |
| `--checkpoint-every-cases` | Append unsaved cases to the Summary CSV after N completed cases; final CSV uses input order; `0` disables intermediate saves | `2000` |
| `--verbose` | Show case-level runtime messages in Rich mode | off |
| `--plain` | Disable Rich run/progress output | off |
| `--debug` | Show a Python traceback for CLI errors | off |

Examples:

```bash
panelsolver fmf -i cases.csv --cases mode_a,mode_b -j 2
panelsolver hypersonic -i cases.xlsx -o results.csv --cases baseline -j 1
```

## Case selection

`--cases` requires at least one value. Selected rows retain input-table order;
unknown case IDs reject the request.

## Progress and errors

On an interactive TTY, the default Rich display shows a summary and live
progress. `--verbose` adds case-level `[RUN]` and `[OK]` messages. Use `--plain`
for plain-text output; redirected or piped stdout and CI use it automatically.

Validation and calculation failures show a concise error and return a nonzero
exit status; `--debug` adds the Python traceback. Output-file failures also
return a nonzero status after the
[continuation and recovery rules](batch-execution-and-recovery.md) are applied.

## Output destinations

Output-path validation rejects collisions with the input table, any STL, and
any planned VTP before execution, even when that case has VTP saving disabled.
The check also rejects portable case/Unicode variants and aliases of an existing
protected file. See [Case files](case-files.md#paths-vtp-destinations-and-components)
for per-case VTP destinations.
