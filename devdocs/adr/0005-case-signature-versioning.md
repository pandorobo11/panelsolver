# ADR 0005: Canonical case signatures separate schema and algorithms

- Status: Accepted (exact Phase 5 schema adopted)
- Date: 2026-08-12

The NPZ serialization portion of this decision is superseded by
[ADR 0009](0009-remove-npz-output.md). Its CSV, VTP, numerical-signature, and
artifact-matching decisions remain in force.

## Context

Both legacy applications used case signatures for cached results and VTP matching,
but normalized inputs differently. The shared platform retains the schema as the
identity that relates an execution case to Summary CSV and VTP artifacts. Tying
that identity to the whole application version would invalidate artifact matching
after UI-only changes; omitting model/geometry versions could match incompatible
results.

## Decision

Build the following exact schema, serialized as UTF-8 JSON with sorted keys,
compact separators, ASCII escaping, and non-finite values rejected. The case
signature is the lowercase SHA-256 digest of those bytes.

```text
schema: {name: "panelsolver.case", version: 1}
geometry: {fingerprint_sha256}
common_case: {
  case_id, Aref_m2, moment_reference_stl_m,
  Lref_Cl_m, Lref_Cm_m, Lref_Cn_m,
  alpha_t_deg, beta_t_deg
}
model: {id, algorithm_version, case}
shielding: {
  algorithm_version, enabled, requested_backend,
  effective_backend, batch_size
}
```

`model.case` is the model-owned normalized signature payload. The shielding
section includes the effective backend so `auto` results produced by rtree and
Embree have distinct case and artifact identities. Shielding cache capacity is
excluded because it cannot change numerical output. The user-visible application
version remains artifact metadata outside this identity.

The Phase 5 signature is always the primary match. Product adapters may supply
an ordered collection of opaque legacy hashes for fallback. Core tests the
primary first and never reconstructs, normalizes, or equates the path/version-
dependent D017 envelopes or the direct/file D018 default variants.

### Current responsibility

The schema above remains the exact public case and artifact signature. The common
execution API also accepts a supplied float64 flow-direction vector within its
documented angle-consistency tolerance and evaluates that accepted vector without
rounding. The frozen schema does not encode those exact three values, so the
signature must not be treated as a complete-result cache key. The platform does
not provide a complete-result cache; each execution evaluates its accepted flow
vector. Summary CSV/VTP matching and every existing digest and fallback rule are
unchanged.

## Consequences

UI and documentation changes need not invalidate calculations, while geometry,
physical-model, shielding-algorithm, and effective-backend changes do. Each model
owns and increments its algorithm version and signature payload. A field,
normalization, or serialization change requires a schema-version increment,
legacy-match migration tests, and documented artifact precedence; silent changes
are prohibited.
