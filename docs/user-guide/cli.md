# CLI guide

The canonical batch entry point selects a physical flow domain:

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

The final column is a schema/application-service reuse choice, not the identity
of the canonical command.

Both batch forms use the same case-table reader and application service. They
accept CSV, XLSX, and XLSM. Summary CSV and optional per-case VTP are the only
formal outputs; Excel 97–2003 BIFF `.xls` and NPZ are not supported. Their
complete field contracts are in the
[Summary CSV reference](../results/summary-csv.md) and
[VTP reference](../results/vtp.md).

| Option | Meaning | Default |
|---|---|---|
| `-i`, `--input` | CSV/XLSX/XLSM case table | required |
| `-o`, `--output` | Summary CSV | `<input_dir>/outputs/<input_stem>_result.csv` |
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
plain output. Validation and execution failures normally show a concise error
and return a nonzero exit status; `--debug` shows the Python traceback.
Per-case VTP output failures do not stop later calculations. The command writes
the Summary CSV with blank `vtp_path` values for those cases, reports the
aggregated output errors, and returns a nonzero exit status after calculation
finishes. Final Summary CSV output failure is likewise reported as an output
failure rather than a calculation failure.

Output-path validation rejects collisions with the input table, any STL, and
any planned VTP before execution. See [Outputs](outputs.md) for artifact
lifecycle behavior and
[Shielding and parallel execution](shielding-and-parallel.md) for execution
details.
