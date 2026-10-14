"""Display-only cell-to-point interpolation; never modifies result artifacts."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pyvista as pv
from vtkmodules.util.numpy_support import vtk_to_numpy

from .viewer_data import (
    ScalarField,
    ViewerBoundaries,
    discover_scalar_fields,
    read_viewer_boundaries,
)

_FEATURE_ANGLE_DEG = 30.0


@dataclass(frozen=True)
class InterpolationGeometry:
    surface: pv.PolyData
    source_cells: np.ndarray
    shielded: bool
    render_surface: pv.PolyData | None = None
    render_point_ids: np.ndarray | None = None


def _face_entries(offsets: np.ndarray, cells: np.ndarray):
    """Gather variable-size face connectivity in O(selected corner count)."""
    sizes = offsets[cells + 1] - offsets[cells]
    selected_offsets = np.concatenate(([0], np.cumsum(sizes)))
    entries = np.repeat(offsets[cells] - selected_offsets[:-1], sizes)
    entries += np.arange(selected_offsets[-1])
    return selected_offsets, entries


def _render_normals(poly, surface, source_cells, offsets, connectivity):
    """Keep imported shading normals separate from the averaging topology."""
    point_normals = poly.point_data.active_normals
    cell_normals = poly.cell_data.active_normals
    if point_normals is None and cell_normals is None:
        return None, None
    if point_normals is not None:
        render_offsets, entries = _face_entries(offsets, source_cells)
        original_points = connectivity[entries]
        render_points = poly.points[original_points]
        point_ids = vtk_to_numpy(surface.GetPolys().GetConnectivityArray())
        # Cleaning/splitting must retain the original corner order. If a filter
        # changes it, fall back rather than attach normals to the wrong corners.
        if not np.array_equal(surface.points[point_ids], render_points):
            raise ValueError("Interpolation topology changed face corners")
        render = pv.PolyData(
            render_points,
            pv.CellArray.from_arrays(render_offsets, np.arange(len(render_points))),
        )
        name = poly.point_data.active_normals_name
        render.point_data[name] = point_normals[original_points]
        render.point_data.active_normals_name = name
    else:
        render = surface.copy(deep=False)
        point_ids = np.arange(surface.n_points)
    if cell_normals is not None:
        name = poly.cell_data.active_normals_name
        render.cell_data[name] = cell_normals[source_cells]
        render.cell_data.active_normals_name = name
    return render, point_ids


def prepare_interpolation_geometry(
    poly: pv.PolyData,
    boundaries: ViewerBoundaries | None = None,
) -> tuple[InterpolationGeometry, ...]:
    """Prepare display topology once per artifact, independent of its scalar."""
    if not isinstance(poly, pv.PolyData) or poly.n_cells != poly.n_faces:
        raise ValueError("Smooth colors requires a polygon surface")
    if boundaries is None:
        fields = discover_scalar_fields(poly.cell_data, n_cells=poly.n_cells)
        boundaries = read_viewer_boundaries(
            poly.cell_data, n_cells=poly.n_cells, fields=fields
        )
    if boundaries.error is not None:
        raise ValueError(boundaries.error)
    shielded = (
        boundaries.shielded
        if boundaries.shielded is not None
        else np.zeros(poly.n_cells, dtype=bool)
    )
    groups = [boundaries.components, shielded]
    keys, group_ids = np.unique(np.column_stack(groups), axis=0, return_inverse=True)
    # NumPy 2.0.0 may return a column-shaped inverse for axis=0.
    group_ids = group_ids.ravel()
    # Read connectivity once; each group gathers only its own corners/points.
    polygons = poly.GetPolys()
    offsets = vtk_to_numpy(polygons.GetOffsetsArray())
    connectivity = vtk_to_numpy(polygons.GetConnectivityArray())
    opacity_groups: dict[bool, list[pv.PolyData]] = {False: [], True: []}
    order = np.argsort(group_ids, kind="stable")
    group_splits = np.flatnonzero(np.diff(group_ids[order])) + 1
    for indices, (_component, shielded) in zip(
        np.split(order, group_splits), keys, strict=True
    ):
        face_offsets, entries = _face_entries(offsets, indices)
        point_ids, local_connectivity = np.unique(
            connectivity[entries], return_inverse=True
        )
        part = pv.PolyData(
            poly.points[point_ids],
            pv.CellArray.from_arrays(face_offsets, local_connectivity),
        )
        part.cell_data["source_cells"] = indices
        part = part.clean(
            tolerance=0.0,
            absolute=True,
            lines_to_points=False,
            polys_to_lines=False,
            strips_to_polys=False,
        )
        part = part.compute_normals(
            cell_normals=False,
            point_normals=True,
            split_vertices=True,
            feature_angle=_FEATURE_ANGLE_DEG,
            # Preserve the source orientation: opposite normals must not blend.
            consistent_normals=False,
            auto_orient_normals=False,
            non_manifold_traversal=False,
        )
        # Generated normals only split averaging vertices. Imported shading
        # normals are restored separately after averaging.
        part.point_data.clear()
        source_cells = np.array(part.cell_data["source_cells"], copy=True)
        # Cleaning may silently remove degenerate polygons. Never present a
        # partial surface as a successful interpolated result. Check identities
        # as well as counts to detect missing, duplicated or remapped cells.
        if not np.array_equal(np.sort(source_cells), indices):
            raise ValueError(
                "Interpolation topology did not preserve every source cell"
            )
        opacity_groups[bool(shielded)].append(part)
    surfaces = []
    for masked, parts in opacity_groups.items():
        if not parts:
            continue
        # Append without merging points: component and crease boundaries remain
        # disconnected. Carry source IDs through VTK rather than assuming order.
        surface = parts[0].append_polydata(*parts[1:]) if len(parts) > 1 else parts[0]
        source_cells = np.array(surface.cell_data["source_cells"], copy=True)
        surface.cell_data.clear()
        render_surface, render_point_ids = _render_normals(
            poly, surface, source_cells, offsets, connectivity
        )
        surfaces.append(
            InterpolationGeometry(
                surface, source_cells, masked, render_surface, render_point_ids
            )
        )
    return tuple(surfaces)


def interpolated_surfaces(
    poly: pv.PolyData,
    field: ScalarField,
    geometry: tuple[InterpolationGeometry, ...] | None = None,
) -> tuple[tuple[pv.PolyData, bool], ...]:
    """Interpolate only the selected scalar on reusable display topology."""
    if not field.interpolable:
        raise ValueError("Smooth colors requires a finite continuous cell scalar")
    scalar_name = field.name
    if geometry is None:
        geometry = prepare_interpolation_geometry(poly)
    values = np.asarray(poly.cell_data[scalar_name], dtype=np.float64)
    surfaces = []
    for item in geometry:
        part = item.surface.copy(deep=False)
        part.cell_data[scalar_name] = values[item.source_cells]
        part = part.cell_data_to_point_data(pass_cell_data=False)
        if not np.isfinite(part.point_data[scalar_name]).all():
            raise ValueError("Interpolated colors are not finite")
        if item.render_surface is not None:
            render = item.render_surface.copy(deep=False)
            render.point_data[scalar_name] = part.point_data[scalar_name][
                item.render_point_ids
            ]
            part = render
        surfaces.append((part, item.shielded))
    return tuple(surfaces)
