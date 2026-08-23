"""Filesystem serializers for validated semantic artifact projections."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyvista as pv

from panelsolver.core import VtpProjection


def write_vtp_projection(path: str | Path, projection: VtpProjection) -> Path:
    """Write one VTP projection with the pinned binary PolyData semantics."""
    if not isinstance(projection, VtpProjection):
        raise TypeError("projection must be a VtpProjection")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    poly = pv.PolyData(projection.points, projection.faces)
    for name, values in projection.cell_data.items():
        poly.cell_data[name] = _vtk_compatible_values(
            values,
            field=f"cell_data.{name}",
        )
    for name, values in projection.field_data.items():
        poly.field_data[name] = _vtk_compatible_values(
            values,
            field=f"field_data.{name}",
        )
    poly.save(str(output), binary=True)
    return output


def _vtk_compatible_values(values: object, *, field: str) -> np.ndarray:
    """Prepare string values for PyVista's VTK bridge without changing them.

    PyVista rejects non-ASCII NumPy Unicode arrays before they reach VTK, while
    UTF-8 bytes arrays are accepted and read back as the original Unicode text.
    Convert only values that need this bridge representation; ASCII strings and
    all numeric arrays retain their existing dtype and contents.
    """
    array = np.asarray(values)
    if array.dtype.kind != "U" or all(
        str(value).isascii() for value in array.reshape(-1)
    ):
        return array
    try:
        return np.char.encode(array, encoding="utf-8")
    except UnicodeError as exc:
        raise ValueError(
            f"{field} contains text that cannot be encoded as UTF-8"
        ) from exc


__all__ = ("write_vtp_projection",)
