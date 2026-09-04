# Coordinate and attitude conventions

FMF and Hypersonic use the coordinate and attitude calculations defined on this
page. It explains what each attitude representation means geometrically and how
all representations resolve to one freestream direction. Accepted input values
and ranges are listed in the
[Case files guide](../user-guide/case-files.md#attitude-modes). Required fields
and defaults are listed in the domain input references.

## Frames, direction, and angle units

The STL frame is the coordinate frame in which the input geometry is stored.
The resolved unit freestream-velocity direction is written as
$\hat{\boldsymbol V}_{\mathrm{STL}}=(V_x,V_y,V_z)$, or `Vhat_stl` /
`velocity_hat_stl` in field and API names. It points in the direction in which
the freestream travels, expressed in STL axes; it does not point upstream. At
zero attitude it is $+X_{\mathrm{STL}}$. The model-neutral
[ray-shielding method](ray-shielding.md#geometry-occlusion-method) traces in the
opposite, upstream direction.

The fixed STL-to-body axis mapping is

```math
(x_{\mathrm{body}},y_{\mathrm{body}},z_{\mathrm{body}})
=(-x_{\mathrm{STL}},+y_{\mathrm{STL}},-z_{\mathrm{STL}}).
```

All attitude definitions below are in the STL frame. Public case angles and
resolved-angle result fields are in degrees. Trigonometric functions in the
equations use radian arguments; input degrees are converted before evaluation,
and resolved `atan2` results are converted back to degrees.

Every `attitude_input` representation resolves to the same
$\hat{\boldsymbol V}_{\mathrm{STL}}$ and to the tangent angles $\alpha_t$ and
$\beta_t$ before panel calculation. The original pair of input angles is not
used directly after this resolution.

Here
$\operatorname{normalize}(\boldsymbol q)=\boldsymbol q/\lVert\boldsymbol q\rVert$.

## Tangent-angle input (`beta_tan`)

In this mode, `alpha_deg` is the tangent angle of attack $\alpha_t$, and
`beta_or_bank_deg` is the tangent sideslip angle $\beta_t$. For inputs in the
principal domain specified by [Case files](../user-guide/case-files.md#attitude-modes),

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

The principal input domain makes $V_x>0$, so the definitions can also be read
from the component ratios:

```math
\frac{V_z}{V_x}=\tan\alpha_t,
\qquad
\frac{-V_y}{V_x}=\tan\beta_t.
```

Positive $\alpha_t$ points the freestream toward $+Z_{\mathrm{STL}}$; positive
$\beta_t$ points it toward $-Y_{\mathrm{STL}}$.

## Sine-definition sideslip input (`beta_sin`)

In this mode, `alpha_deg` is a tangent angle of attack, denoted
$\alpha_{\mathrm{in}}$ to distinguish the input from the resolved result.
`beta_or_bank_deg` is the sine-definition sideslip $\beta_s$.

Define

```math
t=\tan\alpha_{\mathrm{in}},
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

using the nonnegative square root for $V_x$. Thus
$\sin\beta_s=-V_y$, while the X/Z components preserve
$V_z/V_x=\tan\alpha_{\mathrm{in}}$ whenever $V_x\ne0$. The resulting vector is
normalized to protect its unit length from floating-point roundoff.

The common resolved angles are then

```math
\alpha_t=\operatorname{atan2}(V_z,V_x),
\qquad
\beta_t=\operatorname{atan2}(-V_y,V_x).
```

For $|\sin\beta_s|<1$, resolved $\alpha_t$ equals the input tangent angle, but
$\beta_t$ is generally not equal to $\beta_s$. At
$|\sin\beta_s|=1$, the direction lies on the Y axis with $V_x=V_z=0$; that
direction contains no information about the input angle of attack, and the
resolved value is determined by the `atan2` definition rather than recovered
from $\alpha_{\mathrm{in}}$.

Only $\sin\beta_s$ enters the direction. Inputs with the same sine are therefore
equivalent: in particular, $\beta_s+360^\circ k$ and
$180^\circ-\beta_s+360^\circ k$ produce the same direction for any integer
$k$.

## Included-angle and bank input (`bank`)

In this mode, `alpha_deg` is the included angle $i$ measured from the
$+X_{\mathrm{STL}}$ axis, not a tangent angle of attack.
`beta_or_bank_deg` is the bank angle $\phi$ around that axis:

```math
\hat{\boldsymbol V}_{\mathrm{STL}}
=\begin{bmatrix}
\cos i\\
-\sin i\sin\phi\\
\sin i\cos\phi
\end{bmatrix}.
```

At $i=0^\circ$, the direction is exactly $+X_{\mathrm{STL}}$ and bank has no
effect. The zero-bank reference meridian is $+Z_{\mathrm{STL}}$: at
$\phi=0^\circ$, the direction is $(\cos i,0,\sin i)$, so a positive included
angle has its transverse component toward $+Z_{\mathrm{STL}}$.

Positive bank rotates that transverse component from $+Z_{\mathrm{STL}}$
toward $-Y_{\mathrm{STL}}$. Equivalently, it is a right-hand-rule positive
rotation about $+X_{\mathrm{STL}}$. Bank is 360-degree periodic,
$\hat{\boldsymbol V}(i,\phi+360^\circ k)=\hat{\boldsymbol V}(i,\phi)$; the
included angle is likewise evaluated periodically through its sine and cosine.
When $\sin i=0$, the direction lies on the X axis and bank is geometrically
immaterial.

## Resolved tangent angles

For every resolved unit direction
$\hat{\boldsymbol V}_{\mathrm{STL}}=(V_x,V_y,V_z)$, both domains use

```math
\alpha_t=\operatorname{atan2}(V_z,V_x),
\qquad
\beta_t=\operatorname{atan2}(-V_y,V_x).
```

When $V_x\ne0$, these definitions give
$\tan\alpha_t=V_z/V_x$ and $\tan\beta_t=-V_y/V_x$, while `atan2` retains the
quadrant. Input-angle names and resolved-angle names are intentionally distinct:
for example, `alpha_deg` in `bank` mode is the included angle $i$ and generally
is not resolved $\alpha_t$; `beta_or_bank_deg` in `beta_sin` mode is $\beta_s$
and generally is not resolved $\beta_t$.

The resolved $\alpha_t$ is also the angle used by the force-coefficient
stability-axis transformation. See
[Load and coefficient conventions](load-and-coefficient-conventions.md#stability-axis-force-coefficients).
