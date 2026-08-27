"""Explicit assembly-time registry for independent panel-load models."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from panelsolver.core.contracts import (
    LocalLoads,
    ModelCasePayload,
    PanelFlowState,
    PanelGeometry,
    PanelLoadModel,
)
from panelsolver.core.errors import PanelSolverError


class ModelRegistryError(PanelSolverError):
    """Base class for model registration and dispatch contract failures."""


class DuplicateModelError(ModelRegistryError):
    """A registry already contains the requested model ID."""


class UnknownModelError(ModelRegistryError, LookupError):
    """No model is registered for the requested model ID."""


class ModelCaseMismatchError(ModelRegistryError):
    """A model case payload was dispatched to a different model."""


class ModelOutputError(ModelRegistryError):
    """A model returned data that violates the shared output contract."""


class ModelRegistry[ModelT: PanelLoadModel]:
    """Mutable assembly object that dispatches through ``PanelLoadModel`` only.

    Numerical contract objects remain immutable. Registration is intentionally
    explicit and is the sole mutable operation so applications can assemble the
    models they expose without adding concrete-model branches to core.
    """

    def __init__(self, models: Iterable[ModelT] = ()) -> None:
        self._models: dict[str, ModelT] = {}
        for model in models:
            self.register(model)

    @property
    def model_ids(self) -> tuple[str, ...]:
        """Registered IDs in deterministic insertion order."""
        return tuple(self._models)

    def register(self, model: ModelT) -> None:
        """Register one conforming model, rejecting duplicate identities."""
        if not isinstance(model, PanelLoadModel):
            raise ModelRegistryError(
                "model must implement model_id, algorithm_version, "
                "validate_case(), and evaluate()"
            )
        model_id = model.model_id
        algorithm_version = model.algorithm_version
        if (
            not isinstance(model_id, str)
            or not model_id
            or model_id.strip() != model_id
        ):
            raise ModelRegistryError(
                "model_id must be non-empty text without surrounding whitespace"
            )
        if (
            not isinstance(algorithm_version, str)
            or not algorithm_version
            or algorithm_version.strip() != algorithm_version
        ):
            raise ModelRegistryError(
                f"model {model_id!r} must define a non-empty algorithm_version"
            )
        if model_id in self._models:
            raise DuplicateModelError(f"model {model_id!r} is already registered")
        self._models[model_id] = model

    def get(self, model_id: str) -> ModelT:
        """Return one model or raise a stable lookup error."""
        try:
            return self._models[model_id]
        except (KeyError, TypeError) as exc:
            raise UnknownModelError(f"unknown model {model_id!r}") from exc

    def evaluate(
        self,
        geometry: PanelGeometry,
        flow_state: PanelFlowState,
        case: ModelCasePayload,
    ) -> LocalLoads:
        """Validate, dispatch, and verify a model's local-load output."""
        if not isinstance(geometry, PanelGeometry):
            raise ModelRegistryError("geometry must be a PanelGeometry instance")
        if not isinstance(flow_state, PanelFlowState):
            raise ModelRegistryError("flow_state must be a PanelFlowState instance")
        if not isinstance(case, ModelCasePayload):
            raise ModelRegistryError("case must be a ModelCasePayload instance")
        if flow_state.n_faces != geometry.n_faces:
            raise ModelRegistryError("flow_state panel count must match geometry")

        model = self.get(case.model_id)
        if case.model_id != model.model_id:
            raise ModelCaseMismatchError(
                f"case model_id {case.model_id!r} does not match {model.model_id!r}"
            )
        model.validate_case(case)
        loads = model.evaluate(geometry, flow_state, case)
        if not isinstance(loads, LocalLoads):
            raise ModelOutputError(f"model {model.model_id!r} must return LocalLoads")
        if loads.n_faces != geometry.n_faces:
            raise ModelOutputError(
                f"model {model.model_id!r} returned {loads.n_faces} panels; "
                f"expected {geometry.n_faces}"
            )
        if np.any(loads.traction_coeff_stl[flow_state.shielded] != 0.0):
            raise ModelOutputError(
                f"model {model.model_id!r} returned nonzero traction on shielded panels"
            )
        return loads


__all__ = (
    "DuplicateModelError",
    "ModelCaseMismatchError",
    "ModelOutputError",
    "ModelRegistry",
    "ModelRegistryError",
    "UnknownModelError",
)
