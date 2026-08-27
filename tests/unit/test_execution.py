from __future__ import annotations

import unittest

import numpy as np

from panelsolver.app import default_model_registry, request_from_registry
from panelsolver.core import (
    CaseExecutionRequest,
    CommonCasePayload,
    ExecutionError,
    ExecutionModelError,
    LocalLoads,
    MeshValidationPolicy,
    ModelCasePayload,
    ShieldingConfig,
    case_execution_bucket_keys,
    execute_case,
)

from .test_mesh_loading import FIXTURE_STL


class _CountingModel:
    model_id = "synthetic"
    algorithm_version = "synthetic-v1"

    def __init__(self) -> None:
        self.evaluate_calls = 0

    def validate_case(self, case: ModelCasePayload) -> None:
        if case.payload.get("fail_validation"):
            raise RuntimeError("model validation failed")

    def signature_payload(self, case: ModelCasePayload):
        return dict(case.payload)

    def evaluate(self, geometry, flow_state, case):
        self.evaluate_calls += 1
        traction = np.ones((geometry.n_faces, 3), dtype=np.float64)
        traction[flow_state.shielded] = 0.0
        return LocalLoads(traction)


class _WrongOutputModel(_CountingModel):
    def evaluate(self, geometry, flow_state, case):
        return object()


class _FlowEchoModel(_CountingModel):
    def evaluate(self, geometry, flow_state, case):
        self.evaluate_calls += 1
        traction = np.tile(flow_state.velocity_hat_stl, (geometry.n_faces, 1))
        traction[flow_state.shielded] = 0.0
        flow_y = np.full(geometry.n_faces, flow_state.velocity_hat_stl[1])
        return LocalLoads(
            traction,
            {"flow_y": flow_y},
            {"flow_y": float(flow_state.velocity_hat_stl[1])},
        )


def _common_case(**updates) -> CommonCasePayload:
    values = {
        "case_id": "synthetic-case",
        "Aref_m2": 1.0,
        "moment_reference_stl_m": [0.0, 0.0, 0.0],
        "Lref_Cl_m": 1.0,
        "Lref_Cm_m": 1.0,
        "Lref_Cn_m": 1.0,
        "alpha_t_deg": 0.0,
        "beta_t_deg": 0.0,
    }
    values.update(updates)
    return CommonCasePayload(**values)


def _request(model=None, **updates) -> CaseExecutionRequest:
    model = _CountingModel() if model is None else model
    values = {
        "model": model,
        "common_case": _common_case(),
        "model_case": ModelCasePayload("synthetic", {"value": 1}),
        "stl_paths": [FIXTURE_STL / "plate.stl"],
        "scale_m_per_unit": 1.0,
        "velocity_hat_stl": np.array([1.0, 0.0, 0.0]),
        "shielding": ShieldingConfig(enabled=False),
    }
    values.update(updates)
    return CaseExecutionRequest(**values)


