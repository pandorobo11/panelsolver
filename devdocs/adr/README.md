# Architecture decision records

Accepted ADRs are retained as the rationale for architectural decisions:

1. [Use one development repository](0001-single-repository.md)
2. [Put a local load vector at the model boundary](0002-panel-load-vector-contract.md)
3. [Enforce inward dependency direction](0003-dependency-direction.md)
4. [Preserve legacy interfaces with thin frontends](0004-compatibility-frontends.md)
5. [Canonical numerical signatures](0005-case-signature-versioning.md)
6. [Mesh repair policies and content-safe identities](0006-mesh-loading-and-fingerprints.md)
7. [One distribution with distinct compatibility versions](0007-single-distribution-compatibility-versions.md)
8. [Preserve compatibility in the supported domain](0008-supported-domain-compatibility.md)
9. [Remove NPZ output](0009-remove-npz-output.md)
10. [Remove legacy BIFF XLS input](0010-remove-legacy-xls-input.md)
11. [Use flow-domain names on canonical user-facing
    surfaces](0011-canonical-domain-naming.md)
12. [Use the panel-solvers distribution version in runtime
    artifacts](0012-runtime-artifact-distribution-version.md)
13. [Use panelsolver as the canonical project
    identity](0013-canonical-project-identity.md)
14. [Remove the legacy direct-Python compatibility
    surface](0014-remove-legacy-direct-python-api.md)
15. [Remove legacy product identities and artifact
    fallback](0015-remove-legacy-product-identities.md)

ADRs describe why the current contracts exist. Migration execution records and
phase evidence are indexed separately in [History](../history/README.md).
ADR 0013 defines the current project identity; older ADRs retain the
`panel-solvers` spelling where it is part of the decision record they supersede.

A later ADR takes priority only for the portions it explicitly supersedes. An
earlier ADR may therefore remain effective in part even when another part has
been replaced. Determine status and supersession only from the statements in the
ADR texts; do not classify every record as either wholly current or wholly
superseded. Historical project names preserved inside a decision record do not
define the current project identity.
