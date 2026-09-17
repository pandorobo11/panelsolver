"""Independent A3 source oracle and ADR 0019 representation budgets (tests only)."""

import math
from decimal import Decimal, localcontext

import numpy as np


def _norm(values):
    return sum(x * x for x in values).sqrt()


def source_oracle(mesh, loads, case, faces):
    """Use 80-digit topology integrals, never A2/A3 or stored centroids as truth.

    E_A and E_r compare the *source representation* against high precision,
    independently of any sectional output. E_r includes the actual float64
    reference subtraction used by the old integrator. The 1e-70 relative
    envelope conservatively covers the Decimal sqrt/divisions and accumulation
    in these fixtures; it is explicitly added before outward float conversion.
    """
    with localcontext() as context:
        context.prec = 80
        zero = Decimal(0)
        oracle_rounding = Decimal("1e-70")
        reference = [Decimal(float(x)) for x in case.moment_reference_stl_m]
        aref = Decimal(case.Aref_m2)
        area_sum = zero
        force, moment = [zero] * 3, [zero] * 3
        force_scale = moment_scale = budget_force = budget_moment = zero
        for face in faces:
            triangle = mesh.vertices_stl_m[mesh.faces[face]]
            points = [[Decimal(float(x)) for x in p] for p in triangle]
            a = [points[1][i] - points[0][i] for i in range(3)]
            b = [points[2][i] - points[0][i] for i in range(3)]
            cross = [a[i] * b[j] - a[j] * b[i] for i, j in ((1, 2), (2, 0), (0, 1))]
            area = _norm(cross) / 2
            lever = [
                (a[i] + b[i]) / 3 + (points[0][i] - reference[i]) for i in range(3)
            ]
            traction = [Decimal(float(x)) for x in loads.traction_coeff_stl[face]]
            t = _norm(traction)
            face_force = [area * x / aref for x in traction]
            # T is a proper rotation: T(r x F) = T(r) x T(F).
            face_moment = [
                sign * (lever[i] * face_force[j] - lever[j] * face_force[i])
                for sign, (i, j) in zip(
                    (-1, 1, -1), ((1, 2), (2, 0), (0, 1)), strict=True
                )
            ]
            area_sum += area
            force = [x + y for x, y in zip(force, face_force, strict=True)]
            moment = [x + y for x, y in zip(moment, face_moment, strict=True)]
            force_scale += area * t / aref
            # Bound local first-moment arithmetic without using a cancelled
            # resultant or the magnitude of absolute translated coordinates.
            extent = (_norm(a) + _norm(b)) / 3 + _norm(
                [points[0][i] - reference[i] for i in range(3)]
            )
            moment_scale += area * t * extent / aref
            stored_area = Decimal(float(mesh.geometry.areas_m2[face]))
            stored_lever = np.asarray(mesh.geometry.centers_stl_m[face]) - np.asarray(
                case.moment_reference_stl_m
            )
            error_area = abs(stored_area - area) + oracle_rounding * area
            error_lever = (
                _norm([Decimal(float(stored_lever[i])) - lever[i] for i in range(3)])
                + oracle_rounding * extent
            )
            budget_force += t * error_area / aref
            budget_moment += (
                t * (error_area * _norm(lever) + stored_area * error_lever) / aref
            )

        def upper(value):
            return np.nextafter(float(value), np.inf) if value else 0.0

        return {
            "area": float(area_sum),
            "force": np.array([float(x) for x in force]),
            "moment": np.array([float(x) for x in moment]),
            "force_tolerance": upper(
                (Decimal("1e-11") + oracle_rounding) * force_scale
            ),
            "moment_tolerance": upper(
                (Decimal("1e-11") + oracle_rounding) * moment_scale
            ),
            "force_budget": upper(budget_force),
            "moment_budget": upper(budget_moment),
        }


def sum_bins(values):
    return np.array([math.fsum(column) for column in np.asarray(values).T])


def assert_conservation(mesh, loads, case, faces, distribution, baseline):
    expected = source_oracle(mesh, loads, case, faces)
    area_error = abs(math.fsum(distribution.wetted_area_m2) - expected["area"])
    assert area_error <= 1e-11 * expected["area"]
    errors = {}
    for kind, field in (
        ("force", "force_coeff_stl"),
        ("moment", "moment_area_coeff_body_m"),
    ):
        actual = sum_bins(getattr(distribution, field))
        local_error = np.linalg.norm(actual - expected[kind])
        stored_error = np.linalg.norm(actual - getattr(baseline, field))
        tolerance = expected[f"{kind}_tolerance"]
        budget = expected[f"{kind}_budget"]
        assert local_error <= tolerance, (kind, local_error, tolerance)
        assert stored_error <= tolerance + budget, (
            kind,
            stored_error,
            tolerance,
            budget,
        )
        errors[f"{kind}_local_error"] = local_error
        errors[f"{kind}_stored_error"] = stored_error
    # Orthogonal transforms preserve the norm budget; normalized moments get
    # the component-specific reference length, never a common assumed length.
    for field in ("force_coeff_body", "force_coeff_stability"):
        assert np.linalg.norm(
            sum_bins(getattr(distribution, field)) - getattr(baseline, field)
        ) <= (expected["force_tolerance"] + expected["force_budget"])
    lengths = np.array([case.Lref_Cl_m, case.Lref_Cm_m, case.Lref_Cn_m])
    assert np.all(
        np.abs(sum_bins(distribution.moment_coeff_body) - baseline.moment_coeff_body)
        <= (expected["moment_tolerance"] + expected["moment_budget"]) / lengths
    )
    return expected | errors