class ExecutionTests(unittest.TestCase):
    def test_one_engine_evaluates_and_integrates_a_protocol_model(self) -> None:
        model = _CountingModel()
        result = execute_case(_request(model))

        self.assertEqual(1, model.evaluate_calls)
        self.assertEqual("not_used", result.shielding.config.effective_backend)
        self.assertEqual("synthetic", result.results.model_id)
        self.assertEqual(
            result.signature.digest, result.results.metadata["case_signature"]
        )
        self.assertEqual(
            result.mesh.n_faces,
            result.results.local_loads.traction_coeff_stl.shape[0],
        )

    def test_each_call_evaluates_the_exact_accepted_flow_direction(self) -> None:
        model = _FlowEchoModel()
        request_a = _request(
            model,
            velocity_hat_stl=np.array([1.0, 0.0, 0.0]),
        )
        request_b = _request(
            model,
            velocity_hat_stl=np.array([1.0, 1.0e-12, 0.0]),
        )
        next_float = np.nextafter(1.0, 2.0)
        request_c = _request(
            model,
            velocity_hat_stl=np.array([next_float, 0.0, 0.0]),
        )

        first_a = execute_case(request_a)
        first_b = execute_case(request_b)
        first_c = execute_case(request_c)
        repeated_b = execute_case(request_b)

        self.assertEqual(first_a.signature.digest, first_b.signature.digest)
        self.assertEqual(first_a.signature.digest, first_c.signature.digest)
        self.assertEqual(4, model.evaluate_calls)
        np.testing.assert_array_equal(
            first_b.results.local_loads.traction_coeff_stl[:, 1],
            np.full(first_b.mesh.n_faces, 1.0e-12),
        )
        np.testing.assert_array_equal(
            first_c.results.local_loads.traction_coeff_stl[:, 0],
            np.full(first_c.mesh.n_faces, next_float),
        )
        np.testing.assert_array_equal(
            repeated_b.results.local_loads.traction_coeff_stl,
            first_b.results.local_loads.traction_coeff_stl,
        )

    def test_requested_backend_remains_in_signature_when_shielding_is_off(self) -> None:
        model = _CountingModel()
        first = execute_case(
            _request(
                model,
                shielding=ShieldingConfig(enabled=False, ray_backend="rtree"),
            ),
        )
        second = execute_case(
            _request(
                model,
                shielding=ShieldingConfig(enabled=False, ray_backend="embree"),
            ),
        )
        self.assertNotEqual(first.signature.digest, second.signature.digest)
        self.assertEqual(2, model.evaluate_calls)

    def test_mesh_policy_alias_has_strict_request_and_scheduler_identity(self) -> None:
        shielding = ShieldingConfig(enabled=True, ray_backend="rtree")
        strict = _request(
            shielding=shielding,
            mesh_validation_policy=MeshValidationPolicy.STRICT,
        )
        alias = _request(
            shielding=shielding,
            mesh_validation_policy=MeshValidationPolicy.LEGACY_WARN_REPAIR,
        )
        self.assertEqual(MeshValidationPolicy.STRICT, alias.mesh_validation_policy)
        self.assertEqual(
            case_execution_bucket_keys((strict,))[0],
            case_execution_bucket_keys((alias,))[0],
        )

    def test_model_failures_propagate_and_invalid_outputs_are_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "model validation failed"):
            execute_case(
                _request(
                    model_case=ModelCasePayload("synthetic", {"fail_validation": True})
                )
            )
        with self.assertRaisesRegex(ExecutionModelError, "LocalLoads"):
            execute_case(_request(_WrongOutputModel()))

    def test_request_rejects_mismatched_identity_and_flow_direction(self) -> None:
        with self.assertRaisesRegex(ExecutionModelError, "does not match"):
            _request(model_case=ModelCasePayload("other", {}))
        with self.assertRaisesRegex(ExecutionError, "tangent angles"):
            _request(velocity_hat_stl=np.array([0.0, 1.0, 0.0]))
        accepted = _request(
            velocity_hat_stl=np.array([1.0, 1.0e-12, 0.0]),
        )
        np.testing.assert_array_equal(
            accepted.velocity_hat_stl,
            np.array([1.0, 1.0e-12, 0.0]),
        )
        with self.assertRaisesRegex(ExecutionError, "tangent angles"):
            _request(velocity_hat_stl=np.array([1.0, 2.0e-12, 0.0]))

    def test_app_assembles_both_models_without_core_branching(self) -> None:
        registry = default_model_registry()
        self.assertEqual(("sentman", "hypersonic"), registry.model_ids)
        model_case = ModelCasePayload(
            "sentman",
            {"S": 5.0, "Ti_K": 300.0, "Tw_K": 400.0},
        )
        request = request_from_registry(
            registry,
            common_case=_common_case(),
            model_case=model_case,
            stl_paths=[FIXTURE_STL / "plate.stl"],
            scale_m_per_unit=1.0,
            velocity_hat_stl=np.array([1.0, 0.0, 0.0]),
            shielding=ShieldingConfig(enabled=False),
        )
        self.assertEqual("sentman", request.model.model_id)


if __name__ == "__main__":
    unittest.main()
