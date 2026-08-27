from __future__ import annotations

import unittest

import numpy as np

from panelsolver.core import (
    ContractValueError,
    LocalLoads,
    ModelCasePayload,
    PanelFlowState,
    PanelGeometry,
)
from panelsolver.models import (
    DuplicateModelError,
    ModelCaseMismatchError,
    ModelOutputError,
    ModelRegistry,
    ModelRegistryError,
    UnknownModelError,
)


def geometry() -> PanelGeometry:
    return PanelGeometry(
        centers_stl_m=np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
        normals_out_stl=np.array([[-1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]]),
        areas_m2=np.ones(2),
        component_ids=np.zeros(2, dtype=int),
    )


def flow(*, shielded: tuple[bool, bool] = (False, False)) -> PanelFlowState:
    return PanelFlowState(
        velocity_hat_stl=np.array([1.0, 0.0, 0.0]),
        shielded=np.array(shielded, dtype=bool),
    )


class SyntheticModel:
    algorithm_version = "synthetic-1"

    def __init__(self, model_id: str, *, tangential: float = 0.0) -> None:
        self.model_id = model_id
        self.tangential = tangential
        self.validated = False

    def validate_case(self, case: ModelCasePayload) -> None:
        self.validated = True
        scale = case.payload.get("scale")
        if not isinstance(scale, (int, float)) or isinstance(scale, bool):
            raise ContractValueError("ModelCasePayload.payload.scale", "is required")

    def evaluate(
        self,
        geometry: PanelGeometry,
        flow_state: PanelFlowState,
        case: ModelCasePayload,
    ) -> LocalLoads:
        scale = float(case.payload["scale"])
        traction = -scale * geometry.normals_out_stl.copy()
        traction[:, 1] += self.tangential
        traction[flow_state.shielded] = 0.0
        return LocalLoads(
            traction_coeff_stl=traction,
            cell_scalars={
                "normal_traction_coeff": -np.einsum(
                    "ij,ij->i",
                    traction,
                    geometry.normals_out_stl,
                )
            },
            metadata={"model_kind": self.model_id},
        )


class ModelRegistryTests(unittest.TestCase):
    def test_registry_represents_normal_and_tangential_models_uniformly(self) -> None:
        normal = SyntheticModel("normal")
        tangential = SyntheticModel("tangential", tangential=0.25)
        registry = ModelRegistry((normal, tangential))

        normal_loads = registry.evaluate(
            geometry(),
            flow(),
            ModelCasePayload("normal", {"scale": 2.0}),
        )
        tangential_loads = registry.evaluate(
            geometry(),
            flow(),
            ModelCasePayload("tangential", {"scale": 2.0}),
        )

        self.assertEqual(("normal", "tangential"), registry.model_ids)
        self.assertTrue(normal.validated)
        self.assertTrue(tangential.validated)
        np.testing.assert_array_equal(
            normal_loads.traction_coeff_stl[:, 1],
            np.zeros(2),
        )
        np.testing.assert_array_equal(
            tangential_loads.traction_coeff_stl[:, 1],
            np.full(2, 0.25),
        )
        self.assertTrue(
            np.any(
                np.cross(
                    tangential_loads.traction_coeff_stl,
                    geometry().normals_out_stl,
                )
                != 0.0
            )
        )

    def test_registry_rejects_duplicate_unknown_and_nonconforming_models(self) -> None:
        registry = ModelRegistry()
        registry.register(SyntheticModel("normal"))
        with self.assertRaises(DuplicateModelError):
            registry.register(SyntheticModel("normal"))
        with self.assertRaises(UnknownModelError):
            registry.get("missing")
        with self.assertRaises(ModelRegistryError):
            registry.register(object())

    def test_registry_validates_case_before_evaluation(self) -> None:
        registry = ModelRegistry((SyntheticModel("normal"),))
        with self.assertRaises(ContractValueError):
            registry.evaluate(
                geometry(),
                flow(),
                ModelCasePayload("normal", {"not_scale": 2.0}),
            )

    def test_registry_rejects_mismatched_panel_counts(self) -> None:
        registry = ModelRegistry((SyntheticModel("normal"),))
        one_panel_flow = PanelFlowState(
            velocity_hat_stl=np.array([1.0, 0.0, 0.0]),
            shielded=np.array([False]),
        )
        with self.assertRaises(ModelRegistryError):
            registry.evaluate(
                geometry(),
                one_panel_flow,
                ModelCasePayload("normal", {"scale": 2.0}),
            )

    def test_registry_rejects_invalid_model_outputs(self) -> None:
        class WrongTypeModel(SyntheticModel):
            def evaluate(self, geometry, flow_state, case):
                return np.zeros((geometry.n_faces, 3))

        class WrongSizeModel(SyntheticModel):
            def evaluate(self, geometry, flow_state, case):
                return LocalLoads(np.zeros((1, 3)))

        class NonzeroShieldedModel(SyntheticModel):
            def evaluate(self, geometry, flow_state, case):
                return LocalLoads(np.ones((geometry.n_faces, 3)))

        cases = (
            (WrongTypeModel("wrong-type"), flow()),
            (WrongSizeModel("wrong-size"), flow()),
            (NonzeroShieldedModel("nonzero-shielded"), flow(shielded=(False, True))),
        )
        for model, state in cases:
            with (
                self.subTest(model=model.model_id),
                self.assertRaises(ModelOutputError),
            ):
                ModelRegistry((model,)).evaluate(
                    geometry(),
                    state,
                    ModelCasePayload(model.model_id, {"scale": 1.0}),
                )

    def test_registry_detects_identity_mutation_after_registration(self) -> None:
        model = SyntheticModel("before")
        registry = ModelRegistry((model,))
        model.model_id = "after"
        with self.assertRaises(ModelCaseMismatchError):
            registry.evaluate(
                geometry(),
                flow(),
                ModelCasePayload("before", {"scale": 1.0}),
            )


if __name__ == "__main__":
    unittest.main()
