# ADR 0013: Use panelsolver as the canonical project identity

- Status: Accepted
- Date: 2026-08-16
- Supersedes: distribution-name wording in ADR 0007, ADR 0011, and ADR 0012

The legacy-package and legacy-command rows of this identity table, plus related
rollback wording, are superseded by
[ADR 0015](0015-remove-legacy-product-identities.md). All canonical identity rows
remain in force.

## Context

The canonical Python package and commands already use `panelsolver`, while the
repository and Python distribution used `panel-solvers`. Keeping both spellings
as current top-level identities would make installation, metadata lookup,
release artifacts, documentation, and repository links unnecessarily
ambiguous before the first public release.

FMF and Hypersonic are analysis domains inside the product. The `fmfsolver` and
`newtsolver` names remain intentional legacy compatibility identities and are
not candidates for this rename.

## Decision

Use these identities:

| Surface | Identity |
|---|---|
| Product display name | Panel Solver |
| GitHub repository | `panelsolver` |
| Python distribution | `panelsolver` |
| Python package | `panelsolver` |
| Canonical CLI | `panelsolver`, `panelsolver-gui` |
| Canonical domains | `fmf`, `hypersonic` |
| Legacy packages | `fmfsolver`, `newtsolver` |
| Legacy commands | `fmfsolver`, `fmfsolver-gui`, `fmfsolver-cli`, `newtsolver`, `newtsolver-gui`, `newtsolver-cli` |

The canonical repository URL is
`https://github.com/pandorobo11/panelsolver`. Installed-version inspection uses
`importlib.metadata.version("panelsolver")` or the equivalent distribution
lookup. Wheels and source distributions therefore use the `panelsolver-`
filename prefix.

The release manifest schema name is `panelsolver.dist-manifest` at schema
version 1. The schema structure and meaning are unchanged: it already records
and verifies the wheel's arbitrary metadata name and version. Correcting the
pre-release namespace does not require a schema-version bump. Historical audit
records and previously generated candidate artifact names remain unchanged as
evidence and are not accepted as current release inputs.

ADR 0007's one-distribution decision, release tagging, legacy versions, and
rollback ordering remain in force. ADR 0011's domain naming remains in force.
ADR 0012's `solver_version` semantics remain in force; only its distribution
lookup name changes.

## Consequences

The rename changes distribution metadata, artifact filenames, install targets,
release-tool identity checks, and current repository URLs. It does not rename
packages or commands and does not change numerical equations, case files,
Summary CSV/VTP schemas, `solver_version` value format, or numerical results.

Distribution version is artifact provenance outside the canonical and legacy
case-signature payloads, so case signatures remain byte-for-byte unchanged.
The GitHub repository setting must be renamed separately after the code change
lands; repository redirects are not a substitute for updating canonical URLs.
