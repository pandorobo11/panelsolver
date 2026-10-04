# ADR 0020: Panel-constant sectional Cp segments

- Status: Accepted (user-approved feature and endpoint storage plan)
- Date: 2026-10-04

## Decision

Add an independent surface-section workflow alongside ADR 0019's strip
integrals. A row represents one source triangle's intersection segment and
retains **both endpoints**, source face/component identity and the existing
panel scalar. Hypersonic uses `cp`; FMF uses `normal_traction_coeff` under its
own name. No equations, signs, normalization, case signatures or existing output
schemas change. No interpolation or contour assembly is introduced.

A dedicated definition uses equally spaced planes including interval endpoints,
with equal explicit bounds for a single plane. Auto single-plane placement is
the midpoint of selected projected extrema. Coplanar triangles fail their plane;
shared edges retain both source values; point contacts are omitted. Exact
rational predicates on stored float inputs avoid arbitrary snapping tolerances.
Existing source-geometry consistency validation is reused.

Core owns intersections and immutable arrays; app owns parsing, CSV and batch
orchestration. Existing scheduler, cancellation, protection and atomic writer
services are reused. GUI reuses the sectional dialog with an explicit Cp mode.
Different definition kinds cannot mix in a batch. Geometry failures yield
explicit status rows and later definitions continue. Cancellation remains
cooperative, not an interrupt inside rational intersection evaluation.

This extends ADR 0014's public-surface exception to
`panelsolver.postprocess.compute_sectional_cp` and the documented returned
`SectionalCp` fields. It does not change ADR 0019's excluded pressure-section
scope: pressure sections have this independent contract.

## Validation and limits

Analytic endpoint, panel discontinuity, contact, translation, scale, scalar
provenance, serialization, batch, CLI and GUI tests cover the new behavior.
No new production dependency is required. Rational arithmetic is deliberately
conservative and can be slow on large meshes; future acceleration must retain
these predicates and values. Neither output order nor shared coordinates imply
a connected or oriented contour.
