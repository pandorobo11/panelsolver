# Using the CLI

The `panelsolver` command runs every case in a case table without opening the
GUI. Choose the flow domain first:

```text
panelsolver fmf --input PATH [--output PATH] [--workers N]
                [--cases ID [ID ...]] [--checkpoint-every-cases N]
                [--verbose] [--plain] [--debug]
panelsolver hypersonic --input PATH [--output PATH] [--workers N]
                       [--cases ID [ID ...]] [--checkpoint-every-cases N]
                       [--verbose] [--plain] [--debug]
```

| Domain | Flow regime | Model | Case table |
|---|---|---|---|
| `fmf` | free-molecular flow | Sentman | [FMF case table](../reference/fmf-case-table.md) |
| `hypersonic` | hypersonic flow | Newtonian-family pressure methods | [Hypersonic case table](../reference/hypersonic-case-table.md) |

Both commands read a CSV, XLSX, or XLSM case table. They write a
[Summary CSV](../reference/summary-csv.md) and, for each case that has
`save_vtp_on=1`, a [VTP file](../reference/vtp.md).

| Option | What it does | Default |
|---|---|---|
| `-i`, `--input` | Case table to read. | required |
| `-o`, `--output` | Where to write the Summary CSV. | `<input folder>/outputs/<input name>_result.csv` |
| `-j`, `--workers` | Number of cases to run in parallel (at least 1). | `1` |
| `--cases` | Run only these case IDs, separated by spaces or commas. | all cases |
| `--checkpoint-every-cases` | Save results to the Summary CSV after every N finished cases, so you can open partial results during a long run. `0` saves only at the end. See [Batch runs and recovery](batch-runs.md#checkpoints). | `2000` |
| `--verbose` | Show a message for each case. | off |
| `--plain` | Use plain text output instead of the live progress display. | off |
| `--debug` | Show the full Python traceback when an error occurs. | off |

Examples:

```bash
panelsolver fmf -i cases.csv --cases mode_a,mode_b -j 2
panelsolver hypersonic -i cases.xlsx -o results.csv --cases baseline
```

## Case selection

`--cases` needs at least one case ID. The final Summary CSV keeps the selected
cases in case-table order. Execution and progress messages can follow a
different order, even with one worker. An unknown case ID stops the command
before anything runs.

## Progress and errors

In an interactive terminal, the CLI shows a summary and a live progress bar.
`--verbose` adds a `[RUN]` and `[OK]` line for each case. When the output is
redirected to a file or pipe, or runs in CI, plain text is used automatically;
`--plain` forces it.

If a case table is invalid or a calculation fails, the CLI prints a short error
and exits with a nonzero status. Add `--debug` to see the full traceback. If a
result file cannot be written, the CLI also exits with a nonzero status after
saving what it can; see [Batch runs and recovery](batch-runs.md).

## Output destinations

Before running anything, the CLI checks that the Summary CSV will not overwrite
the case table, an STL file, or a VTP file that the run will write. This check
also applies to cases with VTP saving turned off, and it treats file names that
differ only in upper and lower case as the same file. See
[Preparing cases](preparing-cases.md#paths-vtp-destinations-and-components) for
where VTP files go.

## Sectional batches

The `sectional-loads` and `sectional-cp` subcommands are described in
[Sectional loads and Cp](sectional.md).
