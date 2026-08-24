# Phase 1 numerical tolerances

Historical record — non-normative for the current product contract. This page records the repository state at the migration phase or audit named below. Statements such as “current”, supported commands, package names, file formats, and future work apply to that recorded point in time. Pinned source identities, golden evidence, tolerance profiles, and audit results may still be referenced by current developer workflows where devdocs/ or tests explicitly do so. Use docs/, devdocs/architecture/, and accepted or superseding ADRs for the present product contract.

These tolerances define when a future implementation reproduces a pinned legacy
result. They are compatibility limits, not estimates of physical-model error and
not permission to change a formula. Each fixture selects one profile in
`tests/fixtures/phase1/manifest.json`.

## Comparison rule

For a floating expected value `e` and actual value `a`, the semantic comparator
accepts the value only when:

```text
abs(a - e) <= atol + rtol * abs(e)
```

The absolute term therefore controls values at or near zero. NaN and infinity
are never generated into the JSON (`allow_nan=False`) and are not accepted as an
alternative representation of a finite baseline.

## Quantity classes

| Class | `atol` | `rtol` | Applied to | Evidence and reason |
|---|---:|---:|---|---|
| Exact | 0 | 0 | File/key set, ordering, names, logical dtype, shapes, topology, integers, masks, counts, strings, metadata, normalized case inputs, and CSV input cells | These values do not result from floating-point numerical work. A changed input must not be hidden by an output tolerance. |
| Geometry and attitude | `1e-12` | 0 | Vertices/points, centers, normals, areas, `Vhat_stl`, `theta_deg`, and resolved angles | Both pinned attitude suites require absolute agreement at `1e-12`; the small ASCII meshes start with exactly representable coordinates. |
| Sentman | `1e-10` | 0 | `Cp_n`, `C_face_stl`, integrated vectors, and force/moment coefficients | `fmfsolver/tests/test_flat_plate_verification.py` checks the independent Sentman flat-plate formula at absolute `1e-10` for `S={1,10,100}` and angles through 60 degrees. Scalar/vector consistency is tighter (`1e-13`). |
| Hypersonic algebraic | `1e-10` | 0 | Newtonian, modified-Newtonian, and closed-form tangent-wedge panel and integrated values | `newtsolver/tests/test_flat_plate_verification.py` checks the independent Newtonian flat-plate formula at absolute `1e-10`; tangent-wedge branch/vector consistency and local vector/scalar checks use 12 decimal places or `1e-12` to `1e-13`. |
| Hypersonic root solve | `1e-9` | 0 | Prandtl-Meyer panel and integrated values | The safeguarded inverse Prandtl-Meyer iteration is covered by a pinned nine-decimal-place regression. Its internal stopping thresholds are `1e-12`, so absolute `1e-9` preserves the observed algorithm while allowing library/platform iteration variation. |
| Tangent cone | `1e-9` | `5e-8` | Taylor-Maccoll tangent-cone panel values and every downstream integrated value in a case containing them | The pinned solver uses SciPy LSODA with `rtol=1e-8`, `atol=1e-10`, and `max_step=2e-3`. A relative limit five times the ODE request, plus a near-zero absolute limit, is the smallest defensible cross-platform envelope without claiming an independent cone oracle. |

The comparator recognizes geometry by semantic quantity name, not by artifact
container. Thus VTP `points` and NPZ `vertices`, for example, receive the same
geometry limit. A profile supplies a strict default plus explicit semantic-path
overrides. The mixed profiles give the wider PM/cone limit only to affected face
entries, affected component rows, and totals/integrated vectors downstream of
those entries. Newtonian faces and the pure Newtonian component in the same cases
remain at absolute `1e-10`.

## Profile assignment

| Profile | Cases |
|---|---|
| `fmf_default` | Mode B case; atmosphere-derived `S`/`Ti_K` use Sentman tolerance |
| `fmf_mode_a` | Unshielded Mode A cases; copied `S`/`Ti_K` values are exact |
| `fmf_shielded` | Mode A double-plate cases; copied state and shielded-face zero loads are exact |
| `newt_algebraic` | Newtonian, modified Newtonian, tangent wedge, and boundary cases |
| `newt_shielded` | rtree/Embree double-plate cases; shielded-face zero loads are exact |
| `newt_tangent_cone` | Pure tangent-cone case |
| `newt_prandtl_meyer_mixed` | Cube case: PM face entries and dependent totals use absolute `1e-9`; Newtonian faces use absolute `1e-10` |
| `newt_cone_mixed` | Bank/two-component case: cone faces, cone component, and dependent totals use the cone limit; the Newtonian component uses absolute `1e-10` |

`newt_beta_sin_boundary` uses the algebraic profile. Its zero panel and
integrated loads are still compared with the absolute `1e-10` limit, while its
input boundary angle and discrete schema remain exact.

NPZ `Aref_m2` and FMF `Tw_K` are direct copies of normalized inputs and are exact
in every profile. FMF Mode A `S`/`Ti_K` and their CSV `out_*` copies are also
exact. Mode B derives `S` and `Ti_K` from atmosphere interpolation, so those
values retain the Sentman numerical limit. For either ray backend, face indices 2
and 3 have an exact true shield mask and exact-zero `Cp_n`/`C_face_stl`; ordinary
near-zero tolerance cannot hide a load on a shielded face.

## Values normalized before comparison

Only host- or run-dependent values listed in the manifest are normalized:

- temporary archive and fixture-root paths;
- the 64-hex case-signature literal, after proving CSV, VTP, and recomputed
  signatures agree;
- UTC timestamps, after syntax and ordering validation;
- elapsed seconds, after finite/nonnegative validation;
- physical NumPy string width to the logical `string` dtype;
- the platform-specific `embreex`/`embreex4` distribution and version, after
  proving that the rayaccel environment exposes and selects Embree.

An explicit CSV `nan`, positive infinity, or negative infinity is stored as its
own marker and cannot compare equal to a blank cell or finite value. Numerical
VTP/NPZ arrays containing any nonfinite value make generation fail.

Runtime, raw VTP/NPZ bytes, JSON member formatting, and GUI pixels are not
numerical quantities and are not treated with a broad tolerance. Requested and
effective ray backends, shielding masks, field/array names, CSV columns, and row
order remain exact.

## Changing a baseline or tolerance

Do not regenerate expectations merely because a comparison fails. A change must
identify the quantity and case, show the old and new values, cite either a legacy
oracle or an accepted numerical/compatibility decision, explain downstream
effects, and update the manifest and tests in the same review. A formula change
must stay separate from structural migration. Until an independent high-accuracy
tangent-cone reference is added, its golden is evidence of legacy compatibility
only, not scientific validation.
