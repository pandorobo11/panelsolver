---
name: engineering-desktop-ui
description: >
  Audit, design, implement, and review dense PySide6/Qt Widgets interfaces for scientific and
  engineering desktop applications. Prioritizes workflow efficiency, data readability, state and
  provenance clarity, native desktop behavior, accessibility, and incremental migration over
  decorative novelty. Use for analysis tools with tables, numerical inputs, viewers/canvases,
  long-running execution, logs, artifacts, and result comparison.
---

# Engineering Desktop UI

Use this skill for professional engineering and scientific desktop applications where users repeatedly configure analyses, inspect numerical data, run long-lived work, and judge result validity.

The goal is not to make the application look like a web dashboard. The goal is to make expert work faster, clearer, safer, and more consistent while preserving native desktop behavior and existing application contracts.

## Authority and priorities

When recommendations conflict, resolve them in this order:

1. numerical and result trustworthiness;
2. existing supported workflow and compatibility;
3. engineering workflow efficiency;
4. data readability and comparability;
5. state and provenance clarity;
6. native desktop usability and accessibility;
7. maintainable visual architecture;
8. visual distinctiveness and novelty.

If another visual-design skill recommends a treatment that conflicts with these priorities, adapt or reject that treatment.

## Operating modes

Classify the task before editing:

- **Audit:** inspect and report; do not modify files.
- **Foundation:** introduce or improve semantic tokens, palette, generated QSS, typography roles, spacing, and control-state infrastructure without redesigning the workflow.
- **Component:** improve one bounded widget, dialog, table, toolbar, viewer control group, or state surface.
- **Workflow:** change information hierarchy, panel structure, diagnostics placement, or interaction flow. Keep this separate from foundation work.
- **Review:** assess a proposed GUI change for workflow, state clarity, data readability, native behavior, accessibility, and regression risk.

For broad modernization, begin with **Audit** unless the affected scope is already narrowly defined.

## Non-negotiable rules

1. **Preserve behavior during visual work.** Do not change models, solver logic, numerical formulas, signals, slots, commands, selection semantics, shortcuts, persistence, object names, automation hooks, artifact contracts, file semantics, or test-visible behavior unless the task explicitly includes that change.
2. **Keep engineering results primary.** Viewer, plot, canvas, table, or other primary result surfaces receive visual priority over chrome, decoration, and diagnostics.
3. **Treat logs as diagnostic UI.** Logs should normally be secondary, resizable, collapsible, or otherwise prevented from permanently consuming prime workspace area.
4. **Do not hide important state in logs.** Running, cancelling, warning, failed, success, stale, unmatched, invalid, and read-error states must be represented in the main workflow where relevant.
5. **Do not use color alone for status.** Pair color with text, iconography, identity, or accessible descriptions.
6. **Preserve data semantics.** Visual formatting may improve alignment, labels, units, and precision presentation, but must not silently alter stored values, exported fields, file contracts, or numerical meaning.
7. **Prefer compact density.** Expert desktop tools may be dense. Remove wasted space before removing useful information.
8. **Do not inflate every group into a card.** Prefer spacing, grouping, alignment, headers, and subtle dividers before bordered/elevated containers.
9. **Use native Qt behavior first.** Prefer standard widgets, layouts, model/view, splitters, menus, dialogs, selection models, `QPalette`, application QSS, delegates, and narrow style overrides before custom painting.
10. **Keep focus visible.** Keyboard focus must remain visible independently of hover, selection, warning, and error states.
11. **Avoid decorative motion.** Add motion only when it communicates state or spatial continuity and respects reduced-motion preferences.
12. **Separate design foundation from layout redesign.** Do not combine token/theme infrastructure with major information-architecture changes in one PR unless the scope is explicitly approved.

## Ground the design in the engineering task

Before proposing a visual direction, identify:

- the user role and expertise level;
- the application's single primary job;
- the repeated workflow users perform most often;
- the primary engineering result or decision surface;
- the expensive or dangerous actions;
- the states that affect trust in the result;
- the data users compare across rows, cases, runs, or artifacts.

Use the subject's actual instruments and workflow as the source of visual identity. Prefer a functional signature element, such as a compact analysis-state/provenance surface or especially clear comparison workflow, over decorative branding.

## Information hierarchy

Design hierarchy in this order:

1. placement and available area;
2. grouping and spacing;
3. typography and alignment;
4. surface contrast and dividers;
5. semantic color;
6. decoration only when it communicates meaning.

A primary action should be obvious within its local workflow, but engineering applications may legitimately have multiple simultaneous contexts. Avoid artificially forcing the entire application into a single marketing-style call to action.

## Numerical and tabular UI

For dense engineering tables and numerical controls:

