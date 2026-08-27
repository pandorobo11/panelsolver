"""Model-neutral ray shielding with explicit backend and batch policy."""

from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from threading import Lock

import numpy as np
import trimesh
from trimesh.ray import has_embree, ray_triangle

from .errors import PanelSolverError
from .mesh import PanelMesh
from .mesh_loading import geometry_fingerprint

try:
    from trimesh.ray import ray_pyembree as _ray_pyembree
except Exception:  # pragma: no cover - optional dependency import boundary
    _ray_pyembree = None

SHIELDING_ALGORITHM_VERSION = "ray-center-first-hit-v1"


class ShieldingError(PanelSolverError, ValueError):
    """Shielding configuration or execution failed."""


def _shielding_array(value: object, *, field: str) -> np.ndarray:
    try:
        return np.asarray(value)
    except (TypeError, ValueError) as exc:
        raise ShieldingError(f"{field} must be a rectangular array.") from exc


class RayBackend(str, Enum):
    """Supported ray-intersector selectors."""

    AUTO = "auto"
    RTREE = "rtree"
    EMBREE = "embree"


@dataclass(frozen=True, slots=True)
class ShieldingConfig:
    """Product-neutral shielding configuration supplied by a caller."""

    enabled: bool = True
    ray_backend: RayBackend | str = RayBackend.AUTO
    batch_size: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, (bool, np.bool_)):
            raise ShieldingError("enabled must be a boolean.")
        object.__setattr__(self, "enabled", bool(self.enabled))
        object.__setattr__(self, "ray_backend", _normalize_backend(self.ray_backend))
        if self.batch_size is not None:
            object.__setattr__(
                self,
                "batch_size",
                _positive_integer(self.batch_size, field="batch_size"),
            )


@dataclass(frozen=True, slots=True)
class ResolvedShieldingConfig:
    """Backend-aware configuration used in cache and signature identity."""

    enabled: bool
    requested_backend: str
    effective_backend: str
    batch_size: int
    algorithm_version: str = SHIELDING_ALGORITHM_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, (bool, np.bool_)):
            raise ShieldingError("enabled must be a boolean.")
        requested = _normalize_backend(self.requested_backend).value
        if self.effective_backend not in {"not_used", "rtree", "embree"}:
            raise ShieldingError(
                "effective_backend must be one of: not_used, rtree, embree."
            )
        if not isinstance(self.algorithm_version, str) or (
            not self.algorithm_version
            or self.algorithm_version.strip() != self.algorithm_version
        ):
            raise ShieldingError(
                "algorithm_version must be non-empty text without surrounding whitespace."
            )
        if self.enabled:
            if self.effective_backend == "not_used":
                raise ShieldingError(
                    "enabled shielding requires an rtree or embree effective backend."
                )
            batch_size = _positive_integer(self.batch_size, field="batch_size")
        else:
            if self.effective_backend != "not_used" or self.batch_size != 0:
                raise ShieldingError(
                    "disabled shielding requires effective_backend='not_used' "
                    "and batch_size=0."
                )
            batch_size = 0
        object.__setattr__(self, "enabled", bool(self.enabled))
        object.__setattr__(self, "requested_backend", requested)
        object.__setattr__(self, "batch_size", batch_size)


@dataclass(frozen=True, slots=True, eq=False)
class ShieldingResult:
    """Immutable exact mask and the configuration that produced it."""

    shielded: np.ndarray
    config: ResolvedShieldingConfig
    geometry_fingerprint: str
    cache_hit: bool

    def __post_init__(self) -> None:
        mask = _shielding_array(self.shielded, field="shielded")
        if mask.dtype != np.bool_ or mask.ndim != 1:
            raise ShieldingError("shielded must be a one-dimensional bool array.")
        immutable = np.frombuffer(
            np.ascontiguousarray(mask).tobytes(), dtype=np.bool_
        ).reshape(mask.shape)
        object.__setattr__(self, "shielded", immutable)


@dataclass(frozen=True, slots=True)
class ShieldingCacheStats:
    """Atomic statistics for mask and intersector caches."""

    mask_entries: int
    intersector_entries: int
    mask_hits: int
    mask_misses: int
    intersector_hits: int
    intersector_misses: int


_CACHE_LOCK = Lock()
_MASK_CACHE: OrderedDict[tuple[object, ...], np.ndarray] = OrderedDict()
_INTERSECTOR_CACHE: OrderedDict[tuple[object, ...], object] = OrderedDict()
_MASK_HITS = 0
_MASK_MISSES = 0
_INTERSECTOR_HITS = 0
_INTERSECTOR_MISSES = 0
_MASK_CACHE_MAX = 1
_INTERSECTOR_CACHE_MAX = 1


