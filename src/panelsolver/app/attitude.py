"""Full-direction attitude inputs with shared stability-axis resolution."""

from __future__ import annotations

import math
from dataclasses import dataclass
from dataclasses import field as dataclass_field

import numpy as np

from panelsolver.core.frames import stability_alpha_deg

ATTITUDE_INPUT_VALUES = frozenset({"beta_tan", "beta_sin", "bank"})


@dataclass(frozen=True, slots=True, eq=False)
class ResolvedAttitude:
    """Authoritative unit direction, original inputs, and derived stability angle."""

    velocity_hat_stl: np.ndarray
    alpha_deg: float
    beta_or_bank_deg: float
    input_mode: str
    alpha_stability_deg: float = dataclass_field(init=False)

    def __post_init__(self) -> None:
        try:
            raw_velocity = np.asarray(self.velocity_hat_stl)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "velocity_hat_stl must be a real numeric vector with shape (3,)"
            ) from exc
        if raw_velocity.shape != (3,) or raw_velocity.dtype.kind not in "iuf":
            raise ValueError(
                "velocity_hat_stl must be a real numeric vector with shape (3,)"
            )
        try:
            velocity = np.asarray(raw_velocity, dtype=np.float64)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                "velocity_hat_stl must be a real numeric vector with shape (3,)"
            ) from exc
        if not np.isfinite(velocity).all():
            raise ValueError("velocity_hat_stl must be a finite vector with shape (3,)")
        scale = float(np.max(np.abs(velocity)))
        if scale == 0.0:
            raise ValueError("velocity_hat_stl must have nonzero norm")
        scaled = velocity / scale
        scaled_norm = math.hypot(*(float(component) for component in scaled))
        normalized = scaled / scaled_norm
        normalized_norm = math.hypot(*(float(component) for component in normalized))
        if not np.isfinite(normalized).all() or not math.isclose(
            normalized_norm,
            1.0,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            raise ValueError("velocity_hat_stl must normalize to a finite unit vector")
        normalized[normalized == 0.0] = 0.0
        immutable = np.frombuffer(normalized.tobytes(), dtype=np.float64)
        object.__setattr__(self, "velocity_hat_stl", immutable)
        for field in ("alpha_deg", "beta_or_bank_deg"):
            value = getattr(self, field)
            if isinstance(value, (bool, np.bool_)):
                raise ValueError(  # noqa: TRY004 - one public validation boundary
                    f"{field} must be a finite real angle"
                )
            try:
                angle = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"{field} must be a finite real angle") from exc
            if not math.isfinite(angle):
                raise ValueError(f"{field} must be a finite real angle")
            object.__setattr__(self, field, angle)
        object.__setattr__(self, "input_mode", resolve_attitude_mode(self.input_mode))
        object.__setattr__(self, "alpha_stability_deg", stability_alpha_deg(immutable))


def resolve_attitude_mode(value: str | None) -> str:
    if value is None:
        mode = "beta_tan"
    elif not isinstance(value, str):
        raise TypeError("attitude_input must be text or None")
    else:
        mode = value.strip().lower() or "beta_tan"
    if mode not in ATTITUDE_INPUT_VALUES:
        raise ValueError(
            f"Invalid attitude_input: '{value}'. "
            "Expected one of: beta_tan, beta_sin, bank."
        )
    return mode


def _sincos_deg(angle_deg: float) -> tuple[float, float]:
    # remainder avoids adding 180 before reduction, which can round a value
    # immediately adjacent to 90 onto the singular boundary.
    angle = math.remainder(angle_deg, 360.0)
    exact = {
        0.0: (0.0, 1.0),
        90.0: (1.0, 0.0),
        -90.0: (-1.0, 0.0),
        180.0: (0.0, -1.0),
        -180.0: (0.0, -1.0),
    }
    if angle in exact:
        return exact[angle]
    radians = math.radians(angle)
    return math.sin(radians), math.cos(radians)


def resolve_attitude(
    alpha_deg: float,
    beta_or_bank_deg: float,
    attitude_input: str | None = None,
) -> ResolvedAttitude:
    """Resolve original degree inputs without reconstructing flow from angles."""
    mode = resolve_attitude_mode(attitude_input)
    if isinstance(alpha_deg, (bool, np.bool_)) or isinstance(
        beta_or_bank_deg, (bool, np.bool_)
    ):
        raise ValueError("attitude angles must be finite real numbers")  # noqa: TRY004
    alpha_in = float(alpha_deg)
    beta_in = float(beta_or_bank_deg)
    if not math.isfinite(alpha_in) or not math.isfinite(beta_in):
        raise ValueError("attitude angles must be finite")
    if mode != "bank" and not -90.0 <= beta_in <= 90.0:
        raise ValueError(
            "beta_or_bank_deg must be between -90 and 90 degrees inclusive "
            "for beta_tan or beta_sin."
        )
    sin_alpha, cos_alpha = _sincos_deg(alpha_in)
    sin_beta, cos_beta = _sincos_deg(beta_in)
    if mode == "bank":
        velocity = (cos_alpha, -sin_alpha * sin_beta, sin_alpha * cos_beta)
    elif mode == "beta_sin":
        velocity = (cos_alpha * cos_beta, -sin_beta, sin_alpha * cos_beta)
    else:
        if cos_alpha == 0.0 and cos_beta == 0.0:
            raise ValueError(
                "beta_tan direction is undefined when alpha_deg is an odd "
                "multiple of 90 and beta_or_bank_deg is +90 or -90. "
                "Use beta_sin or bank to specify the direction."
            )
        velocity = (
            cos_alpha * cos_beta,
            -abs(cos_alpha) * sin_beta,
            sin_alpha * cos_beta,
        )
    return ResolvedAttitude(np.asarray(velocity), alpha_in, beta_in, mode)


__all__ = (
    "ATTITUDE_INPUT_VALUES",
    "ResolvedAttitude",
    "resolve_attitude",
    "resolve_attitude_mode",
)