- align numbers for scanning; right alignment is the default for comparable numeric columns;
- keep identifiers and free text left aligned;
- use tabular digits where practical;
- make units visible in headers, labels, or adjacent metadata when the unit is part of the user decision;
- preserve domain precision and scientific notation rules;
- separate visual display formatting from stored/exported data semantics;
- distinguish current row, selected rows, keyboard focus, invalid cells, and stale values;
- prefer model/view and delegates over per-cell widget inflation;
- optimize widths and density for comparison, not decorative whitespace;
- do not rename machine fields or file columns merely to improve display labels—use a display mapping instead.

## Operational state model

Define relevant states explicitly. A typical engineering application may need:

| State | Expected treatment |
| --- | --- |
| Empty | neutral explanation plus the next useful action |
| Ready | quiet baseline; primary action available when valid |
| Running | text plus progress/activity; prevent accidental duplicate execution |
| Cancelling | distinct from running; explain whether cancellation is immediate or cooperative |
| Success | completion summary and result identity where useful |
| Warning / partial output | separate successful computation from incomplete or failed artifact/output steps |
| Failed | concise failure summary plus a useful recovery action |
| Invalid | local validation message associated with the affected control/data |
| Stale | warn that displayed or available results do not match current inputs/signature |
| Manual / unmatched | identify provenance and explain that the artifact is not matched to the current case/workspace |
| Read error | state what could not be read and whether a previous result was cleared or retained |

Do not collapse semantically different states into one generic red message or one blank viewer.

## Result provenance and trust

When users can inspect generated, cached, manually opened, or stale artifacts, expose enough identity to judge what is being viewed. Depending on the application, this may include:

- case/run identifier;
- source path;
- current vs stale/mismatched status;
- manually opened vs automatically matched source;
- active scalar/result field;
- timestamp/version/signature when already available in the product contract.

Do not add new provenance semantics to the numerical contract merely for UI decoration. Project existing trusted metadata into the UI.

## Action hierarchy

Use semantic intent rather than button-specific styling:

- **Primary:** the main local action, such as Run or Apply.
- **Secondary:** ordinary supporting actions, such as Open or Save.
- **Subtle/compact:** frequent low-risk contextual commands, such as camera/view controls.
- **Danger:** destructive or interruption actions, such as Cancel when cancellation has meaningful consequences.

A disabled action should remain readable. If the reason for disabling it is not obvious from context, provide an adjacent explanation, tooltip, or accessible description.

## Styling architecture for PySide6 / Qt Widgets

Prefer this responsibility split:

| Mechanism | Responsibility |
| --- | --- |
| semantic tokens / aliases | spacing, typography roles, colors, radii, component metrics |
| `QPalette` | broad active/inactive/disabled colors, selection, links, tooltips |
| generated application QSS | component padding, borders, radii, semantic variants and interaction states |
| dynamic properties | primary/secondary/danger, severity, busy, invalid, stale, or other semantic roles |
| model/view delegates | table/data visuals that QSS cannot express cleanly |
| `QProxyStyle` | narrow metrics or style hints only when necessary |
| composite widgets | bounded message/state/provenance surfaces |
| custom painting | last resort |

Do not scatter hard-coded colors or unrelated `setStyleSheet()` fragments across widgets. Application code should consume semantic roles, not raw color values.

## Density, spacing, and typography

Default to a compact desktop profile unless the product requires otherwise.

Recommended starting points, not mandates:

- spacing scale: `2, 4, 6, 8, 12, 16, 24, 32`;
- compact control target: about 26–28 px, subject to `QFontMetrics` and platform scaling;
- standard control target: about 32 px;
- ordinary radius: 3–4 px; larger radii only for transient/floating surfaces;
- body text: native system UI font;
- data/numeric text: system font with tabular digits where available;
- logs/paths/code: system fixed-width font;
- large display typography: generally unnecessary in engineering workbenches.

Never fix a metric so tightly that text clips at translated labels, platform font changes, or common scaling levels.

## Viewer / canvas guidance

For 2D/3D result viewers:

- preserve the largest practical uninterrupted result area;
- keep controls logically grouped and close to the context they affect;
- avoid rows of equally emphasized buttons when commands have different importance;
- distinguish empty, loading, stale, unmatched, and read-error states from an ordinary blank background;
- expose current result identity and active field/scalar when that helps users trust what they are seeing;
- do not replace native camera/interaction behavior without a demonstrated usability benefit.

## Diagnostics and secondary panels

Diagnostics should support troubleshooting without dominating normal analysis.

Prefer one of:

- collapsible diagnostics region;
- resizable splitter panel;
- `QDockWidget` when docking behavior is appropriate;
- compact status plus an explicit route to detailed diagnostics.

When a diagnostics surface can be hidden, leave an obvious way to restore it. Persist panel state only when the application's persistence contract is intentionally extended.

## Theme and accessibility

A robust theme system should have a path for:

- light;
- dark;
- system-following;
- active/inactive windows;
- disabled controls;
- high-contrast/system-palette fallback where feasible.

Validate:

