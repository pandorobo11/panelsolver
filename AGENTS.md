# Repository instructions

## Purpose and priorities

This repository contains the current Panel Solver product: one neutral platform
for the FMF and Hypersonic domains. Apply these priorities in order:

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

## GUI visual smoke and evidence

Before inspecting the real PySide6/PyVista GUI through Computer Use, follow
[`devdocs/development/gui-visual-smoke.md`](devdocs/development/gui-visual-smoke.md).
Use a normal macOS display; do not set `QT_QPA_PLATFORM=offscreen` or
`PYVISTA_OFF_SCREEN`. Pass the same absolute app path printed at launch to
Computer Use.

Before uploading any GUI screenshot, recording, or UI-tree/text dump to GitHub,
apply its [GUI evidence privacy](devdocs/development/gui-visual-smoke.md#gui-evidence-privacy)
rules: sanitize at capture time without changing layout or state, and never
upload a raw capture to redact afterward.

## Legacy references

The `fmfsolver` and `newtsolver` migration is historical. Consult those
implementations only when a task needs their recorded behavior; their URLs and
pinned commits are in `devdocs/history/migration/MIGRATION_SOURCES.md`, and local
checkouts, when present, live under `.reference/` or as workspace siblings.
Never edit them. If they differ, report both behaviors and their effects. Apply
ADR 0008 when deciding whether the difference belongs to the supported product
contract; historical observation alone does not require preserving
invalid-input or Python-internal behavior.

## Dependency direction

Allowed high-level dependencies are:

- `app -> models -> core`;
- `app -> core`;

Prohibited:

- `core` importing `models`, `app`, or GUI;
- `models` importing `app` or GUI;
- physical equations in GUI code;
- new business or numerical logic in command dispatchers.

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
- Never mix a numerical-formula change with a structural or refactoring PR.

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

Use the cross-platform local validation runner:

```bash
python scripts/check.py --quick  # during development
python scripts/check.py          # before push or pull request
python scripts/check.py --full   # deeper packaging/process validation
```

The unfiltered pytest suite is authoritative; the mypy check covers only a
scoped boundary, not the whole repository. Use pytest as the runner, although
most existing tests are written with `unittest`. Mode contents and targeted
pytest/mypy commands are in
[`devdocs/development/setup-and-testing.md`](devdocs/development/setup-and-testing.md).

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
