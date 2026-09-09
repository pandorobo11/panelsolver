# ADR 0018: Generate every face normal from repaired geometry

- Status: Accepted (user-directed pre-release specification)
- Date: 2026-09-09
- Refines: ADR 0006 normal generation and loader versioning; ADR 0008 numerical
  identity expectations for this pre-release geometry change. ADR 0005 and
  ADR 0017 signature schemas are unchanged.

## Decision

After SI conversion, strict positive finite area validation, and Trimesh winding
and inversion repair, core generates every face normal from the repaired face
cross product. Divide each cross product by its maximum absolute component,
then normalize the scaled vector by its L2 norm. Do not use Trimesh face normals
as the ordinary path or retain an exact-zero fallback. This avoids Trimesh's
absolute normal-generation cutoff without changing the face winding.

Retain all existing geometry validation, the unit-vector tolerance, face order,
component assignments, scale semantics, and physical equations. This does not
admit degenerate geometry or relax the area computation's finite-range limits.
No face is dropped.

The unreleased mesh-loader-v2 now denotes this uniform algorithm, replacing the
experimental zero-only recovery in PR #291. The released/base implementation was
v1; no additional v3 is needed for this revision of the same unreleased change.
The geometry fingerprint fields and canonical encoding remain schema v1, and
current case signatures remain schema v2.

## Compatibility and historical evidence

Preserving the last bits of Trimesh-generated normals is not a compatibility
requirement. Semantic normal comparisons retain absolute tolerance 1e-12, and
existing model-specific coefficient/load tolerances and exact shielding-mask
comparisons remain authoritative. Geometry fingerprints and current case
signatures may change when normal bits change. Recompute affected artifacts to
restore automatic matching; no equivalence rule or old-signature fallback is
introduced.

Checked-in Phase 1 geometry, numerical goldens, and historical v1 signature
strings remain immutable evidence. Reconstruct historical geometry identity from
those golden arrays, not the current STL loader. Current signatures use current
loader geometry and must not auto-match historical v1 signatures (ADR 0017).

## Verification

Cover small open and closed meshes, repaired outward/inverted/inconsistent
winding, SI scaling, area scaling, regular faces, and multiple components.
Retain strict invalid-geometry tests and legacy semantic goldens. Measure normal,
fingerprint, signature, panel-load, coefficient, and shielding differences
without rewriting the historical evidence.
