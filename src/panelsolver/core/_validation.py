"""Validation and immutable-value helpers used by central contracts."""

from __future__ import annotations

import math
import operator
from collections.abc import Iterable, Iterator, Mapping
from numbers import Real

import numpy as np

from .errors import ContractValueError, NonFiniteError, ShapeError

_UNIT_VECTOR_ATOL = 1.0e-12


def _array_input(value: object, *, field: str) -> np.ndarray:
    """Coerce an array input without leaking NumPy's container errors."""
    try:
        return np.asarray(value)
    except (TypeError, ValueError) as exc:
        raise ContractValueError(field, "must be a rectangular array") from exc


class FrozenMapping[T](Mapping[str, T]):
    """Small insertion-ordered, immutable, and pickle-friendly mapping."""

    __slots__ = ("_items",)

    def __init__(
        self,
        values: Mapping[str, T] | Iterable[tuple[str, T]] = (),
    ) -> None:
        items = tuple(values.items()) if isinstance(values, Mapping) else tuple(values)
        keys = [key for key, _ in items]
        if len(keys) != len(set(keys)):
            raise ValueError("FrozenMapping keys must be unique")
        object.__setattr__(self, "_items", items)

    def __getitem__(self, key: str) -> T:
        for candidate, value in self._items:
            if candidate == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (key for key, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return f"FrozenMapping({dict(self._items)!r})"

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(f"{type(self).__name__} is immutable")

    def __reduce__(self) -> tuple[type[object], tuple[dict[str, T]]]:
        return type(self), (dict(self._items),)


class _ImmutableArray(np.ndarray):
    """NumPy array view whose immutable backing survives pickle round trips."""

    __slots__ = ()

    def __reduce__(self) -> tuple[object, tuple[bytes, str, tuple[int, ...]]]:
        return (
            _restore_read_only_array,
            (self.tobytes(order="C"), self.dtype.str, self.shape),
        )


def _restore_read_only_array(
    buffer: bytes,
    dtype: str,
    shape: tuple[int, ...],
) -> np.ndarray:
    return np.frombuffer(buffer, dtype=np.dtype(dtype)).reshape(shape).view(
        _ImmutableArray
    )


def _read_only_array(array: np.ndarray) -> np.ndarray:
    """Return an independent C-contiguous view backed by immutable bytes."""
    contiguous = np.ascontiguousarray(array)
    immutable_buffer = contiguous.tobytes(order="C")
    return (
        np.frombuffer(immutable_buffer, dtype=contiguous.dtype)
        .reshape(contiguous.shape)
        .view(_ImmutableArray)
    )


def float_array(
    value: object,
    *,
    field: str,
    shape: tuple[int | str, ...],
) -> np.ndarray:
    """Copy, validate, and freeze a real-valued array as float64."""
    raw = _array_input(value, field=field)
    if raw.dtype.kind not in "iuf":
        raise ContractValueError(field, "must be a real-valued array")
    array = np.array(raw, dtype=np.float64, copy=True, order="C")
    validate_shape(array, field=field, expected=shape)
    if not np.isfinite(array).all():
        raise NonFiniteError(field)
    return _read_only_array(array)


def index_array(
    value: object,
    *,
    field: str,
    shape: tuple[int | str, ...],
) -> np.ndarray:
    """Copy, validate, and freeze a non-negative integer array."""
    raw = _array_input(value, field=field)
    if raw.dtype.kind not in "iu" or not np.can_cast(
        raw.dtype, np.dtype(np.int64), casting="safe"
    ):
        raise ContractValueError(field, "must be an integer array")
    array = np.array(raw, dtype=np.int64, copy=True, order="C")
    validate_shape(array, field=field, expected=shape)
    if np.any(array < 0):
        raise ContractValueError(field, "must contain only non-negative values")
    return _read_only_array(array)


def bool_array(
    value: object,
    *,
    field: str,
    shape: tuple[int | str, ...],
) -> np.ndarray:
    """Copy, validate, and freeze a strict boolean array."""
    raw = _array_input(value, field=field)
    if raw.dtype.kind != "b":
        raise ContractValueError(field, "must be a boolean array")
    array = np.array(raw, dtype=np.bool_, copy=True, order="C")
    validate_shape(array, field=field, expected=shape)
    return _read_only_array(array)


def scalar_array(
    value: object,
    *,
    field: str,
    shape: tuple[int | str, ...],
) -> np.ndarray:
    """Copy, validate, and freeze a real or boolean visualization array."""
    raw = _array_input(value, field=field)
    if raw.dtype.kind not in "biuf":
        raise ContractValueError(
            field,
            "must be a real-valued or boolean scalar array",
        )
    array = np.array(raw, copy=True, order="C")
    validate_shape(array, field=field, expected=shape)
    if array.dtype.kind == "f" and not np.isfinite(array).all():
        raise NonFiniteError(field)
    return _read_only_array(array)


def validate_shape(
    array: np.ndarray,
    *,
    field: str,
    expected: tuple[int | str, ...],
) -> None:
    """Validate an array shape, where string dimensions are wildcards."""
    if len(array.shape) != len(expected) or any(
        not isinstance(required, str) and actual != required
        for actual, required in zip(array.shape, expected, strict=True)
    ):
        raise ShapeError(field, expected=expected, actual=array.shape)


def require_nonempty_faces(n_faces: int, *, field: str) -> None:
    if n_faces == 0:
        raise ContractValueError(field, "must contain at least one panel")


def validate_unit_vectors(array: np.ndarray, *, field: str) -> None:
    """Require unit vectors within the shared unit-vector absolute tolerance."""
    norms = np.linalg.norm(array, axis=-1)
    if not np.allclose(norms, 1.0, rtol=0.0, atol=_UNIT_VECTOR_ATOL):
        raise ContractValueError(
            field,
            f"must contain unit vectors within absolute tolerance {_UNIT_VECTOR_ATOL:g}",
        )


def real_scalar(
    value: object,
    *,
    field: str,
    positive: bool = False,
) -> float:
    """Return a validated finite Python float without accepting booleans."""
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ContractValueError(field, "must be a real scalar")
    result = float(value)
    if not math.isfinite(result):
        raise NonFiniteError(field)
    if positive and result <= 0.0:
        raise ContractValueError(field, "must be strictly positive")
    return result


def integer_scalar(
    value: object,
    *,
    field: str,
    nonnegative: bool = False,
) -> int:
    """Return a validated Python integer without accepting booleans."""
    if isinstance(value, (bool, np.bool_)):
        raise ContractValueError(field, "must be an integer")
    try:
        result = operator.index(value)
    except TypeError as exc:
        raise ContractValueError(field, "must be an integer") from exc
    if nonnegative and result < 0:
        raise ContractValueError(field, "must be non-negative")
    return result


def nonempty_text(value: object, *, field: str) -> str:
    """Require non-empty text without silently normalizing it."""
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ContractValueError(
            field,
            "must be non-empty text without leading or trailing whitespace",
        )
    return value


def freeze_payload(
    value: object,
    *,
    field: str,
) -> FrozenMapping[object]:
    """Validate and deeply freeze a JSON-shaped metadata mapping."""
    if not isinstance(value, Mapping):
        raise ContractValueError(field, "must be a mapping")
    return _freeze_payload_mapping(value, field=field, active=set())


def _freeze_payload_value(
    value: object,
    *,
    field: str,
    active: set[int],
) -> object:
    if isinstance(value, np.generic):
        value = value.item()

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise NonFiniteError(field)
        return value
    if isinstance(value, Mapping):
        return _freeze_payload_mapping(value, field=field, active=active)
    if isinstance(value, (list, tuple)):
        identity = id(value)
        if identity in active:
            raise ContractValueError(field, "must not contain reference cycles")
        active.add(identity)
        try:
            return tuple(
                _freeze_payload_value(
                    item,
                    field=f"{field}[{index}]",
                    active=active,
                )
                for index, item in enumerate(value)
            )
        finally:
            active.remove(identity)
    raise ContractValueError(
        field,
        "must contain only JSON scalar, mapping, list, or tuple values",
    )


def _freeze_payload_mapping(
    value: Mapping[object, object],
    *,
    field: str,
    active: set[int],
) -> FrozenMapping[object]:
    identity = id(value)
    if identity in active:
        raise ContractValueError(field, "must not contain reference cycles")
    active.add(identity)
    try:
        items: list[tuple[str, object]] = []
        for key, item in value.items():
            if not isinstance(key, str) or not key or key.strip() != key:
                raise ContractValueError(
                    field,
                    "keys must be non-empty text without surrounding whitespace",
                )
            items.append(
                (
                    key,
                    _freeze_payload_value(
                        item,
                        field=f"{field}.{key}",
                        active=active,
                    ),
                )
            )
        return FrozenMapping(items)
    finally:
        active.remove(identity)