- visible keyboard focus;
- logical tab order;
- text and essential non-text contrast;
- icon-only accessible names/tooltips;
- selection independent of keyboard focus;
- long labels and scaling;
- read-only fields remain copyable when appropriate;
- dialogs return focus sensibly after closing.

Do not claim a screen is complete after one light-theme screenshot.

## Workflow for an existing GUI

### 1. Inventory

Inspect:

- top-level windows and major panes;
- widget hierarchy, layouts, splitters, docks, menus, dialogs;
- tables/models/delegates;
- viewer/canvas controls;
- current styling, palettes, inline styles, custom painting;
- operational states and where each state is visible;
- focus order and shortcuts;
- screenshots and GUI regression tests.

### 2. Record behavioral constraints

List the contracts that must remain unchanged during visual work. Include relevant signals, slots, selections, commands, persistence, object names, automation hooks, file/artifact semantics, and tests.

### 3. Walk the primary workflow

Evaluate the actual sequence users perform, for example:

```text
Input -> Configure/select cases -> Run -> Monitor -> Inspect result -> Compare/export
```

For each stage, identify:

- what the user is trying to decide;
- what must be visible;
- what friction or ambiguity exists;
- whether the next action is obvious;
- whether result/state trust is clear.

### 4. Audit before redesign

Return strengths, issues, severity, source location, workflow friction, and migration risks. Propose layout/wireframe alternatives separately from foundation work.

### 5. Establish design foundation

Before major layout changes, centralize semantic tokens, palette/QSS architecture, action roles, focus/disabled states, and theme behavior. Preserve layout and behavior as much as possible.

### 6. Project semantic states

Make existing runtime/result states visible through stable UI properties and bounded state surfaces. Do not invent new domain state merely for styling.

### 7. Improve bounded components

Refine tables, viewer controls, dialogs, and primary/secondary actions in separately reviewable increments.

### 8. Change workflow/layout last

Only after the visual/state foundation is stable should diagnostics placement, splitter policy, comparison surfaces, or broader navigation change.

### 9. Validate repeatedly

Check functional tests plus screenshots/workflow walkthroughs across relevant states, themes, scaling levels, and target platforms.

## Working with other design skills

### Visual/frontend design skills

Use them for:

- aesthetic critique;
- hierarchy and intentionality;
- wording and empty/error-state quality;
- avoiding generic AI-generated visual patterns;
- screenshot-based self-critique.

Adapt or reject web-specific guidance such as:

- hero sections;
- marketing-page composition;
- mobile-first layout assumptions;
- scroll-triggered interactions;
- oversized display typography;
- decorative animation;
- CSS-specific architecture.

### Fluent or toolkit-specific skills

Use them for:

- semantic control states;
- Qt feasibility;
- palette/QSS architecture;
- keyboard/focus/accessibility;
- native platform behavior;
- incremental migration details.

Do not copy a brand shell, exact product layout, or frameless title bar merely to appear modern.

## Review checklist

Before accepting a GUI change, ask:

- Is the primary engineering result still visually dominant?
- Can users tell what will run before starting expensive work?
- Are running/cancelling/failure/output/stale states distinguishable without reading logs?
- Can users tell what result/artifact they are currently viewing?
- Are numerical values easy to compare and units/precision preserved?
- Is useful information density retained?
- Are diagnostics secondary during normal work?
- Are primary, supporting, contextual, and danger actions distinguishable?
- Are focus, keyboard, disabled, selected, and invalid states clear?
- Does the change preserve existing behavior and product contracts?
- Are web-style cards, giant typography, decoration, or motion being used without engineering benefit?
- Was foundation work kept separate from major layout changes?
- Were relevant functional tests and visual/platform checks performed?

## Audit output expectations

Return:

1. executive summary;
2. strengths to preserve;
3. issues with severity, user impact, and source location;
4. primary workflow analysis;
5. layout/wireframe alternatives with trade-offs;
6. design-foundation proposal;
7. operational-state and provenance gaps;
8. implementation phases split into reviewable PRs;
9. regression, keyboard, theme, scaling, and platform validation strategy;
10. explicit recommendations from other design skills that should be adopted, adapted, or rejected.

For Audit mode, do not modify code unless explicitly requested.

## Completion gate

A modernization scope is complete only when the applicable items below are true:

- supported functional behavior is unchanged unless intentionally revised;
- numerical/file/artifact semantics are unchanged unless intentionally revised;
- visual values flow through semantic roles rather than scattered constants;
- applicable operational and interaction states are visibly represented;
- result provenance is clear enough for the application's trust requirements;
- keyboard focus and tab order are usable;
- tables/data preserve units, precision, alignment, and comparison efficiency;
- common themes and scaling levels have been checked;
- target-platform behavior has been exercised where practical;
- existing functional tests pass;
- new state/theme/UI regression tests cover the changed scope;
- layout redesign did not accidentally expand into solver/domain architecture work.
