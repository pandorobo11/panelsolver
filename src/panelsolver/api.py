"""Small stable in-memory API for the two supported physical models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from panelsolver.app.attitude import ResolvedAttitude
from panelsolver.app.case_identity import validate_case_id
from panelsolver.app.execution import request_from_registry
from panelsolver.core import (
    CommonCasePayload,
    ComponentResult,
    IntegratedCoefficients,
    LocalLoads,
    ModelCasePayload,
    PanelFlowState,
    PanelGeometry,
    PayloadValue,
    ShieldingConfig,
    execute_case,
)
from panelsolver.models import HypersonicModel, ModelRegistry, SentmanModel


def _paths(value: Sequence[str | Path]) -> tuple[str | Path, ...]:
    if isinstance(value, (str, bytes, Path)):
        raise TypeError("stl_paths must be a non-empty sequence of paths")
    paths = tuple(value)
    if not paths:
        raise ValueError("stl_paths must not be empty")
    return paths


def _reference_point(value: Sequence[float]) -> tuple[float, float, float]:
    point = tuple(value)
    if len(point) != 3:
        raise ValueError("moment_reference_stl_m must contain exactly three values")
    return point


def _validate_attitude(value: ResolvedAttitude) -> ResolvedAttitude:
    if not isinstance(value, ResolvedAttitude):
        raise TypeError("attitude must be a ResolvedAttitude")
    return value


@dataclass(frozen=True, slots=True)
class FMFCase:
    """Inputs for one free-molecular-flow calculation using Sentman.

    The model inputs are the resolved Sentman Mode A quantities. Use the
    lower-level model API when atmosphere-based Mode B resolution is required.
    """

    case_id: str
    stl_paths: Sequence[str | Path]
    stl_scale_m_per_unit: float
    attitude: ResolvedAttitude
    Aref_m2: float
    moment_reference_stl_m: Sequence[float]
    Lref_Cl_m: float
    Lref_Cm_m: float
    Lref_Cn_m: float
    speed_ratio: float
    translational_temperature_k: float
    wall_temperature_k: float
    shielding: bool = False
    ray_backend: str = "auto"

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", validate_case_id(self.case_id))
        object.__setattr__(self, "stl_paths", _paths(self.stl_paths))
        object.__setattr__(
            self,
            "moment_reference_stl_m",
            _reference_point(self.moment_reference_stl_m),
        )
        _validate_attitude(self.attitude)


@dataclass(frozen=True, slots=True)
class HypersonicCase:
    """Inputs for one hypersonic pressure-model calculation."""

    case_id: str
    stl_paths: Sequence[str | Path]
    stl_scale_m_per_unit: float
    attitude: ResolvedAttitude
    Aref_m2: float
    moment_reference_stl_m: Sequence[float]
    Lref_Cl_m: float
    Lref_Cm_m: float
    Lref_Cn_m: float
    mach: float
    gamma: float
    windward_equation: str = "newtonian"
    leeward_equation: str = "shield"
    shielding: bool = False
    ray_backend: str = "auto"

    def __post_init__(self) -> None:
        object.__setattr__(self, "case_id", validate_case_id(self.case_id))
        object.__setattr__(self, "stl_paths", _paths(self.stl_paths))
        object.__setattr__(
            self,
            "moment_reference_stl_m",
            _reference_point(self.moment_reference_stl_m),
        )
        _validate_attitude(self.attitude)


@dataclass(frozen=True, slots=True, eq=False)
class SolveResult:
    """In-memory integrated and per-face result with no artifact side effects."""

    coefficients: IntegratedCoefficients
    components: tuple[ComponentResult, ...]
    geometry: PanelGeometry
    flow_state: PanelFlowState
    local_loads: LocalLoads
    case_signature: str
    ray_backend_used: str
    warnings: tuple[str, ...]


def _solve(
    case: FMFCase | HypersonicCase,
    *,
    model: SentmanModel | HypersonicModel,
    model_payload: Mapping[str, PayloadValue],
) -> SolveResult:
    attitude = case.attitude
    common = CommonCasePayload(
        case_id=case.case_id,
        Aref_m2=case.Aref_m2,
        moment_reference_stl_m=np.asarray(
            case.moment_reference_stl_m,
            dtype=np.float64,
        ),
        Lref_Cl_m=case.Lref_Cl_m,
        Lref_Cm_m=case.Lref_Cm_m,
        Lref_Cn_m=case.Lref_Cn_m,
        alpha_t_deg=attitude.alpha_t_deg,
        beta_t_deg=attitude.beta_t_deg,
    )
    model_case = ModelCasePayload(model.model_id, model_payload)
    request = request_from_registry(
        ModelRegistry((model,)),
        common_case=common,
        model_case=model_case,
        stl_paths=case.stl_paths,
        scale_m_per_unit=case.stl_scale_m_per_unit,
        velocity_hat_stl=attitude.velocity_hat_stl,
        shielding=ShieldingConfig(
            enabled=case.shielding,
            ray_backend=case.ray_backend,
        ),
    )
    execution = execute_case(request)
    results = execution.results
    return SolveResult(
        coefficients=results.total,
        components=results.components,
        geometry=results.geometry,
        flow_state=results.flow_state,
        local_loads=results.local_loads,
        case_signature=execution.signature.digest,
        ray_backend_used=execution.shielding.config.effective_backend,
        warnings=execution.warnings,
    )


def solve_fmf(case: FMFCase) -> SolveResult:
    """Solve an FMF case with the Sentman model entirely in memory."""
    if not isinstance(case, FMFCase):
        raise TypeError("case must be an FMFCase")
    return _solve(
        case,
        model=SentmanModel(),
        model_payload={
            "S": case.speed_ratio,
            "Ti_K": case.translational_temperature_k,
            "Tw_K": case.wall_temperature_k,
        },
    )


def solve_hypersonic(case: HypersonicCase) -> SolveResult:
    """Solve a hypersonic case entirely in memory."""
    if not isinstance(case, HypersonicCase):
        raise TypeError("case must be a HypersonicCase")
    return _solve(
        case,
        model=HypersonicModel(),
        model_payload={
            "Mach": case.mach,
            "gamma": case.gamma,
            "windward_eq": case.windward_equation,
            "leeward_eq": case.leeward_equation,
        },
    )


__all__ = (
    "FMFCase",
    "HypersonicCase",
    "SolveResult",
    "solve_fmf",
    "solve_hypersonic",
)
