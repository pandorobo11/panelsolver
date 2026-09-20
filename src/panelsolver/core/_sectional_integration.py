"""Internal A3 traction integration; no stable public API or artifact identity."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ._sectional_geometry import (
    SectionalFragmentGeometry,
    compute_sectional_fragment_geometry,
)
from ._validation import float_array, integer_scalar
from .contracts import CommonCasePayload, LocalLoads
from .errors import ContractValueError, NonFiniteError
from .frames import body_to_stability, stl_to_body
from .mesh import PanelMesh
from .sectional import ResolvedSectionalLoadSpec


@dataclass(frozen=True, slots=True, eq=False)
class SectionalLoadDistribution:
    """Primitive strip integrals, with immutable derived coefficient views.

    Area includes every surface fragment, including zero-traction surfaces.
    All vectors have shape (bins, 3); coefficients are dimensionless except
    the area-normalized moment numerator, which has units of metres.
    """

    wetted_area_m2: np.ndarray
    force_coeff_stl: np.ndarray
    force_coeff_body: np.ndarray
    force_coeff_stability: np.ndarray
    moment_area_coeff_body_m: np.ndarray
    moment_coeff_body: np.ndarray

    def __post_init__(self) -> None:
        area = float_array(self.wetted_area_m2, field="wetted_area_m2", shape=("bins",))
        if len(area) == 0 or np.any(area < 0):
            raise ContractValueError("wetted_area_m2", "requires nonnegative bins")
        object.__setattr__(self, "wetted_area_m2", area)
        for name in (
            "force_coeff_stl",
            "force_coeff_body",
            "force_coeff_stability",
            "moment_area_coeff_body_m",
            "moment_coeff_body",
        ):
            object.__setattr__(
                self,
                name,
                float_array(getattr(self, name), field=name, shape=(len(area), 3)),
            )

    @property
    def CA(self) -> np.ndarray:
        return _negative(self.force_coeff_body[:, 0])

    @property
    def CY(self) -> np.ndarray:
        return self.force_coeff_body[:, 1]

    @property
    def CN(self) -> np.ndarray:
        return _negative(self.force_coeff_body[:, 2])

    @property
    def CD(self) -> np.ndarray:
        return _negative(self.force_coeff_stability[:, 0])

    @property
    def CL(self) -> np.ndarray:
        return _negative(self.force_coeff_stability[:, 2])

    @property
    def Cl(self) -> np.ndarray:
        return self.moment_coeff_body[:, 0]

    @property
    def Cm(self) -> np.ndarray:
        return self.moment_coeff_body[:, 1]

    @property
    def Cn(self) -> np.ndarray:
        return self.moment_coeff_body[:, 2]


def _negative(values: np.ndarray) -> np.ndarray:
    # Unary minus allocates a writable array; freeze signed views as well.
    return float_array(-values, field="coefficient view", shape=values.shape)


@dataclass(frozen=True, slots=True, eq=False)
class SectionalComponentDistribution:
    """One original mesh component, using the selected total's bins/references."""

    component_id: int
    distribution: SectionalLoadDistribution

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "component_id",
            integer_scalar(self.component_id, field="component_id", nonnegative=True),
        )
        if not isinstance(self.distribution, SectionalLoadDistribution):
            raise ContractValueError(
                "distribution", "must be a SectionalLoadDistribution"
            )


@dataclass(frozen=True, slots=True, eq=False)
class SectionalLoadResult:
    """Internal A4 handoff, retaining only resolved bins and numerical context.

    These names are not a stable Python surface. A4 owns retained solve context
    and public adaptation; A5 owns artifact identity/signatures.
    """

    spec: ResolvedSectionalLoadSpec
    case: CommonCasePayload
    total: SectionalLoadDistribution
    components: tuple[SectionalComponentDistribution, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.spec, ResolvedSectionalLoadSpec):
            raise ContractValueError("spec", "must be a ResolvedSectionalLoadSpec")
        if not isinstance(self.case, CommonCasePayload):
            raise ContractValueError("case", "must be a CommonCasePayload")
        try:
            components = tuple(self.components)
        except TypeError as exc:
            raise ContractValueError(
                "components", "must be component distributions"
            ) from exc
        if not all(
            isinstance(item, SectionalComponentDistribution) for item in components
        ):
            raise ContractValueError("components", "must be component distributions")
        if (
            tuple(item.component_id for item in components)
            != self.spec.selected_component_ids
        ):
            raise ContractValueError("components", "must follow selected component IDs")
        for distribution in (self.total, *(item.distribution for item in components)):
            if not isinstance(distribution, SectionalLoadDistribution):
                raise ContractValueError(
                    "distribution", "must be a SectionalLoadDistribution"
                )
            if len(distribution.wetted_area_m2) != self.spec.definition.bin_count:
                raise ContractValueError("distribution", "bin count must match spec")
        object.__setattr__(self, "components", components)


def _sum_rows(rows: np.ndarray) -> np.ndarray:
    """Accurately reduce each column in deterministic source/component order."""
    return np.array([math.fsum(column) for column in rows.T], dtype=np.float64)


