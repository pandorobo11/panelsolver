# ADR 0004: Preserve legacy interfaces with thin frontends

- Status: Accepted
- Date: 2026-08-12
- Refined by: ADR 0008 (supported-domain surface)

The package-import and best-effort direct-Python portions of this decision were
superseded by [ADR 0014](0014-remove-legacy-direct-python-api.md). Its remaining
frontend, command, GUI-identity, and artifact-fallback portions are superseded by
[ADR 0015](0015-remove-legacy-product-identities.md). Historical file and
numerical evidence remains governed by the current supported-domain decisions.

## Context

Users and automation may rely on two command families, package imports, input
schemas, outputs, and GUI entry points. Requiring an immediate switch to a single
new interface would combine architecture migration with a breaking product
migration.

## Decision

Reserve `src/fmfsolver` and `src/newtsolver` for thin compatibility frontends.
They may translate legacy input and select shared application/model
configuration, but cannot implement new numerical, validation, exception,
artifact, caching, execution, or GUI behavior. Preserve old package and command
names through the compatibility period. ADR 0008 makes direct Python call-shape
and implementation details best effort; removing a supported command, normal GUI
operation, file field, or numerical behavior still needs a separate accepted
plan.

Compatibility implementation is isolated in private `panelsolver._compat`,
whose dependencies point inward to app/models/core. Shared layers do not import
that package. The former internal `panelsolver.app.legacy_*` paths are not
retained because forwarders there would reverse the accepted dependency
direction; product frontend paths remain the best-effort import surface.

## Consequences

Legacy users can migrate independently of internal refactoring. Compatibility
tests become a first-class suite, and some forwarding code remains temporarily.
Phase 0 provides importable placeholders but does not falsely register nonworking
commands.
