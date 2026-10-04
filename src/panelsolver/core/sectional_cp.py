"""Panel-constant surface scalars on plane/triangle intersection segments."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

import numpy as np

from ._sectional_geometry import _validate_source
from ._validation import float_array, index_array
from .contracts import LocalLoads
from .errors import ContractValueError
from .mesh import PanelMesh
from .sectional import (
    SectionalLoadDefinition,
    _real,
    _uniform_bins,
    resolve_sectional_load_spec,
)


@dataclass(frozen=True, slots=True, eq=False)
class SectionalCpDefinition:
    """Parallel cutting planes; distances and origin are in STL metres."""

    axis_origin_stl_m: np.ndarray
    axis_direction_stl: np.ndarray
    section_count: int
    start_m: float | None = None
    stop_m: float | None = None
    component_ids: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        base = self.selection_definition()
        for name in ("axis_origin_stl_m", "axis_direction_stl", "component_ids"):
            object.__setattr__(self, name, getattr(base, name))
        if (
            isinstance(self.section_count, bool)
            or not isinstance(self.section_count, int)
            or self.section_count < 1
        ):
            raise ContractValueError(
                "section_count", "must be a positive Python integer"
            )
        if (self.start_m is None) != (self.stop_m is None):
            raise ContractValueError("start_m/stop_m", "supply both or neither")
        if self.start_m is not None:
            start = _real(self.start_m, field="start_m")
            stop = _real(self.stop_m, field="stop_m")
            if (self.section_count == 1 and start != stop) or (
                self.section_count > 1 and start >= stop
            ):
                raise ContractValueError(
                    "start_m/stop_m",
                    "one plane requires equal bounds; multiple planes require start < stop",
                )
            object.__setattr__(self, "start_m", start)
            object.__setattr__(self, "stop_m", stop)

    def selection_definition(self) -> SectionalLoadDefinition:
        # A finite dummy interval reuses axis/selection validation, including
        # planar meshes. It is never used to choose the cutting positions.
        return SectionalLoadDefinition(
            self.axis_origin_stl_m,
            self.axis_direction_stl,
            1,
            0.0,
            1.0,
            self.component_ids,
        )

    @property
    def axis_direction_hat_stl(self) -> np.ndarray:
        return self.selection_definition().axis_direction_hat_stl

    def __reduce__(self):
        return (
            type(self),
            (
                self.axis_origin_stl_m,
                self.axis_direction_stl,
                self.section_count,
                self.start_m,
                self.stop_m,
                self.component_ids,
            ),
        )

    def __deepcopy__(self, memo):
        return self


@dataclass(frozen=True, slots=True, eq=False)
class CpPlane:
    position_m: float
    status: str
    message: str
    source_face_indices: np.ndarray
    component_ids: np.ndarray
    endpoints_stl_m: np.ndarray
    scalar_values: np.ndarray

    def __post_init__(self):
        n = len(self.source_face_indices)
        for name in ("source_face_indices", "component_ids"):
            object.__setattr__(
                self, name, index_array(getattr(self, name), field=name, shape=(n,))
            )
        object.__setattr__(
            self,
            "endpoints_stl_m",
            float_array(self.endpoints_stl_m, field="endpoints_stl_m", shape=(n, 2, 3)),
        )
        object.__setattr__(
            self,
            "scalar_values",
            float_array(self.scalar_values, field="scalar_values", shape=(n,)),
        )

    def __reduce__(self):
        return (
            type(self),
            (
                self.position_m,
                self.status,
                self.message,
                self.source_face_indices,
                self.component_ids,
                self.endpoints_stl_m,
                self.scalar_values,
            ),
        )


@dataclass(frozen=True, slots=True, eq=False)
class SectionalCp:
    definition: SectionalCpDefinition
    selected_component_ids: tuple[int, ...]
    scalar_name: str
    planes: tuple[CpPlane, ...]
    case_signature: str


def compute_cp_sections(
    mesh: PanelMesh,
    loads: LocalLoads,
    definition: SectionalCpDefinition,
    signature: str,
) -> SectionalCp:
    """Extract panel values without solving, averaging, or load integration.

    Signs use exact rational projections of the stored float64 geometry and
    normalized axis. This avoids a translation-dependent snapping epsilon.
    Intersections are rounded only when converted back to float64 coordinates.
    """
    if not isinstance(mesh, PanelMesh) or not isinstance(loads, LocalLoads):
        raise TypeError("mesh and loads must be PanelMesh and LocalLoads")
    if not isinstance(definition, SectionalCpDefinition):
        raise TypeError("definition must be SectionalCpDefinition")
    spec = resolve_sectional_load_spec(mesh, definition.selection_definition())
    scalar_name = "cp" if "cp" in loads.cell_scalars else "normal_traction_coeff"
    if scalar_name not in loads.cell_scalars:
        raise ContractValueError(
            "cell_scalars", "no supported pressure/normal traction scalar"
        )
    values = float_array(
        loads.cell_scalars[scalar_name], field=scalar_name, shape=(len(mesh.faces),)
    )
    faces = spec.selected_face_indices
    origin = tuple(Fraction(float(x)) for x in definition.axis_origin_stl_m)
    direction = tuple(Fraction(float(x)) for x in definition.axis_direction_hat_stl)
    vertices = {}
    projected = {}
    for face in faces:
        _validate_source(mesh, int(face), mesh.vertices_stl_m[mesh.faces[face]])
        for vertex in mesh.faces[face]:
            key = int(vertex)
            if key not in vertices:
                point = tuple(Fraction(float(x)) for x in mesh.vertices_stl_m[key])
                vertices[key] = point
                projected[key] = sum(
                    (point[k] - origin[k]) * direction[k] for k in range(3)
                )
    start, stop = definition.start_m, definition.stop_m
    if start is None:
        start, stop = float(min(projected.values())), float(max(projected.values()))
        if definition.section_count == 1:
            start = stop = float(
                (min(projected.values()) + max(projected.values())) / 2
            )
    if definition.section_count == 1:
        positions = float_array([start], field="positions_m", shape=(1,))
    else:
        if start >= stop:
            raise ContractValueError(
                "range", "multiple planes need a nonzero projected extent"
            )
        positions = _uniform_bins(start, stop, definition.section_count - 1)[0]
    planes = []
    for position in positions:
        offset = Fraction(float(position))
        indices, endpoints = [], []
        message = ""
        for face in faces:
            ids = [int(i) for i in mesh.faces[face]]
            distances = [projected[i] - offset for i in ids]
            if all(d == 0 for d in distances):
                message = f"Cutting plane is coplanar with source face {face}"
                break
            points = [vertices[ids[k]] for k, d in enumerate(distances) if d == 0]
            for a, b in ((0, 1), (1, 2), (2, 0)):
                da, db = distances[a], distances[b]
                if (da < 0 < db) or (db < 0 < da):
                    t = da / (da - db)
                    va, vb = vertices[ids[a]], vertices[ids[b]]
                    points.append(tuple(va[k] + t * (vb[k] - va[k]) for k in range(3)))
            if len(points) == 2:
                segment = [[float(x) for x in p] for p in points]
                if segment[0] == segment[1]:
                    message = f"Intersection of source face {face} is not representable as a nonzero float64 segment"
                    break
                indices.append(int(face))
                endpoints.append(segment)
        if message:
            indices, endpoints = [], []
        selected = np.asarray(indices, dtype=np.int64)
        planes.append(
            CpPlane(
                float(position),
                "failed" if message else "ok" if indices else "empty",
                message,
                selected,
                mesh.face_component_ids[selected],
                np.asarray(endpoints, dtype=float).reshape((-1, 2, 3)),
                values[selected],
            )
        )
    return SectionalCp(
        definition, spec.selected_component_ids, scalar_name, tuple(planes), signature
    )
