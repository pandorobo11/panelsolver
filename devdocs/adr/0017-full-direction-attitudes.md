# ADR 0017: Full-direction attitudes and explicit stability axes

- Status: Accepted (user-directed specification)
- Date: 2026-09-07
- Supersedes: attitude domains and resolved-angle output contracts under ADR 0008;
  common-case signature schema under ADR 0005; the ResolvedAttitude fields under
  ADR 0014. Physical model equations, force signs and reference normalization
  remain unchanged.

## Decision

All modes resolve directly to an immutable unit STL freestream vector. Input
alpha is finite and periodic. Both beta modes accept sideslip in [-90, 90]
including endpoints. Bank retains finite periodic included and bank angles.
Original numeric inputs are preserved separately from resolved state.

For alpha a and sideslip b, beta_sin is
(cos(a) cos(b), -sin(b), sin(a) cos(b)). Beta_tan normalizes
(cos(a) cos(b), -abs(cos(a)) sin(b), sin(a) cos(b)). Positive sideslip
therefore always points toward -Y, including backwards flow. Bank remains
(cos(i), -sin(i) sin(phi), sin(i) cos(phi)). Angles are degrees at the boundary.

Tangent input with both cosines exactly zero is rejected: the direction is
underdetermined. Other tangent poles use the forward-map extension, even when
the original pair cannot be recovered. Exact quadrants are evaluated exactly;
adjacent representable angles are not snapped to the boundary. Scale before
normalization so a tiny but nonzero tangent vector remains valid.

Every mode derives alpha_stability_deg = atan2(Vz, Vx), canonicalized to (-180, 180].
If hypot(Vx, Vz) <= 64 * float64 epsilon for the normalized direction, use 0.
Do not modify the physical flow vector to choose this representative axis.
No source/status field or resolved sine-sideslip field is exported. Original
angles and the output vector permit interpretation of the documented fallback.
A continuous stability frame across all approaches to lateral flow is impossible.

Replace alpha_t_deg_resolved and beta_t_deg_resolved in CSV/VTP with
alpha_stability_deg and velocity_hat_x_stl, velocity_hat_y_stl,
velocity_hat_z_stl. CSV retains its original input columns. VTP adds alpha_deg
and beta_or_bank_deg field data containing the original finite numeric inputs.
The public ResolvedAttitude exposes velocity_hat_stl, alpha_deg,
beta_or_bank_deg, input_mode and derived alpha_stability_deg. The direct
constructor treats the supplied direction as authoritative; original angle
fields provide provenance. Both solve entry points use the same derived frame.

Core retains only the stability angle in the common integration case. It
validates that angle against the authoritative execution direction; it must not
reconstruct a physical vector from two projected tangent angles.

## Signatures and migration

Increment panelsolver.case to schema version 2. Replace common_case's
alpha_t_deg and beta_t_deg with alpha_stability_deg and velocity_hat_stl
(the exact three evaluated float64 components). Other envelope sections retain
their definitions. Old digests remain frozen historical evidence and must not
automatically match new artifacts. Manual VTP inspection remains available.
No rounding-based equivalence or complete-result caching is introduced.

This is an intentional output/API breaking change. Consumers must migrate old
resolved-angle fields to the direction and stability-angle fields. Existing
beta_sin inputs outside [-90, 90] now fail validation and must be expressed
using an in-range sideslip and appropriate alpha. Previous forwards-domain
physical coefficients remain subject to the existing regression tolerances;
last-bit trigonometric differences and exact-axis residual removal are expected.
Formerly rejected backwards/pole inputs become supported, except the tangent
zero-direction corner. Near-lateral stability CD/CL may change due to the
explicit common fallback; body-axis forces and moments do not depend on it.

## Verification

Test all modes, backwards directions, exact/adjacent poles, original-angle
preservation, frame fallback threshold, periodicity and invalid numeric inputs.
Verify FMF and Hypersonic solves, CSV/VTP semantic fields, current artifact
matching, and rejection of v1 automatic matches. Retain historical numerical
fixtures and coefficient tolerances. Run the standard local validation runner.
