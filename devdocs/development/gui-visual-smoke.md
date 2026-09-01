# GUI visual smoke on macOS

Use the repository-owned macOS helper when a GUI change needs inspection of the
real `MainWindow`, including the PyVista/VTK `QtInteractor`, through Computer
Use. This is development tooling; it does not change or package the production
GUI.

## Prerequisites

Prepare the locked local environment from the repository root:

```bash
uv sync --locked --extra rayaccel --group docs
```

The helper resolves the repository root from its own bundle location. It does
not contain a developer-specific checkout path. It uses `.venv/bin/python` when
available and otherwise falls back to `uv run`.

## Launch

From the repository root, resolve the helper in the current physical checkout
and open an ordinary production-composed window that follows the system theme:

```bash
visual_app="$(pwd -P)/tools/macos/PanelSolverVisual.app"
printf '%s\n' "$visual_app"
open "$visual_app" --args --domain fmf --theme system
```

Keep the printed absolute path: pass that exact path to Computer Use so the
launched bundle and the inspected bundle come from the same checkout.

The development-only launcher accepts:

- `--domain fmf|hypersonic`;
- `--theme light|dark|system`;
- `--input PATH` to load a supported CSV/XLSX/XLSM file after the window opens;
- `--row N` to select and focus a zero-based row after loading the input.

For a representative state containing loaded cases, an enabled Run button, a
disabled Cancel button, and a focused selected row, use:

```bash
open "$visual_app" --args \
  --domain hypersonic \
  --theme light \
  --input examples/hypersonic/pressure_models.csv \
  --row 0
```

Repeat with `--theme dark` for the dark-theme inspection. Close the first helper
instance before launching the second one. If matching generated VTP outputs are
already present beside the input, selecting the row also exercises the normal
artifact-matching path and displays the real VTP. The helper does not generate
or copy solver output.

## Capture without Computer Use

For a stable `MainWindow` state, the helper can save the Qt client area without
using Computer Use or macOS Screen Recording permission. For non-interactive
automation, remove any old image, launch a new helper instance with `open -W -n`
so the command waits for that instance to exit, and verify that a nonempty image
was written:

```bash
shot="/tmp/panelsolver-hypersonic-light.png"
rm -f -- "$shot"
open -W -n "$visual_app" --args \
  --domain hypersonic \
  --theme light \
  --input examples/hypersonic/pressure_models.csv \
  --row 0 \
  --screenshot "$shot" \
  --quit-after-screenshot
test -s "$shot"
```

The non-interactive path validates the input and requested row before opening
the GUI. Invalid input, an out-of-range row, state-preparation failure, or image
capture failure exits nonzero and does not attempt the screenshot. Removing an
old image first and checking it after `open -W -n` prevents a failed run from
being mistaken for a fresh capture. Use `--stderr PATH` with `open` when an
automation runner needs the helper's diagnostics in a file.

The capture combines Qt's client-area image with the real `QtInteractor`
viewport exported through PyVista. This avoids the blank native child surface
that `QWidget.grab()` produces when used alone and preserves HiDPI output. The
result includes the cases panel, selection and focus state, log, VTK viewport,
viewer controls, and enabled/disabled state. It does not include the native
title bar, window shadow, separate dialogs, open menus, or tooltips.

The ordinary interactive workflow remains the earlier `open "$visual_app"`
form without `--quit-after-screenshot`: it leaves the GUI open and retains the
normal validation dialogs for a person to inspect. A screenshot may still be
requested in that mode, but `open` is asynchronous and must not be used as a
completion signal for downstream automation.

This is still a normal-display workflow. Do not set `QT_QPA_PLATFORM=offscreen`
or `PYVISTA_OFF_SCREEN`; those limitations remain unchanged. Use Computer Use
when evidence must include native window chrome or interaction with transient or
separate windows.

## Computer Use target

Use the absolute path printed during launch as the Computer Use app target. For
example, pass the fully expanded value in this form:

```text
/absolute/path/to/current/checkout/tools/macos/PanelSolverVisual.app
```

The `open "$visual_app"` target and the path passed to Computer Use must identify
the same bundle. The stable bundle identifier remains available as a shorter
target when only one matching bundle is registered:

```text
io.github.pandorobo11.panelsolver.visual-smoke
```

Multiple checkouts or Codex worktrees can each contain this app. Launch Services
may register more than one copy, all with the intentionally stable bundle ID, so
Computer Use can reject the bundle-ID target as ambiguous. If that happens,
switch to the current checkout's absolute app path; the path uniquely selects
the intended copy without changing its bundle ID.

The executable is Python, but the app bundle gives Computer Use a specific app
target instead of relying on a generic `python3.12` process name. Inspect the
fresh accessibility tree after every action and use it to locate the current
controls.

Capture evidence should normally show:

- the complete `MainWindow` and native title bar;
- CasesPanel input path, table, selection, spin controls, Run/Cancel, progress,
  and log;
- the real VTK canvas plus ViewerPanel combo boxes, checkboxes, range fields,
  camera buttons, and export state;
- keyboard focus, selected row, enabled/disabled controls, and both themes.

Keep incidental screenshots outside the repository and attach them to the
relevant issue or pull request. Commit screenshots only when they are an
intentional part of durable documentation.

## Maintained GUI-guide screenshots

Regenerate both committed light-theme screenshots in `docs/assets/screenshots/`
from a prepared development environment with one normal-display command:

```bash
python scripts/generate_docs_gui_screenshots.py
```

The generator copies the Hypersonic pressure-model input and its geometry to a
temporary workspace, calculates `newt_pm` through the current GUI adapter/runtime
path, loads the temporary input into the real `MainWindow`, and reuses this
helper's Qt/VTK compositor. It validates the empty and current-result Viewer
states before capture and replaces the visible input path with its stable example
path after layout. It writes only `gui-overview.png` and `gui-result.png` to the
repository; calculation outputs remain temporary.

## Why normal display is required

Do not set either of these variables for this workflow:

```text
QT_QPA_PLATFORM=offscreen
PYVISTA_OFF_SCREEN
```

On macOS, `pyvistaqt.QtInteractor` connects Qt's native widget handle to VTK's
Cocoa render window. Qt's offscreen platform can return a placeholder `winId`
without a native Cocoa `NSView`; VTK then fails while configuring its native
render window and the process may exit with status 139. Opening this helper app
through Launch Services attaches the process to the normal WindowServer and
provides the native view required by the real interactor.

Headless GUI tests should continue to inject a lightweight plotter/interactor
where appropriate. The helper is for visual validation, not a production VTK
workaround and not a replacement for focused automated tests.

## Scope of visual findings

Record visual findings without silently expanding the implementation under
review. In particular, QPalette/QSS does not control the pixels painted inside
VTK's OpenGL render surface. A theme-specific VTK background would require an
explicit Viewer/theme integration change and belongs in its own bounded issue.
