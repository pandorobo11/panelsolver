# US1976 Sentman atmosphere data provenance

## Runtime dataset

FMF/Sentman Mode B uses a bundled table containing four physical quantities:

| Column | Unit | Meaning |
|---|---|---|
| geometric altitude | km | geometric altitude above mean sea level |
| temperature | K | kinetic/static translational temperature |
| speed of sound | m/s | PDAS Big Tables sound speed |
| mean molecular speed | m/s | PDAS Big Tables mean particle speed |

The table has 201 rows at 5 km intervals from 0 through 1000 km inclusive.
Panel Solver linearly interpolates these values and does not extrapolate beyond
the tabulated altitude range. Runtime use requires neither an external data file
nor network access.

Pressure, density, viscosity, gravity, number density, mean free path, molecular
weight, and other atmosphere fields are not included because the solver does not
use them.

## Scientific source

The technical definition is
[*U.S. Standard Atmosphere, 1976*](https://ntrs.nasa.gov/api/citations/19770009539/downloads/19770009539.pdf),
issued as NOAA-S/T-76-1562 and NASA-TM-X-74335 and catalogued by the NASA
Technical Reports Server as document
[19770009539](https://ntrs.nasa.gov/citations/19770009539). The NTRS record
identifies the report as a U.S. Government work for which public use is
permitted.

The numerical regeneration source is PDAS `bigtables.py` version 1.5
(2022-03-18) from the official
[atmosphere package](https://www.pdas.com/atmosdownload.html). The PDAS legal
statement identifies the individual programs and PDAS-added program value as
public domain. Panel Solver does not claim copyright in the underlying U.S.
Government data or PDAS program and does not relicense them as Apache-2.0.
The authoritative source identities, hashes, and rights notice are preserved in
the bundled `THIRD_PARTY_NOTICES.md`.

## Formatting and numerical compatibility

The generated grid preserves the published PDAS formatting used by the source
program:

- altitude: integer kilometers;
- temperature: three digits after the decimal;
- speed of sound: two digits after the decimal;
- mean molecular speed: two digits after the decimal.

This rounding is part of the current numerical contract. Panel Solver does not
replace the published table values with higher-precision intermediate binary
results.

The root `THIRD_PARTY_NOTICES.md` is the authoritative consolidated rights and
source-identity notice. Maintainer regeneration steps, source-hash verification,
and full audit evidence are repository and source-distribution materials rather
than part of the installed offline help.
