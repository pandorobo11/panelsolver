"""Internal A2 strip geometry; no aerodynamic quantities or public exports.

Ownership uses the unmodified float64 projections used by A1. Geometry is
clipped in source-local STL coordinates, independently of validation tolerances.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ._validation import float_array, index_array
from .errors import ContractValueError, NonFiniteError
from .mesh import PanelMesh
from .sectional import ResolvedSectionalLoadSpec

_U = np.finfo(np.float64).eps / 2
_TINY = np.finfo(np.float64).smallest_subnormal


def _gamma(count: int) -> float:
    return count * _U / (1 - count * _U)


def _finite(value: np.ndarray | float, field: str) -> None:
    if not np.isfinite(value).all():
        raise NonFiniteError(field)


@dataclass(frozen=True, slots=True, eq=False)
class SectionalFragmentGeometry:
    """Compact, immutable face/bin integrals in source-face then bin order.

    Every row has positive surface area. ``origins_stl_m`` is the source face's
    first vertex, repeated per fragment so no topology reinterpretation is
    needed downstream. ``area_first_moments_local_stl_m3`` integrates
    ``r_stl - origin_stl``. Thus the absolute first moment is mathematically
    ``Q_local + A * origin``; evaluate a reference-relative integral as
    ``Q_local + A * (origin - reference)`` without forming that absolute value.
    The empty result has shapes (0,) and (0, 3), without dummy rows.
    """

    source_face_indices: np.ndarray
    bin_indices: np.ndarray
    areas_m2: np.ndarray
    origins_stl_m: np.ndarray
    area_first_moments_local_stl_m3: np.ndarray

    def __post_init__(self) -> None:
        faces = index_array(
            self.source_face_indices,
            field="source_face_indices",
            shape=("n_fragments",),
        )
        count = len(faces)
        bins = index_array(self.bin_indices, field="bin_indices", shape=(count,))
        areas = float_array(self.areas_m2, field="areas_m2", shape=(count,))
        if np.any(areas <= 0):
            raise ContractValueError("areas_m2", "fragments must have positive area")
        if np.any(faces[1:] < faces[:-1]) or np.any(
            (faces[1:] == faces[:-1]) & (bins[1:] <= bins[:-1])
        ):
            raise ContractValueError(
                "source_face_indices/bin_indices", "must be in unique face/bin order"
            )
        object.__setattr__(self, "source_face_indices", faces)
        object.__setattr__(self, "bin_indices", bins)
        object.__setattr__(self, "areas_m2", areas)
        for name in ("origins_stl_m", "area_first_moments_local_stl_m3"):
            object.__setattr__(
                self,
                name,
                float_array(getattr(self, name), field=name, shape=(count, 3)),
            )


def _cross_rounding_bound(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    # Each edge subtraction, product and product difference contributes rounding.
    # gamma(8) covers the two edge errors, product/subtraction errors, and
    # evaluation of the bound itself. Use product magnitudes, not a potentially
    # cancelled cross component. Subnormal operations each add at most one ulp.
    a, b = np.abs(a), np.abs(b)
    return (
        _gamma(8) * (a[[1, 2, 0]] * b[[2, 0, 1]] + a[[2, 0, 1]] * b[[1, 2, 0]])
        + 8 * _TINY
    )


def _validate_source(
    mesh: PanelMesh, face: int, triangle: np.ndarray
) -> tuple[np.ndarray, float]:
    """Validate topology against the loader's independent rounding envelope.

    Trimesh uses (v1-v0) x (v2-v1), sqrt(sum(cross**2))/2, and mean(v0,v1,v2).
    Our local geometry uses (v1-v0) x (v2-v0). Bound both cross evaluations,
    norm rounding (including subnormal squares), and both centroid evaluations.
    No clipping residual, global translation scale for area, or ownership epsilon
    enters these bounds. Stored vertices are authoritative, not uncertain inputs.
    """
    field = f"sectional source face {face}"
    _finite(triangle, field)
    local = triangle - triangle[0]
    adjacent = triangle[2] - triangle[1]
    _finite(local, field)
    _finite(adjacent, field)
    cross = np.cross(local[1], local[2])
    loader_cross = np.cross(local[1], adjacent)
    _finite(cross, field)
    _finite(loader_cross, field)
    area = math.hypot(*cross) / 2
    _finite(area, field)
    if area == 0:
        raise ContractValueError(field, "degenerate or unrepresentable triangle area")

    cross_error = _cross_rounding_bound(local[1], local[2]) + _cross_rounding_bound(
        local[1], adjacent
    )
    squares = loader_cross * loader_cross
    squared_norm = float(np.sum(squares))
    _finite(squared_norm, field)
    loader_norm = math.hypot(*loader_cross)
    if loader_norm == 0 or squared_norm == 0:
        raise ContractValueError(field, "unrepresentable source area calculation")
    # sqrt is Lipschitz with error <= E / norm here; division by two gives area.
    square_error = math.fsum(math.ulp(float(x)) for x in squares) + 2 * math.ulp(
        squared_norm
    )
    stored_area = float(mesh.geometry.areas_m2[face])
    area_error = (
        math.hypot(*cross_error) / 2
        + (square_error / loader_norm) / 2
        + _gamma(8) * (area + stored_area)
    )
    _finite(area_error, field)
    if abs(stored_area - area) > area_error:
        raise ContractValueError(field, "topology area disagrees with PanelGeometry")

    local_center = local[1] / 3 + local[2] / 3
    stored_local_center = mesh.geometry.centers_stl_m[face] - triangle[0]
    # Two absolute additions and division in the loader mean: gamma(3).
    # Local edge subtraction, division and addition: gamma(3), plus the
    # subtraction used to compare the stored absolute centroid in this frame.
    center_error = (
        _gamma(3) * np.sum(np.abs(triangle / 3), axis=0)
        + _gamma(3) * (np.abs(local[1] / 3) + np.abs(local[2] / 3))
        + _gamma(1) * np.abs(stored_local_center)
        + 8 * _TINY
    )
    _finite(local_center, field)
    _finite(stored_local_center, field)
    _finite(center_error, field)
    if np.any(np.abs(stored_local_center - local_center) > center_error):
        raise ContractValueError(
            field, "topology centroid disagrees with PanelGeometry"
        )
    return local, area


def _band_area(area: float, width: float, span: float, weight: float) -> float:
    # Evaluate area * width / span * weight without losing a small ratio before
    # multiplying by a large area. All four operands are positive and finite.
    ma, ea = math.frexp(area)
    mw, ew = math.frexp(width)
    ms, es = math.frexp(span)
    mt, et = math.frexp(weight)
    try:
        result = math.ldexp(ma * mw / ms * mt, ea + ew - es + et)
    except OverflowError as exc:
        raise NonFiniteError("sectional fragment area") from exc
    if result == 0:
        raise ContractValueError("sectional fragment", "positive area underflow")
    _finite(result, "sectional fragment area")
    return result


def _first_moment(
    area: float, points: np.ndarray, weights: np.ndarray, divisor: int
) -> np.ndarray:
    """Area-weighted local positions, without underflowing a centroid first."""
    ma, ea = math.frexp(area)
    result = []
    try:
        for axis in range(3):
            terms = []
            for point, weight in zip(points[:, axis], weights, strict=True):
                mp, ep = math.frexp(float(point))
                mw, ew = math.frexp(float(weight))
                value = math.ldexp(ma * mp * mw / divisor, ea + ep + ew)
                if point != 0 and weight != 0 and value == 0:
                    raise ContractValueError(
                        "sectional fragment", "first moment underflow"
                    )
                terms.append(value)
            result.append(math.fsum(terms))
    except OverflowError as exc:
        raise NonFiniteError("sectional fragment first moment") from exc
    moment = np.array(result)
    _finite(moment, "sectional fragment first moment")
    return moment


def _band_integrals(
    local: np.ndarray,
    projected: np.ndarray,
    source_area: float,
    lower: float,
    upper: float,
) -> tuple[float, np.ndarray]:
    """Analytically clip/integrate a triangle over a positive-width strip.

    Vertices are in increasing projected order. Split at the middle projection.
    In each half, cross-section endpoints move linearly from a common tip along
    two source edges. A strip portion is a convex quadrilateral (or triangle).
    Its area density is linear in distance from that tip; its first-moment
    density is quadratic. Integrating these polynomials avoids subtracting nearly
    coincident 3D intersections to recover a narrow strip's surface area.

    For normalized tip distances ta,tb, area = source_area * width/span *
    (ta+tb). The area-weighted mean distance is
    2/3 * (ta**2 + ta*tb + tb**2)/(ta+tb). Interpolate the two 3D source
    edges at that mean distance and average their positions. The source-area
    factor is the affine surface Jacobian, never a conservation correction.
    Endpoint distances are retained independently on both source edges so their
    complementary weights remain accurate even immediately next to a vertex.
    """
    span = float(projected[2] - projected[0])
    _finite(span, "sectional projected span")
    areas, moments = [], []
    for tip, other, far, a, b in (
        (0, 1, 2, lower, min(upper, float(projected[1]))),
        (2, 1, 0, max(lower, float(projected[1])), upper),
    ):
        if a >= b:
            continue
        short_span = abs(float(projected[other] - projected[tip]))
        distances = np.abs(np.array([a, b]) - projected[tip])
        parameters = distances / short_span
        if np.any((distances != 0) & (parameters == 0)):
            raise ContractValueError("sectional fragment", "tip distance underflow")
        small, large = float(np.min(parameters)), float(np.max(parameters))
        # Linear endpoint weights for the area-weighted mean position. Compute
        # complementary barycentric weights from opposite-end distances, never
        # as 1-t: a narrow slice near t=1 must retain its small local position.
        scaled = parameters / large
        endpoint_weights = (scaled + np.sum(scaled)) / (3 * np.sum(scaled))
        point_weights = np.zeros(3)
        for endpoint, extent in ((other, short_span), (far, span)):
            from_tip = distances / extent
            from_end = np.abs(np.array([a, b]) - projected[endpoint]) / extent
            if np.any((distances != 0) & (from_tip == 0)) or np.any(
                (np.array([a, b]) != projected[endpoint]) & (from_end == 0)
            ):
                raise ContractValueError("sectional fragment", "intersection underflow")
            tip_weight = float(endpoint_weights @ from_end)
            end_weight = float(endpoint_weights @ from_tip)
            if (np.any(from_end != 0) and tip_weight == 0) or (
                np.any(from_tip != 0) and end_weight == 0
            ):
                raise ContractValueError("sectional fragment", "intersection underflow")
            point_weights[tip] += tip_weight
            point_weights[endpoint] += end_weight
        area = _band_area(source_area, b - a, span, small + large)
        moment = _first_moment(area, local, point_weights, 2)
        areas.append(area)
        moments.append(moment)
    return _sum_integrals(areas, moments)


def _sum_integrals(
    areas: list[float], moments: list[np.ndarray]
) -> tuple[float, np.ndarray]:
    try:
        area = math.fsum(areas)
        moment = np.array([math.fsum(x) for x in zip(*moments, strict=True)])
    except OverflowError as exc:
        raise NonFiniteError("sectional fragment integrals") from exc
    _finite(area, "sectional fragment area")
    _finite(moment, "sectional fragment first moment")
    return area, moment


def compute_sectional_fragment_geometry(
    mesh: PanelMesh, spec: ResolvedSectionalLoadSpec
) -> SectionalFragmentGeometry:
    """Validate selected source triangles and integrate their strip fragments.

    Use the same mesh that resolved ``spec``. No selection/range/bin policy is
    repeated here. After the unique selected-vertex lookup, work is
    O(selected faces * log(bins) + intersected face/bin pairs); storage is
    O(selected topology + positive-area fragments), never faces times all bins.
    All selected faces are validated, including those outside an explicit range.
    """
    if not isinstance(mesh, PanelMesh):
        raise ContractValueError("mesh", "must be a PanelMesh instance")
    if not isinstance(spec, ResolvedSectionalLoadSpec):
        raise ContractValueError("spec", "must be a ResolvedSectionalLoadSpec")
    faces = spec.selected_face_indices
    if np.any(faces >= mesh.n_faces):
        raise ContractValueError("selected_face_indices", "outside the supplied mesh")
    vertices, inverse = np.unique(mesh.faces[faces], return_inverse=True)
    # Match A1's selected-vertex matrix projection, including its operation shape.
    # Reprojecting individual vertices/faces can select a different BLAS reduction.
    with np.errstate(over="ignore", invalid="ignore", under="ignore"):
        offsets = mesh.vertices_stl_m[vertices] - spec.axis_origin_stl_m
        _finite(offsets, "selected_vertex_offsets_stl_m")
        projected = offsets @ spec.axis_direction_hat_stl
        _finite(projected, "selected_vertex_projections_m")
        face_projections = projected[inverse].reshape(-1, 3)
        source_indices, bin_indices, areas, origins, moments = [], [], [], [], []
        edges = spec.bin_edges_m
        count = len(edges) - 1
        for face, projection in zip(faces, face_projections, strict=True):
            triangle = mesh.vertices_stl_m[mesh.faces[face]]
            local, source_area = _validate_source(mesh, int(face), triangle)
            low, high = float(np.min(projection)), float(np.max(projection))
            if high < edges[0] or low > edges[-1]:
                continue
            first = min(
                count - 1, max(0, int(np.searchsorted(edges, low, side="right")) - 1)
            )
            last = min(count - 1, int(np.searchsorted(edges, high, side="left")) - 1)
            if low == high:
                last = first  # Whole face: exact right ownership, including end edge.
            elif high == edges[0] or low == edges[-1]:
                continue  # Only a line/point intersects the outer boundary.
            order = np.argsort(projection, kind="stable")
            sorted_local, sorted_projection = local[order], projection[order]
            for bin_index in range(first, last + 1):
                if low == high:
                    area = source_area
                    moment = _first_moment(area, local, np.ones(3), 3)
                else:
                    area, moment = _band_integrals(
                        sorted_local,
                        sorted_projection,
                        source_area,
                        max(low, float(edges[bin_index])),
                        min(high, float(edges[bin_index + 1])),
                    )
                source_indices.append(face)
                bin_indices.append(bin_index)
                areas.append(area)
                origins.append(triangle[0])
                moments.append(moment)
    return SectionalFragmentGeometry(
        np.array(source_indices, dtype=np.int64),
        np.array(bin_indices, dtype=np.int64),
        np.array(areas, dtype=np.float64),
        np.array(origins, dtype=np.float64).reshape(-1, 3),
        np.array(moments, dtype=np.float64).reshape(-1, 3),
    )
