"""Shared attitude parsing with one supported principal domain."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

ATTITUDE_INPUT_VALUES = frozenset({"beta_tan", "beta_sin", "bank"})
_ZERO_DIRECTION_ATOL = 1.0e-14


@dataclass(frozen=True, slots=True, eq=False)
class ResolvedAttitude:
    """One public attitude input resolved to the tangent-angle convention."""

    velocity_hat_stl: np.ndarray
    alpha_t_deg: float
    beta_t_deg: float
    input_mode: str

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
        if scale < _ZERO_DIRECTION_ATOL:
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
        immutable = np.frombuffer(normalized.tobytes(), dtype=np.float64)
        object.__setattr__(self, "velocity_hat_stl", immutable)
        for field in ("alpha_t_deg", "beta_t_deg"):
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


def _unit(values: tuple[float, float, float], *, message: str) -> np.ndarray:
    velocity = np.asarray(values, dtype=np.float64)
    norm = float(np.linalg.norm(velocity))
    if norm < _ZERO_DIRECTION_ATOL:
        raise ValueError(message)
    return velocity / norm


def resolve_attitude(
    alpha_deg: float,
    beta_or_bank_deg: float,
    attitude_input: str | None = None,
) -> ResolvedAttitude:
    """Resolve a supported attitude to the shared tangent-angle convention."""
    mode = resolve_attitude_mode(attitude_input)
    if isinstance(alpha_deg, (bool, np.bool_)) or isinstance(
        beta_or_bank_deg, (bool, np.bool_)
    ):
        raise ValueError(  # noqa: TRY004 - one public validation boundary
            "attitude angles must be finite real numbers"
        )
    alpha_in = float(alpha_deg)
    beta_in = float(beta_or_bank_deg)
    if not math.isfinite(alpha_in) or not math.isfinite(beta_in):
        raise ValueError("attitude angles must be finite")

    if mode == "beta_tan":
        if not -90.0 < alpha_in < 90.0 or not -90.0 < beta_in < 90.0:
            raise ValueError(
                "attitude_input='beta_tan' requires alpha_deg and "
                "beta_or_bank_deg to be strictly between -90 and 90 degrees."
            )
        alpha_rad = math.radians(alpha_in)
        beta_rad = math.radians(beta_in)
        cos_alpha = math.cos(alpha_rad)
        velocity = _unit(
            (
                cos_alpha * math.cos(beta_rad),
                -math.sin(beta_rad) * cos_alpha,
                math.sin(alpha_rad) * math.cos(beta_rad),
            ),
            message="Invalid alpha/beta leading to zero direction.",
        )
        return ResolvedAttitude(velocity, alpha_in, beta_in, mode)

    if mode == "bank":
        alpha_rad = math.radians(alpha_in)
        bank_rad = math.radians(beta_in)
        velocity = _unit(
            (
                math.cos(alpha_rad),
                -math.sin(alpha_rad) * math.sin(bank_rad),
                math.sin(alpha_rad) * math.cos(bank_rad),
            ),
            message="Invalid bank-angle inputs leading to zero direction.",
        )
    else:
        if not -90.0 < alpha_in < 90.0:
            raise ValueError(
                "attitude_input='beta_sin' requires alpha_deg to be "
                "strictly between -90 and 90 degrees."
            )
        alpha_rad = math.radians(alpha_in)
        beta_sin_rad = math.radians(beta_in)
        tangent_alpha = math.tan(alpha_rad)
        sin_beta = math.sin(beta_sin_rad)
        x_squared = (1.0 - sin_beta * sin_beta) / (1.0 + tangent_alpha * tangent_alpha)
        if x_squared < -1.0e-14:
            raise ValueError("Inconsistent alpha_t/beta_s inputs.")
        x_squared = max(x_squared, 0.0)
        x_value = (1.0 if math.cos(alpha_rad) >= 0.0 else -1.0) * math.sqrt(x_squared)
        velocity = _unit(
            (x_value, -sin_beta, tangent_alpha * x_value),
            message="Invalid beta-sin inputs leading to zero direction.",
        )

    alpha_t_deg = math.degrees(math.atan2(float(velocity[2]), float(velocity[0])))
    beta_t_deg = math.degrees(math.atan2(float(-velocity[1]), float(velocity[0])))
    return ResolvedAttitude(velocity, alpha_t_deg, beta_t_deg, mode)


__all__ = (
    "ATTITUDE_INPUT_VALUES",
    "ResolvedAttitude",
    "resolve_attitude",
    "resolve_attitude_mode",
)
