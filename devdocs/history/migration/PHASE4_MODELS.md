# Phase 4 physical-model adapters

Historical record — non-normative. This page records the repository state at the migration phase or audit named below. Statements such as “current”, supported commands, package names, file formats, and future work apply to that recorded point in time. Use docs/, devdocs/architecture/, and accepted or superseding ADRs for the present contract.

Phase 4 moves only physical-model behavior behind the Phase 2
`PanelLoadModel` protocol. Geometry loading, shielding calculation, common
integration, artifact projection, execution, signatures, compatibility
frontends, and GUI behavior remain in their owning phases.

## Phase 4a: Sentman

`panelsolver.models.SentmanModel` uses the stable model ID `sentman` and
algorithm version `sentman-b62bc844`. Its numerical oracle is pinned
`fmfsolver` commit `b62bc844d02a8f5212e62a53dea3238a1414317d`.

The model payload keeps the two legacy flow modes separate:

- Mode A requires `S`, `Ti_K`, and `Tw_K`;
- Mode B requires `Mach`, `Altitude_km`, and `Tw_K`, then uses the pinned
  US1976 linear interpolation and mean-to-most-probable speed conversion.

The returned traction is the legacy Sentman vector numerator. This is a thin
normalization adapter, not a formula change: the old routine applied `/Aref`
inside the equation, while the adopted contract requires the common integrator
to apply `area_m2 / Aref_m2`. Both incident tangential/freestream and normal
reflected terms are retained. Shielded faces are exact-zero vectors.

`LocalLoads.cell_scalars` contains `Cp_n` and `theta_deg`. Model metadata contains
resolved `mode`, `S`, `Ti_K`, and `Tw_K`. `signature_payload()` returns only the
normalized raw model inputs and deliberately does not construct, serialize, or
hash the Phase 5 common signature envelope.

The required US1976 columns are transcribed from both pinned CSV files into
private numeric constants with source hashes. Model code imports no filesystem,
artifact, GUI, scheduler, application, or compatibility module.

Verification recomputes all six FMF Phase 1 cases, including Mode B, bank,
multi-component, and both shielding backends, then passes the model loads through
the Phase 3 integration and aggregation functions. Existing golden files and
tolerances are unchanged.

## Phase 4b: hypersonic

`panelsolver.models.HypersonicModel` uses the stable model ID `hypersonic` and
algorithm version `hypersonic-dc1357d0`. Its numerical oracle is pinned
`newtsolver` commit `dc1357d0d50bbedfdc8b3429cab37e6b98b56c70`.

The model payload requires positive `Mach`, `gamma > 1`, and independent
`windward_eq` / `leeward_eq` selectors. Newtonian with leeward `shield` remains
valid below Mach 1, while modified Newtonian, tangent wedge, tangent cone, and
Prandtl–Meyer retain their Mach-greater-than-one checks. A single selector is
broadcast; a semicolon list maps in ascending component-ID order. The two
selector vocabularies remain separate.

The model returns pressure-only traction `-Cp * normal_out_stl`. As with
Sentman, legacy `/Aref` is removed only at the adapter boundary because the
common integrator owns `area_m2 / Aref_m2`. `leeward_eq=shield` is still a
zero-pressure equation choice and is not conflated with the independent ray
shield mask.

The modified-Newtonian normal-shock relation, tangent-wedge closed form and
detached bridge, tangent-cone Taylor–Maccoll table/PCHIP path, and safeguarded
Prandtl–Meyer inverse are copied from the pinned source without changing their
constants, branches, caches, solver settings, or termination tests. In
particular, tangent cone retains 220 shock-angle samples and LSODA
`rtol=1e-8`, `atol=1e-10`, `max_step=2e-3`; inverse Prandtl–Meyer retains the
40-step bracket, 60-step solve, and `1e-12` convergence thresholds.

`LocalLoads.cell_scalars` contains the hypersonic `Cp_n` and `theta_deg`.
Metadata and `signature_payload()` contain only `Mach`, `gamma`, and canonical
windward/leeward selectors. They do not reuse the Sentman Mode A/B or thermal
schema, and they do not construct the Phase 5 signature envelope.

Verification recomputes all nine newtsolver Phase 1 cases, including each
equation family, mixed per-component selectors, bank, boundary, and both
shielding backends. Existing golden files and the separate algebraic,
root-solve, and tangent-cone tolerance profiles are unchanged.
