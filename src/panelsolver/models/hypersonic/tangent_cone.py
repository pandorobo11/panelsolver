from __future__ import annotations

"""Tangent-cone pressure model based on the Taylor-Maccoll equation."""

import math
from functools import lru_cache

import numpy as np
from scipy.integrate import solve_ivp
from scipy.interpolate import PchipInterpolator

from .modified_newtonian import modified_newtonian_cp_max
from .tangent_wedge import _oblique_theta_from_beta

_TM_N_BETA = 220
_TM_ODE_RTOL = 1.0e-8
_TM_ODE_ATOL = 1.0e-10
_TM_ODE_MAX_STEP = 2.0e-3


def _nondim_speed_from_mach(Mach: float, gamma: float) -> float:
    """Return ``V/Vmax`` from Mach using Anderson Eq. (13.81)."""
    m = float(Mach)
    g = float(gamma)
    return float((1.0 + 2.0 / ((g - 1.0) * m * m)) ** -0.5)


def _mach_from_nondim_speed(v_prime: float, gamma: float) -> float:
    """Return Mach from ``V/Vmax`` using Anderson Eq. (13.81)."""
    g = float(gamma)
    vp = min(max(float(v_prime), 1.0e-12), 1.0 - 1.0e-12)
    denom = (g - 1.0) * (1.0 / (vp * vp) - 1.0)
    if denom <= 0.0:
        return float("inf")
    return float(math.sqrt(2.0 / denom))


def _taylor_maccoll_rhs(
    theta: float, vr: float, vtheta: float, gamma: float
) -> tuple[float, float]:
    """Taylor-Maccoll first-order system in nondimensional form."""
    th = max(float(theta), 1.0e-8)
    g = float(gamma)
    v2 = float(vr * vr + vtheta * vtheta)
    a = 0.5 * (g - 1.0) * max(1.0 - v2, 1.0e-12)
    denom = a - vtheta * vtheta
    if abs(denom) < 1.0e-12:
        denom = math.copysign(1.0e-12, denom if denom != 0.0 else 1.0)
    dvr_dtheta = vtheta
    dvt_dtheta = (vr * vtheta * vtheta - a * (2.0 * vr + vtheta / math.tan(th))) / denom
    return float(dvr_dtheta), float(dvt_dtheta)


def _taylor_maccoll_event_vtheta_zero(_theta: float, y: np.ndarray) -> float:
    """Surface is reached when the circumferential velocity becomes zero."""
    return float(y[1])


_taylor_maccoll_event_vtheta_zero.terminal = True
_taylor_maccoll_event_vtheta_zero.direction = 0


def _integrate_taylor_maccoll_to_surface(
    Mach: float,
    gamma: float,
    beta_s: float,
) -> tuple[float, float] | None:
    """Integrate from shock to cone and return ``(theta_c, cp_c)``.

    Uses ``scipy.integrate.solve_ivp(..., method="LSODA")`` for adaptive stepping.
    """
    M = float(Mach)
    g = float(gamma)
    beta = float(beta_s)
    delta = _oblique_theta_from_beta(M, g, beta)
    if delta <= 0.0:
        return None

    mn1 = M * math.sin(beta)
    if mn1 <= 1.0:
        return None
    mn2_sq = (1.0 + 0.5 * (g - 1.0) * mn1 * mn1) / (g * mn1 * mn1 - 0.5 * (g - 1.0))
    if mn2_sq <= 0.0:
        return None
    sin_term = math.sin(beta - delta)
    if abs(sin_term) < 1.0e-12:
        return None
    m2 = math.sqrt(mn2_sq) / sin_term
    if not math.isfinite(m2) or m2 <= 0.0:
        return None

    p2_p1 = 1.0 + (2.0 * g / (g + 1.0)) * (mn1 * mn1 - 1.0)
    v2_prime = _nondim_speed_from_mach(m2, g)
    angle = beta - delta
    vr = v2_prime * math.cos(angle)
    vtheta = -v2_prime * math.sin(angle)
    try:
        sol = solve_ivp(
            fun=lambda theta, y: _taylor_maccoll_rhs(
                theta, float(y[0]), float(y[1]), g
            ),
            t_span=(beta, 1.0e-6),
            y0=np.array([vr, vtheta], dtype=float),
            method="LSODA",
            rtol=_TM_ODE_RTOL,
            atol=_TM_ODE_ATOL,
            events=_taylor_maccoll_event_vtheta_zero,
            max_step=_TM_ODE_MAX_STEP,
        )
    except Exception:
        return None

    if (not sol.success) or (len(sol.t_events) == 0) or (len(sol.t_events[0]) == 0):
        return None

    theta_c = float(sol.t_events[0][0])
    vr_c = float(sol.y_events[0][0][0])
    v_c = min(max(abs(vr_c), 1.0e-12), 1.0 - 1.0e-12)
    m_c = _mach_from_nondim_speed(v_c, g)
    if not math.isfinite(m_c) or m_c <= 0.0:
        return None
    p_c_p2 = (
        (1.0 + 0.5 * (g - 1.0) * m2 * m2) / (1.0 + 0.5 * (g - 1.0) * m_c * m_c)
    ) ** (g / (g - 1.0))
    p_c_p1 = p2_p1 * p_c_p2
    cp_c = (2.0 / (g * M * M)) * (p_c_p1 - 1.0)
    return float(theta_c), float(max(cp_c, 0.0))


