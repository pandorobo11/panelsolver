"""Model-independent attitude and coordinate-frame transforms."""

from __future__ import annotations

import math

import numpy as np

from ._validation import float_array, real_scalar, validate_unit_vectors
from .errors import ContractValueError, NonFiniteError, ShapeError


def stability_alpha_deg(velocity_hat_stl: object) -> float:
    """Resolve the common stability angle from a unit STL flow direction.

    A projection at or below 64 float64 eps uses the common zero-angle frame.
    This does not modify the flow direction used for physical calculations.
    """
    velocity = float_array(velocity_hat_stl, field="velocity_hat_stl", shape=(3,))
    validate_unit_vectors(velocity, field="velocity_hat_stl")
    x, _, z = (float(value) for value in velocity)
    if math.hypot(x, z) <= 64.0 * np.finfo(np.float64).eps:
        return 0.0
    angle = math.degrees(math.atan2(z, x))
    if angle >= 180.0:
        angle = -180.0
    return 0.0 if angle == 0.0 else angle


def stl_to_body(vectors_stl: object) -> np.ndarray:
    """Transform STL-axis vectors to body axes without changing their shape.

    The trailing dimension must have length three; any number of leading
    dimensions is preserved. The verified axis mapping is
    ``body = (-x_stl, +y_stl, -z_stl)``.
    """
    vectors = _vector_array(vectors_stl, field="vectors_stl")
    return np.ascontiguousarray(vectors * np.array([-1.0, 1.0, -1.0], dtype=np.float64))


def body_to_stability(
    vectors_body: object,
    *,
    alpha_stability_deg: float,
) -> np.ndarray:
    """Rotate body-axis vectors into stability axes at derived ``alpha_stability_deg``.

    The trailing dimension must have length three; any number of leading
    dimensions is preserved. Positive ``alpha_stability_deg`` uses a right-handed rotation
    about ``+Y_body``.
    """
    vectors = _vector_array(vectors_body, field="vectors_body")
    alpha = math.radians(real_scalar(alpha_stability_deg, field="alpha_stability_deg"))
    cosine = math.cos(alpha)
    sine = math.sin(alpha)
    rotation = np.array(
        [
            [cosine, 0.0, sine],
            [0.0, 1.0, 0.0],
            [-sine, 0.0, cosine],
        ],
        dtype=np.float64,
    )
    return np.ascontiguousarray(vectors @ rotation.T)


def rotation_matrix_y_rad(alpha_rad: float) -> np.ndarray:
    """Return the pinned right-handed rotation matrix about ``+Y``."""
    alpha = real_scalar(alpha_rad, field="alpha_rad")
    cosine = math.cos(alpha)
    sine = math.sin(alpha)
    return np.array(
        [
            [cosine, 0.0, sine],
            [0.0, 1.0, 0.0],
            [-sine, 0.0, cosine],
        ],
        dtype=np.float64,
    )


def _vector_array(value: object, *, field: str) -> np.ndarray:
    try:
        raw = np.asarray(value)
    except (TypeError, ValueError) as exc:
        raise ContractValueError(
            field,
            "must be a rectangular real-valued vector array",
        ) from exc
    if raw.dtype.kind not in "iuf":
        raise ContractValueError(field, "must be a real-valued vector array")
    if raw.ndim == 0 or raw.shape[-1] != 3:
        raise ShapeError(field, expected=("...", 3), actual=raw.shape)
    array = np.array(raw, dtype=np.float64, copy=True, order="C")
    if not np.isfinite(array).all():
        raise NonFiniteError(field)
    return array


__all__ = (
    "body_to_stability",
    "rotation_matrix_y_rad",
    "stability_alpha_deg",
    "stl_to_body",
)
