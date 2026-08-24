"""One-case model-neutral execution through the shared numerical pipeline."""

from __future__ import annotations

from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

import numpy as np

from ._validation import (
    float_array,
    nonempty_text,
    real_scalar,
    validate_unit_vectors,
)
from .aggregation import assemble_common_results
from .contracts import (
    CommonCasePayload,
    CommonResults,
    LocalLoads,
    ModelCasePayload,
    PanelFlowState,
    PanelGeometry,
    PanelLoadModel,
)
from .errors import PanelSolverError
from .frames import velocity_hat_stl_from_tangent_angles
from .mesh import PanelMesh
from .mesh_loading import (
    LoadedPanelMesh,
    MeshLoadError,
    MeshValidationPolicy,
    _normalize_policy,
    load_panel_mesh,
)
from .shielding import ShieldingConfig, ShieldingResult, compute_shielding
from .signatures import CaseSignature, build_case_signature


class ExecutionError(PanelSolverError, ValueError):
    """Shared execution input or state is invalid."""


class ExecutionModelError(ExecutionError):
    """A model identity or output violates the execution boundary."""


@runtime_checkable
class ExecutablePanelLoadModel(PanelLoadModel, Protocol):
    """Panel-load model with its model-owned normalized signature payload."""

    def signature_payload(self, case: ModelCasePayload) -> Mapping[str, object]:
        """Return the normalized model-case portion of ADR 0005."""
        ...


@dataclass(frozen=True, slots=True)
class SchedulingAffinityHint:
    """Performance-only identity for likely process-local cache reuse.

    This hint never participates in a numerical cache key, case signature, or
    correctness decision.  ``priority`` only orders hits for the same class of
    primary scheduler work; larger values represent more valuable reuse.
    """

    identity: Hashable
    priority: int = 1

    def __post_init__(self) -> None:
        try:
            hash(self.identity)
        except TypeError as exc:
            raise TypeError("scheduling affinity identity must be hashable") from exc
        if isinstance(self.priority, (bool, np.bool_)) or not isinstance(
            self.priority,
            (int, np.integer),
        ):
            raise TypeError("scheduling affinity priority must be an integer")
        priority = int(self.priority)
        if priority < 1:
            raise ValueError("scheduling affinity priority must be >= 1")
        object.__setattr__(self, "priority", priority)


@runtime_checkable
class SchedulingAffinityProvider(Protocol):
    """Optional model-owned source of scheduler performance hints."""

    def scheduling_affinities(
        self,
        case: ModelCasePayload,
    ) -> Sequence[SchedulingAffinityHint]:
        """Return cache-reuse hints without changing numerical identity."""
        ...


