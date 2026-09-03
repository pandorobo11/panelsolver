#!/usr/bin/env python3
"""Generate the package-internal Sentman US1976 table from pinned PDAS."""

from __future__ import annotations

import argparse
import difflib
import hashlib
import importlib.util
import math
import sys
from pathlib import Path
from types import ModuleType

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_SOURCE = (
    REPOSITORY_ROOT / "tools" / "reference" / "pdas" / "bigtables_v1_5.py"
)
GENERATED_MODULE = (
    REPOSITORY_ROOT / "src" / "panelsolver" / "models" / "_sentman_atmosphere_data.py"
)
REFERENCE_SOURCE_SHA256 = (
    "11e82d35d66a61c4326acf04fcad0c9ab471112721151b65cfdf4faff43f9994"
)
UPSTREAM_BIGTABLES_SHA256 = (
    "eca87577139ac3b2845d1d4eca91604ac278a491918979f2d2316bf88a9a3a28"
)


def _load_reference() -> ModuleType:
    source_bytes = REFERENCE_SOURCE.read_bytes()
    actual_hash = hashlib.sha256(source_bytes).hexdigest()
    if actual_hash != REFERENCE_SOURCE_SHA256:
        raise RuntimeError(
            "PDAS reference snapshot hash mismatch: "
            f"expected {REFERENCE_SOURCE_SHA256}, got {actual_hash}"
        )

    spec = importlib.util.spec_from_file_location(
        "_pdas_bigtables_v1_5_reference",
        REFERENCE_SOURCE,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load PDAS reference snapshot: {REFERENCE_SOURCE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _published_row(
    pdas: ModuleType, altitude_km: int
) -> tuple[int, float, float, float]:
    altitude = float(altitude_km)
    if altitude > 86.0:
        temperature_ratio = pdas.KineticTemperature(altitude) / pdas.TZERO
    else:
        _, _, temperature_ratio = pdas.LowerAtmosphere(altitude)

    molecular_weight_ratio = pdas.MolecularWeight(altitude) / pdas.MOLWT_ZERO
    mean_speed_ratio = math.sqrt(temperature_ratio / molecular_weight_ratio)

    # These formats are the PDAS bigtables.py WriteF3Cell/WriteF2Cell formats.
    temperature_K = float(format(temperature_ratio * pdas.TZERO, ".3f"))
    speed_of_sound_ms = float(
        format(pdas.ASOUNDZERO * math.sqrt(temperature_ratio), ".2f")
    )
    mean_molecular_speed_ms = float(
        format(pdas.PART_SPEED_ZERO * mean_speed_ratio, ".2f")
    )
    return (
        altitude_km,
        temperature_K,
        speed_of_sound_ms,
        mean_molecular_speed_ms,
    )


def generate_rows() -> tuple[tuple[int, float, float, float], ...]:
    """Return the 0--1000 km PDAS published-value grid used by Sentman."""
    pdas = _load_reference()
    return tuple(_published_row(pdas, altitude) for altitude in range(0, 1001, 5))


def render_module() -> str:
    """Render deterministic Python source for the package-internal table."""
    lines = [
        '"""Generated US1976 published values used by the Sentman model.',
        "",
        "Do not edit by hand. Regenerate with:",
        "",
        "    python scripts/generate_us1976_sentman_table.py",
        "",
        "Source: PDAS public-domain bigtables.py v1.5, via the pinned minimal",
        "reference snapshot. Temperature uses the upstream 3-decimal display",
        "precision; both speeds use the upstream 2-decimal display precision.",
        f"Upstream bigtables.py SHA-256: {UPSTREAM_BIGTABLES_SHA256}",
        '"""',
        "",
        "US1976_SENTMAN_TABLE = (",
        "    # geometric_altitude_km, temperature_K, speed_of_sound_ms, mean_molecular_speed_ms",
    ]
    for altitude, temperature, sound_speed, mean_speed in generate_rows():
        lines.append(
            f"    ({altitude}, {temperature:.3f}, {sound_speed:.2f}, {mean_speed:.2f}),"
        )
    lines.extend(
        (
            ")",
            "",
            "",
            '__all__ = ("US1976_SENTMAN_TABLE",)',
            "",
        )
    )
    return "\n".join(lines)


def _check(expected: str) -> int:
    current = GENERATED_MODULE.read_text(encoding="utf-8")
    if current == expected:
        print(f"US1976 Sentman table is current: {GENERATED_MODULE}")
        return 0

    print(f"US1976 Sentman table is stale: {GENERATED_MODULE}", file=sys.stderr)
    sys.stderr.writelines(
        difflib.unified_diff(
            current.splitlines(keepends=True),
            expected.splitlines(keepends=True),
            fromfile=str(GENERATED_MODULE),
            tofile="regenerated",
        )
    )
    return 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed generated module without modifying it",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    expected = render_module()
    if args.check:
        return _check(expected)
    GENERATED_MODULE.write_text(expected, encoding="utf-8", newline="\n")
    print(f"Generated {len(generate_rows())} US1976 rows: {GENERATED_MODULE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
