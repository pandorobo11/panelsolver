# Phase 1 golden baselines

Historical record — non-normative. This page records the repository state at the migration phase or audit named below. Statements such as “current”, supported commands, package names, file formats, and future work apply to that recorded point in time. Use docs/, devdocs/architecture/, and accepted or superseding ADRs for the present contract.

The committed baselines are semantic captures from the immutable legacy commits,
not outputs produced by the new shared packages:

| Product | Commit | Version | Locked legacy suite |
|---|---|---:|---:|
| `fmfsolver` | `b62bc844d02a8f5212e62a53dea3238a1414317d` | 1.3.8 | 75 passed |
| `newtsolver` | `dc1357d0d50bbedfdc8b3429cab37e6b98b56c70` | 1.0.3 | 90 passed |

Each source checkout is verified for commit, origin URL, and clean tracked state,
then archived to a temporary directory. Locked base and `rayaccel` environments
are created inside the archive with Python 3.12 explicitly selected. Generation
neither installs from nor writes into the reference checkout.
The base suite/contract sections and rayaccel CLI/case sections carry separate
environment provenance rather than being attributed to one mixed environment.

## What is frozen

The 15 valid cases jointly capture:

- normalized inputs, CLI output/order, and ordered summary CSV cells;
- VTP geometry, named cell arrays, and field metadata;
- NPZ named arrays, logical dtype, shape, and values;
- face-order `C_face_stl`, `Cp_n`, `theta_deg`, shielding mask, area, centers,
  normals, and component/STL index;
- integrated STL/body force, body moment, all eight coefficients, totals, and
  per-component rows;
- rtree and Embree shield paths, plus base/accelerated `auto` selection probes;
- command help, import/module surface, environment precedence and errors, invalid
  input issue structure, package context, and legacy suite result.

The four input meshes are byte-identical to both source repositories and have
SHA-256 hashes in `tests/fixtures/phase1/manifest.json`. The generated JSON
contains no pickle payload; trusted legacy NPZ object arrays are converted to
logical JSON strings during capture.

## Case matrix and integrated anchors

The tables below are navigation aids. Full precision, all coefficients, every
panel value, and all artifact fields remain authoritative in the case JSON.

### FMF / Sentman

| Case | Main coverage | Backend | Faces / shielded | `CA` | `CY` | `CN` | `Cm` | `CD` | `CL` |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| `fmf_zero_plate` | analytic plate, zero attitude | not used | 2 / 0 | 2.3944907701811076 | 0 | 0 | 0 | 2.3944907701811076 | -0 |
| `fmf_mode_b_offset` | atmosphere Mode B, sideslip, reference offset | not used | 2 / 0 | 1.9395147014761185 | 0.31975501572094567 | 0.48590464087788443 | -0.13321339003787633 | 1.9991887157860129 | -0.03263550126068604 |
| `fmf_beta_sin_boundary` | valid `beta_sin` boundary | not used | 2 / 0 | 0.04000000000000001 | -0.11283791670955128 | 0 | 0 | 0.04000000000000001 | -0 |
| `fmf_bank_multicomponent` | bank, two components, moments | not used | 4 / 0 | 1.9159942411981503 | -0.3659981507749165 | 0.7848855672305093 | -0.4859315118312561 | 2.0615243385814703 | -0.1928644274807182 |
| `fmf_shield_rtree` | double plate shielding | rtree | 4 / 2 | 2.3944907701811076 | 0 | 0 | 0 | 2.3944907701811076 | -0 |
| `fmf_shield_embree` | double plate shielding | Embree | 4 / 2 | 2.3944907701811076 | 0 | 0 | 0 | 2.3944907701811076 | -0 |

### Hypersonic

