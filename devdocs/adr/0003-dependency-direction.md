# ADR 0003: Enforce inward dependency direction

- Status: Accepted
- Date: 2026-08-12

## Context

The current applications couple solver-specific imports into duplicated CLI and
GUI code. Without a dependency rule, migration would merely relocate conditional
logic and make core depend on concrete models or UI frameworks.

## Decision

Allow `app -> models -> core`, `app -> core`, and compatibility frontends toward
the shared layers. Prohibit core imports from models/app/frontends, model imports
from app/frontends, physics in GUI code, and new domain logic in frontends. Models
are selected by an application-level specification/registry, never by core.

## Consequences

Core stays model- and UI-independent and can be tested with synthetic contracts.
Some assembly code is required in app/frontends. Automated dependency tests
should be added when nonempty modules appear in Phases 2–3.
