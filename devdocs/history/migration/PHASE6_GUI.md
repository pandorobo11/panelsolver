# Phase 6 shared GUI and viewer

Historical record — non-normative for the current product contract. This page records the repository state at the migration phase or audit named below. Statements such as “current”, supported commands, package names, file formats, and future work apply to that recorded point in time. Pinned source identities, golden evidence, tolerance profiles, and audit results may still be referenced by current developer workflows where devdocs/ or tests explicitly do so. Use docs/, devdocs/architecture/, and accepted or superseding ADRs for the present product contract.

Phase 6 migrates the duplicated Qt/PyVista shell behind one model-neutral
`SolverSpec`. It does not complete case-file compatibility, artifact
serialization, command registration, distribution mechanics, or public import
forwarding; those remain Phase 7 work.

## Dependency sequence

The implementation is serialized as follows:

1. `SolverSpec` and product-selected presentation/lifecycle policies;
2. headless artifact matching and dynamic scalar discovery;
3. the shared VTP viewer and camera controls;
4. case loading, table selection, and automatic viewer matching;
5. progress, cooperative cancellation, and close lifecycle;
6. single and selected-case image export;
7. shared bootstrap, thin compatibility launchers, and final acceptance.

Each slice starts from the latest accepted `main`, uses one issue and one
worktree, and is merged only after the complete local and cross-platform gates
pass.

## Solver specification boundary

`panelsolver.app.SolverSpec` carries product identity, model identity, exact
window title, ordered case-table columns, preferred display scalars, overlay
formatting, close policy, and an optional complete adapter bundle. Shared widgets
receive this object and never import a compatibility frontend or branch on a
model name.

The adapter bundle is deliberately optional in this phase. It defines the one
injection point for case reading, signature candidates, scheduled execution,
result-path validation, and resolved wind direction. The product-compatible
implementations remain Phase 7 work; Phase 6 widgets are tested with injected
adapters and headless fixtures.

## Retained product differences

- D022 remains exact: FMF uses `Sentman FMF Solver (GUI)` and newtsolver uses
  `newtsolver (GUI)`.
- D023/D027 are not normalized. FMF selects `defer_until_idle`; newtsolver
  selects `immediate`, retaining the absence of an equivalent close deferral in
  the pinned implementation.
- Product case schemas and overlay fields remain separate. FMF Mode A/B and
  thermal fields are not added to the hypersonic schema; hypersonic equation
  selectors are not added to FMF.
- Preferred scalar order is independently selected even where the current
  pinned lists are equal. Later viewer discovery must accept additional
  model-specific cell arrays dynamically (D019).

The close-policy choice records both observable contracts; it does not declare
either one a universal behavior.

## Artifact matching and scalar discovery

Automatic case selection and selected-case image export require both exact case
ID and a matching signature. The Phase 5 canonical signature is tried first;
only ordered opaque legacy hashes supplied by the selected product adapter are
valid fallbacks. Duplicate case IDs are checked in input order and case ID alone
is never sufficient. Manual VTP inspection remains allowed without a match, as
recorded by D024.

Viewer scalar discovery is headless and artifact-driven. It accepts finite
numeric or boolean cell arrays with exact `(n_cells,)` alignment, prioritizes the
available names from `SolverSpec.preferred_scalars`, and then retains additional
eligible arrays in artifact order. Vector, string, nonfinite, empty, and
misaligned arrays are not offered for scalar coloring. Boolean arrays and the
legacy byte-valued `shielded` field use a categorical `[0, 1]` range. This keeps
D019 model-specific additions visible without defining a universal VTP scalar
schema.

## Shared viewer

`panelsolver.app.viewer.ViewerPanel` is the single Qt/PyVista rendering widget.
It receives `SolverSpec`, an artifact reader, and a plotter factory; tests inject
a non-OpenGL plotter while production uses `QtInteractor`. Loading refreshes the
scalar selector from the Phase 6b discovery service and chooses the first
available preferred scalar. A manually opened signature-mismatched VTP remains
visible but receives no mismatched case context.

The viewer retains the pinned jet default, edges, shield transparency, overlay,
automatic/explicit ranges, parallel projection, axes, Cartesian/ISO cameras,
and camera state across redraws. Wind cameras use only the spec adapter's
resolved `velocity_hat_stl`; the viewer does not parse product attitudes or
evaluate a model. A failed read or invalid cell-data envelope clears the prior
view. Phase 6f adds single and selected-case image export without defining image
pixels as golden data.

CI exercises real Qt widgets with an injected non-OpenGL plotter on all three
platforms. The Ubuntu job installs the minimal `libegl1` runtime required to
import PySide6; it does not render through OpenGL. On macOS, constructing VTK's
native `QtInteractor` under `QT_QPA_PLATFORM=offscreen` exits in the platform
rendering layer, so this is not used as a headless gate. A normal-display
`QtInteractor` smoke remains part of the Phase 6g launcher acceptance; pixel
output is not a golden.

## Shared cases and selection

`panelsolver.app.cases_panel.CasesPanel` receives a fully adapted `SolverSpec`.
It does not import a product case reader, signature builder, or collision policy.
The selected adapter returns mapping rows; the table shows the product's ordered
schema followed by unknown columns in stable input order and remains read-only.
Selected rows are returned in table/input order, and an empty selection means all
loaded rows.

