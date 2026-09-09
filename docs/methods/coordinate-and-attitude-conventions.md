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

Every representation resolves directly to one unit flow direction. Physical
loads and shielding use that vector. The stability angle is derived separately;
flow is never reconstructed from resolved tangent angles.

The default input mode is `beta_sin` when the mode is omitted or blank.
Explicit `beta_tan` and `bank` selections retain their definitions below.

## Sine-definition sideslip input (`beta_sin`)

For `alpha_deg` $\alpha$ and `beta_or_bank_deg` $\beta_s$:

```math
\hat{\boldsymbol V}_{\mathrm{STL}}=
\begin{bmatrix}
\cos\alpha\cos\beta_s\\
-\sin\beta_s\\
\sin\alpha\cos\beta_s
\end{bmatrix}.
```

Alpha is any finite periodic angle; sideslip is in [-90°, 90°], including
endpoints. This covers every direction, including backward flow. Positive
sideslip always points toward -Y. At beta = ±90°, direction is ∓Y regardless
of input alpha. The geometric angle of attack is then undetermined.

## Tangent-angle input (`beta_tan`)

`alpha_deg` is the angle of the XZ projection, and `beta_or_bank_deg` is
sideslip measured relative to the absolute X component:

```math
\beta_t=\mathrm{atan2}(-V_y,|V_x|).
```

For input angles $\alpha$ and $\beta_t$, the forward map is

```math
\hat{\boldsymbol V}_{\mathrm{STL}}=\mathrm{normalize}
\begin{bmatrix}
\cos\alpha\cos\beta_t\\
-|\cos\alpha|\sin\beta_t\\
\sin\alpha\cos\beta_t
\end{bmatrix}.
```

Alpha is any finite periodic angle; sideslip is in [-90°, 90°], including
endpoints. Positive sideslip points toward -Y for both forward and backward
flow. Unlike a signed-X tangent ratio, its lateral sign does not reverse when
alpha passes 90°.

The forward map extends to single-angle poles even though the original pair
cannot always be recovered:

| Inputs | Direction and interpretation |
|---|---|
| Alpha = ±90° modulo 360°, abs(beta) < 90° | ±Z; input beta does not affect direction and cannot be recovered. |
| Beta = ±90°, cos(alpha) != 0 | ∓Y; input alpha cannot be recovered. |
| Alpha an odd multiple of 90° and beta = ±90° | Undefined zero vector; rejected. Use beta_sin or bank to specify Y/Z proportions. |

## Included-angle and bank input (`bank`)

`alpha_deg` is the included angle $i$ from +X_STL and `beta_or_bank_deg` is
the bank angle $\phi$ about +X_STL:

```math
\hat{\boldsymbol V}_{\mathrm{STL}}=
\begin{bmatrix}
\cos i\\
-\sin i\sin\phi\\
\sin i\cos\phi
\end{bmatrix}.
```

Both inputs are finite periodic angles. Zero bank is the +Z meridian;
positive bank rotates toward -Y, following a positive right-hand rotation
about +X. When sin(i) = 0 the direction is on the X axis and bank is immaterial.
The included angle is not generally the stability angle.

## Stability angle and numerical boundaries

The stability angle describes the direction of the flow projected onto the
STL XZ plane. Panel Solver derives it from the flow vector in every mode and
uses it for the
[coefficient transformation](load-and-coefficient-conventions.md#stability-axis-force-coefficients):

```math
\alpha_{\mathrm{stab}}=\mathrm{atan2}(V_z,V_x).
```

The result is saved as `alpha_stability_deg`, in the range (-180°, 180°].
For example, -180° is reported as +180°. This derived angle is separate from
`alpha_deg`, which records what you entered; in `bank` mode, that input is an
included angle rather than the stability angle.

For a normalized flow direction, if `hypot(Vx, Vz)` is at or below 64 times
float64 machine epsilon (approximately 1.42e-14), the XZ projection is treated
as too small to define a useful stability angle. Panel Solver uses 0° for the
coefficient transformation in this case, so the stability axes coincide with
the body axes. This convention does not change the flow direction used to
calculate loads and shielding, and there is no globally continuous stability
frame across every approach to lateral flow.

Finite periodic angles are reduced before trigonometric evaluation. Exact
multiples of 90° use exact sine/cosine values of 0 or ±1. Adjacent floating-point
values are not rounded to these boundaries. Tiny nonzero tangent vectors are
scaled before normalization; only the exact zero-direction corner is rejected.
Zero components and zero stability angle use positive zero.

## Input angles and saved results

Summary CSV and VTP keep both the original inputs and the calculated attitude:

| Saved information | Meaning |
|---|---|
| `alpha_deg`, `beta_or_bank_deg` | The angles you entered, before removing full turns. |
| Attitude mode | The mode used to interpret those angles: `beta_sin`, `beta_tan`, or `bank`. |
| Unit STL flow vector | The calculated direction used for loads and shielding. |
| `alpha_stability_deg` | The angle used to transform coefficients into stability axes. |

For example, an input `alpha_deg` of 460° gives the same direction as 100°,
but the saved input remains 460°. The calculated direction and stability angle
are saved separately. See the [Summary CSV](../results/summary-csv.md) and
[VTP](../results/vtp.md) references for the field names.

The flow vector does not always identify the original angle pair. For example,
with `beta_sin` and sideslip 90°, every input alpha gives the same -Y direction.
Panel Solver therefore keeps your original angles instead of trying to recover
them from the calculated direction.
