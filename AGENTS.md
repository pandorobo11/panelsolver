# Repository instructions

## Purpose and priorities

This repository contains the current Panel Solver product: one neutral platform
for the FMF and Hypersonic domains plus thin `fmfsolver` and `newtsolver`
compatibility frontends. Apply these priorities in order:

1. numerical correctness;
2. existing user compatibility;
3. architecture boundaries;
4. maintainability;
5. performance;
6. reduced code volume.

Never change numerical behavior or a public contract merely to remove duplicate
code.

## Read before editing

Before changing code, read in this order:

1. `devdocs/README.md`;
2. the relevant current architecture in `devdocs/architecture/`;
3. the relevant current user contract in `docs/`;
4. relevant ADRs in `devdocs/adr/`;
5. only the historical evidence in `devdocs/history/` needed for the task;
6. the current issue or task.

## GUI visual smoke on macOS

When inspecting the real PySide6/PyVista GUI through Computer Use, resolve the
helper in the current checkout from the repository root and use that same
absolute path for both launch and the Computer Use app target:

```bash
visual_app="$(pwd -P)/tools/macos/PanelSolverVisual.app"
printf '%s\n' "$visual_app"
open "$visual_app" --args --domain fmf --theme system
```

Pass the printed path to Computer Use. The bundle ID
`io.github.pandorobo11.panelsolver.visual-smoke` is a convenient target only
when it identifies one bundle; if Computer Use reports an ambiguous app
identifier, switch to the current checkout's absolute path. Use a normal macOS
display; do not set `QT_QPA_PLATFORM=offscreen` or `PYVISTA_OFF_SCREEN`. See
[`devdocs/development/gui-visual-smoke.md`](devdocs/development/gui-visual-smoke.md)
for representative loaded-state and light/dark capture commands.

### GUI evidence privacy

Before uploading a GUI screenshot, recording, or companion evidence to GitHub,
remove developer- and machine-specific paths from every value the artifact or
capture tooling can emit. For a pixel screenshot, sanitize rendered widgets,
table cells, visible logs, and captured tooltip or status text. When uploading
an accessibility/UI-tree or text dump, also sanitize emitted accessible text,
hidden serialized text, What's This content, and other captured metadata.
Prefer a runtime-only sanitized capture from the real GUI, and never upload a
raw Computer Use capture first and attempt to redact it afterward.

Sanitization must preserve the geometry and state being evaluated. Do not let
redaction trigger autosizing, column resizing, reflow, wrapping, minimum-size
changes, control repositioning or visibility changes, or changes to focus,
checked, or running state. Preserve representative text width, or sanitize
after layout and width calculation without retriggering autosizing or reflow.

Inspect each upload candidate visually and, where available and practical, use
text and metadata checks such as OCR, embedded-string scanning, and metadata
inspection. Cover macOS, Linux, and Windows user-profile, checkout/worktree,
and temporary paths, including drive-letter and environment-based Windows
forms, as well as local usernames and temporary output paths. Upload only the
verified sanitized files.

## Legacy references

The legacy implementations are read-only references. Their authoritative URLs
and commits are in `devdocs/history/migration/MIGRATION_SOURCES.md`. Local checkouts may live at
`.reference/fmfsolver`, `.reference/newtsolver`, or the workspace sibling paths.
Do not edit them during migration work. If the implementations differ, report
both behaviors and their effects. Apply ADR 0008 when deciding whether the
difference belongs to the supported product contract; historical observation
alone does not require preserving invalid-input or Python-internal behavior.

## Dependency direction

Allowed high-level dependencies are:

- `app -> models -> core`;
- `app -> core`;
- compatibility frontends (`fmfsolver`, `newtsolver`) -> `app/models/core`.

Prohibited:

- `core` importing `models`, `app`, GUI, or a compatibility frontend;
- `models` importing `app`, GUI, or a compatibility frontend;
- physical equations in GUI code;
- new business or numerical logic in a compatibility frontend.

Keep `src/fmfsolver` and `src/newtsolver` as thin compatibility frontends.

