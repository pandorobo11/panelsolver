# Hypersonic Panel Methods

The Hypersonic domain evaluates pressure-only panel traction using
Newtonian-family flow models. Choose windward and leeward pressure equations
for the surfaces in your case.

## Surface equations

`windward_eq` accepts:

- `newtonian`;
- `modified_newtonian`;
- `tangent_wedge`;
- `tangent_cone`.

`leeward_eq` accepts:

- `shield`: zero leeward pressure coefficient (`Cp = 0`);
- `prandtl_meyer`: expansion pressure/suction model.

A single selector applies to every STL. With multiple STL components, provide
exactly one semicolon-separated selector per component to choose equations
independently. Empty entries and mismatched counts are invalid.

## Pressure-model equations

### Panel geometry and local pressure convention

For each panel, define:

- $\hat{\boldsymbol V}$: unit flow direction in the STL frame;
- $\boldsymbol n_{\mathrm{out}}$: STL outward unit normal;
- $\boldsymbol n_{\mathrm{in}}=-\boldsymbol n_{\mathrm{out}}$: inward unit
  normal;
- $\mu=\boldsymbol n_{\mathrm{in}}\mathbin{\boldsymbol\cdot}
  \hat{\boldsymbol V}$: local incidence direction cosine;
- $\delta=\sin^{-1}\mu$: local panel turning angle.

Panels with $\mu>0$ are windward ($\delta>0$); panels with $\mu\leq0$ are
leeward ($\delta\leq0$). The output normal-to-flow angle is
$\mathtt{theta\_deg}=\cos^{-1}(\boldsymbol n_{\mathrm{out}}\mathbin{\boldsymbol\cdot}
\hat{\boldsymbol V})$, or $90^\circ+\delta$ when expressed in degrees.

All pressure models use

```math
C_p
=
\frac{p-p_\infty}{\tfrac12\rho_\infty V_\infty^2}
=
\frac{2}{\gamma M_\infty^2}
\left(\frac{p}{p_\infty}-1\right),
```

where $\gamma$ is the specific-heat ratio. The local panel pressure coefficient
is stored as `cp` and gives the traction

```math
\boldsymbol{\tau}_j=-C_{p,j}\boldsymbol n_{\mathrm{out},j}.
```

Panel-area weighting, force/moment integration, and coefficient signs are
specified in [Load and coefficient conventions](../reference/load-and-coefficient-conventions.md).

The windward choices differ only in how they obtain this local $C_p$:
Newtonian uses impact momentum, Modified Newtonian scales it by a finite-Mach
stagnation cap, tangent wedge uses a local weak oblique shock, and tangent cone
uses local conical flow. The leeward choice either assigns zero pressure
coefficient or an isentropic expansion pressure. Geometry and whole-vehicle
integration are the same for every choice.

### Newtonian

For a windward panel, the Newtonian impact approximation gives

```math
C_p=2\sin^2\delta=2\mu^2.
```

This represents the surface-normal momentum change of particles impacting the
panel. The coefficient depends only on local incidence.

### Modified Newtonian

Modified Newtonian replaces the factor 2 with a stagnation-point cap:

```math
C_p=C_{p,\max}\sin^2\delta=C_{p,\max}\mu^2.
```

The implementation obtains that cap from a normal shock followed by isentropic
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

Above the maximum attached turning angle, this attached oblique-shock branch is
replaced by the [implementation-defined continuation](#detached-branch-continuation).

### Tangent cone

Tangent cone interprets each windward panel's $\delta$ as a local circular-cone
half-angle. For a candidate conical shock angle, the code first obtains the
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
defined below.

### Leeward shield

For `leeward_eq=shield`,

```math
C_p=0.
```

This sets surface pressure to freestream pressure, $p=p_\infty$.
The separate [`shielding_on` setting](../reference/ray-shielding.md#ray-shielding-versus-leeward_eqshield)
controls geometric occlusion.

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

### Detached-branch continuation

Tangent wedge and tangent cone use the same implementation-defined continuation
after their respective attached weak branches end. Let $\delta_{\max}$ be the
maximum attached turning angle and $C_{p,\mathrm{crit}}$ its pressure
coefficient. The implementation uses

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

This interpolation connects the end of the attached branch,
$C_p(\delta_{\max})=C_{p,\mathrm{crit}}$, continuously to the
Modified-Newtonian cap, $C_p(90^\circ)=C_{p,\max}$. It is an
implementation-defined pressure continuation, not a detached-shock solution.

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

**Figure.** Local panel $C_p$ at $M_\infty=6$ and $\gamma=1.4$, with ray
shielding off and `leeward_eq=shield`. Solid Tangent segments are attached weak
branches; dashed segments are the continuations defined above.

Newtonian reaches $C_p=2$ at $\delta=90^\circ$. Modified Newtonian retains the
same $\sin^2\delta$ shape with a finite-Mach stagnation cap. Tangent Wedge and
Tangent Cone use their local shock relations up to their attachment limits,
then approach that same cap. Compare the curves within each method's
[physical assumptions](#assumptions-and-limits).

#### Leeward response

![Leeward Hypersonic pressure coefficients versus local panel angle at Mach 6](../assets/plots/hypersonic-leeward-cp-vs-angle.svg)

**Figure.** Local panel $C_p$ at $M_\infty=6$ and $\gamma=1.4$, with
`windward_eq=newtonian` and ray shielding off. The leeward `shield` equation
gives zero pressure coefficient. Prandtl–Meyer gives expansion suction bounded
by the vacuum pressure coefficient.

## Flow inputs and constraints

`Mach` must be positive and `gamma` must be greater than 1. Modified Newtonian,
tangent wedge, tangent cone, and Prandtl–Meyer require `Mach > 1`.
Newtonian with leeward `shield` accepts any positive Mach, including subsonic
inputs. Physical applicability follows the assumptions below.

See the [Hypersonic input reference](../reference/hypersonic-input.md) for the
complete case schema. Local `cp` is documented in the
[VTP reference](../results/vtp.md#hypersonic); integrated coefficients are in the
[Summary CSV reference](../results/summary-csv.md).

## Assumptions and limits

These methods evaluate each panel independently using local, inviscid pressure
relations for a calorically perfect gas with constant $\gamma$. Choose a
method whose assumptions suit the vehicle and flow regime; accepted input
ranges establish that a relation can be evaluated, not its physical accuracy.

The common model scope excludes viscosity and boundary layers, heat transfer,
real-gas chemistry, shock interactions, and coupled flow between panels.
Method-specific approximations are:

- **Tangent wedge:** each panel uses its own local weak oblique-shock relation.
- **Tangent cone:** the panel angle supplies a cone half-angle; surface
  curvature and a physical cone axis are not reconstructed.
- **Prandtl–Meyer:** isentropic expansion, excluding separated flow.
- **Beyond attachment:** tangent methods use the
  [pressure continuation](#detached-branch-continuation) defined above.

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
