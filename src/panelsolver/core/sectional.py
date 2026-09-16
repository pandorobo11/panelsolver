"""Internal sectional-load definitions and geometry-dependent bin resolution.

This boundary resolves only axis, component selection, range, and uniform bins.
It does not clip triangles or evaluate/integrate loads (ADR 0019, A1).
"""

from __future__ import annotations

from dataclasses import InitVar, dataclass, field
from typing import Literal

import numpy as np

from ._validation import (
    float_array,
    index_array,
    integer_scalar,
    real_scalar,
    validate_shape,
)
from .errors import ContractValueError, NonFiniteError
from .mesh import PanelMesh


def _real(value: object, *, field: str) -> float:
    try:
        return real_scalar(value, field=field)
    except OverflowError as exc:
        raise NonFiniteError(field) from exc


def _input_array(
    value: object, *, field: str, shape: tuple[int | str, ...]
) -> np.ndarray:
    # Preserve mixed boolean/numeric elements until scalar validation; ordinary
    # NumPy coercion would silently turn [True, 0, 0] into an integer vector.
    try:
        array = np.asarray(value, dtype=object)
    except (TypeError, ValueError) as exc:
        raise ContractValueError(field, "must be a rectangular array") from exc
    validate_shape(array, field=field, expected=shape)
    return array


def _axis_vector(value: object, *, field: str) -> np.ndarray:
    raw = _input_array(value, field=field, shape=(3,))
    return float_array(
        [_real(item, field=field) for item in raw], field=field, shape=(3,)
    )


@dataclass(frozen=True, slots=True, eq=False)
class SectionalLoadDefinition:
    """Mesh-independent numerical inputs, with a safely normalized STL axis.

    Origin and range are in metres; direction is dimensionless and its sign is
    retained. The raw direction is kept separately from the derived unit axis.
    ``bin_count`` is a required Python integer. No file or batch identity is
    part of this contract.
    """

    axis_origin_stl_m: np.ndarray
    axis_direction_stl: np.ndarray
    bin_count: int
    start_m: float | None = None
    stop_m: float | None = None
    component_ids: tuple[int, ...] | None = None
    axis_direction_hat_stl: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        origin = _axis_vector(self.axis_origin_stl_m, field="axis_origin_stl_m")
        direction = _axis_vector(self.axis_direction_stl, field="axis_direction_stl")
        magnitude = float(np.max(np.abs(direction)))
        if magnitude == 0.0:
            raise ContractValueError("axis_direction_stl", "must be nonzero")
        scaled = direction / magnitude
        unit = scaled / np.linalg.norm(scaled)

        if (self.start_m is None) != (self.stop_m is None):
            raise ContractValueError(
                "start_m/stop_m", "must both be supplied or omitted"
            )
        if self.start_m is not None and self.stop_m is not None:
            start = _real(self.start_m, field="start_m")
            stop = _real(self.stop_m, field="stop_m")
            if start >= stop:
                raise ContractValueError(
                    "start_m/stop_m", "must satisfy start_m < stop_m"
                )
            object.__setattr__(self, "start_m", start)
            object.__setattr__(self, "stop_m", stop)

        if isinstance(self.bin_count, bool) or not isinstance(self.bin_count, int):
            raise ContractValueError("bin_count", "must be a Python integer")
        if self.bin_count < 1:
            raise ContractValueError("bin_count", "must be at least 1")

        if self.component_ids is not None:
            raw_ids = _input_array(
                self.component_ids, field="component_ids", shape=("n_components",)
            )
            ids = tuple(
                integer_scalar(item, field="component_ids", nonnegative=True)
                for item in raw_ids
            )
            if not ids or len(ids) != len(set(ids)):
                raise ContractValueError(
                    "component_ids", "must be nonempty and distinct"
                )
            # Match the mesh's int64 ID domain, without wrapping oversized input.
            index_array(ids, field="component_ids", shape=(len(ids),))
            object.__setattr__(self, "component_ids", tuple(sorted(ids)))

        object.__setattr__(self, "axis_origin_stl_m", origin)
        object.__setattr__(self, "axis_direction_stl", direction)
        object.__setattr__(
            self,
            "axis_direction_hat_stl",
            float_array(unit, field="axis_direction_hat_stl", shape=(3,)),
        )

    @property
    def range_mode(self) -> Literal["auto", "explicit"]:
        return "auto" if self.start_m is None else "explicit"


def _uniform_bins(start: float, stop: float, count: int) -> tuple[np.ndarray, ...]:
    if count >= np.iinfo(np.intp).max // np.dtype(np.float64).itemsize:
        raise ContractValueError("bin_count", "edge array is too large to represent")
    try:
        fractions = np.arange(count + 1, dtype=np.float64) / count
    except (MemoryError, ValueError, OverflowError) as exc:
        raise ContractValueError("bin_count", "cannot allocate bin edges") from exc
    with np.errstate(over="ignore", invalid="ignore"):
        if start < 0.0 < stop:
            # The full span may overflow even when every bin width is finite.
            edges = start * (1.0 - fractions) + stop * fractions
        else:
            edges = start + (stop - start) * fractions
        edges[0], edges[-1] = start, stop
        edges = float_array(edges, field="bin_edges_m", shape=(count + 1,))
        widths = float_array(np.diff(edges), field="bin_widths_m", shape=(count,))
        if np.any(widths <= 0.0):
            raise ContractValueError("bin_edges_m", "must be strictly increasing")
        centers = edges[:-1] + widths / 2.0
        # Do not underflow a subnormal half-width before adding it. Endpoints
        # this close cannot have an overflowing sum, so average them directly.
        tiny_widths = widths < np.finfo(np.float64).tiny
        centers[tiny_widths] = (edges[:-1][tiny_widths] + edges[1:][tiny_widths]) / 2.0
        centers = float_array(centers, field="bin_centers_m", shape=(count,))
    return edges, centers, widths