@dataclass(frozen=True, slots=True, eq=False)
class CaseExecutionRequest:
    """Validated inputs required to execute exactly one numerical case."""

    model: ExecutablePanelLoadModel
    common_case: CommonCasePayload
    model_case: ModelCasePayload
    stl_paths: Sequence[str | Path]
    scale_m_per_unit: float
    velocity_hat_stl: np.ndarray
    shielding: ShieldingConfig = field(default_factory=ShieldingConfig)
    mesh_validation_policy: MeshValidationPolicy | str = MeshValidationPolicy.STRICT

    def __post_init__(self) -> None:
        if not isinstance(self.model, ExecutablePanelLoadModel):
            raise ExecutionModelError(
                "model must implement PanelLoadModel and signature_payload()"
            )
        if not isinstance(self.common_case, CommonCasePayload):
            raise TypeError("common_case must be a CommonCasePayload instance")
        if not isinstance(self.model_case, ModelCasePayload):
            raise TypeError("model_case must be a ModelCasePayload instance")
        try:
            model_id = nonempty_text(self.model.model_id, field="model.model_id")
            nonempty_text(
                self.model.algorithm_version,
                field="model.algorithm_version",
            )
        except PanelSolverError as exc:
            raise ExecutionModelError(str(exc)) from exc
        if self.model_case.model_id != model_id:
            raise ExecutionModelError(
                f"model_case model_id {self.model_case.model_id!r} does not match "
                f"model {model_id!r}"
            )

        if isinstance(self.stl_paths, (str, bytes, Path)):
            raise ExecutionError("stl_paths must be a non-empty sequence of paths.")
        try:
            stl_paths = tuple(str(path) for path in self.stl_paths)
        except TypeError as exc:
            raise ExecutionError(
                "stl_paths must be a non-empty sequence of paths."
            ) from exc
        if not stl_paths or any(not path for path in stl_paths):
            raise ExecutionError("stl_paths must be a non-empty sequence of paths.")
        try:
            scale = real_scalar(
                self.scale_m_per_unit,
                field="scale_m_per_unit",
                positive=True,
            )
            velocity = float_array(
                self.velocity_hat_stl,
                field="velocity_hat_stl",
                shape=(3,),
            )
            validate_unit_vectors(velocity, field="velocity_hat_stl")
        except PanelSolverError as exc:
            raise ExecutionError(str(exc)) from exc
        expected_velocity = velocity_hat_stl_from_tangent_angles(
            self.common_case.alpha_t_deg,
            self.common_case.beta_t_deg,
        )
        if not np.allclose(velocity, expected_velocity, rtol=0.0, atol=1.0e-12):
            raise ExecutionError(
                "velocity_hat_stl must match the resolved common-case tangent angles."
            )
        if not isinstance(self.shielding, ShieldingConfig):
            raise TypeError("shielding must be a ShieldingConfig instance")
        try:
            validation_policy = _normalize_policy(self.mesh_validation_policy)
        except MeshLoadError as exc:
            raise ExecutionError("mesh_validation_policy is invalid.") from exc

        object.__setattr__(self, "stl_paths", stl_paths)
        object.__setattr__(self, "scale_m_per_unit", scale)
        object.__setattr__(self, "velocity_hat_stl", velocity)
        object.__setattr__(self, "mesh_validation_policy", validation_policy)


def case_execution_affinity_hints(
    requests: Sequence[CaseExecutionRequest],
) -> tuple[tuple[SchedulingAffinityHint, ...], ...]:
    """Collect optional model-owned hints for model-neutral scheduling."""
    collected: list[tuple[SchedulingAffinityHint, ...]] = []
    for request in requests:
        if not isinstance(request, CaseExecutionRequest):
            raise TypeError("requests must contain only CaseExecutionRequest instances")
        if not isinstance(request.model, SchedulingAffinityProvider):
            collected.append(())
            continue
        provided = request.model.scheduling_affinities(request.model_case)
        try:
            hints = tuple(provided)
        except TypeError as exc:
            raise ExecutionModelError(
                "model scheduling_affinities() must return an iterable of hints"
            ) from exc
        if not all(isinstance(hint, SchedulingAffinityHint) for hint in hints):
            raise ExecutionModelError(
                "model scheduling_affinities() must return SchedulingAffinityHint "
                "instances"
            )
        collected.append(hints)
    return tuple(collected)


@dataclass(frozen=True, slots=True, eq=False)
class CaseExecutionResult:
    """Complete one-case result before product artifact serialization."""

    mesh: PanelMesh
    shielding: ShieldingResult
    results: CommonResults
    signature: CaseSignature
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        expected = (
            ("mesh", self.mesh, PanelMesh),
            ("shielding", self.shielding, ShieldingResult),
            ("results", self.results, CommonResults),
            ("signature", self.signature, CaseSignature),
        )
        for name, value, expected_type in expected:
            if not isinstance(value, expected_type):
                raise ExecutionError(
                    f"{name} must be a {expected_type.__name__} instance."
                )
        warnings = tuple(self.warnings)
        if not all(isinstance(message, str) for message in warnings):
            raise ExecutionError("warnings must contain only strings.")
        if self.mesh.n_faces != self.results.geometry.n_faces:
            raise ExecutionError("mesh and results face counts must match.")
        if not np.array_equal(
            self.shielding.shielded,
            self.results.flow_state.shielded,
        ):
            raise ExecutionError("shielding and results masks must match.")
        object.__setattr__(self, "warnings", warnings)


def _model_identity(model: ExecutablePanelLoadModel) -> tuple[str, str]:
    try:
        return (
            nonempty_text(model.model_id, field="model.model_id"),
            nonempty_text(
                model.algorithm_version,
                field="model.algorithm_version",
            ),
        )
    except PanelSolverError as exc:
        raise ExecutionModelError(str(exc)) from exc


