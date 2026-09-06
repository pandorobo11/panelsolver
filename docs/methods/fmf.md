# Free Molecular Flow (FMF)

FMF evaluates free-molecular-flow panel loads with the Sentman model. Its local
nondimensional traction includes normal and tangential contributions.

## Flow inputs

Supply exactly one of these input pairs:

- **Mode A:** positive molecular speed ratio `S = V_inf / sqrt(2 R Ti)` and
  positive incident freestream translational (static) temperature `Ti_K`.
- **Mode B:** positive `Mach` and geometric `Altitude_km` in the inclusive
  `0–1000 km` range of the bundled US1976 table. The solver linearly interpolates
  static temperature, sound speed, and mean molecular speed. It computes
  `V_inf = Mach * c`, converts mean molecular speed to most-probable speed with
  `V_mp = sqrt(pi) / 2 * V_mean`, and resolves `S = V_inf / V_mp` and `Ti_K`.

Both modes also require positive wall temperature `Tw_K`. The model assumes
complete thermal accommodation, using the wall temperature as the diffusely
reflected molecular temperature (`T_r = T_w`).

The [FMF input reference](../inputs/fmf-input.md) lists columns, defaults,
and validity requirements.

## Sentman local-load equation

For each panel, the model computes a local nondimensional traction vector
$\boldsymbol\tau$. Panel-area weighting and whole-vehicle force/moment
integration are defined in
[Load and coefficient conventions](load-and-coefficient-conventions.md#local-traction-and-panel-contributions).

### Geometry and symbols

- $\hat{\boldsymbol V}$ is the unit flow direction in the STL frame.
- $\boldsymbol n_{\mathrm{out}}$ is the STL outward unit normal.
- $\boldsymbol n_{\mathrm{in}}=-\boldsymbol n_{\mathrm{out}}$ is the inward
  unit normal used in Sentman's original report.
- $\gamma=\boldsymbol n_{\mathrm{in}}\mathbin{\boldsymbol\cdot}
  \hat{\boldsymbol V}$ is the direction cosine between the flow and inward
  normal.
- $S$ is the molecular speed ratio (`S`), $T_i$ is the incident translational
  temperature (`Ti_K`), and $T_w$ is the wall temperature (`Tw_K`).

### Auxiliary functions and local traction

Define

```math
h = \gamma S,
\qquad
\Phi = 1 + \mathrm{erf}(h),
\qquad
E = e^{-h^2}.
```

The implemented coefficients are

```math
c_{\parallel}
=
\gamma\Phi
+
\frac{E}{S\sqrt{\pi}},
```

```math
c_{n,i}
=
\frac{\Phi}{2S^2},
```

and

```math
c_{n,r}
=
\frac{1}{2}
\sqrt{\frac{T_w}{T_i}}
\left[
\frac{\gamma\sqrt{\pi}}{S}\Phi
+
\frac{E}{S^2}
\right].
```

The local traction coefficient is therefore

```math
\boldsymbol{\tau}
=
c_{\parallel}\hat{\boldsymbol V}
+
\left(c_{n,i}+c_{n,r}\right)\boldsymbol n_{\mathrm{in}}.
```

The three terms have distinct roles. The
$c_{\parallel}\hat{\boldsymbol V}$ term is the incident-molecule load in the
flow direction and retains the component tangent to the panel.
$c_{n,i}\boldsymbol n_{\mathrm{in}}$ is the normal contribution from the
random thermal motion of incident molecules, while
$c_{n,r}\boldsymbol n_{\mathrm{in}}$ is the normal contribution from diffusely
reflected molecules. Under complete diffuse reflection, reflected tangential
momentum cancels statistically, so the reflected term appears only in the
normal direction. The error-function and exponential terms account for the
random thermal motion of incident molecules.

### Representative angular response

For this illustrative angular response, the flow direction is fixed at
$\hat{\boldsymbol V}=[1,0,0]$ and the panel normal varies as
$\boldsymbol n_{\mathrm{in}}=[\sin\delta,\cos\delta,0]$. Thus
$\mu=\boldsymbol n_{\mathrm{in}}\mathbin{\boldsymbol\cdot}
\hat{\boldsymbol V}=\sin\delta$, where $\delta=-90^\circ$ faces directly away
from the flow, $\delta=0^\circ$ is grazing incidence, and $\delta=+90^\circ$
faces directly into the flow. The output angle is related by
$\delta=\mathtt{theta\_deg}-90^\circ$.

![Sentman local normal and tangential traction versus local panel angle at S=7](../assets/plots/sentman-local-traction-vs-angle.svg)

**Figure.** Local panel traction at $S=7$, $T_i=1000\ \mathrm{K}$, and
$T_w=180.625\ \mathrm{K}$, giving $\sqrt{T_w/T_i}=0.425$. The case uses
complete diffuse reflection and thermal accommodation ($T_r=T_w$), with ray
shielding off. The vertical line marks grazing incidence ($\delta=0^\circ$).

The plotted normal component is

```math
\mathtt{normal\_traction\_coeff}
=
-\boldsymbol\tau\mathbin{\boldsymbol\cdot}\boldsymbol n_{\mathrm{out}}.
```

The tangential positive direction is the in-plane projection of the uniform
flow direction,

```math
\hat{\boldsymbol t}
=
\frac{
\hat{\boldsymbol V}
-(\hat{\boldsymbol V}\mathbin{\boldsymbol\cdot}\boldsymbol n_{\mathrm{out}})
\boldsymbol n_{\mathrm{out}}
}{
\left\lVert
\hat{\boldsymbol V}
-(\hat{\boldsymbol V}\mathbin{\boldsymbol\cdot}\boldsymbol n_{\mathrm{out}})
\boldsymbol n_{\mathrm{out}}
\right\rVert
},
```

and the tangential component is

```math
\mathtt{tangential\_traction\_coeff}
=
\boldsymbol\tau\mathbin{\boldsymbol\cdot}\hat{\boldsymbol t}.
```

At normal incidence the in-plane direction is undefined and the tangential
component is exactly zero. Random molecular thermal motion produces finite
traction at grazing incidence and a response extending into negative local
angles.

### Assumptions and implementation scope

Sentman's Eq. (21) applies within kinetic theory, free-molecular flow, and
complete diffuse reflection. FMF fixes the reflected temperature to the wall
temperature as described under [Flow inputs](#flow-inputs); specular or mixed
reflection and adjustable thermal accommodation are outside this model's scope.

[Ray shielding](ray-shielding.md) approximates geometric occlusion
by setting a hidden panel's entire traction vector to zero. Multiple reflections
between surfaces are outside this approximation.

Mode B uses the same free-molecular model. Its bundled atmosphere table provides
conditions within the tabulated altitude range. Table sources, rounding, and
reproducibility are documented in
[US1976 data provenance](../appendix/us1976-data-provenance.md).

## Outputs and scope

FMF VTP includes the local `normal_traction_coeff`, `tangential_traction_coeff`,
and `theta_deg` scalars. Summary CSV records the resolved `mode`, `out_S`, and
`out_Ti_K`; `Tw_K` remains an input column.

See the [VTP reference](../results/vtp.md#fmf) for array types and units, and the
[Summary CSV reference](../results/summary-csv.md#fmf-resolved-state-fields) for
resolved-state columns. Interpret results within the
[model assumptions](#assumptions-and-implementation-scope) above.

## Reference

Lee H. Sentman, *Free Molecule Flow Theory and Its Application to the
Determination of Aerodynamic Forces*, LMSC-448514, 1961, Section II-B,
especially Eq. (21).