@dataclass(frozen=True, slots=True, eq=False)
class ResolvedSectionalLoadSpec:
    """Immutable A2 input resolved against one mesh's face component IDs.

    Construct through ``resolve_sectional_load_spec(mesh, definition)``. The
    mesh is used only during construction; all derived fields are read-only
    constructor outputs, so callers cannot supply inconsistent bin metadata.
    Face indices retain mesh order; component IDs are ascending. Use this spec
    with the same mesh topology in A2. Geometry consistency/clipping is deferred
    to A2, including ADR 0019's right-bin ownership at internal boundaries.
    """

    mesh: InitVar[PanelMesh]
    definition: SectionalLoadDefinition
    selected_component_ids: tuple[int, ...] = field(init=False)
    selected_face_indices: np.ndarray = field(init=False)
    all_components_selected: bool = field(init=False)
    selected_geometry_min_m: float = field(init=False)
    selected_geometry_max_m: float = field(init=False)
    resolved_start_m: float = field(init=False)
    resolved_stop_m: float = field(init=False)
    bin_edges_m: np.ndarray = field(init=False)
    bin_centers_m: np.ndarray = field(init=False)
    bin_widths_m: np.ndarray = field(init=False)

    def __post_init__(self, mesh: PanelMesh) -> None:
        if not isinstance(mesh, PanelMesh):
            raise ContractValueError("mesh", "must be a PanelMesh instance")
        definition = self.definition
        if not isinstance(definition, SectionalLoadDefinition):
            raise ContractValueError("definition", "must be a SectionalLoadDefinition")
        available_ids = mesh.geometry.unique_component_ids
        selected_ids = definition.component_ids
        if selected_ids is None:
            selected_ids = available_ids
        unknown_ids = set(selected_ids) - set(available_ids)
        if unknown_ids:
            raise ContractValueError(
                "component_ids", f"absent from mesh: {sorted(unknown_ids)}"
            )
        face_indices = index_array(
            np.flatnonzero(np.isin(mesh.face_component_ids, selected_ids)),
            field="selected_face_indices",
            shape=("n_selected_faces",),
        )
        vertex_indices = np.unique(mesh.faces[face_indices].ravel())
        with np.errstate(over="ignore", invalid="ignore"):
            offsets = mesh.vertices_stl_m[vertex_indices] - definition.axis_origin_stl_m
            if not np.isfinite(offsets).all():
                raise NonFiniteError("selected_vertex_offsets_stl_m")
            projected = offsets @ definition.axis_direction_hat_stl
        if not np.isfinite(projected).all():
            raise NonFiniteError("selected_vertex_projections_m")
        minimum, maximum = float(np.min(projected)), float(np.max(projected))
        start = minimum if definition.start_m is None else definition.start_m
        stop = maximum if definition.stop_m is None else definition.stop_m
        if start >= stop:
            raise ContractValueError(
                "auto range", "zero projected extent; supply explicit bounds"
            )
        edges, centers, widths = _uniform_bins(start, stop, definition.bin_count)

        object.__setattr__(self, "selected_component_ids", selected_ids)
        object.__setattr__(self, "selected_face_indices", face_indices)
        object.__setattr__(
            self, "all_components_selected", selected_ids == available_ids
        )
        object.__setattr__(self, "selected_geometry_min_m", minimum)
        object.__setattr__(self, "selected_geometry_max_m", maximum)
        object.__setattr__(self, "resolved_start_m", start)
        object.__setattr__(self, "resolved_stop_m", stop)
        object.__setattr__(self, "bin_edges_m", edges)
        object.__setattr__(self, "bin_centers_m", centers)
        object.__setattr__(self, "bin_widths_m", widths)

    @property
    def axis_origin_stl_m(self) -> np.ndarray:
        return self.definition.axis_origin_stl_m

    @property
    def axis_direction_hat_stl(self) -> np.ndarray:
        return self.definition.axis_direction_hat_stl

    @property
    def range_mode(self) -> Literal["auto", "explicit"]:
        return self.definition.range_mode

    @property
    def covers_selected_geometry(self) -> bool:
        """Closed outer-bound coverage, independent of any loads or shielding."""
        return (
            self.resolved_start_m <= self.selected_geometry_min_m
            and self.selected_geometry_max_m <= self.resolved_stop_m
        )


def resolve_sectional_load_spec(
    mesh: PanelMesh, definition: SectionalLoadDefinition
) -> ResolvedSectionalLoadSpec:
    """Resolve selected topology, geometric extent, and uniform bins (no loads)."""
    return ResolvedSectionalLoadSpec(mesh, definition)


__all__ = (
    "ResolvedSectionalLoadSpec",
    "SectionalLoadDefinition",
    "resolve_sectional_load_spec",
)
