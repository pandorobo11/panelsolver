# GUI guide

Launch the canonical GUI with a flow-domain selector:

```bash
panelsolver-gui fmf
panelsolver-gui hypersonic
```

These open `Panel Solver — FMF` and `Panel Solver — Hypersonic`. FMF currently
uses the Sentman physical model; Hypersonic provides Newtonian-family methods.

The legacy compatibility commands `fmfsolver`, `fmfsolver-gui`, `newtsolver`,
and `newtsolver-gui` remain available with their existing titles and behavior.

## Offline help

Every launcher uses the shared **Help** menu:

- **Documentation** opens the bundled offline site home;
- **About** shows Panel Solver, the installed `panelsolver` distribution
  version, the active FMF or Hypersonic domain, and the Apache-2.0 license.

Pages are opened as local `file://` URLs through the desktop browser. The wheel
contains the complete site, so Help does not use the network or require MkDocs
at runtime. If the installed resource is missing or the browser rejects the
local URL, the GUI reports an error. An editable checkout may build a temporary
site with the docs dependency group installed; that temporary resource remains
alive for the lifetime of the window.

## Run cases

1. Choose **Select Input File** or **File > Open Input File...** and open a CSV,
   XLSX, or XLSM case table. If no remembered input directory exists, the dialog
   starts in the current directory. After a successful normal load, later dialogs
   start in that file's directory. If the remembered directory no longer exists,
   the dialog falls back to the current directory.
2. Select one or more table rows. With no selection, **Run Selected Cases** runs
   every loaded row.
3. Set **Workers**. Use `1` for the simplest deterministic run.
4. Set **Checkpoint every** in cases. The default is `2000`; use `0` to
   disable intermediate Summary CSV snapshots.
5. Choose **Run Selected Cases** and select the summary CSV destination.
6. Follow progress and diagnostics in the log panel.

Input validation issues are shown with spreadsheet row, case ID, field, and
message. The GUI uses the same reader, execution engine, checkpoint behavior,
and output serializers as the CLI.

## Start from an example

Choose **File > New from Example** to see only the examples for the active FMF
or Hypersonic domain. Select a workspace directory; the GUI copies the chosen
case table and its required geometry there with their relative layout intact,
then opens the copied table. Packaged examples are never run in place, and
opening one does not replace the remembered directory for normal input files.

## View and export

When a case saves VTP, the first selected case's result is loaded automatically. A
selected row also loads an existing `<out_dir>/<case_id>.vtp` when its case ID
and accepted signature match. The viewer can switch among available cell
scalars, adjust the camera and coloring, open another VTP, and save images.
Relative `out_dir` values, automatic VTP loading, and default image directories
are all resolved from the loaded input table's directory.

Closing the window during a run requests cooperative cancellation and waits for
worker cleanup. An active ray query or model solve may finish before cancellation
is observed; files already written are not rolled back.

See [Case files](case-files.md), [Outputs](outputs.md), and
[Troubleshooting](troubleshooting.md).
