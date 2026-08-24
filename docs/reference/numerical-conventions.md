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

## Coordinate frames

The STL frame is the coordinate frame in which the input geometry is stored.
This document writes the resolved unit freestream-velocity direction as
$\hat{\boldsymbol V}_{\mathrm{STL}}=(V_x,V_y,V_z)$, or `Vhat_stl` /
`velocity_hat_stl` in field and API names. It points in the direction in which
the freestream travels, expressed in STL axes; it is not the direction pointing
upstream. At zero attitude it points along $+X_{\mathrm{STL}}$.

The frozen STL-to-body axis mapping is

```math
(x_{\mathrm{body}},y_{\mathrm{body}},z_{\mathrm{body}})
=(-x_{\mathrm{STL}},+y_{\mathrm{STL}},-z_{\mathrm{STL}}).
```

All attitude definitions below are in the STL frame. The FMF and Hypersonic
domains use the same shared attitude resolver and therefore the same axes,
signs, and transformations.

## Attitude conventions

Public attitude values are supplied in degrees. The equations below use radian
arguments for trigonometric functions. Each `attitude_input` representation is
first resolved to the same $\hat{\boldsymbol V}_{\mathrm{STL}}$ and to the
resolved tangent angles $\alpha_t$ and $\beta_t$; panel calculations do not use
the original representation directly. This section is the canonical definition
of those axes, signs, angle domains, and transformations.
[Case files](../user-guide/case-files.md) explains how to choose an input
representation.

Here $\operatorname{normalize}(\boldsymbol q)=\boldsymbol q/\lVert\boldsymbol q\rVert$.

### Tangent-angle input (`beta_tan`)

In this mode, `alpha_deg` is the tangent angle of attack $\alpha_t$ and
`beta_or_bank_deg` is the tangent sideslip angle $\beta_t$. Both inputs must be
strictly between -90° and 90°.

```math
\hat{\boldsymbol V}_{\mathrm{STL}}
=\operatorname{normalize}\!\begin{bmatrix}
\cos\alpha_t\cos\beta_t\\
-\sin\beta_t\cos\alpha_t\\
\sin\alpha_t\cos\beta_t
\end{bmatrix}
=\operatorname{normalize}\!\begin{bmatrix}
1\\-\tan\beta_t\\\tan\alpha_t
\end{bmatrix}.
```

The principal input range makes $V_x>0$, so the definitions can also be read
directly from the component ratios:

```math
\frac{V_z}{V_x}=\tan\alpha_t,
\qquad
\frac{-V_y}{V_x}=\tan\beta_t.
```

Positive $\alpha_t$ points the freestream toward $+Z_{\mathrm{STL}}$; positive
$\beta_t$ points it toward $-Y_{\mathrm{STL}}$.

### Sine-definition sideslip input (`beta_sin`)

In this mode, `alpha_deg` is a tangent angle of attack, denoted $\alpha_{\rm in}$
here to distinguish the input from the resolved result.
`beta_or_bank_deg` is the sine-definition sideslip $\beta_s$. The allowed range
is $-90^\circ<\alpha_{\rm in}<90^\circ$; $\beta_s$ may be any finite angle.

Define

```math
t=\tan\alpha_{\rm in},
\qquad
s=\sin\beta_s.
```

The unit direction is defined by

```math
V_y=-s,
\qquad
V_x=\sqrt{\frac{1-s^2}{1+t^2}},
\qquad
V_z=tV_x,
```

with the nonnegative square root for $V_x$. Thus the sideslip definition is
$\sin\beta_s=-V_y$, while the X/Z components preserve the input tangent-angle
relation $V_z/V_x=\tan\alpha_{\rm in}$ whenever $V_x\ne0$. The implementation
normalizes this mathematically unit-length vector to protect against floating-
point roundoff.

The common resolved angles are then

```math
\alpha_t=\operatorname{atan2}(V_z,V_x),
\qquad
\beta_t=\operatorname{atan2}(-V_y,V_x).
```

For $|\sin\beta_s|<1$, the resolved $\alpha_t$ equals the input tangent angle;
$\beta_t$ is generally not equal to $\beta_s$. At $|\sin\beta_s|=1$, the
direction lies on the Y axis, $V_x=V_z=0$, so the direction contains no
information about the input angle of attack.

Only $\sin\beta_s$ is used. Consequently, inputs with the same sine produce the
same direction: in particular, $\beta_s+360^\circ k$ and
$180^\circ-\beta_s+360^\circ k$ are equivalent for any integer $k$.

### Included angle / bank input (`bank`)

In this mode, `alpha_deg` is the included angle $i$ measured from the
$+X_{\mathrm{STL}}$ axis, not a tangent angle of attack.
`beta_or_bank_deg` is the bank angle $\phi$ around that axis. Both inputs may be
any finite angle.

```math
\hat{\boldsymbol V}_{\mathrm{STL}}
=\begin{bmatrix}
\cos i\\
-\sin i\sin\phi\\
\sin i\cos\phi
\end{bmatrix}.
```

At $i=0^\circ$, the result is exactly
$\hat{\boldsymbol V}_{\mathrm{STL}}=+X_{\mathrm{STL}}$ and bank has no effect.
The zero-bank reference meridian is $+Z_{\mathrm{STL}}$: at
$\phi=0^\circ$, the vector is $(\cos i,0,\sin i)$, so a positive included
angle has its transverse component toward $+Z_{\mathrm{STL}}$.

Positive bank rotates that transverse component from $+Z_{\mathrm{STL}}$
toward $-Y_{\mathrm{STL}}$. Equivalently, it is a right-hand-rule positive
rotation about $+X_{\mathrm{STL}}$. Bank is 360° periodic,
$\hat{\boldsymbol V}(i,\phi+360^\circ k)=\hat{\boldsymbol V}(i,\phi)$; the
finite included-angle input is likewise evaluated periodically by its sine and
cosine. When $\sin i=0$, the direction lies on the X axis and bank is
geometrically immaterial.

### Resolved tangent angles

For any resolved unit direction
$\hat{\boldsymbol V}_{\mathrm{STL}}=(V_x,V_y,V_z)$, the tangent angles used by
the common numerical pipeline are

```math
\alpha_t=\operatorname{atan2}(V_z,V_x),
\qquad
\beta_t=\operatorname{atan2}(-V_y,V_x).
```

The `atan2` results are converted to degrees in the resolved fields. When
$V_x\ne0$, these definitions give
$\tan\alpha_t=V_z/V_x$ and $\tan\beta_t=-V_y/V_x$ while retaining the quadrant
through `atan2`. Input-mode names and resolved-angle names are distinct: most
notably, `alpha_deg` in `bank` mode is the included angle $i$, and generally is
not the resolved tangent angle $\alpha_t$.

## Loads and normalization

A model returns a local nondimensional traction coefficient vector per panel:

```text
C_face_stl = traction_coeff_stl * (area_m2 / Aref_m2)
C_total_stl = sum(C_face_stl)
```

Hypersonic traction is pressure-only `-Cp * normal_out_stl`. Sentman can include
a tangential/freestream contribution, so `Cp` is not the universal computation
contract.

## Coefficients and moments

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