Selecting the first row auto-loads `<out_dir>/<case_id>.vtp` only when the shared
Phase 6b matcher accepts its exact case ID and signature. Missing, unreadable, or
stale artifacts clear the previous view. Input read/validation failure likewise
clears all old input, table, and viewer state; structured issues use one shared
dialog without depending on either product exception type.

The result chooser keeps the pinned `<input_dir>/outputs/<stem>_result.csv`
default and creates `outputs` before the dialog, including when the user cancels.
Product-specific D009 collision rules are invoked only through the spec adapter.
The panel emits a run request containing selected-or-all rows, worker count, and
validated output path; Phase 6e owns execution and lifecycle.

## Execution and window lifecycle

`GuiRunRequest` is the product-neutral boundary passed to the injected execution
adapter. It carries an ordered tuple of mapping rows, the validated output path,
workers, and callbacks for log delivery, deterministic `done/total` progress,
and cooperative cancellation. Product adapters retain ownership of checkpoint
and final result serialization. At the historical Phase 6 boundary they also
retained the Phase 5 `WorkerLogPolicy`/`PartialResultPolicy` choices; that
product-specific D015 behavior is superseded by ADR 0008, and both products now
use `FORWARD`/`YIELD_COMPLETED`. `GuiRunResult` exposes only the first completed
VTP needed to refresh the viewer.

`CaseRunWorker` executes the adapter on a `QThread`. Only
`SchedulerCancelled` is classified as cancellation; another exception remains
the primary failure even when cancellation was also requested. The panel rejects
double starts, disables mutable controls while active, restores them on every
terminal path, and releases worker/thread references only after `QThread` exit.
Cancellation remains case-boundary cooperative and does not promise interruption
inside a ray query, root solve, or ODE.

The shared `MainWindow` keeps the pinned 1480 x 900 horizontal splitter. ADR
0008 supersedes the product-selected `SolverSpec.close_policy` recorded for
D023: both products request cancellation, ignore active-run close requests, and
close only after `run_finished` confirms QThread cleanup.

## Image export

Single-view export preserves PNG, JPEG, and TIFF choices and starts in the
current artifact directory. It captures the current viewport without repeating
automatic artifact matching, so a manually opened stale VTP remains exportable
under D024.

Selected-case export preserves table order and writes `<case_id>.png`, defaulting
the folder chooser to the first row's `out_dir/images`. Every automatic VTP is
read and checked through the same exact case/signature matcher as selection;
missing, unreadable, stale, and screenshot-failing rows are logged and counted
as skipped. Current artifacts are loaded with explicit row context before
capture, preserving each product's independent overlay formatter. Filesystem
existence/directory creation, artifact reading, screenshots, and GUI event
processing are injectable test boundaries. Image pixels are not golden data.

## Bootstrap and compatibility selectors

`panelsolver.app.gui_bootstrap` is the only QApplication/window bootstrap. The
thin `fmfsolver.app.gui_app` and `newtsolver.app.gui_app` modules select their own
spec and call that bootstrap; they contain no widget, matcher, scheduler, or
physics implementation. When a Phase 7 adapter bundle is absent, the bootstrap
adds one common placeholder whose every operation raises a clear
`GuiAdaptersUnavailable` error and logs that calculations must continue in the
pinned legacy product. This permits launcher/shell acceptance without implying
that Phase 7 compatibility is complete.

The wheel includes both GUI modules and the shared bootstrap. Installed-wheel
smoke runs outside the repository working directory and checks both model IDs.
It also asserts that `fmfsolver`, `fmfsolver-gui`, `fmfsolver-cli`, `newtsolver`,
`newtsolver-gui`, and `newtsolver-cli` are not registered in Phase 6.

## Phase 6 acceptance record

- All 15 Phase 1 cases pass through the unchanged semantic golden matrix. No
  expected coefficient, panel load, shielding mask, CSV field, VTP/NPZ array,
  case signature, sign, axis, normalization, or tolerance changed in Phase 6.
- Headless GUI tests construct real Qt widgets with injected non-OpenGL plotters
  and deterministic adapters. Ubuntu, Windows, and macOS run the same suite.
- On 2026-08-12, a macOS normal-display smoke with `QT_QPA_PLATFORM` unset
  constructed the real `QtInteractor`, displayed the shared FMF shell, verified
  the exact `Sentman FMF Solver (GUI)` title, and captured the visible cases,
  viewer, camera, and export controls. The requested pre-show size remains
  1480 x 900; macOS constrained the captured on-screen window to 1470 x 815.
- Native `QtInteractor` with macOS `QT_QPA_PLATFORM=offscreen` exits in the VTK
  platform rendering layer and is not treated as a supported headless render.
  This does not affect the cross-platform injected-plotter GUI gate.

The retained differences are intentional: exact D022 titles, independent case
schemas and overlay formatters, adapter-selected worker/failure policies,
FMF-only deferred close versus newtsolver immediate close, primary-first ordered
legacy artifact signatures, and D024 manual stale-artifact inspection/export.
No GUI difference was selected as a universal product behavior.

Phase 7 must supply and test the real product case readers, signature fallbacks,
execution/checkpoint/final serializers, collision policies, and wind adapters;
register all six legacy commands; forward the frozen public Python imports;
and decide distribution mechanics. It must not silently replace the independent
GUI policies above, alter numerical formulas while wiring adapters, or infer
compatibility merely because the Phase 6 shell is importable. Phase 7 remains
not started.
