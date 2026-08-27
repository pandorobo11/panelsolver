"""Model-independent attitude and coordinate-frame transforms."""

from __future__ import annotations

import math

import numpy as np

from ._validation import real_scalar
from .errors import ContractValueError, NonFiniteError, ShapeError

_ZERO_DIRECTION_ATOL = 1.0e-14


def velocity_hat_stl_from_tangent_angles(
    alpha_t_deg: float,
    beta_t_deg: float,
) -> np.ndarray:
    """Return the STL-frame unit direction for resolved tangent angles.

    The arguments are already-resolved ``alpha_t`` and ``beta_t`` values. This
    function deliberately does not parse a legacy attitude mode or impose
    either product's public angle-domain policy.
    """
    alpha = math.radians(real_scalar(alpha_t_deg, field="alpha_t_deg"))
    beta = math.radians(real_scalar(beta_t_deg, field="beta_t_deg"))
    cos_alpha = math.cos(alpha)
    cos_beta = math.cos(beta)
    velocity = np.array(
        [
            cos_alpha * cos_beta,
            -math.sin(beta) * cos_alpha,
            math.sin(alpha) * cos_beta,
        ],
        dtype=np.float64,
    )
    norm = float(np.linalg.norm(velocity))
    if norm < _ZERO_DIRECTION_ATOL:
        raise ContractValueError(
            "velocity_hat_stl",
            "resolved tangent angles must not produce a zero direction",
        )
    return velocity / norm


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
    alpha_t_deg: float,
) -> np.ndarray:
    """Rotate body-axis vectors into stability axes at resolved ``alpha_t``.

    The trailing dimension must have length three; any number of leading
    dimensions is preserved. Positive ``alpha_t`` uses a right-handed rotation
    about ``+Y_body``.
    """
    vectors = _vector_array(vectors_body, field="vectors_body")
    alpha = math.radians(real_scalar(alpha_t_deg, field="alpha_t_deg"))
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
    "stl_to_body",
    "velocity_hat_stl_from_tangent_angles",
)
