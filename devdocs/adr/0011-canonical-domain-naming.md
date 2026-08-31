# ADR 0011: Use flow-domain names on canonical user-facing surfaces

- Status: Accepted
- Date: 2026-08-15

The distribution-name sentence in this record is superseded by
[ADR 0013](0013-canonical-project-identity.md). Its domain, package, CLI, and
legacy-identity decisions remain in force.

The predecessor package, command, and identity-retention portions are superseded
by [ADR 0015](0015-remove-legacy-product-identities.md). Its canonical FMF and
Hypersonic domain naming remains in force.

## Context

The distribution contains two physical-model families and two legacy product
identities. Using a physical equation name or a legacy product name where a user
is choosing an analysis domain obscures that distinction and would make future
canonical CLI, GUI, and Python additions inconsistent.

## Decision

Canonical user-facing selectors use flow-domain names. The canonical domains are
`fmf` for free molecular flow and `hypersonic` for hypersonic panel methods.

Sentman is the physical model currently supported inside the FMF domain.
Newtonian, Modified Newtonian, Tangent Wedge, Tangent Cone, Prandtl–Meyer, and
related selectors are physical model or method identities inside the Hypersonic
domain. They are not top-level product identities.

`fmfsolver` and `newtsolver` are legacy compatibility product names. They remain
on the existing compatibility packages and six compatibility commands, with
their existing versions and GUI titles, but new canonical surfaces do not use
those names as domain selectors.

The installable distribution is `panel-solvers`. The canonical Python package
and command namespace is `panelsolver`. Accordingly, the canonical commands use
`panelsolver fmf`, `panelsolver hypersonic`, `panelsolver-gui fmf`, and
`panelsolver-gui hypersonic`; the package-root Python API uses `FMFCase` and
`solve_fmf` for the FMF domain while retaining `SentmanModel` and the internal
`sentman` model identity.

Future canonical public API, CLI, and GUI naming follows this domain-first rule.
Physical equation names remain where equations or method selection are being
described. No general naming framework, universal case hierarchy, or public
model registry is introduced by this decision.

Current domain-specific application composition is owned under
`panelsolver.domains`. This includes case-table schemas and adaptation,
runtime/projection/output policies, and canonical CLI/GUI composition. The
legacy `fmfsolver` and `newtsolver` packages delegate inward and retain only
compatibility identities, translations, and legacy artifact-signature fallback.
Production `panelsolver` code does not import either legacy package.

## Consequences

Users choose a flow domain with one consistent vocabulary, while documentation
can name the physical method precisely and legacy automation retains its
compatibility entry points. This naming decision does not change equations,
numerical values, artifacts, signatures, schemas, compatibility versions, or
runtime pipelines.