def _validated_model_output(
    model: ExecutablePanelLoadModel,
    geometry: PanelGeometry,
    flow_state: PanelFlowState,
    model_case: ModelCasePayload,
    identity: tuple[str, str],
) -> LocalLoads:
    loads = model.evaluate(geometry, flow_state, model_case)
    if _model_identity(model) != identity:
        raise ExecutionModelError("model identity changed during evaluation.")
    if not isinstance(loads, LocalLoads):
        raise ExecutionModelError("model must return a LocalLoads instance.")
    if loads.n_faces != geometry.n_faces:
        raise ExecutionModelError(
            f"model returned {loads.n_faces} panels; expected {geometry.n_faces}."
        )
    if np.any(loads.traction_coeff_stl[flow_state.shielded] != 0.0):
        raise ExecutionModelError(
            "model returned nonzero traction on ray-shielded panels."
        )
    return loads


def _prepare_case_execution(
    request: CaseExecutionRequest,
    warning_callback: Callable[[str], None] | None,
) -> tuple[
    tuple[str, str],
    LoadedPanelMesh,
    ShieldingResult,
    PanelFlowState,
    CaseSignature,
]:
    """Resolve the exact geometry/shielding identity used by execution."""
    identity = _model_identity(request.model)
    request.model.validate_case(request.model_case)
    model_signature_payload = request.model.signature_payload(request.model_case)
    if _model_identity(request.model) != identity:
        raise ExecutionModelError("model identity changed during case validation.")
    loaded = load_panel_mesh(
        request.stl_paths,
        request.scale_m_per_unit,
        validation_policy=request.mesh_validation_policy,
        warning_callback=warning_callback,
    )
    shielding = compute_shielding(
        loaded.mesh,
        request.velocity_hat_stl,
        request.shielding,
    )
    flow_state = PanelFlowState(request.velocity_hat_stl, shielding.shielded)
    signature = build_case_signature(
        geometry_fingerprint=loaded.geometry_fingerprint,
        common_case=request.common_case,
        model_id=identity[0],
        model_algorithm_version=identity[1],
        model_case_payload=model_signature_payload,
        shielding_config=shielding.config,
    )
    return identity, loaded, shielding, flow_state, signature


def prepare_case_signature(
    request: CaseExecutionRequest,
    *,
    warning_callback: Callable[[str], None] | None = None,
) -> CaseSignature:
    """Build the execution signature without evaluating physical panel loads.

    Mesh loading and shielding identity use the same path as :func:`execute_case`.
    Shielding itself is resolved because the effective backend and batch size are
    part of ADR 0005 and cannot be inferred safely from the requested selector.
    The returned value is the public case and artifact matching identity.
    """
    if not isinstance(request, CaseExecutionRequest):
        raise TypeError("request must be a CaseExecutionRequest instance")
    return _prepare_case_execution(request, warning_callback)[4]


def execute_case(
    request: CaseExecutionRequest,
    *,
    warning_callback: Callable[[str], None] | None = None,
) -> CaseExecutionResult:
    """Execute one case without concrete-model branches or artifact writes."""
    if not isinstance(request, CaseExecutionRequest):
        raise TypeError("request must be a CaseExecutionRequest instance")

    identity, loaded, shielding, flow_state, signature = _prepare_case_execution(
        request,
        warning_callback,
    )

    loads = _validated_model_output(
        request.model,
        loaded.mesh.geometry,
        flow_state,
        request.model_case,
        identity,
    )
    metadata = {
        "case_signature": signature.digest,
        "geometry_fingerprint": loaded.geometry_fingerprint,
        "ray_backend_used": shielding.config.effective_backend,
        "shielding_algorithm_version": shielding.config.algorithm_version,
    }
    results = assemble_common_results(
        request.common_case,
        request.model_case,
        loaded.mesh.geometry,
        flow_state,
        loads,
        metadata=metadata,
    )
    return CaseExecutionResult(
        mesh=loaded.mesh,
        shielding=shielding,
        results=results,
        signature=signature,
        warnings=loaded.warnings,
    )


__all__ = (
    "CaseExecutionRequest",
    "CaseExecutionResult",
    "ExecutablePanelLoadModel",
    "ExecutionError",
    "ExecutionModelError",
    "SchedulingAffinityHint",
    "SchedulingAffinityProvider",
    "case_execution_affinity_hints",
    "execute_case",
    "prepare_case_signature",
)