def _normalize_backend(value: RayBackend | str | None) -> RayBackend:
    raw = str(value.value if isinstance(value, RayBackend) else value or "auto")
    try:
        return RayBackend(raw.strip().lower() or "auto")
    except ValueError as exc:
        raise ShieldingError(
            "ray_backend must be one of: auto, rtree, embree."
        ) from exc


def _positive_integer(value: object, *, field: str) -> int:
    if isinstance(value, (bool, np.bool_)):
        raise ShieldingError(f"{field} must be an integer >= 1.")
    try:
        if isinstance(value, (str, int, np.integer)):
            parsed = int(value)
        else:
            raise TypeError
    except (TypeError, ValueError, OverflowError) as exc:
        raise ShieldingError(f"{field} must be an integer >= 1.") from exc
    if parsed < 1:
        raise ShieldingError(f"{field} must be an integer >= 1.")
    return parsed


def _resolve_batch_size(config: ShieldingConfig, effective_backend: str) -> int:
    if config.batch_size is not None:
        return config.batch_size
    return 64 if effective_backend == RayBackend.EMBREE.value else 8


def _validated_direction(value: np.ndarray) -> np.ndarray:
    direction = _shielding_array(value, field="velocity_hat_stl")
    if direction.shape != (3,):
        raise ShieldingError("velocity_hat_stl must have shape (3,).")
    if direction.dtype.kind not in "fiu":
        raise ShieldingError("velocity_hat_stl must contain real numbers.")
    direction = np.asarray(direction, dtype=np.float64)
    if not np.all(np.isfinite(direction)):
        raise ShieldingError("velocity_hat_stl must contain only finite values.")
    norm = float(np.linalg.norm(direction))
    if not math.isfinite(norm) or norm == 0.0:
        raise ShieldingError("velocity_hat_stl must have nonzero finite norm.")
    return -direction / norm


def _ray_mesh(mesh: PanelMesh) -> trimesh.Trimesh:
    return trimesh.Trimesh(
        vertices=np.array(mesh.vertices_stl_m, copy=True),
        faces=np.array(mesh.faces, copy=True),
        process=False,
    )


def _new_intersector(ray_mesh: trimesh.Trimesh, backend: str) -> object:
    if backend == RayBackend.RTREE.value:
        return ray_triangle.RayMeshIntersector(ray_mesh)
    if not has_embree or _ray_pyembree is None:
        raise ShieldingError(
            "ray_backend='embree' was requested, but Embree is not available. "
            "Install optional dependency 'rayaccel' or use ray_backend='rtree'."
        )
    return _ray_pyembree.RayMeshIntersector(ray_mesh)


def _resolve_intersector(
    mesh: PanelMesh,
    requested_backend: RayBackend,
    fingerprint: str,
) -> tuple[object, str]:
    global _INTERSECTOR_HITS, _INTERSECTOR_MISSES
    ray_mesh = _ray_mesh(mesh)
    if requested_backend is RayBackend.AUTO:
        auto_intersector = ray_mesh.ray
        module = type(auto_intersector).__module__
        effective = (
            RayBackend.EMBREE.value
            if "ray_pyembree" in module
            else RayBackend.RTREE.value
        )
    else:
        auto_intersector = None
        effective = requested_backend.value

    key = (SHIELDING_ALGORITHM_VERSION, fingerprint, effective)
    with _CACHE_LOCK:
        cached = _INTERSECTOR_CACHE.get(key)
        if cached is not None:
            _INTERSECTOR_HITS += 1
            _INTERSECTOR_CACHE.move_to_end(key)
            return cached, effective

    intersector = auto_intersector or _new_intersector(ray_mesh, effective)
    with _CACHE_LOCK:
        _INTERSECTOR_MISSES += 1
        _INTERSECTOR_CACHE[key] = intersector
        _INTERSECTOR_CACHE.move_to_end(key)
        while len(_INTERSECTOR_CACHE) > _INTERSECTOR_CACHE_MAX:
            _INTERSECTOR_CACHE.popitem(last=False)
    return intersector, effective


def _mask_cache_key(
    fingerprint: str,
    upstream_direction: np.ndarray,
    resolved: ResolvedShieldingConfig,
) -> tuple[object, ...]:
    # Grazing masks can change discontinuously below decimal rounding scales.
    direction_key = np.ascontiguousarray(
        upstream_direction,
        dtype=np.dtype("<f8"),
    ).tobytes()
    return (
        resolved.algorithm_version,
        fingerprint,
        resolved.effective_backend,
        resolved.batch_size,
        direction_key,
    )


