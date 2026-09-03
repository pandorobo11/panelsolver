# Load and coefficient conventions

This page defines the model-neutral conventions for local panel loads, common
force/moment integration, and aggregate coefficients. The
[FMF solver page](../solvers/fmf.md) owns Sentman physics, and the
[Hypersonic solver page](../solvers/hypersonic.md) owns pressure-model physics.
Result association, shape, and stored dtype remain in the
[VTP reference](../results/vtp.md).

## Local traction and panel contributions

For panel $j$, a physical model returns a local nondimensional traction
coefficient vector $\boldsymbol\tau_{j,\mathrm{STL}}$, named
`traction_coeff_stl`. It is expressed in STL axes and does not yet include the
panel area or reference-area weighting.

The common integrator forms the per-panel force-coefficient contribution
`C_face_stl` as

```math
\boldsymbol C_{\mathrm{face},j,\mathrm{STL}}
=
\boldsymbol\tau_{j,\mathrm{STL}}
\frac{A_j}{A_{\mathrm{ref}}},
```

then sums the contributions:

```math
\boldsymbol C_{\mathrm{total},\mathrm{STL}}
=\sum_j\boldsymbol C_{\mathrm{face},j,\mathrm{STL}}.
```

Thus `traction_coeff_stl` and `C_face_stl` are not interchangeable. The former
is the model's local traction coefficient; the latter already contains exactly
one factor of `area_m2 / Aref_m2` and is the value summed for force and used for
moment integration. Do not multiply `C_face_stl` by panel area again.

A scalar pressure coefficient is not the universal computation contract.
Hypersonic local traction is pressure-only, but Sentman can also contribute
tangential load. The shared boundary therefore retains the complete traction
vector. Model-specific `cp`, `normal_traction_coeff`, and
`tangential_traction_coeff` are interpreted on their solver pages and in the
[VTP reference](../results/vtp.md#model-specific-cell-data); they are not
substitutes for the common vector.

Ray shielding may set a panel's complete local traction, and therefore its
`C_face_stl`, to exact zero. See
[Ray shielding](ray-shielding.md).

## Body-axis force coefficients

The total STL-frame force coefficient is transformed to body axes with the
frozen STL-to-body mapping defined in
[Coordinate and attitude conventions](coordinate-and-attitude-conventions.md#frames-direction-and-angle-units):

```math
\boldsymbol C_{\mathrm{body}}
=\operatorname{STLToBody}(\boldsymbol C_{\mathrm{total},\mathrm{STL}}).
```

Writing its components as $(C_{X,\mathrm{body}},C_{Y,\mathrm{body}},
C_{Z,\mathrm{body}})$, the public body-axis coefficients are

```math
C_A=-C_{X,\mathrm{body}},
\qquad
C_Y=C_{Y,\mathrm{body}},
\qquad
C_N=-C_{Z,\mathrm{body}}.
```

`CA` is axial force, `CY` is side force, and `CN` is normal force with these
fixed signs.

## Stability-axis force coefficients

Drag and lift use the resolved tangent angle of attack $\alpha_t$, not
necessarily the original `alpha_deg` input. The complete attitude resolution is
defined in
[Coordinate and attitude conventions](coordinate-and-attitude-conventions.md#resolved-tangent-angles).

The body-to-stability transformation is the right-handed rotation about
$+Y_{\mathrm{body}}$:

```math
\boldsymbol C_{\mathrm{stability}}
=
\begin{bmatrix}
\cos\alpha_t & 0 & \sin\alpha_t\\
0 & 1 & 0\\
-\sin\alpha_t & 0 & \cos\alpha_t
\end{bmatrix}
\boldsymbol C_{\mathrm{body}}.
```

The public stability-axis coefficients are

```math
C_D=-C_{X,\mathrm{stability}},
\qquad
C_L=-C_{Z,\mathrm{stability}}.
```

Equivalently,

```math
C_D
=-(C_{X,\mathrm{body}}\cos\alpha_t
+C_{Z,\mathrm{body}}\sin\alpha_t),
```

```math
C_L
=C_{X,\mathrm{body}}\sin\alpha_t
-C_{Z,\mathrm{body}}\cos\alpha_t.
```

## Moment coefficients

The configured moment reference point is supplied in STL coordinates. Both it
and each face center are transformed to body coordinates before the lever-arm
cross product. The body-frame, area-normalized moment numerator is

```math
\overline{\boldsymbol C}_{M,\mathrm{body}}
=
\sum_j
\left(
\boldsymbol r_{j,\mathrm{body}}
-\boldsymbol r_{\mathrm{ref},\mathrm{body}}
\right)
\times
\boldsymbol C_{\mathrm{face},j,\mathrm{body}}.
```

It has units of length because the force contribution is dimensionless. Its
body X, Y, and Z components are normalized by the configured axis-specific
reference lengths:

```math
C_l=\frac{\overline C_{M,X,\mathrm{body}}}{L_{\mathrm{ref},Cl}},
\qquad
C_m=\frac{\overline C_{M,Y,\mathrm{body}}}{L_{\mathrm{ref},Cm}},
\qquad
C_n=\frac{\overline C_{M,Z,\mathrm{body}}}{L_{\mathrm{ref},Cn}}.
```

These are the public `Cl`, `Cm`, and `Cn` roll-, pitch-, and yaw-moment
coefficients. Input units and validity for the reference point, `Aref_m2`, and
the three reference lengths are owned by the
[FMF input reference](fmf-input.md) and
[Hypersonic input reference](hypersonic-input.md).

## Total and component coefficients

A component result sums only the faces assigned to that STL component, then
applies the same transforms and coefficient definitions as the total. It uses
the case's global reference area, global moment reference point, and global
`Lref_Cl_m`, `Lref_Cm_m`, and `Lref_Cn_m`; a component is not independently
renormalized. Consequently, component force and moment coefficients sum to the
corresponding total coefficients, within the numerical tolerance appropriate to
the selected model.

## Common panel angle

The common geometric diagnostic `theta_deg` is the angle between the outward
STL-frame panel normal and the resolved freestream direction:

```math
\theta
=
\operatorname{acos}
\left(
\boldsymbol n_{\mathrm{out},\mathrm{STL}}
\mathbin{\boldsymbol\cdot}
\hat{\boldsymbol V}_{\mathrm{STL}}
\right),
```

reported in degrees from 0 through 180. It is not a force contribution and is
not summed. Its VTP representation is defined in the
[VTP reference](../results/vtp.md#common-cell-data); model-specific use is
explained on the solver pages.
