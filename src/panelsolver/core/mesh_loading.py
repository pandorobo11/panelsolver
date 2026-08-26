"""Strict, model-neutral STL loading and geometry fingerprinting."""

from __future__ import annotations

import hashlib
import io
import math
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from threading import Lock

import numpy as np
import trimesh

from .contracts import PanelGeometry
from .errors import PanelSolverError
from .mesh import MeshComponent, PanelMesh

MESH_LOADER_ALGORITHM_VERSION = "mesh-loader-v1"
GEOMETRY_FINGERPRINT_SCHEMA_VERSION = 1


class MeshLoadError(PanelSolverError, ValueError):
    """A source mesh cannot satisfy the shared geometry contract."""


class MeshValidationPolicy(str, Enum):
    """Accepted mesh-policy names; both enforce ADR 0008 strict safety."""

    STRICT = "strict"
    LEGACY_WARN_REPAIR = "legacy_warn_repair"


@dataclass(frozen=True, slots=True)
class MeshSourceFingerprint:
    """Resolved source identity used by the process-local mesh cache."""

    path: str
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class LoadedPanelMesh:
    """A validated panel mesh with source and geometry provenance."""

    mesh: PanelMesh
    geometry_fingerprint: str
    source_fingerprints: tuple[MeshSourceFingerprint, ...]
    validation_policy: MeshValidationPolicy
    warnings: tuple[str, ...]
    loader_algorithm_version: str = MESH_LOADER_ALGORITHM_VERSION


@dataclass(frozen=True, slots=True)
class MeshCacheStats:
    """Runtime statistics for the process-local mesh cache."""

    entries: int
    hits: int
    misses: int


@dataclass(frozen=True, slots=True)
class _MeshSourceSnapshot:
    fingerprint: MeshSourceFingerprint
    content: bytes


_CACHE_LOCK = Lock()
_MESH_CACHE: OrderedDict[tuple[object, ...], LoadedPanelMesh] = OrderedDict()
_CACHE_HITS = 0
_CACHE_MISSES = 0
_MESH_CACHE_MAX = 1


def _source_snapshot(path_value: str | Path) -> _MeshSourceSnapshot:
    try:
        path = Path(path_value).expanduser().resolve()
        content = path.read_bytes()
    except (OSError, TypeError, ValueError) as exc:
        raise MeshLoadError(
            f"Unable to read mesh source {path_value!r}: {exc}"
        ) from exc
    fingerprint = MeshSourceFingerprint(
        str(path),
        len(content),
        hashlib.sha256(content).hexdigest(),
    )
    return _MeshSourceSnapshot(fingerprint, content)


def _normalize_policy(value: MeshValidationPolicy | str) -> MeshValidationPolicy:
    try:
        MeshValidationPolicy(value)
    except (TypeError, ValueError) as exc:
        choices = ", ".join(policy.value for policy in MeshValidationPolicy)
        raise MeshLoadError(f"validation_policy must be one of: {choices}.") from exc
    return MeshValidationPolicy.STRICT


def _normalize_scale(value: float) -> float:
    if isinstance(value, (bool, np.bool_)):
        raise MeshLoadError("scale_m_per_unit must be a finite value > 0.")
    try:
        scale = float(value)
    except (TypeError, ValueError) as exc:
        raise MeshLoadError("scale_m_per_unit must be a finite value > 0.") from exc
    if not math.isfinite(scale) or scale <= 0.0:
        raise MeshLoadError("scale_m_per_unit must be a finite value > 0.")
    return scale


def _canonical_array_bytes(value: np.ndarray, dtype: str) -> bytes:
    array = np.ascontiguousarray(np.asarray(value, dtype=np.dtype(dtype)))
    return b"".join(
        (
            np.asarray([array.ndim], dtype="<i8").tobytes(),
            np.asarray(array.shape, dtype="<i8").tobytes(),
            array.tobytes(),
        )
    )


