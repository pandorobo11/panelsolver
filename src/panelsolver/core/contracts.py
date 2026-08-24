"""Immutable, validated contracts at the physical-model boundary."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np

from ._validation import (
    FrozenMapping,
    bool_array,
    float_array,
    freeze_payload,
    index_array,
    integer_scalar,
    nonempty_text,
    real_scalar,
    require_nonempty_faces,
    scalar_array,
    validate_unit_vectors,
)
from .errors import ContractValueError

type PayloadScalar = None | bool | int | float | str
type PayloadValue = (
    PayloadScalar | tuple[PayloadValue, ...] | Mapping[str, PayloadValue]
)


@dataclass(frozen=True, slots=True, eq=False)
class PanelGeometry:
    """Per-panel geometry in STL axes, independent of a mesh implementation.

    All arrays are private, C-contiguous copies. They never share memory with
    caller inputs and are exposed through immutable NumPy buffers.
    """

    centers_stl_m: np.ndarray
    normals_out_stl: np.ndarray
    areas_m2: np.ndarray
    component_ids: np.ndarray

    def __post_init__(self) -> None:
        centers = float_array(
            self.centers_stl_m,
            field="PanelGeometry.centers_stl_m",
            shape=("n_faces", 3),
        )
        n_faces = centers.shape[0]
        require_nonempty_faces(n_faces, field="PanelGeometry.centers_stl_m")
        normals = float_array(
            self.normals_out_stl,
            field="PanelGeometry.normals_out_stl",
            shape=(n_faces, 3),
        )
        validate_unit_vectors(normals, field="PanelGeometry.normals_out_stl")
        areas = float_array(
            self.areas_m2,
            field="PanelGeometry.areas_m2",
            shape=(n_faces,),
        )
        if np.any(areas <= 0.0):
            raise ContractValueError(
                "PanelGeometry.areas_m2",
                "must contain only strictly positive panel areas",
            )
        component_ids = index_array(
            self.component_ids,
            field="PanelGeometry.component_ids",
            shape=(n_faces,),
        )

        object.__setattr__(self, "centers_stl_m", centers)
        object.__setattr__(self, "normals_out_stl", normals)
        object.__setattr__(self, "areas_m2", areas)
        object.__setattr__(self, "component_ids", component_ids)

    @property
    def n_faces(self) -> int:
        """Number of panels represented by every per-panel field."""
        return self.centers_stl_m.shape[0]

    @property
    def unique_component_ids(self) -> tuple[int, ...]:
        """Sorted component identities present in the geometry."""
        return tuple(int(value) for value in np.unique(self.component_ids))


@dataclass(frozen=True, slots=True, eq=False)
class PanelFlowState:
    """Common flow state supplied to a load model for every panel.

    ``velocity_hat_stl`` is one unit freestream-velocity direction in STL axes.
    ``shielded`` is a strict boolean mask with one entry per panel.
    """

    velocity_hat_stl: np.ndarray
    shielded: np.ndarray

    def __post_init__(self) -> None:
        velocity = float_array(
            self.velocity_hat_stl,
            field="PanelFlowState.velocity_hat_stl",
            shape=(3,),
        )
        validate_unit_vectors(velocity, field="PanelFlowState.velocity_hat_stl")
        shielded = bool_array(
            self.shielded,
            field="PanelFlowState.shielded",
            shape=("n_faces",),
        )
        require_nonempty_faces(shielded.shape[0], field="PanelFlowState.shielded")

        object.__setattr__(self, "velocity_hat_stl", velocity)
        object.__setattr__(self, "shielded", shielded)

    @property
    def n_faces(self) -> int:
        return self.shielded.shape[0]


@dataclass(frozen=True, slots=True, eq=False)
class LocalLoads:
    """A model's local, nondimensional traction and visualization outputs.

    ``traction_coeff_stl`` has shape ``(n_faces, 3)``. The common integrator
    later applies ``area_m2 / Aref_m2``; this contract never collapses the
    vector to a pressure coefficient.
    """

    traction_coeff_stl: np.ndarray
    cell_scalars: Mapping[str, np.ndarray] = field(default_factory=dict)
    metadata: Mapping[str, PayloadValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        traction = float_array(
            self.traction_coeff_stl,
            field="LocalLoads.traction_coeff_stl",
            shape=("n_faces", 3),
        )
        n_faces = traction.shape[0]
        require_nonempty_faces(n_faces, field="LocalLoads.traction_coeff_stl")
        if not isinstance(self.cell_scalars, Mapping):
            raise ContractValueError("LocalLoads.cell_scalars", "must be a mapping")

        scalars: list[tuple[str, np.ndarray]] = []
        for name, values in self.cell_scalars.items():
            validated_name = nonempty_text(
                name,
                field="LocalLoads.cell_scalars key",
            )
            scalars.append(
                (
                    validated_name,
                    scalar_array(
                        values,
                        field=f"LocalLoads.cell_scalars.{validated_name}",
                        shape=(n_faces,),
                    ),
                )
            )

        object.__setattr__(self, "traction_coeff_stl", traction)
        object.__setattr__(self, "cell_scalars", FrozenMapping(scalars))
        object.__setattr__(
            self,
            "metadata",
            freeze_payload(self.metadata, field="LocalLoads.metadata"),
        )

    @property
    def n_faces(self) -> int:
        return self.traction_coeff_stl.shape[0]


@dataclass(frozen=True, slots=True, eq=False)
class CommonCasePayload:
    """Validated model-independent numerical inputs after attitude resolution.

    Public case-ID and attitude-input policies are validated and resolved by
    higher-level adapters before constructing this payload.
    """

    case_id: str
    Aref_m2: float
    moment_reference_stl_m: np.ndarray
    Lref_Cl_m: float
    Lref_Cm_m: float
    Lref_Cn_m: float
    alpha_t_deg: float
    beta_t_deg: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "case_id",
            nonempty_text(self.case_id, field="CommonCasePayload.case_id"),
        )
        object.__setattr__(
            self,
            "Aref_m2",
            real_scalar(
                self.Aref_m2,
                field="CommonCasePayload.Aref_m2",
                positive=True,
            ),
        )
        object.__setattr__(
            self,
            "moment_reference_stl_m",
            float_array(
                self.moment_reference_stl_m,
                field="CommonCasePayload.moment_reference_stl_m",
                shape=(3,),
            ),
        )
        for name in ("Lref_Cl_m", "Lref_Cm_m", "Lref_Cn_m"):
            object.__setattr__(
                self,
                name,
                real_scalar(
                    getattr(self, name),
                    field=f"CommonCasePayload.{name}",
                    positive=True,
                ),
            )
        for name in ("alpha_t_deg", "beta_t_deg"):
            object.__setattr__(
                self,
                name,
                real_scalar(
                    getattr(self, name),
                    field=f"CommonCasePayload.{name}",
                ),
            )


@dataclass(frozen=True, slots=True, eq=False)
class ModelCasePayload:
    """Opaque, deeply immutable inputs whose semantics belong to one model."""

    model_id: str
    payload: Mapping[str, PayloadValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_id",
            nonempty_text(self.model_id, field="ModelCasePayload.model_id"),
        )
        object.__setattr__(
            self,
            "payload",
            freeze_payload(self.payload, field="ModelCasePayload.payload"),
        )


@runtime_checkable
class PanelLoadModel(Protocol):
    """Runtime model interface consumed uniformly by the model registry."""

    @property
    def model_id(self) -> str:
        """Stable registry identity for this physical model."""
        ...

    @property
    def algorithm_version(self) -> str:
        """Version of numerical behavior owned by the model."""
        ...

    def validate_case(self, case: ModelCasePayload) -> None:
        """Validate model-specific payload fields or raise ``ContractError``."""
        ...

    def evaluate(
        self,
        geometry: PanelGeometry,
        flow_state: PanelFlowState,
        case: ModelCasePayload,
    ) -> LocalLoads:
        """Evaluate one local traction vector per panel."""
        ...


@dataclass(frozen=True, slots=True, eq=False)
class IntegratedCoefficients:
    """Frame-explicit total or component force and moment coefficients."""

    force_coeff_stl: np.ndarray
    force_coeff_body: np.ndarray
    force_coeff_stability: np.ndarray
    moment_area_coeff_body_m: np.ndarray
    moment_coeff_body: np.ndarray

    def __post_init__(self) -> None:
        for name in (
            "force_coeff_stl",
            "force_coeff_body",
            "force_coeff_stability",
            "moment_area_coeff_body_m",
            "moment_coeff_body",
        ):
            object.__setattr__(
                self,
                name,
                float_array(
                    getattr(self, name),
                    field=f"IntegratedCoefficients.{name}",
                    shape=(3,),
                ),
            )

    @property
    def CA(self) -> float:
        return -float(self.force_coeff_body[0])

    @property
    def CY(self) -> float:
        return float(self.force_coeff_body[1])

    @property
    def CN(self) -> float:
        return -float(self.force_coeff_body[2])

    @property
    def Cl(self) -> float:
        return float(self.moment_coeff_body[0])

    @property
    def Cm(self) -> float:
        return float(self.moment_coeff_body[1])

    @property
    def Cn(self) -> float:
        return float(self.moment_coeff_body[2])

    @property
    def CD(self) -> float:
        return -float(self.force_coeff_stability[0])

    @property
    def CL(self) -> float:
        return -float(self.force_coeff_stability[2])


@dataclass(frozen=True, slots=True, eq=False)
class ComponentResult:
    """Integrated result and identity for one geometry component."""

    component_id: int
    integrated: IntegratedCoefficients
    face_count: int
    shielded_face_count: int
    metadata: Mapping[str, PayloadValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        component_id = integer_scalar(
            self.component_id,
            field="ComponentResult.component_id",
            nonnegative=True,
        )
        face_count = integer_scalar(
            self.face_count,
            field="ComponentResult.face_count",
            nonnegative=True,
        )
        shielded_face_count = integer_scalar(
            self.shielded_face_count,
            field="ComponentResult.shielded_face_count",
            nonnegative=True,
        )
        if not isinstance(self.integrated, IntegratedCoefficients):
            raise ContractValueError(
                "ComponentResult.integrated",
                "must be an IntegratedCoefficients instance",
            )
        if shielded_face_count > face_count:
            raise ContractValueError(
                "ComponentResult.shielded_face_count",
                "must not exceed face_count",
            )

        object.__setattr__(self, "component_id", component_id)
        object.__setattr__(self, "face_count", face_count)
        object.__setattr__(self, "shielded_face_count", shielded_face_count)
        object.__setattr__(
            self,
            "metadata",
            freeze_payload(self.metadata, field="ComponentResult.metadata"),
        )


@dataclass(frozen=True, slots=True, eq=False)
class CommonResults:
    """Complete immutable numerical result envelope before artifact projection."""

    case: CommonCasePayload
    model_case: ModelCasePayload
    geometry: PanelGeometry
    flow_state: PanelFlowState
    local_loads: LocalLoads
    total: IntegratedCoefficients
    components: tuple[ComponentResult, ...]
    metadata: Mapping[str, PayloadValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        expected_types = (
            ("case", self.case, CommonCasePayload),
            ("model_case", self.model_case, ModelCasePayload),
            ("geometry", self.geometry, PanelGeometry),
            ("flow_state", self.flow_state, PanelFlowState),
            ("local_loads", self.local_loads, LocalLoads),
            ("total", self.total, IntegratedCoefficients),
        )
        for name, value, expected_type in expected_types:
            if not isinstance(value, expected_type):
                raise ContractValueError(
                    f"CommonResults.{name}",
                    f"must be a {expected_type.__name__} instance",
                )

        try:
            components = tuple(self.components)
        except TypeError as exc:
            raise ContractValueError(
                "CommonResults.components",
                "must be an iterable of ComponentResult instances",
            ) from exc
        if not components or not all(
            isinstance(component, ComponentResult) for component in components
        ):
            raise ContractValueError(
                "CommonResults.components",
                "must contain one ComponentResult for every geometry component",
            )
        if self.geometry.n_faces != self.flow_state.n_faces:
            raise ContractValueError(
                "CommonResults.flow_state",
                "panel count must match geometry",
            )
        if self.geometry.n_faces != self.local_loads.n_faces:
            raise ContractValueError(
                "CommonResults.local_loads",
                "panel count must match geometry",
            )
        if np.any(
            self.local_loads.traction_coeff_stl[self.flow_state.shielded] != 0.0
        ):
            raise ContractValueError(
                "CommonResults.local_loads",
                "shielded panels must have exact-zero traction",
            )

        by_id = {component.component_id: component for component in components}
        if len(by_id) != len(components):
            raise ContractValueError(
                "CommonResults.components",
                "component_id values must be unique",
            )
        expected_ids = set(self.geometry.unique_component_ids)
        if set(by_id) != expected_ids:
            raise ContractValueError(
                "CommonResults.components",
                f"component IDs must equal geometry component IDs {sorted(expected_ids)}",
            )
        for component_id, component in by_id.items():
            face_mask = self.geometry.component_ids == component_id
            expected_faces = int(np.count_nonzero(face_mask))
            expected_shielded = int(
                np.count_nonzero(self.flow_state.shielded[face_mask])
            )
            if component.face_count != expected_faces:
                raise ContractValueError(
                    "CommonResults.components",
                    f"component {component_id} face_count must be {expected_faces}",
                )
            if component.shielded_face_count != expected_shielded:
                raise ContractValueError(
                    "CommonResults.components",
                    f"component {component_id} shielded_face_count must be "
                    f"{expected_shielded}",
                )

        object.__setattr__(self, "components", components)
        object.__setattr__(
            self,
            "metadata",
            freeze_payload(self.metadata, field="CommonResults.metadata"),
        )

    @property
    def model_id(self) -> str:
        return self.model_case.model_id


__all__ = (
    "CommonCasePayload",
    "CommonResults",
    "ComponentResult",
    "IntegratedCoefficients",
    "LocalLoads",
    "ModelCasePayload",
    "PanelFlowState",
    "PanelGeometry",
    "PanelLoadModel",
    "PayloadScalar",
    "PayloadValue",
)