| Case | Main coverage | Backend | Faces / shielded | `CA` | `CY` | `CN` | `Cm` | `CD` | `CL` |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| `newt_zero_newtonian` | analytic Newtonian plate | not used | 2 / 0 | 2 | 0 | 0 | 0 | 2 | -0 |
| `newt_modified_offset` | modified Newtonian, reference offset | not used | 2 / 0 | 1.648457288500289 | 0 | 0 | -0.16484572885002893 | 1.5922874684968789 | -0.42665214130193535 |
| `newt_tangent_wedge` | closed-form tangent-wedge path | not used | 2 / 0 | 0.20132741031167226 | 0 | 0 | 0 | 0.0521073680898304 | -0.19446734515994032 |
| `newt_tangent_cone` | Taylor-Maccoll/LSODA path | not used | 2 / 0 | 0.1503422427717429 | 0 | 0 | 0 | 0.03891143571275385 | -0.14521945507544748 |
| `newt_prandtl_meyer` | leeward expansion on cube | not used | 12 / 0 | 1.8531033470723135 | -0.08826633596268368 | 0.1671763707831065 | 0 | 1.8332288103696512 | -0.3181384646808615 |
| `newt_beta_sin_boundary` | valid `beta_sin` boundary | not used | 2 / 0 | 0 | 0 | 0 | 0 | -0 | -0 |
| `newt_bank_multicomponent` | bank, cone + Newtonian, two components | not used | 4 / 0 | 1.5606484331470378 | 0 | 0 | -0.1560648433147038 | 1.3827854795929961 | -0.7235522436639056 |
| `newt_shield_rtree` | double plate shielding | rtree | 4 / 2 | 2 | 0 | 0 | 0 | 2 | -0 |
| `newt_shield_embree` | double plate shielding | Embree | 4 / 2 | 2 | 0 | 0 | 0 | 2 | -0 |

For both products and both ray implementations, the double-plate mask is exactly
`[false, false, true, true]`. Loads on the last two faces are exact zero. The
unshielded two-layer force is therefore reduced by half: FMF `CA=CD` changes from
`4.788981540362215` to `2.3944907701811076`, and Newtonian from `4` to `2`.

The multi-component tests also require each of the eight total coefficients to
equal the ordered component-row sum within the selected profile. This freezes
global reference-area/point/length use, not merely the CSV shape.

## Reproduction and comparison

Run the documented generator from a clean `panel-solvers` checkout with the two
pinned sibling repositories:

```bash
uv run python scripts/generate_phase1_goldens.py \
  --fmf-repo ../fmfsolver \
  --newt-repo ../newtsolver \
  --check
```

`--check` regenerates into a temporary capture tree and reports semantic
differences without updating tracked files. Direct capture-tree comparison is
available through `scripts/compare_phase1_goldens.py`. See
`tests/fixtures/phase1/README.md` for the storage format and
`TOLERANCES.md` for the quantity-to-tolerance mapping.

## Deliberate non-goldens

Raw CSV/VTP/NPZ bytes, temporary/absolute paths, literal case signatures,
timestamps, elapsed runtime, and NumPy fixed-string widths are not portable byte
goldens. They are either compared semantically or validated relationally before a
documented marker is stored. The platform-specific Embree distribution is also
normalized after availability/selection checks. GUI screenshots are not
committed because platform, font, and OpenGL rendering would dominate their
pixels; GUI-visible actions and state are recorded in
`BEHAVIORAL_INVENTORY.md` instead.

## Inputs to Phase 2

Phase 2 can treat the following as evidence-backed boundaries:

- `LocalLoads` must retain an `(n_faces, 3)` local vector plus visualization
  scalars and model metadata; scalar `Cp` alone loses Sentman tangential load.
- Geometry, model evaluation, integration, component aggregation, and artifact
  projection are distinct contracts even though the legacy pipelines combine
  them.
- Common result types need explicit STL/body/stability frames and must retain the
  eight integrated coefficients and component identity.
- Model case payloads must remain independent: FMF Mode A/B and thermal inputs
  are not hypersonic Mach/gamma/equation selectors.
- Validation of shapes, finite values, references, and array ownership belongs in
  the central contracts; product-specific angle, ID, and spreadsheet policies do
  not.

Phase 2 must not resolve the differences in `LEGACY_DIFFERENCES.md`. In
particular, angle boundaries, mesh strictness, signature payloads, Python
re-exports, old XLS behavior, and NPZ omissions still need later compatibility
decisions or ADRs.
