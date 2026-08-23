# Hypersonic Panel Methods

The Hypersonic domain evaluates pressure-only panel traction for
Newtonian-family flow models. The local load is `-cp` times the outward panel
normal; the shared engine
owns geometry scaling, shielding, integration, components, and artifacts.

## Surface equations

`windward_eq` accepts:

- `newtonian`;
- `modified_newtonian`;
- `tangent_wedge`;
- `tangent_cone`.

`leeward_eq` accepts:

- `shield`: zero leeward pressure;
- `prandtl_meyer`: expansion pressure/suction model.

A single selector applies to every STL. With multiple STL components, provide
exactly one semicolon-separated selector per component to choose equations
independently. Empty entries and mismatched counts are invalid.

## Pressure-model equations

### Common panel geometry and normalization

For each panel, define:

- $\hat{\boldsymbol V}$: unit flow direction in the STL frame;
- $\boldsymbol n_{\mathrm{out}}$: STL outward unit normal;
- $\boldsymbol n_{\mathrm{in}}=-\boldsymbol n_{\mathrm{out}}$: inward unit
  normal;
- $\mu=\boldsymbol n_{\mathrm{in}}\mathbin{\boldsymbol\cdot}
  \hat{\boldsymbol V}$: local incidence direction cosine;
- $\delta=\sin^{-1}\mu$: local panel turning angle.

The code classifies $\mu>0$ as windward and $\mu\leq0$ as leeward. Thus
$\delta$ is positive on windward panels and nonpositive on leeward panels. It
is a panel-local angle, not the whole-vehicle `alpha_deg`. It is also distinct
from the output normal-to-flow angle
`theta_deg` $=\cos^{-1}(\boldsymbol n_{\mathrm{out}}\mathbin{\boldsymbol\cdot}
\hat{\boldsymbol V})$; in degrees, `theta_deg` is $90^\circ+\delta$.

All pressure models use

```math
C_p
=
\frac{p-p_\infty}{\tfrac12\rho_\infty V_\infty^2}
=
\frac{2}{\gamma M_\infty^2}
\left(\frac{p}{p_\infty}-1\right),
```

where $\gamma$ is the specific-heat ratio, not the incidence cosine. `cp` is
the Hypersonic domain's local panel pressure-coefficient output. The model
returns local pressure-only traction

```math
\boldsymbol{\tau}_j=-C_{p,j}\boldsymbol n_{\mathrm{out},j},
\qquad
\Delta\boldsymbol C_j
=
\boldsymbol{\tau}_j\frac{A_j}{A_{\mathrm{ref}}}.
```

The shared integrator, not the model, applies $A_j/A_{\mathrm{ref}}$ exactly
once, sums $\boldsymbol C_{\mathrm{total,STL}}=\sum_j
\Delta\boldsymbol C_j$, and forms whole-vehicle force and moment coefficients.
Frame transformations and lever-arm moments occur only after these local panel
contributions have been formed. See
[Numerical conventions](../reference/numerical-conventions.md) for coordinate
transforms, coefficient signs, and moment normalization.

These are local, inviscid panel approximations for a calorically perfect gas
with constant $\gamma$; they are not general CFD. They omit boundary layers,
viscosity, heat transfer, real-gas chemistry, shock--shock and
shock--boundary-layer interactions, and coupled flow between neighboring
panels. Tangent methods estimate pressure from each panel's local angle rather
than solving a global three-dimensional flow field. `cp` remains a local
value until the common engine performs the area integration. The code's input
domain checks establish only that a selected relation can be evaluated; they do
not establish that its physical approximation is accurate for a particular
vehicle, Mach number, or flow regime.

The windward choices differ only in how they obtain this local $C_p$:
Newtonian uses impact momentum, Modified Newtonian scales it by a finite-Mach
stagnation cap, tangent wedge uses a local weak oblique shock, and tangent cone
uses local conical flow. The leeward choice either assigns zero pressure
coefficient or an isentropic expansion pressure. Geometry and whole-vehicle
integration are otherwise common.

### Newtonian

For a windward panel, the Newtonian impact approximation gives

```math
C_p=2\sin^2\delta=2\mu^2.
```

This represents the surface-normal momentum change of particles impacting the
panel. Mach number and $\gamma$ do not appear directly in this equation. The
implemented Newtonian plus leeward `shield` path consequently accepts any
positive Mach number, including subsonic values; input acceptance does not
claim that Newtonian hypersonic impact theory is physically valid there.

