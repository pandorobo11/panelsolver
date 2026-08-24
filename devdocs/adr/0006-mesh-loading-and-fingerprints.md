# ADR 0006: Preserve repair policies and use content-safe mesh identities

- Status: Accepted
- Date: 2026-08-12
- Refined by: ADR 0008 (dual repair behavior is transitional)

## Context

Phase 1 difference D011 records two normal-repair contracts. FMF rejects a
repair exception or remaining inconsistent winding, while newtsolver warns and
continues. D012 records different metadata-only mesh-cache keys, neither of
which proves that source bytes are unchanged. Mesh loading also feeds shielding,
signatures, and every integrated coefficient, so a false cache hit or silent
normal-policy change has numerical consequences.

The Phase 2 `PanelGeometry` contract already requires finite unit normals and
strictly positive finite areas. Phase 5 cannot admit geometry that violates that
accepted contract merely to imitate newtsolver's missing explicit check.

## Decision

The shared loader accepts two policy names:

- `strict` rejects normal-repair exceptions and remaining inconsistent winding,
  serving as the neutral default and effective policy;
- `legacy_warn_repair` remains an accepted compatibility input name but
  normalizes immediately to effective `strict` behavior under ADR 0008.

Both policies reject non-finite geometry, non-unit normals, empty geometry, and
non-positive areas through the Phase 2 contract. Compatibility frontends may
select a repair policy; physical models never do.

The process-local mesh cache key contains the loader algorithm version, resolved
source paths, SHA-256 of every source file, SI scale, and effective validation
policy. The compatibility alias therefore shares cache, scheduler-bucket, and
loaded-mesh numerical identity with `strict`.
Source bytes are read before cache lookup, avoiding stale reuse after a
metadata-preserving replacement. Cached results are immutable Phase 2/3
contracts.

A separate versioned geometry fingerprint hashes canonical little-endian
numerical arrays: SI-scaled vertices, ordered faces, centers, outward normals,
areas, and component IDs. Paths and timestamps are excluded. Face order and
component IDs are included because they affect shielding and model component
selection.

## Consequences

Phase 5 retained the two repair-failure behaviors during migration. Phase 8 now
applies ADR 0008 strict safety to both frontends: repair exceptions and remaining
inconsistent winding are rejected. The legacy policy enum name remains accepted
internally, resolves to the same effective identity, and no longer enables
permissive behavior. ADR 0008 no
longer treats that invalid-geometry difference as a permanent product contract;
future convergence must retain the strict common geometry safety boundary. The
content hash adds file-reading cost before a mesh-cache hit; correctness has
priority over the legacy metadata-only optimization. A future loader, repair,
or fingerprint algorithm change must increment its explicit version and add
cache/signature migration tests.