def geometry_fingerprint(mesh: PanelMesh) -> str:
    """Return the versioned SHA-256 identity of numerical mesh content.

    Source paths and file timestamps are intentionally excluded. Face order,
    component assignment, derived geometry, topology, and SI-scaled vertices
    are included because each can affect shielding or integrated coefficients.
    """
    if not isinstance(mesh, PanelMesh):
        raise TypeError("mesh must be a PanelMesh instance")

    digest = hashlib.sha256()
    digest.update(b"panelsolver.geometry\0")
    digest.update(
        np.asarray([GEOMETRY_FINGERPRINT_SCHEMA_VERSION], dtype="<i8").tobytes()
    )
    fields = (
        ("vertices_stl_m", mesh.vertices_stl_m, "<f8"),
        ("faces", mesh.faces, "<i8"),
        ("centers_stl_m", mesh.geometry.centers_stl_m, "<f8"),
        ("normals_out_stl", mesh.geometry.normals_out_stl, "<f8"),
        ("areas_m2", mesh.geometry.areas_m2, "<f8"),
        ("component_ids", mesh.geometry.component_ids, "<i8"),
    )
    for name, values, dtype in fields:
        digest.update(name.encode("ascii"))
        digest.update(b"\0")
        digest.update(_canonical_array_bytes(values, dtype))
    return digest.hexdigest()


def _load_source_mesh(source: _MeshSourceSnapshot) -> trimesh.Trimesh:
    path = source.fingerprint.path
    try:
        loaded = trimesh.load_mesh(
            file_obj=io.BytesIO(source.content),
            file_type="stl",
            force="mesh",
        )
    except Exception as exc:
        raise MeshLoadError(f"Failed to load mesh source {path}: {exc}") from exc
    if isinstance(loaded, trimesh.Scene):
        geometries = tuple(loaded.geometry.values())
        if not geometries:
            raise MeshLoadError(f"Mesh source {path} contains no geometry.")
        loaded = trimesh.util.concatenate(geometries)
    if not isinstance(loaded, trimesh.Trimesh):
        raise MeshLoadError(f"Mesh source {path} did not produce a triangle mesh.")
    if len(loaded.faces) == 0:
        raise MeshLoadError(f"Mesh source {path} contains no triangle faces.")
    return loaded


def _load_uncached(
    source_snapshots: tuple[_MeshSourceSnapshot, ...],
    scale_m_per_unit: float,
    validation_policy: MeshValidationPolicy,
) -> LoadedPanelMesh:
    sources = tuple(source.fingerprint for source in source_snapshots)
    source_meshes = [_load_source_mesh(source) for source in source_snapshots]
    component_ids = np.concatenate(
        [
            np.full(len(source_mesh.faces), index, dtype=np.int64)
            for index, source_mesh in enumerate(source_meshes)
        ]
    )
    combined = (
        trimesh.util.concatenate(source_meshes)
        if len(source_meshes) > 1
        else source_meshes[0]
    )
    combined.vertices = (
        np.asarray(combined.vertices, dtype=np.float64) * scale_m_per_unit
    )
    vertices = np.asarray(combined.vertices, dtype=np.float64)
    if not np.isfinite(vertices).all():
        raise MeshLoadError(
            "Mesh geometry violates the shared contract: contains non-finite vertices."
        )
    faces = np.asarray(combined.faces, dtype=np.int64)
    with np.errstate(over="ignore", invalid="ignore"):
        edges_a = vertices[faces[:, 1]] - vertices[faces[:, 0]]
        edges_b = vertices[faces[:, 2]] - vertices[faces[:, 0]]
        pre_repair_areas = 0.5 * np.linalg.norm(np.cross(edges_a, edges_b), axis=1)
    invalid_pre_repair = ~np.isfinite(pre_repair_areas) | (pre_repair_areas <= 0.0)
    if np.any(invalid_pre_repair):
        count = int(np.count_nonzero(invalid_pre_repair))
        raise MeshLoadError(
            "Mesh geometry violates the shared contract: "
            f"contains {count} degenerate or non-finite triangle face(s)."
        )

    warning_messages: list[str] = []
    try:
        trimesh.repair.fix_normals(combined, multibody=True)
    except Exception as exc:
        message = f"Failed to repair mesh face normals: {exc}"
        raise MeshLoadError(message) from exc

    if not combined.is_winding_consistent:
        raise MeshLoadError(
            "Mesh face winding remains inconsistent after normal repair."
        )
    if not combined.is_watertight:
        warning_messages.append(
            "[WARN] Mesh is not watertight (trimesh). Continuing anyway."
        )

    areas = np.asarray(combined.area_faces, dtype=np.float64)
    invalid_areas = ~np.isfinite(areas) | (areas <= 0.0)
    if np.any(invalid_areas):
        count = int(np.count_nonzero(invalid_areas))
        raise MeshLoadError(
            "Mesh geometry violates the shared contract: "
            f"contains {count} degenerate or non-finite triangle face(s)."
        )

    try:
        geometry = PanelGeometry(
            centers_stl_m=np.asarray(combined.triangles_center, dtype=np.float64),
            normals_out_stl=np.asarray(combined.face_normals, dtype=np.float64),
            areas_m2=areas,
            component_ids=component_ids,
        )
        panel_mesh = PanelMesh(
            vertices_stl_m=np.asarray(combined.vertices, dtype=np.float64),
            faces=np.asarray(combined.faces, dtype=np.int64),
            geometry=geometry,
            components=tuple(
                MeshComponent(component_id=index, source=source.path)
                for index, source in enumerate(sources)
            ),
        )
    except PanelSolverError as exc:
        raise MeshLoadError(
            f"Mesh geometry violates the shared contract: {exc}"
        ) from exc

    return LoadedPanelMesh(
        mesh=panel_mesh,
        geometry_fingerprint=geometry_fingerprint(panel_mesh),
        source_fingerprints=sources,
        validation_policy=validation_policy,
        warnings=tuple(warning_messages),
    )


