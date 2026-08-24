# Developer documentation

Use repository documentation in this order:

1. [`docs/`](../docs/index.md) is the current user-facing specification for
   supported commands, inputs, outputs, numerical conventions, physical models,
   and the stable Python API.
2. [`devdocs/architecture/`](architecture/overview.md) describes the current
   implementation architecture and internal ownership boundaries.
3. [Accepted ADRs](adr/README.md) explain current architectural decisions. When
   an ADR explicitly supersedes part of an earlier decision, the superseding ADR
   takes priority for that part.
4. [`devdocs/history/`](history/README.md) preserves historical and
   non-normative migration and audit evidence.

Words such as “current”, “supported”, “next”, and “must” inside a historical
record describe the repository state at the time named by that record. Do not
use historical prose as present implementation instructions. If a historical
record conflicts with the current user specification, current architecture, or
an accepted/superseding ADR, use those current sources instead.

History is retained deliberately: pinned migration sources, golden baselines,
tolerances, legacy-difference observations, and audit results remain evidence
for compatibility and regression work. Read only the history relevant to the
task after establishing the current contract from the sources above.