def _distribution(
    values: np.ndarray, case: CommonCasePayload
) -> SectionalLoadDistribution:
    force_stl, moment_body = values[:, 1:4], values[:, 4:7]
    force_body = stl_to_body(force_stl)
    return SectionalLoadDistribution(
        wetted_area_m2=values[:, 0],
        force_coeff_stl=force_stl,
        force_coeff_body=force_body,
        force_coeff_stability=body_to_stability(
            force_body, alpha_stability_deg=case.alpha_stability_deg
        ),
        moment_area_coeff_body_m=moment_body,
        moment_coeff_body=moment_body
        / np.array([case.Lref_Cl_m, case.Lref_Cm_m, case.Lref_Cn_m]),
    )


def integrate_sectional_loads(
    mesh: PanelMesh,
    spec: ResolvedSectionalLoadSpec,
    local_loads: LocalLoads,
    case: CommonCasePayload,
) -> SectionalLoadResult:
    """Integrate full-vector traction over A2 fragments using global references.

    Supply the same mesh/spec pair as A1 and loads from that mesh's solve. A2
    runs once here, so callers cannot attach unrelated cached fragments. Like
    A1/A2, this boundary does not fingerprint mesh identity. It checks face and
    component alignment; retaining matching topology is the caller's duty.

    Beyond A2 geometry, work/storage are O(selected faces + fragments + C*B),
    where C*B is the required component/bin output size. No face-by-bin scan,
    shielding/model evaluation, source-moment scaling, or residual repair occurs.
    """
    for name, value, expected in (
        ("mesh", mesh, PanelMesh),
        ("spec", spec, ResolvedSectionalLoadSpec),
        ("local_loads", local_loads, LocalLoads),
        ("case", case, CommonCasePayload),
    ):
        if not isinstance(value, expected):
            raise ContractValueError(name, f"must be a {expected.__name__}")
    if local_loads.n_faces != mesh.n_faces:
        raise ContractValueError("local_loads", "panel count must match mesh")
    if np.any(spec.selected_face_indices >= mesh.n_faces):
        raise ContractValueError("selected_face_indices", "outside the supplied mesh")
    selected_ids = spec.selected_component_ids
    component_positions = {
        component_id: i for i, component_id in enumerate(selected_ids)
    }
    face_components = dict(
        zip(
            spec.selected_face_indices,
            mesh.face_component_ids[spec.selected_face_indices],
            strict=True,
        )
    )
    if set(face_components.values()) != set(selected_ids):
        raise ContractValueError("spec", "selected components disagree with mesh")

    fragments = compute_sectional_fragment_geometry(mesh, spec)
    if not isinstance(fragments, SectionalFragmentGeometry):
        raise ContractValueError("fragments", "must be a SectionalFragmentGeometry")
    bin_count = spec.definition.bin_count
    if np.any(fragments.source_face_indices >= mesh.n_faces):
        raise ContractValueError("source_face_indices", "outside the supplied mesh")
    if np.any(fragments.bin_indices >= bin_count):
        raise ContractValueError("bin_indices", "outside the supplied spec")
    groups: dict[tuple[int, int], list[int]] = {}
    for row, (face, bin_index) in enumerate(
        zip(fragments.source_face_indices, fragments.bin_indices, strict=True)
    ):
        if face not in face_components:
            raise ContractValueError("source_face_indices", "outside selected faces")
        component = component_positions[face_components[face]]
        groups.setdefault((component, int(bin_index)), []).append(row)

    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            traction = local_loads.traction_coeff_stl[fragments.source_face_indices]
            force_stl = traction * (fragments.areas_m2 / case.Aref_m2)[:, None]
            # Keep the local first moment: never construct a rounded absolute Q
            # or divide by tiny area to recover a fragment centroid.
            q_reference_stl = fragments.area_first_moments_local_stl_m3 + (
                fragments.areas_m2[:, None]
                * (fragments.origins_stl_m - case.moment_reference_stl_m)
            )
            moment_body = (
                np.cross(stl_to_body(q_reference_stl), stl_to_body(traction))
                / case.Aref_m2
            )
            values = np.column_stack((fragments.areas_m2, force_stl, moment_body))
            by_component = np.zeros((len(selected_ids), bin_count, 7))
            for (component, bin_index), rows in groups.items():
                by_component[component, bin_index] = _sum_rows(values[rows])
            total = np.array(
                [
                    _sum_rows(by_component[:, bin_index])
                    for bin_index in range(bin_count)
                ]
            )
            return SectionalLoadResult(
                spec=spec,
                case=case,
                total=_distribution(total, case),
                components=tuple(
                    SectionalComponentDistribution(
                        component_id, _distribution(values, case)
                    )
                    for component_id, values in zip(
                        selected_ids, by_component, strict=True
                    )
                ),
            )
    except (FloatingPointError, OverflowError) as exc:
        raise NonFiniteError("sectional load integration") from exc
