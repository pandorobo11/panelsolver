# Quickstart

The repository includes one small, runnable case for each flow domain. Both use the
shared mesh at `examples/geometry/plate.stl`; they are not regression fixtures.
The same canonical `examples/fmf/`, `examples/hypersonic/`, and
`examples/geometry/` tree is available in
`panelsolver-examples-v<version>.zip`. Run commands from the directory that
contains the extracted `examples/` folder.

## Run FMF

```bash
panelsolver fmf --input examples/fmf/basic.csv --workers 1 --checkpoint-every-cases 0
```

This is a Sentman Mode A case using `S=5`, `Ti_K=300 K`, and `Tw_K=300 K`.
Its summary and VTP output are written to `examples/fmf/outputs/`.

## Run Hypersonic

```bash
panelsolver hypersonic --input examples/hypersonic/basic.csv --workers 1 --checkpoint-every-cases 0
```

This is a `Mach=6`, `gamma=1.4` case. Omitted equation columns select the
defaults: Newtonian on windward panels and zero pressure (`shield`) on leeward
panels. Its outputs are written to `examples/hypersonic/outputs/`.

## Use the GUI

Launch the canonical domain GUI:

```bash
panelsolver-gui fmf
panelsolver-gui hypersonic
```

Use **File > New from Example > Basic** to copy the matching table and geometry
to a workspace, or select the corresponding `basic.csv` directly. Select its
row and choose **Run Selected Cases**. The GUI displays the generated VTP when
one is saved.

## What was written

By default, the CLI writes:

- `outputs/basic_result.csv`: one integrated result row for the case, plus
  component rows when the case contains multiple STL files;
- `outputs/<case_id>.vtp`: the calculated triangle mesh, per-panel load data,
  and case provenance.

Use the [Summary CSV reference](../results/summary-csv.md) and
[VTP reference](../results/vtp.md) to interpret every field. See
[Outputs](../user-guide/outputs.md) for artifact paths, write behavior, and
recovery, and [Case files](../user-guide/case-files.md) before editing the
examples.

## Try the feature examples next

After the basic run, try `flow_modes.csv`, `shielding.csv`, `components.csv`,
or `attitude_modes.csv` under `examples/fmf/`. The matching Hypersonic
examples under `examples/hypersonic/` provide `pressure_models.csv`,
`shielding.csv`, `components.csv`,
and `attitude_modes.csv`. Run each with the same CLI command pattern, replacing
the input path. Commands, expected relationships, GUI files, and output
locations are collected in the repository-level `examples/README.md`.
