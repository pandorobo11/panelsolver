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
