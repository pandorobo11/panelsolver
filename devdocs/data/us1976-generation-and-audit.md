# US1976 table generation and audit

This page is the maintainer record for the FMF/Sentman Mode B atmosphere table.
Scientific and model-facing provenance is documented in
[the user reference](../../docs/reference/us1976-data-provenance.md). The
authoritative consolidated rights and source-identity notice is
[`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md).

## Pinned source identity

The regeneration implementation is PDAS `bigtables.py` version 1.5
(2022-03-18), obtained on 2026-08-15 from
`https://www.pdas.com/packages/atmos.zip`.

| Object | SHA-256 |
|---|---|
| downloaded `atmos.zip` | `6ede29f1e4f104ad3d5cbe990071682fd903ab04d7d47b168a4c17817714365a` |
| upstream `bigtables.py` | `eca87577139ac3b2845d1d4eca91604ac278a491918979f2d2316bf88a9a3a28` |
| repository minimal calculation snapshot | `11e82d35d66a61c4326acf04fcad0c9ab471112721151b65cfdf4faff43f9994` |

`tools/reference/pdas/bigtables_v1_5.py` is a development-only minimal snapshot
of the constants and calculation functions needed for geometric altitude,
temperature, speed of sound, and mean molecular speed. HTML generation, unused
properties, and the upstream program's unconditional HTML-writing entry point
are omitted. Neither the snapshot nor the generator is imported at runtime.

Before changing the snapshot, obtain the official package, verify the package
and upstream-file hashes, compare the retained calculations and constants, and
review the PDAS legal statement and `THIRD_PARTY_NOTICES.md`. A legitimate
upstream update requires an explicit review and corresponding updates to every
recorded identity and audit result; do not silently replace the pinned source.

## Deterministic generation

The transformation is:

```text
U.S. Standard Atmosphere, 1976
  -> PDAS public-domain bigtables.py v1.5
  -> tools/reference/pdas/bigtables_v1_5.py
  -> scripts/generate_us1976_sentman_table.py
  -> src/panelsolver/models/_sentman_atmosphere_data.py
  -> panelsolver.models.sentman_atmosphere
```

The generator evaluates `0, 5, ..., 1000` geometric kilometers and applies the
PDAS published-value formatting: integer altitude, three-decimal temperature,
and two-decimal sound and mean molecular speeds. Regenerate or verify without
network access:

```bash
python scripts/generate_us1976_sentman_table.py
python scripts/generate_us1976_sentman_table.py --check
```

CI runs the `--check` form before building distributions. The generated Python
module is included in wheel and sdist. The generator and PDAS snapshot are
included in the sdist but not the wheel.

## Legacy equivalence evidence

The prior implementation transcribed four arrays from two CSV files at pinned
legacy `fmfsolver` commit
`b62bc844d02a8f5212e62a53dea3238a1414317d`:

| Legacy file | Used columns | SHA-256 |
|---|---|---|
| `us1976_table1.csv` | `Z`, `T`, `c` | `4afc36572b2126818d777e3e92fa33ec2440c1a6ad2f61aef5f65c0966f2a491` |
| `us1976_table2.csv` | `Z`, `V` | `7afe3132cd59836c77cdc32be6e0821de20027f9cf41974d3a337769ec7a534a` |

Every generated grid value was compared independently with the prior altitude,
temperature, sound-speed, and mean-speed arrays. Each column produced 201/201
exact matches, zero nonzero differences, and maximum absolute difference `0.0`.
Unit tests retain per-column SHA-256 evidence in addition to known points and
interpolation samples. No golden fixture or tolerance changed.

When modifying the generator, snapshot, rounding, or table, rerun the full-grid
comparison and the FMF Mode B regression suite. Record the source identity,
reason, numerical effect, and compatibility decision before accepting any
nonzero difference. Also verify that the user provenance page and
`THIRD_PARTY_NOTICES.md` still agree on scientific source, public-domain basis,
source identity, rounding, and the Apache-2.0 rights boundary.
