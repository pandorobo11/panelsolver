# ADR 0008: Preserve compatibility in the supported domain

- Status: Accepted
- Date: 2026-08-14

The NPZ compatibility-surface portion of this decision is superseded by
[ADR 0009](0009-remove-npz-output.md). Its CSV, VTP, numerical, and supported-
domain decisions otherwise remain in force.

The legacy BIFF `.xls` case-file portion of this decision is superseded by
[ADR 0010](0010-remove-legacy-xls-input.md). Its CSV, XLSX, XLSM, VTP,
numerical, and other supported-domain decisions remain in force.

The best-effort legacy direct-Python portion is superseded by
[ADR 0014](0014-remove-legacy-direct-python-api.md). The command, GUI, file,
artifact, and numerical supported-domain decisions remain in force.

## Context

Phase 1 correctly recorded every observable difference between the pinned FMF
and newtsolver implementations. Later migration work sometimes treated all of
those observations as permanent compatibility requirements, including behavior
for invalid inputs and Python implementation details. That conflicts with the
repository goal of one shared application and execution platform whose product
differences are limited to the physical models and their user-facing schemas.

The migration must continue to protect normal supported calculations and file
interfaces without recreating accidental NaN propagation, NumPy broadcasting,
class identity, pickle paths, cache internals, or failure-envelope details merely
because the legacy programs happened to differ there.

## Decision

FMF and newtsolver may differ only where the selected physical model or migration
entry point requires it:

1. model-specific input columns, schema, defaults, and physical-domain fields;
2. physical equations and model-owned numerical methods;
3. model-specific output columns, visualization scalars, and metadata;
4. compatibility package names, command names, product versions, and window
   titles.

Validation, the exception hierarchy, scheduler, caches, GUI implementation,
mesh/result/validation classes, and other application or execution mechanics are
shared platform behavior. Compatibility frontends may translate model schemas
and retain migration names, but they do not need product-owned copies of shared
classes or functions.

The supported compatibility surface is the command-line interface, normal GUI
operation through the two launchers, documented case files, and documented
result CSV/VTP/NPZ semantics. Existing direct Python modules remain available on
a best-effort basis, but exact callable keyword names, direct GUI methods,
function or class object identity, `__module__`, `__qualname__`, pickle globals,
and cache objects or `cache_info()` are not compatibility contracts unless a
future ADR explicitly promotes a neutral API.

Supported numerical inputs must be validated before unsafe calculation or
serialization. Common boundaries reject NaN, infinity, booleans used as numbers,
non-rectangular or invalid shapes, overflowed derived state, degenerate geometry,
and zero or negative reference quantities. Products do not preserve accidental
NaN/Inf propagation, permissive broadcasting, or a shielded early return that
bypasses invalid normalization inputs. Exact exception text, cause/context,
traceback structure, and import-time versus execution-time validation are not
contracts; stable shared exception categories and field-aware diagnostics are.

For D015, the migration implementation was temporarily different. The
historical evidence was:

- FMF selects `FORWARD / DISCARD_CHUNK`;
- newtsolver selects `DROP / YIELD_COMPLETED`.

That historical difference is superseded by the adopted common
`FORWARD / YIELD_COMPLETED` policy for both products. The implemented
remediation forwards worker logs and warnings and retains successful earlier
cases from a later-failing chunk in input-ordered progress, checkpoints, and
summary results. It does not alter successful-run results, cancellation,
startup/unexpected-exit handling, cleanup, artifacts, signatures, cache
identities, or numerical formulas.

Phase 1 evidence remains an authoritative record of what the pinned programs
did. Its historical behavior columns are not, by themselves, normative Phase 8
requirements. ADR 0008 supersedes instructions to preserve every recorded
legacy discrepancy until a separate product-specific decision is made.

## Consequences

Normal supported inputs retain their numerical values, ordered file schemas,
semantic artifact arrays and metadata, product model fields, and migration entry
points. No golden, tolerance, sign, frame, normalization, signature schema, or
cache identity changes merely because of this decision.

Shared safety and architecture corrections may intentionally converge behavior
outside that supported domain. Such changes need focused tests for the common
rule, but do not need product-specific identity, pickle, message, traceback, or
invalid-value compatibility fixtures. A change to a supported numerical value
or documented file contract still requires separate evidence, compatibility
handling, and an accepted decision.
