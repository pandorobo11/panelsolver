from __future__ import annotations

import hashlib
import math
import unittest
from itertools import pairwise

from panelsolver.models._sentman_atmosphere_data import US1976_SENTMAN_TABLE
from panelsolver.models.sentman_atmosphere import (
    altitude_range_km,
    sample_at_altitude_km,
)

# SHA-256 values captured from each pre-migration canonical array.  Explicit
# published-value formatting makes these full-grid checks independent of tuple
# layout while preserving every supported numeric value.
PREVIOUS_COLUMN_SHA256 = {
    "geometric_altitude_km": "e488e86463d21e330140b9d559444642ac69bebbf3130de5e387dcd5a156c3ac",
    "temperature_K": "d067b2a38103722e846b123f0989b64ab32aeb4ef416ecf4a2713a2d4fd88d64",
    "speed_of_sound_ms": "f42641736c89cc01da6a3af3df69ebe6e05222d08b9baf12c0451d6432b8b3f6",
    "mean_molecular_speed_ms": "9d40cc51db5681b36bce2fbcd801e5b92d9afe760875fbb367a363e39a4fe2b9",
}


class SentmanAtmosphereTableTests(unittest.TestCase):
    def test_single_canonical_table_has_only_required_quantities(self) -> None:
        self.assertIs(type(US1976_SENTMAN_TABLE), tuple)
        self.assertEqual(201, len(US1976_SENTMAN_TABLE))
        self.assertTrue(all(type(row) is tuple for row in US1976_SENTMAN_TABLE))
        self.assertTrue(all(len(row) == 4 for row in US1976_SENTMAN_TABLE))

        altitudes = [row[0] for row in US1976_SENTMAN_TABLE]
        self.assertEqual((0, 1000), (altitudes[0], altitudes[-1]))
        self.assertEqual(201, len(set(altitudes)))
        self.assertTrue(all(next_z > z for z, next_z in pairwise(altitudes)))
        self.assertTrue(
            all(
                math.isfinite(float(value))
                for row in US1976_SENTMAN_TABLE
                for value in row
            )
        )
        self.assertEqual((0.0, 1000.0), altitude_range_km())

    def test_representative_low_and_high_altitude_points(self) -> None:
        rows = {row[0]: row[1:] for row in US1976_SENTMAN_TABLE}
        expected = {
            0: (288.150, 340.29, 458.94),
            90: (186.867, 274.04, 369.96),
            100: (195.081, 280.00, 381.36),
            500: (999.236, 633.69, 1215.05),
            1000: (1000.000, 633.94, 2318.12),
        }
        self.assertEqual(expected, {altitude: rows[altitude] for altitude in expected})

    def test_full_grid_matches_pre_migration_column_hashes(self) -> None:
        columns = tuple(zip(*US1976_SENTMAN_TABLE, strict=True))
        formats = (".0f", ".3f", ".2f", ".2f")
        names = tuple(PREVIOUS_COLUMN_SHA256)
        for name, values, value_format in zip(names, columns, formats, strict=True):
            with self.subTest(column=name):
                payload = (
                    "\n".join(format(value, value_format) for value in values) + "\n"
                ).encode()
                self.assertEqual(
                    PREVIOUS_COLUMN_SHA256[name],
                    hashlib.sha256(payload).hexdigest(),
                )

    def test_interpolation_matches_pre_migration_samples(self) -> None:
        expected = {
            87.5: {"T_K": 187.88, "c_ms": 274.78, "Vmean_ms": 370.775},
            102.5: {"T_K": 201.958, "c_ms": 284.85, "Vmean_ms": 389.795},
            997.5: {"T_K": 1000.0, "c_ms": 633.94, "Vmean_ms": 2315.575},
        }
        for altitude_km, sample in expected.items():
            with self.subTest(altitude_km=altitude_km):
                self.assertEqual(sample, sample_at_altitude_km(altitude_km))


if __name__ == "__main__":
    unittest.main()
