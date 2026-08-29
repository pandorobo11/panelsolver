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
4. [`devdocs/history/`](history/README.md) preserves migration and audit evidence
   that is non-normative for the current product contract.

Development workflows begin with
[setup and testing](development/setup-and-testing.md). For normal-display
PySide6/PyVista inspection on macOS, use the
[GUI visual-smoke helper](development/gui-visual-smoke.md).

Words such as “current”, “supported”, “next”, and “must” inside a historical
record describe the repository state at the time named by that record. Do not
use that historical prose as present implementation instructions or derive the
current product contract from it. If a historical record conflicts with the
current user specification, current architecture, or an accepted/superseding
ADR, use those current sources instead.

Historical prose and recorded evidence have different roles. Pinned source
identities, golden baselines, tolerance profiles, and audit results remain valid
verification evidence when current developer documentation or tests explicitly
reference them. History is retained deliberately for that compatibility and
regression work. Read only the evidence relevant to the task after establishing
the current product contract from the sources above.