### Modified Newtonian

Modified Newtonian replaces the factor 2 with a stagnation-point cap:

```math
C_p=C_{p,\max}\sin^2\delta=C_{p,\max}\mu^2.
```

The current code obtains that cap from a normal shock followed by isentropic
deceleration of the post-shock flow:

```math
\frac{p_2}{p_\infty}
=1+\frac{2\gamma}{\gamma+1}\left(M_\infty^2-1\right),
\qquad
M_2^2
=
\frac{1+\tfrac12(\gamma-1)M_\infty^2}
{\gamma M_\infty^2-\tfrac12(\gamma-1)},
```

```math
\frac{p_{0,2}}{p_2}
=
\left(1+\frac{\gamma-1}{2}M_2^2\right)^{\frac{\gamma}{\gamma-1}},
\qquad
\frac{p_{0,2}}{p_\infty}
=
\frac{p_2}{p_\infty}\frac{p_{0,2}}{p_2},
```

```math
C_{p,\max}
=
\frac{2}{\gamma M_\infty^2}
\left(\frac{p_{0,2}}{p_\infty}-1\right).
```

Here $p_{0,2}$ is the total pressure obtained by bringing the flow immediately
behind the normal shock to rest isentropically. This cap is also the endpoint
used by the implementation-defined detached continuation below.

### Tangent wedge

Tangent wedge treats each windward panel as a local two-dimensional wedge of
turning angle $\delta$. An attached shock satisfies the
$\delta$ – $\beta$ – $M$ relation

```math
\tan\delta
=
2\cot\beta
\frac{M_\infty^2\sin^2\beta-1}
{M_\infty^2\left(\gamma+\cos2\beta\right)+2}.
```

The implementation selects the weak attached solution for shock angle $\beta$.
It then applies the normal-shock pressure jump to the shock-normal Mach number:

```math
M_{n1}=M_\infty\sin\beta,
\qquad
\frac{p_2}{p_\infty}
=1+\frac{2\gamma}{\gamma+1}\left(M_{n1}^2-1\right),
```

```math
C_p
=
\frac{2}{\gamma M_\infty^2}
\left(\frac{p_2}{p_\infty}-1\right).
```

This is a panel-by-panel pressure estimate: an attached solution on one panel
does not propagate a downstream state to its neighbors and does not account for
intersections between the locally inferred shocks.