def clear_mesh_cache(*, reset_stats: bool = True) -> None:
    """Clear the process-local mesh cache and optionally its counters."""
    global _CACHE_HITS, _CACHE_MISSES
    with _CACHE_LOCK:
        _MESH_CACHE.clear()
        if reset_stats:
            _CACHE_HITS = 0
            _CACHE_MISSES = 0


def mesh_cache_stats() -> MeshCacheStats:
    """Return an atomic snapshot of process-local mesh-cache statistics."""
    with _CACHE_LOCK:
        return MeshCacheStats(len(_MESH_CACHE), _CACHE_HITS, _CACHE_MISSES)


def load_panel_mesh(
    stl_paths: Sequence[str | Path],
    scale_m_per_unit: float,
    *,
    validation_policy: MeshValidationPolicy | str = MeshValidationPolicy.STRICT,
    warning_callback: Callable[[str], None] | None = None,
) -> LoadedPanelMesh:
    """Load ordered STL sources into the immutable shared mesh contract.

    The cache key reads and hashes source bytes on every call. This intentionally
    avoids the legacy metadata-only cache identities, which can reuse stale
    geometry after metadata-preserving file replacement.
    """
    global _CACHE_HITS, _CACHE_MISSES
    if isinstance(stl_paths, (str, bytes, Path)):
        raise MeshLoadError("stl_paths must be a non-empty sequence of paths.")
    try:
        path_values = tuple(stl_paths)
    except TypeError as exc:
        raise MeshLoadError("stl_paths must be a non-empty sequence of paths.") from exc
    if not path_values:
        raise MeshLoadError("stl_paths must be a non-empty sequence of paths.")

    scale = _normalize_scale(scale_m_per_unit)
    policy = _normalize_policy(validation_policy)
    source_snapshots = tuple(_source_snapshot(path) for path in path_values)
    sources = tuple(source.fingerprint for source in source_snapshots)
    key = (
        MESH_LOADER_ALGORITHM_VERSION,
        policy.value,
        scale,
        tuple((source.path, source.size, source.sha256) for source in sources),
    )
    with _CACHE_LOCK:
        cached = _MESH_CACHE.get(key)
        if cached is not None:
            _CACHE_HITS += 1
            _MESH_CACHE.move_to_end(key)

    if cached is None:
        loaded = _load_uncached(source_snapshots, scale, policy)
        with _CACHE_LOCK:
            _CACHE_MISSES += 1
            _MESH_CACHE[key] = loaded
            _MESH_CACHE.move_to_end(key)
            while len(_MESH_CACHE) > _MESH_CACHE_MAX:
                _MESH_CACHE.popitem(last=False)
    else:
        loaded = cached

    if warning_callback is not None:
        for message in loaded.warnings:
            warning_callback(message)
    return loaded


__all__ = (
    "GEOMETRY_FINGERPRINT_SCHEMA_VERSION",
    "MESH_LOADER_ALGORITHM_VERSION",
    "LoadedPanelMesh",
    "MeshCacheStats",
    "MeshLoadError",
    "MeshSourceFingerprint",
    "MeshValidationPolicy",
    "clear_mesh_cache",
    "geometry_fingerprint",
    "load_panel_mesh",
    "mesh_cache_stats",
)
