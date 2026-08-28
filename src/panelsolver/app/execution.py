"""Application assembly for the model-neutral one-case execution engine."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np

from panelsolver.core import (
    CaseExecutionRequest,
    CommonCasePayload,
    ExecutablePanelLoadModel,
    MeshValidationPolicy,
    ModelCasePayload,
    ShieldingConfig,
)
from panelsolver.models import (
    HypersonicModel,
    ModelRegistry,
    SentmanModel,
)


def default_model_registry() -> ModelRegistry[ExecutablePanelLoadModel]:
    """Return the registry of built-in Sentman and Hypersonic models."""
    return ModelRegistry((SentmanModel(), HypersonicModel()))


def request_from_registry[ModelT: ExecutablePanelLoadModel](
    registry: ModelRegistry[ModelT],
    *,
    common_case: CommonCasePayload,
    model_case: ModelCasePayload,
    stl_paths: Sequence[str | Path],
    scale_m_per_unit: float,
    velocity_hat_stl: np.ndarray,
    shielding: ShieldingConfig | None = None,
    mesh_validation_policy: MeshValidationPolicy | str = MeshValidationPolicy.STRICT,
) -> CaseExecutionRequest:
    """Select a registered model without introducing a concrete-model branch."""
    if not isinstance(registry, ModelRegistry):
        raise TypeError("registry must be a ModelRegistry instance")
    return CaseExecutionRequest(
        model=registry.get(model_case.model_id),
        common_case=common_case,
        model_case=model_case,
        stl_paths=stl_paths,
        scale_m_per_unit=scale_m_per_unit,
        velocity_hat_stl=velocity_hat_stl,
        shielding=ShieldingConfig() if shielding is None else shielding,
        mesh_validation_policy=mesh_validation_policy,
    )


__all__ = ("default_model_registry", "request_from_registry")
