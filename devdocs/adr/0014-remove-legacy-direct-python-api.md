# ADR 0014: Remove the legacy direct-Python compatibility surface

- Status: Accepted
- Date: 2026-08-23
- Supersedes: the direct-Python compatibility portions of ADR 0004, ADR 0007,
  ADR 0008, and ADR 0012

## Context

The migration retained most modules and functions from the pinned `fmfsolver`
and `newtsolver` packages as best-effort forwarding wrappers. No external use of
those direct-Python APIs has been identified. The canonical package-root API,
commands, GUI, case-file readers, output writers, shared engine, and physical
models now own the supported behavior.

Keeping the wrappers duplicates module inventories, call shapes, result
translation, scheduler/error translation, mesh and shielding adapters, and
model-helper exports. That maintenance cost obscures the actual support boundary
and makes internal improvements look like compatibility changes even when the
documented user contracts are unaffected.

## Decision

The supported Python API is the exact package-root `panelsolver` surface:
`FMFCase`, `HypersonicCase`, `ResolvedAttitude`, `SolveResult`,
`resolve_attitude`, `solve_fmf`, and `solve_hypersonic`.

Direct imports under `fmfsolver.*` and `newtsolver.*` are not a supported API.
The legacy packages contain only the modules needed to host these command entry
points:

- `fmfsolver`, `fmfsolver-gui`, and `fmfsolver-cli`;
- `newtsolver`, `newtsolver-gui`, and `newtsolver-cli`.

The four GUI launch commands retain their legacy product IDs and window titles.
Their private frontends also retain ordered D017/D018 legacy signature fallback
so the current GUI can recognize artifacts made by the pinned legacy products.
The historical `1.3.8` and `1.0.3` values remain private signature inputs, not
Python package versions.

The implementation classification is:

| Class | Disposition |
|---|---|
| A — direct-Python compatibility only | Remove legacy readers/writers/exporters, direct runners, signature functions, scheduler, mesh, shielding, physics-helper paths, re-export modules, translation adapters, and their tests |
| B — legacy command/GUI operation | Keep only package roots, command entry-point modules, and private GUI identity composition |
| C — legacy artifact recognition | Keep private signature reconstruction and migration-baseline version constants |
| D — canonical implementation | Keep `panelsolver` core/models/app/domains implementations unchanged |

Canonical CLI/GUI behavior, CSV/XLSX/XLSM case schemas and defaults, Summary
CSV and VTP semantics, numerical formulas and values, signs, frames,
normalization, and the canonical signature schema are unchanged.

## Consequences

Code importing legacy modules such as `fmfsolver.core`, `fmfsolver.io`,
`newtsolver.core`, or `newtsolver.io` must migrate to the stable package-root API
or to documented commands and file contracts. This is an intentional breaking
cleanup before the first stable release and is recorded in the changelog.

The legacy package names remain install-time implementation details because the
console-script entry points import them. Their module names, attributes, and
callables can change without deprecation. Installed-wheel tests verify the small
frontend inventory, all six command registrations, all four legacy GUI
dispatches and identities, both legacy CLI contracts, and legacy artifact
fallback.