def clear_shielding_cache(*, reset_stats: bool = True) -> None:
    """Clear process-local mask/intersector caches and optionally counters."""
    global _INTERSECTOR_HITS, _INTERSECTOR_MISSES, _MASK_HITS, _MASK_MISSES
    with _CACHE_LOCK:
        _MASK_CACHE.clear()
        _INTERSECTOR_CACHE.clear()
        if reset_stats:
            _MASK_HITS = 0
            _MASK_MISSES = 0
            _INTERSECTOR_HITS = 0
            _INTERSECTOR_MISSES = 0


def shielding_cache_stats() -> ShieldingCacheStats:
    """Return an atomic snapshot of shielding-cache state."""
    with _CACHE_LOCK:
        return ShieldingCacheStats(
            mask_entries=len(_MASK_CACHE),
            intersector_entries=len(_INTERSECTOR_CACHE),
            mask_hits=_MASK_HITS,
            mask_misses=_MASK_MISSES,
            intersector_hits=_INTERSECTOR_HITS,
            intersector_misses=_INTERSECTOR_MISSES,
        )


def compute_shielding(
    mesh: PanelMesh,
    velocity_hat_stl: np.ndarray,
    config: ShieldingConfig | None = None,
) -> ShieldingResult:
    """Compute the pinned face-center first-hit shielding mask."""
    global _MASK_HITS, _MASK_MISSES
    if not isinstance(mesh, PanelMesh):
        raise TypeError("mesh must be a PanelMesh instance")
    if config is None:
        config = ShieldingConfig()
    if not isinstance(config, ShieldingConfig):
        raise TypeError("config must be a ShieldingConfig instance")

    fingerprint = geometry_fingerprint(mesh)
    if not config.enabled:
        return ShieldingResult(
            np.zeros(mesh.n_faces, dtype=np.bool_),
            ResolvedShieldingConfig(
                enabled=False,
                requested_backend=config.ray_backend.value,
                effective_backend="not_used",
                batch_size=0,
            ),
            fingerprint,
            False,
        )

    upstream_direction = _validated_direction(velocity_hat_stl)
    intersector, effective_backend = _resolve_intersector(
        mesh,
        config.ray_backend,
        fingerprint,
    )
    resolved = ResolvedShieldingConfig(
        enabled=True,
        requested_backend=config.ray_backend.value,
        effective_backend=effective_backend,
        batch_size=_resolve_batch_size(config, effective_backend),
    )
    key = _mask_cache_key(fingerprint, upstream_direction, resolved)
    with _CACHE_LOCK:
        cached = _MASK_CACHE.get(key)
        if cached is not None:
            _MASK_HITS += 1
            _MASK_CACHE.move_to_end(key)
            return ShieldingResult(cached, resolved, fingerprint, True)

    centers = mesh.geometry.centers_stl_m
    bounds = np.stack(
        (np.min(mesh.vertices_stl_m, axis=0), np.max(mesh.vertices_stl_m, axis=0))
    )
    diagonal_m = float(np.linalg.norm(bounds[1] - bounds[0]))
    epsilon_m = max(1.0e-9, 1.0e-6 * diagonal_m)
    shielded = np.zeros(mesh.n_faces, dtype=np.bool_)
    for start in range(0, mesh.n_faces, resolved.batch_size):
        end = min(start + resolved.batch_size, mesh.n_faces)
        origins = centers[start:end] + upstream_direction[None, :] * epsilon_m
        directions = np.repeat(upstream_direction[None, :], end - start, axis=0)
        triangle_indices, ray_indices = intersector.intersects_id(
            ray_origins=origins,
            ray_directions=directions,
            multiple_hits=False,
            return_locations=False,
        )
        if len(ray_indices) == 0:
            continue
        global_ray_indices = np.asarray(ray_indices, dtype=np.int64) + start
        hit_other_face = np.asarray(triangle_indices) != global_ray_indices
        if np.any(hit_other_face):
            shielded[global_ray_indices[hit_other_face]] = True

    with _CACHE_LOCK:
        _MASK_MISSES += 1
        immutable = np.frombuffer(shielded.tobytes(), dtype=np.bool_)
        _MASK_CACHE[key] = immutable
        _MASK_CACHE.move_to_end(key)
        while len(_MASK_CACHE) > _MASK_CACHE_MAX:
            _MASK_CACHE.popitem(last=False)
    return ShieldingResult(shielded, resolved, fingerprint, False)


__all__ = (
    "SHIELDING_ALGORITHM_VERSION",
    "RayBackend",
    "ResolvedShieldingConfig",
    "ShieldingCacheStats",
    "ShieldingConfig",
    "ShieldingError",
    "ShieldingResult",
    "clear_shielding_cache",
    "compute_shielding",
    "shielding_cache_stats",
)
