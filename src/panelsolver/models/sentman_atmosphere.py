"""US1976 atmosphere sampling owned by the Sentman physical model."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from ._sentman_atmosphere_data import US1976_SENTMAN_TABLE

_TABLE = np.asarray(US1976_SENTMAN_TABLE, dtype=np.float64)

if _TABLE.ndim != 2 or _TABLE.shape[1] != 4:
    raise RuntimeError("generated US1976 Sentman table must have four columns")
if not np.isfinite(_TABLE).all():
    raise RuntimeError("generated US1976 Sentman table must contain finite values")
_TABLE.setflags(write=False)
_ALTITUDE_KM = _TABLE[:, 0]
_TEMPERATURE_K = _TABLE[:, 1]
_SPEED_OF_SOUND_MS = _TABLE[:, 2]
_MEAN_MOLECULAR_SPEED_MS = _TABLE[:, 3]

if not np.all(np.diff(_ALTITUDE_KM) > 0.0):
    raise RuntimeError("generated US1976 altitudes must be strictly increasing")


def altitude_range_km() -> tuple[float, float]:
    """Return the pinned table's inclusive geometric-altitude range."""
    return float(_ALTITUDE_KM[0]), float(_ALTITUDE_KM[-1])


def sample_at_altitude_km(altitude_km: float) -> dict[str, float]:
    """Linearly interpolate the exact atmosphere columns used by legacy FMF."""
    altitude = float(altitude_km)
    if not math.isfinite(altitude):
        raise ValueError(f"Altitude_km must be finite, got {altitude!r}")
    minimum, maximum = altitude_range_km()
    if altitude < minimum or altitude > maximum:
        raise ValueError(f"Altitude_km={altitude} out of range [{minimum}, {maximum}]")
    return {
        "T_K": float(np.interp(altitude, _ALTITUDE_KM, _TEMPERATURE_K)),
        "c_ms": float(np.interp(altitude, _ALTITUDE_KM, _SPEED_OF_SOUND_MS)),
        "Vmean_ms": float(np.interp(altitude, _ALTITUDE_KM, _MEAN_MOLECULAR_SPEED_MS)),
    }


def mean_to_most_probable_speed(mean_speed_ms: float) -> float:
    """Convert mean molecular speed to the legacy most-probable speed."""
    return (math.sqrt(math.pi) / 2.0) * float(mean_speed_ms)


def load_us1976_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return defensive legacy-shaped views of the shared atmosphere table."""
    return (
        pd.DataFrame({"Z": _ALTITUDE_KM, "T": _TEMPERATURE_K, "c": _SPEED_OF_SOUND_MS}),
        pd.DataFrame({"Z": _ALTITUDE_KM, "V": _MEAN_MOLECULAR_SPEED_MS}),
    )


__all__ = (
    "altitude_range_km",
    "load_us1976_tables",
    "mean_to_most_probable_speed",
    "sample_at_altitude_km",
)
