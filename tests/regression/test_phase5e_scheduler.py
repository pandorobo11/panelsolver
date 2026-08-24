from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

from panelsolver.app import default_model_registry, request_from_registry
from panelsolver.core import (
    CommonCasePayload,
    ModelCasePayload,
    PartialResultPolicy,
    ShieldingConfig,
    WorkerLogPolicy,
    case_execution_bucket_keys,
    execute_case,
    iter_execution_results_parallel,
)
from panelsolver.core.execution import case_execution_affinity_hints

REPOSITORY_ROOT = Path(__file__).parents[2]
FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "phase1"
GOLDEN_ROOT = FIXTURE_ROOT / "golden"


def _npz_array(golden: dict, name: str) -> np.ndarray:
    record = golden["npz"]["arrays"][name]
    return np.asarray(record["values"]).reshape(record["shape"])


def _request_for(path: Path):
    golden = json.loads(path.read_text(encoding="utf-8"))
    normalized = golden["normalized_input"]
    model_id = "sentman" if path.parent.name == "fmfsolver" else "hypersonic"
    common_case = CommonCasePayload(
        case_id=normalized["case_id"],
        Aref_m2=normalized["Aref_m2"],
        moment_reference_stl_m=[
            normalized["ref_x_m"],
            normalized["ref_y_m"],
            normalized["ref_z_m"],
        ],
        Lref_Cl_m=normalized["Lref_Cl_m"],
        Lref_Cm_m=normalized["Lref_Cm_m"],
        Lref_Cn_m=normalized["Lref_Cn_m"],
        alpha_t_deg=float(_npz_array(golden, "alpha_t_deg_resolved")),
        beta_t_deg=float(_npz_array(golden, "beta_t_deg_resolved")),
    )
    source_names = [
        Path(value).name for value in str(normalized["stl_path"]).split(";")
    ]
    return request_from_registry(
        default_model_registry(),
        common_case=common_case,
        model_case=ModelCasePayload(model_id, normalized),
        stl_paths=[FIXTURE_ROOT / "inputs" / "stl" / name for name in source_names],
        scale_m_per_unit=normalized["stl_scale_m_per_unit"],
        velocity_hat_stl=_npz_array(golden, "Vhat_stl"),
        shielding=ShieldingConfig(
            enabled=bool(normalized["shielding_on"]),
            ray_backend=normalized["ray_backend"],
        ),
    )


class Phase5eSchedulerRegressionTests(unittest.TestCase):
    def test_both_models_match_serial_engine_through_spawn_scheduler(self) -> None:
        paths = (
            GOLDEN_ROOT / "fmfsolver" / "fmf_zero_plate.json",
            GOLDEN_ROOT / "newtsolver" / "newt_zero_newtonian.json",
        )
        requests = tuple(_request_for(path) for path in paths)
        serial = tuple(execute_case(request) for request in requests)
        progress = []
        snapshots = []
        parallel_pairs = list(
            iter_execution_results_parallel(
                requests,
                2,
                log_policy=WorkerLogPolicy.FORWARD,
                partial_result_policy=PartialResultPolicy.DISCARD_CHUNK,
                chunk_cases=1,
                progress_cb=progress.append,
                snapshot_cb=snapshots.append,
            )
        )
        parallel = dict(parallel_pairs)
        self.assertEqual({0, 1}, set(parallel))
        self.assertEqual([1, 2], [event.completed for event in progress])
        self.assertEqual((0, 1), tuple(index for index, _result in snapshots[-1]))
        for index, expected in enumerate(serial):
            actual = parallel[index]
            self.assertEqual(expected.signature, actual.signature)
            np.testing.assert_array_equal(
                expected.shielding.shielded,
                actual.shielding.shielded,
            )
            np.testing.assert_array_equal(
                expected.results.local_loads.traction_coeff_stl,
                actual.results.local_loads.traction_coeff_stl,
            )
            np.testing.assert_array_equal(
                expected.results.total.force_coeff_stl,
                actual.results.total.force_coeff_stl,
            )
            np.testing.assert_array_equal(
                expected.results.total.moment_area_coeff_body_m,
                actual.results.total.moment_area_coeff_body_m,
            )

    def test_bucket_hints_share_only_model_neutral_shielding_work(self) -> None:
        sentman = _request_for(
            GOLDEN_ROOT / "fmfsolver" / "fmf_shield_rtree.json"
        )
        hypersonic = _request_for(
            GOLDEN_ROOT / "newtsolver" / "newt_shield_rtree.json"
        )
        disabled = _request_for(
            GOLDEN_ROOT / "fmfsolver" / "fmf_zero_plate.json"
        )
        keys = case_execution_bucket_keys((sentman, hypersonic, disabled))
        self.assertEqual(keys[0], keys[1])
        self.assertEqual("single", keys[2][0])
        self.assertNotEqual(
            execute_case(sentman).signature,
            execute_case(hypersonic).signature,
        )

    def test_model_affinity_hints_do_not_change_primary_bucket_identity(self) -> None:
        sentman = _request_for(
            GOLDEN_ROOT / "fmfsolver" / "fmf_zero_plate.json"
        )
        cone = _request_for(
            GOLDEN_ROOT / "newtsolver" / "newt_tangent_cone.json"
        )
        wedge = _request_for(
            GOLDEN_ROOT / "newtsolver" / "newt_tangent_wedge.json"
        )
        hints = case_execution_affinity_hints((sentman, cone, wedge))
        self.assertEqual((), hints[0])
        self.assertEqual(("tangent_cone", 6.0, 1.4), hints[1][0].identity)
        self.assertEqual(("tangent_wedge", 6.0, 1.4), hints[2][0].identity)

        shielding = ShieldingConfig(enabled=True, ray_backend="rtree")
        cone_key, wedge_key = case_execution_bucket_keys(
            (
                replace(cone, shielding=shielding),
                replace(wedge, shielding=shielding),
            )
        )
        self.assertEqual(cone_key, wedge_key)


if __name__ == "__main__":
    unittest.main()
