# Numerical conventions

## Units, arrays, and validation

- Internal physical quantities use SI units.
- Public case angles are degrees; internal trigonometry uses radians.
- Per-face scalars have shape `(n_faces,)`; per-face vectors have shape
  `(n_faces, 3)`.
- Central floating arrays are `float64`; component IDs are `int64`; shielding
  masks are boolean.
- NaN, infinity, numeric booleans, invalid shapes, overflowed derived state,
  degenerate geometry, and zero/negative normalization quantities are rejected
  at shared boundaries.

## STL flow direction and attitude

For resolved tangent angles:

```text
Vhat_stl = normalize([
    cos(alpha_t) cos(beta_t),
   -sin(beta_t) cos(alpha_t),
    sin(alpha_t) cos(beta_t),
])
```

Positive `alpha_t` points the freestream toward `+Z_stl`; positive `beta_t`
points it toward `-Y_stl`. `beta_sin` and included-angle/bank inputs resolve to
the same explicit vector before panel calculations. Reader domains are listed in
[Case files](../user-guide/case-files.md).
Canonical runtime resolution applies that same documented domain to both
physical models; in particular, `beta_tan` uses the principal open interval
(-90°, 90°) for both input angles.

## Loads and normalization

A model returns a local nondimensional traction coefficient vector per panel:

```text
C_face_stl = traction_coeff_stl * (area_m2 / Aref_m2)
C_total_stl = sum(C_face_stl)
```

Hypersonic traction is pressure-only `-Cp * normal_out_stl`. Sentman can include
a tangential/freestream contribution, so `Cp` is not the universal computation
contract.

## Frames, coefficients, and moments

The frozen STL-to-body axis mapping is `(-x_stl, +y_stl, -z_stl)`.

```text
CA = -Fx_body
CY =  Fy_body
CN = -Fz_body
```

`CD` and `CL` use a body-to-stability Y rotation by resolved `alpha_t`. Body
moment numerator is `(center_body - reference_body) × C_face_body`; roll, pitch,
and yaw components are divided by `Lref_Cl_m`, `Lref_Cm_m`, and `Lref_Cn_m`.
Component coefficients use the same global reference quantities as the total.

`theta_deg = acos(normal_out_stl · Vhat_stl)`. Hypersonic exposes its local
pressure coefficient as `cp`. FMF derives `normal_traction_coeff` and
`tangential_traction_coeff` from `traction_coeff_stl`; the tangential positive
direction is the normalized in-plane projection of `velocity_hat_stl`.
Ray-shielded panels have exact-zero traction.

Quantity-specific golden tolerances remain historical regression policy in
[Phase 1 tolerances](../history/migration/phase1/TOLERANCES.md); there is no
repository-wide default tolerance.
