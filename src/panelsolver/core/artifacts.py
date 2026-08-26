"""Semantic, model-neutral VTP artifact projection."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np

from ._validation import (
    FrozenMapping,
    _read_only_array,
    float_array,
    index_array,
    nonempty_text,
)
from .contracts import CommonResults
from .errors import ContractValueError, NonFiniteError
from .integration import integrate_panel_loads
from .mesh import PanelMesh


@dataclass(frozen=True, slots=True)
class ArtifactProjectionPolicy:
    """Adapter-supplied run values and explicit product-specific additions."""

    attitude_input_used: str
    case_signature: str
    ray_backend_used: str
    solver_version: str
    vtp_field_data: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (
            "attitude_input_used",
            "case_signature",
            "ray_backend_used",
            "solver_version",
        ):
            object.__setattr__(
                self,
                name,
                nonempty_text(
                    getattr(self, name), field=f"ArtifactProjectionPolicy.{name}"
                ),
            )
        object.__setattr__(
            self,
            "vtp_field_data",
            _freeze_named_arrays(
                self.vtp_field_data,
                field="ArtifactProjectionPolicy.vtp_field_data",
                field_arrays=True,
            ),
        )


@dataclass(frozen=True, slots=True, eq=False)
class VtpProjection:
    """In-memory semantic VTP points, faces, cell arrays, and field arrays."""

    points: np.ndarray
    faces: np.ndarray
    cell_data: Mapping[str, np.ndarray]
    field_data: Mapping[str, np.ndarray]

    def __post_init__(self) -> None:
        points = float_array(
            self.points,
            field="VtpProjection.points",
            shape=("n_vertices", 3),
        )
        faces = index_array(
            self.faces,
            field="VtpProjection.faces",
            shape=("n_connectivity",),
        )
        if faces.size == 0 or faces.size % 4:
            raise ContractValueError(
                "VtpProjection.faces",
                "must contain flattened triangle connectivity",
            )
        connectivity = faces.reshape(-1, 4)
        if np.any(connectivity[:, 0] != 3):
            raise ContractValueError(
                "VtpProjection.faces",
                "each flattened cell must start with the triangle size 3",
            )
        if np.any(connectivity[:, 1:] >= points.shape[0]):
            raise ContractValueError(
                "VtpProjection.faces",
                "contains a vertex index outside points",
            )
        face_count = connectivity.shape[0]
        cell_data = _freeze_named_arrays(
            self.cell_data,
            field="VtpProjection.cell_data",
        )
        for name, array in cell_data.items():
            if array.ndim == 0 or array.shape[0] != face_count:
                raise ContractValueError(
                    f"VtpProjection.cell_data.{name}",
                    "first dimension must match the face count",
                )
        field_data = _freeze_named_arrays(
            self.field_data,
            field="VtpProjection.field_data",
            field_arrays=True,
        )
        object.__setattr__(self, "points", points)
        object.__setattr__(self, "faces", faces)
        object.__setattr__(self, "cell_data", cell_data)
        object.__setattr__(self, "field_data", field_data)


def project_vtp_artifact(
    mesh: PanelMesh,
    results: CommonResults,
    policy: ArtifactProjectionPolicy,
) -> VtpProjection:
    """Project common results and policy additions into VTP semantics."""
    _validate_projection_inputs(mesh, results, policy)
    integration = integrate_panel_loads(
        results.geometry, results.local_loads, results.case
    )
    cell_data: dict[str, object] = {
        "C_face_stl": integration.face_force_coeff_stl,
        "area_m2": results.geometry.areas_m2,
        "center_x_stl_m": results.geometry.centers_stl_m[:, 0],
        "center_y_stl_m": results.geometry.centers_stl_m[:, 1],
        "center_z_stl_m": results.geometry.centers_stl_m[:, 2],
        # VTK stores this mask as an unsigned byte.
        "shielded": results.flow_state.shielded.astype(np.uint8),
        "stl_index": results.geometry.component_ids.astype(np.int32),
    }
    _add_without_collision(
        cell_data,
        results.local_loads.cell_scalars,
        field="LocalLoads.cell_scalars",
    )

    sources = tuple(component.source for component in mesh.components)
    field_data: dict[str, object] = {
        "alpha_t_deg_resolved": [results.case.alpha_t_deg],
        "attitude_input_used": [policy.attitude_input_used],
        "beta_t_deg_resolved": [results.case.beta_t_deg],
        "case_id": [results.case.case_id],
        "case_signature": [policy.case_signature],
        "ray_backend_used": [policy.ray_backend_used],
        "solver_version": [policy.solver_version],
        "stl_count": [len(sources)],
        # PyVista's NumPy-to-VTK string bridge rejects non-ASCII NumPy Unicode
        # arrays. JSON escapes keep the serialized value ASCII-safe without
        # changing the paths recovered by json.loads().
        "stl_paths_json": [
            json.dumps(sources, ensure_ascii=True, separators=(",", ":"))
        ],
    }
    _add_without_collision(
        field_data,
        policy.vtp_field_data,
        field="ArtifactProjectionPolicy.vtp_field_data",
    )
    vtp_faces = np.column_stack(
        (np.full(mesh.n_faces, 3, dtype=np.int64), mesh.faces)
    ).reshape(-1)
    return VtpProjection(mesh.vertices_stl_m, vtp_faces, cell_data, field_data)


def _validate_projection_inputs(
    mesh: PanelMesh,
    results: CommonResults,
    policy: ArtifactProjectionPolicy,
) -> None:
    if not isinstance(mesh, PanelMesh):
        raise ContractValueError("projection.mesh", "must be a PanelMesh instance")
    if not isinstance(results, CommonResults):
        raise ContractValueError(
            "projection.results",
            "must be a CommonResults instance",
        )
    if not isinstance(policy, ArtifactProjectionPolicy):
        raise ContractValueError(
            "projection.policy",
            "must be an ArtifactProjectionPolicy instance",
        )
    geometry_pairs = (
        (mesh.geometry.centers_stl_m, results.geometry.centers_stl_m),
        (mesh.geometry.normals_out_stl, results.geometry.normals_out_stl),
        (mesh.geometry.areas_m2, results.geometry.areas_m2),
        (mesh.geometry.component_ids, results.geometry.component_ids),
    )
    if any(not np.array_equal(left, right) for left, right in geometry_pairs):
        raise ContractValueError(
            "projection.mesh",
            "mesh geometry must equal result geometry",
        )


def _add_without_collision(
    target: dict[str, object],
    additions: Mapping[str, object],
    *,
    field: str,
) -> None:
    collisions = set(target) & set(additions)
    if collisions:
        raise ContractValueError(
            field,
            f"must not override common fields {sorted(collisions)}",
        )
    target.update(additions)


def _freeze_named_arrays(
    value: Mapping[str, object],
    *,
    field: str,
    field_arrays: bool = False,
) -> FrozenMapping[np.ndarray]:
    if not isinstance(value, Mapping):
        raise ContractValueError(field, "must be a mapping")
    items: list[tuple[str, np.ndarray]] = []
    for raw_name, raw_array in value.items():
        name = nonempty_text(raw_name, field=f"{field} key")
        array = _semantic_array(raw_array, field=f"{field}.{name}")
        if field_arrays and array.ndim == 0:
            array = _semantic_array([array.item()], field=f"{field}.{name}")
        if field_arrays and array.shape[0] == 0:
            raise ContractValueError(
                f"{field}.{name}",
                "field arrays must not be empty",
            )
        items.append((name, array))
    return FrozenMapping(sorted(items))


def _semantic_array(value: object, *, field: str) -> np.ndarray:
    try:
        raw = np.asarray(value)
    except (TypeError, ValueError) as exc:
        raise ContractValueError(field, "must be a rectangular semantic array") from exc
    if raw.dtype.kind not in "biufUS":
        raise ContractValueError(
            field,
            "must contain boolean, integer, float, or string values",
        )
    array = np.array(raw, copy=True, order="C")
    if array.dtype.kind == "f" and not np.isfinite(array).all():
        raise NonFiniteError(field)
    # Preserve the source shape while still returning an immutable array.
    return _read_only_array(array).reshape(array.shape)


__all__ = (
    "ArtifactProjectionPolicy",
    "VtpProjection",
    "project_vtp_artifact",
)
