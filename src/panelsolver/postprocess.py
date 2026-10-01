"""Stable sectional-load postprocessing of an in-memory solve result.

Only the callable and returned field interfaces are public. Nested result
constructors and numerical modules remain implementation details.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from panelsolver.api import SolveResult
from panelsolver.core._sectional_integration import (
    SectionalLoadResult as _SectionalLoadResult,
)
from panelsolver.core._sectional_integration import integrate_sectional_loads
from panelsolver.core.sectional import (
    SectionalLoadDefinition,
    resolve_sectional_load_spec,
)


@dataclass(frozen=True, slots=True, eq=False)
class SectionalLoads(_SectionalLoadResult):
    """Immutable strip integrals and the originating physical case signature.

    ``spec`` exposes axis, requested/resolved range, bins, selection and coverage.
    ``case`` exposes original common references and case identity. ``total`` and
    ``components`` reuse core distributions without copying coefficient arrays.
    Their documented returned fields are stable; direct construction is private.
    """

    case_signature: str

    def __deepcopy__(self, memo: dict[int, object]) -> SectionalLoads:
        # All returned fields are immutable; copying a NumPy subclass otherwise
        # risks making a supposedly frozen numerical buffer writable.
        return self


def compute_sectional_loads(
    result: SolveResult,
    *,
    axis_origin_stl_m: Sequence[float] | np.ndarray,
    axis_direction_stl: Sequence[float] | np.ndarray,
    bin_count: int,
    start_m: float | None = None,
    stop_m: float | None = None,
    component_ids: Sequence[int] | None = None,
) -> SectionalLoads:
    """Integrate solved traction in equal-width strips along an STL-frame axis.

    Origin and signed bounds are metres; direction is a nonzero dimensionless
    vector. Omit both bounds for the selected geometry's range. Component IDs are
    the original zero-based input-STL IDs, or all components when omitted.
    ``total`` means the selected components within this range, using the original
    references.

    This performs no source reads, shielding or physical solves. A manually
    constructed/replaced result without retained solve context raises ValueError.
    """
    if not isinstance(result, SolveResult):
        raise TypeError("result must be a SolveResult")
    context = result._sectional_context
    if context is None:
        raise ValueError(
            "result has no retained solve context; use the original result from "
            "solve_fmf() or solve_hypersonic()"
        )
    definition = SectionalLoadDefinition(
        axis_origin_stl_m=axis_origin_stl_m,  # type: ignore[arg-type]
        axis_direction_stl=axis_direction_stl,  # type: ignore[arg-type]
        bin_count=bin_count,
        start_m=start_m,
        stop_m=stop_m,
        component_ids=component_ids,  # type: ignore[arg-type]
    )
    numerical = integrate_sectional_loads(
        context.mesh,
        resolve_sectional_load_spec(context.mesh, definition),
        result.local_loads,
        context.case,
    )
    return SectionalLoads(
        numerical.spec,
        numerical.case,
        numerical.total,
        numerical.components,
        result.case_signature,
    )


__all__ = ("SectionalLoads", "compute_sectional_loads")