Above the maximum attached turning angle, this attached oblique-shock branch is
replaced by the [implementation-defined continuation](#detached-branch-continuation).

### Tangent cone

Tangent cone interprets each windward panel's $\delta$ as a local circular-cone
half-angle. It does not reconstruct the surface curvature or a physical local
cone axis. For a candidate conical shock angle, the code first obtains the
immediate post-shock state from oblique-shock relations, then integrates the
Taylor--Maccoll system toward the cone. Velocity is nondimensionalized as

```math
v=\frac{V}{V_{\max}}
=
\left[1+\frac{2}{(\gamma-1)M^2}\right]^{-1/2}.
```

With radial and polar components $v_r$ and $v_\theta$, the implemented system
is

```math
\frac{dv_r}{d\theta}=v_\theta,
```

```math
\frac{dv_\theta}{d\theta}
=
\frac{v_rv_\theta^2-a\left(2v_r+v_\theta\cot\theta\right)}
{a-v_\theta^2},
\qquad
a=\frac{\gamma-1}{2}\left(1-v_r^2-v_\theta^2\right).
```

The location where $v_\theta=0$ is the cone surface. If $M_2,p_2$ are the
immediate post-shock values and $M_c,p_c$ are the surface values, the pressure
conversion is

```math
\frac{p_c}{p_2}
=
\left[
\frac{1+\tfrac12(\gamma-1)M_2^2}
{1+\tfrac12(\gamma-1)M_c^2}
\right]^{\frac{\gamma}{\gamma-1}},
\qquad
C_{p,c}
=
\frac{2}{\gamma M_\infty^2}
\left(\frac{p_c}{p_\infty}-1\right).
```

The implementation evaluates candidate shock angles, retains the attached weak
branch of the cone-angle relation for $C_p$, and interpolates that relation for
panel angles. Beyond its maximum attached cone angle it uses the continuation
defined below, rather than an attached Taylor--Maccoll solution. Each panel is
evaluated independently, so this local cone analogy does not recover the
configuration's actual three-dimensional conical-flow topology.

### Leeward shield

For `leeward_eq=shield`,

```math
C_p=0.
```

This is a leeward surface-pressure equation. It is separate from
`shielding_on=1`, which performs ray-occlusion geometry processing and forces a
panel hidden by another face to zero load regardless of its pressure equation.
See [Shielding and parallel execution](../user-guide/shielding-and-parallel.md).

### Prandtl–Meyer expansion

Leeward panels have $\delta<0$ except at the zero-incidence boundary. The
Prandtl--Meyer function for $M>1$ is

```math
\nu(M)
=
\sqrt{\frac{\gamma+1}{\gamma-1}}
\tan^{-1}\left[
\sqrt{\frac{\gamma-1}{\gamma+1}\left(M^2-1\right)}
\right]
-\tan^{-1}\sqrt{M^2-1}.
```

The implementation's sign convention is

```math
\nu_2=\nu(M_\infty)-\delta,
\qquad
\nu(M_2)=\nu_2.
```

Because $\delta<0$, the Prandtl--Meyer angle increases by $|\delta|$. The code
monotonically inverts this relation numerically, then uses the isentropic
pressure ratio

```math
\frac{p_2}{p_\infty}
=
\left[
\frac{1+\tfrac12(\gamma-1)M_2^2}
{1+\tfrac12(\gamma-1)M_\infty^2}
\right]^{-\frac{\gamma}{\gamma-1}},
\qquad
C_p
=
\frac{2}{\gamma M_\infty^2}
\left(\frac{p_2}{p_\infty}-1\right).
```

The finite-Mach expansion limit and vacuum-pressure lower bound are

```math
\nu_{\max}
=
\frac{\pi}{2}
\left(\sqrt{\frac{\gamma+1}{\gamma-1}}-1\right),
\qquad
C_{p,\mathrm{vac}}=-\frac{2}{\gamma M_\infty^2}.
```

Expansion states below $\nu_{\max}$ are inverted numerically; larger requested
turns use the vacuum coefficient, which is also enforced as the lower bound.
This is an isentropic expansion model and does not represent separated flow.

### Detached-branch continuation

Tangent wedge and tangent cone share an implementation-defined continuation
after their respective attached weak branches end. Let $\delta_{\max}$ be the
maximum attached turning angle and $C_{p,\mathrm{crit}}$ its pressure
coefficient. The current code uses

```math
w
=
\mathrm{clip}\left(
\frac{\sin^2\delta-\sin^2\delta_{\max}}
{1-\sin^2\delta_{\max}},
0,1
\right),
```

```math
C_p
=
C_{p,\mathrm{crit}}
+\left(C_{p,\max}-C_{p,\mathrm{crit}}\right)w.
```

This preserves continuity with $C_p(\delta_{\max})=C_{p,\mathrm{crit}}$ and
reaches $C_p(90^\circ)=C_{p,\max}$. It is not a standard attached
oblique-shock solution or an attached Taylor--Maccoll solution, and it does not
directly solve a detached shock field. It is the current code's
implementation-defined bridge to the Modified-Newtonian cap.

### Representative angular response

Both illustrative angular responses below fix
$\hat{\boldsymbol V}=[1,0,0]$ and vary the panel normal as
$\boldsymbol n_{\mathrm{in}}=[\sin\delta,\cos\delta,0]$. Therefore
$\mu=\boldsymbol n_{\mathrm{in}}\mathbin{\boldsymbol\cdot}
\hat{\boldsymbol V}=\sin\delta$, and
$\delta=\mathtt{theta\_deg}-90^\circ$. At $\delta=-90^\circ$ the panel faces
directly away from the flow, $\delta=0^\circ$ is grazing incidence, and at
$\delta=+90^\circ$ it faces directly into the flow.

#### Windward response

![Windward Hypersonic pressure coefficients versus local panel angle at Mach 6](../assets/plots/hypersonic-windward-cp-vs-angle.svg)

**Figure.** Representative local response at $M_\infty=6$ and $\gamma=1.4$, with no ray
shielding and `leeward_eq=shield`. Solid Tangent segments are attached weak
branches; dashed Tangent segments are implementation-defined continuations to
the Modified-Newtonian cap. These curves show the local response of one
isolated, unshielded panel before multiplication by $A_j/A_{\mathrm{ref}}$.
They are not whole-vehicle aerodynamic polars. The plotted $C_p$ values are
local panel coefficients, not whole-vehicle force coefficients.

Newtonian reaches $C_p=2$ at $\delta=90^\circ$. Modified Newtonian retains the
same $\sin^2\delta$ shape but scales it by the finite-Mach $C_{p,\max}$.
Tangent Wedge and Tangent Cone use their local shock relations at small and
moderate angles. After each model's computed attachment limit, the current
implementation-defined continuation connects its critical value to
$C_{p,\max}$; the dashed portions are not detached-shock solutions. Agreement
or separation among these curves does not establish a universal ranking of
model accuracy.

#### Leeward response

![Leeward Hypersonic pressure coefficients versus local panel angle at Mach 6](../assets/plots/hypersonic-leeward-cp-vs-angle.svg)

**Figure.** Representative local response at $M_\infty=6$ and $\gamma=1.4$, with
`windward_eq=newtonian` and no ray shielding. The leeward `shield` equation
assigns $C_p=0$, while Prandtl--Meyer gives expansion suction; the vacuum
pressure coefficient is the lower bound. Ray shielding is a separate geometry
operation. These curves show the local response of one isolated, unshielded
panel before multiplication by $A_j/A_{\mathrm{ref}}$. They are not
whole-vehicle aerodynamic polars. The plotted $C_p$ values are local panel
coefficients, not whole-vehicle force coefficients.

The `leeward_eq=shield` selector is only the zero-pressure equation for a
leeward-oriented, otherwise active panel. In contrast, `shielding_on=1` performs
ray-occlusion testing and forces any geometrically hidden panel to zero load,
independently of whether its selected leeward equation is `shield` or
`prandtl_meyer`.

## Flow inputs and constraints

`Mach` must be positive and `gamma` must be greater than 1. Modified Newtonian,
tangent wedge, tangent cone, and Prandtl–Meyer require `Mach > 1`. The implemented
Newtonian + leeward `shield` path accepts positive subsonic Mach because its
formula does not use a supersonic relation; that acceptance should not be read as
a claim that the hypersonic approximation is physically suitable there.

Tangent-wedge and tangent-cone paths retain their accepted detached/limited
branches, and Prandtl–Meyer retains its bounded numerical inversion. These panel
approximations do not model viscous effects, full shock interaction, or general
three-dimensional CFD physics. Select them only within a justified engineering
approximation regime.

See the [Hypersonic input reference](../reference/hypersonic-input.md) and
[numerical conventions](../reference/numerical-conventions.md).

## References

1. Ames Research Staff, *Equations, Tables, and Charts for Compressible Flow*,
   [NACA Report 1135](https://ntrs.nasa.gov/citations/19930091059), 1953.
   Normal/oblique shocks, isentropic flow, Prandtl--Meyer expansion, and conical
   flow relations.
2. Lees, L., *Hypersonic Flow*, IAS Preprint No. 554, 1955. Newtonian and
   hypersonic local-surface approximations.
3. Taylor, G. I. and Maccoll, J. W., “The Air Pressure on a Cone Moving at High
   Speeds—I,” *Proceedings of the Royal Society A*, Vol. 139, No. 838,
   pp. 278–297, 1933, [DOI 10.1098/rspa.1933.0017](https://doi.org/10.1098/rspa.1933.0017).
4. Taylor, G. I. and Maccoll, J. W., “The Air Pressure on a Cone Moving at High
   Speeds—II,” *Proceedings of the Royal Society A*, Vol. 139, No. 838,
   pp. 298–311, 1933, [DOI 10.1098/rspa.1933.0018](https://doi.org/10.1098/rspa.1933.0018).
5. Armstrong, W. O. and Wells, W. R., *Tables of Aerodynamic Coefficients
   Obtained from Developed Newtonian Expressions for Complete and Partial Conic
   and Spheric Bodies at Combined Angles of Attack and Sideslip with Some
   Comparisons with Hypersonic Experimental Data*,
   [NASA TR R-127](https://ntrs.nasa.gov/citations/19630006549), 1962.
   Supporting Newtonian and modified-Newtonian reference.