@lru_cache(maxsize=128)
def _tangent_cone_attached_table(
    Mach: float, gamma: float
) -> tuple[np.ndarray, np.ndarray]:
    """Build attached-branch table ``theta -> Cp`` using Taylor-Maccoll integration."""
    M = float(Mach)
    g = float(gamma)
    if M <= 1.0:
        raise ValueError(f"tangent_cone requires Mach > 1, got {M}")
    if g <= 1.0:
        raise ValueError(f"gamma must be > 1, got {g}")

    mu = math.asin(1.0 / M)
    betas = np.linspace(mu + 1.0e-4, 0.5 * math.pi - 1.0e-3, _TM_N_BETA, dtype=float)
    theta_list: list[float] = []
    cp_list: list[float] = []
    for beta in betas:
        solved = _integrate_taylor_maccoll_to_surface(M, g, float(beta))
        if solved is None:
            continue
        theta_c, cp_c = solved
        if theta_c <= 0.0 or theta_c >= 0.5 * math.pi:
            continue
        if not (math.isfinite(theta_c) and math.isfinite(cp_c)):
            continue
        theta_list.append(float(theta_c))
        cp_list.append(float(max(cp_c, 0.0)))

    if len(theta_list) < 6:
        raise RuntimeError(
            "Failed to build tangent-cone table from Taylor-Maccoll integration."
        )

    theta_raw = np.asarray(theta_list, dtype=float)
    cp_raw = np.asarray(cp_list, dtype=float)
    # theta(beta) is multi-valued (weak/strong branches). Keep only weak branch:
    # from Mach angle to the first global theta peak.
    i_peak = int(np.argmax(theta_raw))
    theta_weak = theta_raw[: i_peak + 1]
    cp_weak = cp_raw[: i_peak + 1]

    theta_out = [0.0]
    cp_out = [0.0]
    prev_theta = -1.0
    for th, cp in zip(theta_weak, cp_weak):
        th_f = float(th)
        cp_f = float(cp)
        if th_f <= prev_theta + 1.0e-7:
            continue
        theta_out.append(th_f)
        cp_out.append(cp_f)
        prev_theta = th_f

    theta_arr = np.asarray(theta_out, dtype=float)
    cp_arr = np.maximum.accumulate(np.asarray(cp_out, dtype=float))
    return theta_arr, cp_arr


@lru_cache(maxsize=128)
def _tangent_cone_detach_limit(Mach: float, gamma: float) -> tuple[float, float]:
    """Return ``(theta_max, cp_crit)`` on the attached tangent-cone branch."""
    theta, cp = _tangent_cone_attached_table(float(Mach), float(gamma))
    return float(theta[-1]), float(cp[-1])


@lru_cache(maxsize=128)
def _tangent_cone_attached_pchip(Mach: float, gamma: float) -> PchipInterpolator:
    """Return cached PCHIP interpolator for attached ``theta -> Cp`` table."""
    theta, cp = _tangent_cone_attached_table(float(Mach), float(gamma))
    return PchipInterpolator(theta, cp, extrapolate=True)


def tangent_cone_pressure_coefficient(
    Mach: float,
    gamma: float,
    deltar: float | np.ndarray,
    *,
    cp_cap: float | None = None,
) -> np.ndarray:
    """Return tangent-cone ``Cp`` for one or many turning angles.

    Args:
        Mach: Freestream Mach number (>1).
        gamma: Ratio of specific heats (>1).
        deltar: Local turning angle(s) [rad].
        cp_cap: Optional ``Cp`` cap (defaults to modified-Newtonian ``Cp_max``).

    Returns:
        ``Cp`` array with the same shape as ``np.asarray(deltar)``.
    """
    M = float(Mach)
    g = float(gamma)
    theta_all = np.asarray(deltar, dtype=float)
    if M <= 1.0:
        raise ValueError(f"tangent_cone requires Mach > 1, got {M}")
    if g <= 1.0:
        raise ValueError(f"gamma must be > 1, got {g}")

    out = np.zeros_like(theta_all, dtype=float)
    windward = theta_all > 0.0
    if not np.any(windward):
        return out

    cap = (
        float(cp_cap)
        if cp_cap is not None
        else modified_newtonian_cp_max(Mach=M, gamma=g)
    )
    theta_table, cp_table = _tangent_cone_attached_table(M, g)
    pchip = _tangent_cone_attached_pchip(M, g)
    theta_max = float(theta_table[-1])
    cp_crit = float(min(max(cp_table[-1], 0.0), cap))

    theta = theta_all[windward]
    cp_w = np.zeros_like(theta, dtype=float)
    attached = theta <= theta_max
    if np.any(attached):
        cp_a = pchip(theta[attached])
        cp_w[attached] = np.clip(cp_a, 0.0, cap)

    detached = ~attached
    if np.any(detached):
        s2 = np.square(np.sin(theta[detached]))
        s0_2 = math.sin(theta_max) ** 2
        denom = max(1.0 - s0_2, 1.0e-12)
        w = np.clip((s2 - s0_2) / denom, 0.0, 1.0)
        cp_w[detached] = cp_crit + (cap - cp_crit) * w

    out[windward] = np.clip(cp_w, 0.0, cap)
    return out
