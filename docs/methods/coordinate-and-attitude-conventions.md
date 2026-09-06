# Coordinate and attitude conventions

FMF and Hypersonic use the coordinate and attitude calculations defined on this
page. It explains what each attitude representation means geometrically and how
all representations resolve to one freestream direction. Accepted input values
and ranges are listed in the
[Case files guide](../inputs/case-files.md#attitude-modes). Required fields
and defaults are listed in the domain input references.

## Frames, direction, and angle units

The STL frame is the coordinate frame in which the input geometry is stored.
The resolved unit freestream-velocity direction is written as
$\hat{\boldsymbol V}_{\mathrm{STL}}=(V_x,V_y,V_z)$, or `Vhat_stl` /
`velocity_hat_stl` in field and API names. It points in the direction in which
the freestream travels, expressed in STL axes. At zero attitude it is
$+X_{\mathrm{STL}}$.

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
$\beta_t$ used for panel calculation.

Here
$\operatorname{normalize}(\boldsymbol q)=\boldsymbol q/\lVert\boldsymbol q\rVert$.

## Tangent-angle input (`beta_tan`)

In this mode, `alpha_deg` is the tangent angle of attack $\alpha_t$, and
`beta_or_bank_deg` is the tangent sideslip angle $\beta_t$. For inputs in the
principal domain specified by [Case files](../inputs/case-files.md#attitude-modes),

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

With $t=\tan\alpha_{\mathrm{in}}$ and $s=\sin\beta_s$, the unit direction is

```math
\hat{\boldsymbol V}_{\mathrm{STL}}
=\operatorname{normalize}\!\begin{bmatrix}
\sqrt{\dfrac{1-s^2}{1+t^2}}\\
-s\\
t\sqrt{\dfrac{1-s^2}{1+t^2}}
\end{bmatrix}.
```

For $|\sin\beta_s|<1$, resolved $\alpha_t$ equals the input tangent angle, while
$\beta_t$ follows the [resolved-angle definition](#resolved-tangent-angles).
At $|\sin\beta_s|=1$, the flow lies on the Y axis and the angle of attack is
geometrically undetermined. Panel Solver returns $\alpha_t=0^\circ$ and
$\beta_t=+90^\circ$ for $\sin\beta_s=1$, or $-90^\circ$ for $\sin\beta_s=-1$.

## Included-angle and bank input (`bank`)

In this mode, `alpha_deg` is the included angle $i$ measured from the
$+X_{\mathrm{STL}}$ axis.
`beta_or_bank_deg` is the bank angle $\phi$ around that axis:

```math
\hat{\boldsymbol V}_{\mathrm{STL}}
=\begin{bmatrix}
\cos i\\
-\sin i\sin\phi\\
\sin i\cos\phi
\end{bmatrix}.
```

The zero-bank reference meridian is $+Z_{\mathrm{STL}}$: at
$\phi=0^\circ$, the direction is $(\cos i,0,\sin i)$, so a positive included
angle has its transverse component toward $+Z_{\mathrm{STL}}$.

Positive bank rotates that transverse component from $+Z_{\mathrm{STL}}$
toward $-Y_{\mathrm{STL}}$. Equivalently, it is a right-hand-rule positive
rotation about $+X_{\mathrm{STL}}$.
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
quadrant.

The resolved $\alpha_t$ is also the angle used by the force-coefficient
stability-axis transformation. See
[Load and coefficient conventions](load-and-coefficient-conventions.md#stability-axis-force-coefficients).