## Model boundary

The common model contract must represent each panel's local nondimensional load
vector, visualization scalars, and model metadata. It must not reduce every model
to pressure coefficient alone, because that would discard Sentman tangential
loads. The common engine owns area/reference normalization and force/moment
integration.

## Numerical rules

- Use SI internally.
- Make degree versus radian explicit in names or types.
- Make coordinate frames explicit with suffixes such as `_stl`, `_body`, and
  `_wind`.
- Store per-panel vectors as `(n_faces, 3)` unless an approved ADR says otherwise.
- Validate shapes where NumPy broadcasting is used.
- Reject NaN, infinity, numeric booleans, invalid shapes, overflowed derived
  state, degenerate faces, and zero or negative reference quantities at a shared
  validation boundary.
- Do not change signs, axes, or normalization conventions without an accepted ADR
  and compatibility plan.
- Never mix a numerical-formula change with a structural migration PR.

## Regression and compatibility

Do not update expected coefficients, panel loads, shielding masks, CSV columns,
VTP fields, or case signatures without documenting the intended change,
evidence, effect, and tolerance. Compare VTP semantic arrays and metadata, not
file bytes. ADR 0008 defines the supported compatibility surface: commands,
normal GUI operation, documented case files, and documented CSV/VTP
semantics. Direct Python keyword names, GUI methods, object identity, module or
qualname, pickle globals, cache internals, and exact exception details are not
contracts unless another ADR explicitly promotes a neutral API.

## Change discipline

- Keep one issue to one independently reviewable change.
- Edit only the files needed for the task.
- Do not include unrelated cleanup, renaming, or formatting.
- Explain every new production dependency.
- Do not push directly to `main`, rewrite history, or merge on behalf of the user
  unless explicitly requested.
- If code, tests, literature, and ADRs disagree about supported numerical or file
  behavior, stop that decision and report the conflict. For invalid inputs or
  excluded Python implementation details, follow ADR 0008's common safety and
  convergence rules instead of recreating an accidental legacy difference.

## Verification

Use the cross-platform local validation runner as the primary workflow:

```bash
python scripts/check.py --quick  # during development
python scripts/check.py          # before push or pull request
python scripts/check.py --full   # deeper packaging/process validation
```

On POSIX systems, `scripts/check.sh` accepts the same arguments and only forwards
them to the Python runner. Each mode begins with the locked dependency sync.
The runner reports each step and elapsed time and stops at the first failure.

The quick mode runs Ruff formatting and lint, scoped mypy, and
`pytest -m "not slow"`. The default standard mode substitutes the authoritative
full pytest suite, then checks generated sources and plots, builds strict docs,
and builds the distributions. Full additionally runs the scheduler lifecycle
probe, distribution verification, and installed-wheel smoke in a temporary
clean environment.

For targeted typing troubleshooting, the exact checked boundary remains:

```bash
uv run --no-sync mypy src/panelsolver/core/contracts.py src/panelsolver/core/execution.py src/panelsolver/models/registry.py src/panelsolver/app/execution.py src/panelsolver/api.py src/panelsolver/__init__.py
```

This checks only the explicit model-contract, registry, execution, and
package-root solve API boundary shown above; it is not a repository-wide typing
guarantee.

Most existing tests remain written with `unittest`; use pytest as the standard
test runner.

For targeted test troubleshooting, the fast command is
`uv run --no-sync pytest -m "not slow"` and the full command is
`uv run --no-sync pytest`. The unfiltered pytest suite remains authoritative.

As applicable, also test the changed CLI's `--help`, the built wheel, the GUI,
Embree and rtree backends, and model-specific golden regressions.

## Completion report

Report changed files, implemented behavior, design choices, checks and results,
numeric differences, compatibility impact, remaining risks, and follow-up work.

## Review priorities

Review numerical formulas, units, signs, coordinate frames, shapes/broadcasting,
compatibility, cache/signature keys, worker failure/cancellation, mesh normals and
degenerate faces, output completeness, and missing regression coverage before
style concerns.
