# Phase 3 computed-data adapters

Historical record — non-normative for the current product contract. This page records the repository state at the migration phase or audit named below. Statements such as “current”, supported commands, package names, file formats, and future work apply to that recorded point in time. Pinned source identities, golden evidence, tolerance profiles, and audit results may still be referenced by current developer workflows where devdocs/ or tests explicitly do so. Use docs/, devdocs/architecture/, and accepted or superseding ADRs for the present product contract.

Phase 3 ends at an intentionally narrow boundary around the pinned legacy
pipelines. A product still resolves and validates its public input, loads and
repairs the mesh, selects shielding, and evaluates its own physical equations.
Only after those operations does its thin adapter pass already-computed data to
the shared path:

```text
resolved common case + topology/geometry + shield mask + local traction/scalars
    -> shared attitude/frame primitive
    -> Phase 2 mesh, flow, and local-load contracts
    -> shared integration and component aggregation
    -> product-policy CSV plus semantic VTP/NPZ projections
```

`panelsolver.app.legacy_adapter` owns this routing without a product-name branch.
`fmfsolver.legacy_adapter` supplies the FMF-only `mode`, `S`, `Ti_K`, and `Tw_K`
projection fields. `newtsolver.legacy_adapter` supplies its windward/leeward VTP
metadata. Neither wrapper imports a legacy solver module or contains a physical
formula.

## Policies that remain adapter-only

The list below records the Phase 3 migration state. ADR 0008 now supersedes the
old rule that every ledger entry remains a dual contract: model-specific schemas
and outputs remain product-owned, while shared infrastructure and invalid-input
safety converge. In the Phase 3 implementation:

- attitude-mode parsing and the D007 angle-domain difference happen before this
  adapter;
- mesh loading/repair strictness (D011), shielding/backend behavior, cache and
  signature construction remain in their later owning phases;
- signatures are opaque adapter inputs, preserving D017/D018 rather than
  redesigning them;
- CSV collision scope, temp naming/`fsync`, and product columns retain D009,
  D010, and D029 respectively;
- FMF NPZ additions and newtsolver VTP equation fields retain D019/D020.

The adapter performs no VTP/NPZ file serialization. It creates immutable semantic
projections for regression comparison; CSV snapshot serialization uses the
separate explicit writer policies introduced in Phase 3f.

## Verification boundary

The complete 15-case Phase 1 matrix is reconstructed only from captured,
already-computed panel data and routed through the adapters. The existing Phase 1
semantic comparator then checks every CSV column/cell, VTP named array/field, and
NPZ named array with its selected path-specific tolerance. No golden or tolerance
is regenerated.

The reference repositories remain clean, read-only oracles at:

- `fmfsolver`: `b62bc844d02a8f5212e62a53dea3238a1414317d`
- `newtsolver`: `dc1357d0d50bbedfdc8b3429cab37e6b98b56c70`
