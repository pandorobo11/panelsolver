# ADR 0009: Remove NPZ output

- Status: Accepted
- Date: 2026-08-15
- Supersedes: the NPZ serialization portion of ADR 0005 and the NPZ
  compatibility-surface portion of ADR 0008

## Context

The products historically offered an independent NPZ output alongside Summary
CSV and VTP. NPZ is not used for caching, resuming execution, or GUI display.
Recomputing one case is sufficiently fast that maintaining a third artifact
projection, serializer, schema, and public exporter has no practical value.
There are no known NPZ users.

This is an intentional compatibility change, not a numerical-model change. The
Phase 1 NPZ captures and migration records remain useful evidence of the pinned
legacy products even though that format is no longer part of the current
product.

## Decision

Summary CSV and VTP are the only formal outputs going forward. Remove NPZ output
immediately rather than introducing a deprecation period, compatibility no-op,
or exporter stub. Remove its case input, result path, runtime projection and
serialization, neutral symbols, and compatibility-frontend exporters.

An old case-table header containing `save_npz_on` is rejected with a field-aware
message instructing the user to delete it. Summary CSV removes only the
`save_npz_on` input column and `npz_path` result column; every other column keeps
its value, order, blank semantics, and total/component ordering.

Existing NPZ files on disk are not automatically deleted. Historical NPZ
goldens, Phase 1 fixtures, provenance, migration records, hashes, and tolerances
remain unchanged as evidence. Current-versus-historical regression comparisons
exclude only the retired input/result fields and current NPZ projection or
serialization.

This decision does not change numerical formulas, coordinate systems, signs,
normalization, VTP semantics, or the case-signature schema or values. It also
does not change either product compatibility version or the shared distribution
version; such version changes require explicit separate direction. The CSV,
VTP, numerical-signature, cache-identity, and supported-domain portions of ADR
0005 and ADR 0008 are not superseded.

## Consequences

Users must remove `save_npz_on` from old case files. They use VTP for panel and
visualization data and Summary CSV for aggregate total/component results. Old
NPZ files remain where users placed them, but current commands and Python APIs
neither create nor expose them.

The codebase retains one VTP projection path and one durable Summary CSV path.
Regression coverage continues to prove zero numerical, VTP-semantic, and
case-signature differences while preserving the read-only historical evidence.
