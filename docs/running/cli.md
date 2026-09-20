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
protected file. See [Case files](../inputs/case-files.md#paths-vtp-destinations-and-components)
for per-case VTP destinations.

## Sectional load batches

Both domains can calculate finite-width sectional loads from a separate
[definition CSV](../inputs/sectional-loads.md):

```bash
panelsolver fmf sectional-loads -i examples/fmf/flow_modes.csv -d examples/sectional_loads.csv -o outputs/fmf_sections.csv
panelsolver hypersonic sectional-loads -i examples/hypersonic/basic.csv -d examples/sectional_loads.csv -o outputs/hypersonic_sections.csv
```

These commands work from the repository root with the supplied examples.
Use `--cases ID [ID ...]` and `--sections ID [ID ...]` independently; omitted
filters select all. Cases keep input-table order; sections keep definition-file
order. Unknown IDs are errors. Case selectors accept comma-separated IDs as in
ordinary solve. Section selectors use exact labels (quote labels with spaces
or commas); `--sections=--label` selects a label beginning with hyphens.

`-i/--input`, `-d/--definitions` and `-o/--output` are required.
`-j/--workers` defaults to one and parallelizes cases through the existing
scheduler. `--plain`, `--verbose` and `--debug` have the usual meanings.
The help describes STL coordinates, metre units, auto range and component IDs.
Axes and ranges are specified only in the definition file.

Each case executes physics once, then applies all selected definitions to that
same in-memory execution. Mode B and other domain case inputs remain supported.
No Summary CSV or VTP is required or generated, regardless of `save_vtp_on`.
The [dedicated result CSV](../results/sectional-loads-csv.md) includes all bins,
total and component scopes, coverage, references and the physical signature.

The complete definition file is validated before solving. Mesh-dependent
definition failures stop the batch, retaining earlier successful pairs. Ctrl-C
requests cooperative cancellation: serial runs check case/definition boundaries;
parallel workers finish at case boundaries. Already-dispatched work may finish.
Partial results are saved with `batch_status` and completion counts; failed pairs
are never emitted as zero results. Exit codes are 0 for complete success, 1 for
validation/calculation/save failure, 2 for command argument errors, and 130 for
cancellation when any requested partial save succeeds. If no pair succeeds,
the output remains untouched. Save failure is reported independently and returns 1.
