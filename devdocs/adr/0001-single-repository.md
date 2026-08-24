# ADR 0001: Use one development repository

- Status: Accepted
- Date: 2026-08-12

## Context

`fmfsolver` and `newtsolver` share the mesh-to-load-to-integration-to-artifact and
GUI pipeline, but duplicated implementations have already diverged in mesh
validation, case safety, caching, scheduling, and lifecycle details. A third
permanent shared repository would add coordinated releases and cross-repository
changes.

## Decision

Develop the shared core, independent physical models, shared application, and
legacy compatibility frontends in this single neutral repository. Do not treat
either legacy codebase as the architectural parent. Keep legacy repositories as
read-only numerical references until Phase 8 acceptance.

## Consequences

Common changes can be tested and released atomically, but layer boundaries must
prevent a monolith. Distribution names may remain separate temporarily; source
repository unification does not itself decide packaging or user-facing removal.
