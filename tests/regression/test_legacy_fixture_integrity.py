from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import unittest
from fnmatch import fnmatchcase
from pathlib import Path, PureWindowsPath
from unittest import mock

import numpy as np

REPOSITORY_ROOT = Path(__file__).parents[2]
FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "phase1"
GOLDEN_ROOT = FIXTURE_ROOT / "golden"
MANIFEST = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
COEFFICIENTS = ("CA", "CY", "CN", "Cl", "Cm", "Cn", "CD", "CL")
COMMON_VTP_CELL_ARRAYS = {
    "area_m2",
    "shielded",
    "Cp_n",
    "theta_deg",
    "C_face_stl",
    "center_x_stl_m",
    "center_y_stl_m",
    "center_z_stl_m",
    "stl_index",
}
COMMON_VTP_FIELD_ARRAYS = {
    "case_id",
    "case_signature",
    "solver_version",
    "stl_count",
    "ray_backend_used",
    "attitude_input_used",
    "alpha_t_deg_resolved",
    "beta_t_deg_resolved",
    "stl_paths_json",
}
COMMON_NPZ_ARRAYS = {
    "vertices",
    "faces",
    "centers_stl_m",
    "normals_out_stl",
    "areas_m2",
    "shielded",
    "Vhat_stl",
    "Aref_m2",
    "attitude_input",
    "alpha_t_deg_resolved",
    "beta_t_deg_resolved",
    "C_force_stl",
    "C_force_body",
    "C_M_body",
    "CA",
    "CY",
    "CN",
    "Cl",
    "Cm",
    "Cn",
    "CD",
    "CL",
    "Cp_n",
    "face_stl_index",
    "stl_paths",
    "ray_backend_used",
}


def _load_case(solver: str, case_id: str) -> dict:
    return json.loads(
        (GOLDEN_ROOT / solver / f"{case_id}.json").read_text(encoding="utf-8")
    )


def _values(record: dict) -> np.ndarray:
    return np.asarray(record["values"])


def _total_row(case: dict) -> dict:
    rows = [row for row in case["csv"]["rows"] if row["scope"] == "total"]
    if len(rows) != 1:
        raise AssertionError("Expected one total row")
    return rows[0]


def _case_metadata(solver: str) -> dict[str, dict]:
    return {item["case_id"]: item for item in MANIFEST["cases"][solver]}


def _numeric_leaf_paths(value: object, path: tuple[str, ...] = ()) -> list[str]:
    if isinstance(value, dict):
        return [
            leaf
            for key, item in value.items()
            for leaf in _numeric_leaf_paths(item, (*path, str(key)))
        ]
    if isinstance(value, list):
        return [
            leaf
            for index, item in enumerate(value)
            for leaf in _numeric_leaf_paths(item, (*path, str(index)))
        ]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return ["/".join(path)]
    return []


class LegacyFixtureManifestTests(unittest.TestCase):
    def test_pinned_sources_match_migration_sources(self) -> None:
        migration_sources = (
            REPOSITORY_ROOT
            / "devdocs"
            / "history"
            / "migration"
            / "MIGRATION_SOURCES.md"
        ).read_text(encoding="utf-8")
        for source in MANIFEST["sources"].values():
            self.assertRegex(source["commit"], r"^[0-9a-f]{40}$")
            self.assertIn(source["commit"], migration_sources)
            self.assertIn(source["repository"], migration_sources)

    def test_source_assets_have_recorded_content_hashes(self) -> None:
        for relative, expected in MANIFEST["assets"].items():
            digest = hashlib.sha256((FIXTURE_ROOT / relative).read_bytes()).hexdigest()
            self.assertEqual(expected, digest, relative)

    def test_every_declared_case_has_one_provenanced_golden(self) -> None:
        for solver, source in MANIFEST["sources"].items():
            metadata = _case_metadata(solver)
            actual = {
                path.stem
                for path in (GOLDEN_ROOT / solver).glob("*.json")
                if path.name != "contracts.json"
            }
            self.assertEqual(set(metadata), actual)
            for case_id, expected in metadata.items():
                case = _load_case(solver, case_id)
                provenance = case["provenance"]
                self.assertEqual(source["repository"], provenance["source_repository"])
                self.assertEqual(source["commit"], provenance["source_commit"])
                self.assertRegex(provenance["source_lock_sha256"], r"^[0-9a-f]{64}$")
                self.assertEqual(
                    MANIFEST["generation"]["command"], provenance["generation_command"]
                )
                self.assertEqual(
                    expected["requested_backend"], provenance["requested_backend"]
                )
                self.assertEqual(
                    expected["requested_backend"],
                    case["normalized_input"]["ray_backend"],
                )
                self.assertEqual(
                    expected["expected_effective_backend"],
                    provenance["effective_backend"],
                )
                self.assertEqual(
                    expected["tolerance_profile"], provenance["tolerance_profile"]
                )
                self.assertIn(
                    provenance["tolerance_profile"], MANIFEST["tolerance_profiles"]
                )

    def test_fixture_matrix_covers_phase1_minimum(self) -> None:
        covered = {"invalid_input", *MANIFEST["contract_coverage"]}
        for cases in MANIFEST["cases"].values():
            for case in cases:
                covered.update(case["coverage"])
        for solver, paths in MANIFEST["invalid_inputs"].items():
            self.assertTrue(paths, solver)
        self.assertEqual(set(), set(MANIFEST["required_coverage"]) - covered)

    def test_every_tolerance_override_matches_a_captured_numeric_value(self) -> None:
        all_paths: set[str] = set()
        for solver in MANIFEST["sources"]:
            for case_id, metadata in _case_metadata(solver).items():
                paths = set(_numeric_leaf_paths(_load_case(solver, case_id)))
                all_paths.update(paths)
                profile = MANIFEST["tolerance_profiles"][metadata["tolerance_profile"]]
                for override in profile.get("path_overrides", []):
                    for pattern in override["paths"]:
                        self.assertTrue(
                            any(fnmatchcase(path, pattern) for path in paths),
                            f"{case_id}: unused tolerance path {pattern}",
                        )
        for pattern in MANIFEST["exact_numeric_paths"]:
            self.assertTrue(
                any(fnmatchcase(path, pattern) for path in all_paths),
                f"unused exact numeric path {pattern}",
            )


class LegacyFixtureComparatorTests(unittest.TestCase):
    def test_public_command_and_environment_contracts_are_captured(self) -> None:
        expected_scripts = {
            "fmfsolver": {"fmfsolver", "fmfsolver-gui", "fmfsolver-cli"},
            "newtsolver": {"newtsolver", "newtsolver-gui", "newtsolver-cli"},
        }
        expected_suite_counts = {"fmfsolver": 75, "newtsolver": 90}
        for solver in MANIFEST["sources"]:
            contract = json.loads(
                (GOLDEN_ROOT / solver / "contracts.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                expected_scripts[solver], set(contract["package"]["scripts"])
            )
            self.assertEqual([], contract["package"]["package_all"])
            self.assertIn(
                f"usage: {solver.replace('solver', 'solver-cli')}",
                contract["cli"]["help"],
            )
            self.assertIn(solver, contract["module_paths"])
            self.assertEqual(
                expected_suite_counts[solver], contract["legacy_suite"]["tests_run"]
            )
            self.assertEqual("passed", contract["legacy_suite"]["status"])

            locked = contract["environments"]["locked"]
            accelerated = contract["environments"]["rayaccel"]
            self.assertFalse(locked["trimesh_has_embree"])
            self.assertEqual(
                "rtree", locked["backend_selection"]["auto"]["value"]["effective"]
            )
            self.assertEqual("error", locked["backend_selection"]["embree"]["status"])
            self.assertTrue(accelerated["trimesh_has_embree"])
            self.assertEqual(
                "embree", accelerated["backend_selection"]["auto"]["value"]["effective"]
            )
            self.assertEqual(
                "rtree", accelerated["backend_selection"]["rtree"]["value"]["effective"]
            )
            self.assertEqual(
                "embree",
                accelerated["backend_selection"]["embree"]["value"]["effective"],
            )
            self.assertFalse(locked["embree_binding"]["available"])
            self.assertTrue(accelerated["embree_binding"]["available"])
            self.assertEqual(
                "<platform-specific-embree-distribution>",
                accelerated["embree_binding"]["distribution"],
            )
            self.assertEqual("3.12", locked["python"])
            self.assertEqual("3.12", accelerated["python"])

            provenance = contract["provenance"]
            environments = MANIFEST["generation"]["environments"]
            self.assertEqual(environments, provenance["environments"])
            self.assertEqual(environments[0], provenance["legacy_suite_environment"])
            self.assertEqual(environments[1], provenance["cli_run_environment"])

            invalid = contract["invalid_inputs"]
            expected_names = {
                Path(path).name for path in MANIFEST["invalid_inputs"][solver]
            }
            self.assertEqual(expected_names, set(invalid))
            self.assertTrue(all(item["status"] == "error" for item in invalid.values()))

    def test_semantic_comparator_accepts_the_committed_tree(self) -> None:
        module = self._load_comparator_module()
        differences = module.compare_capture_trees(GOLDEN_ROOT, GOLDEN_ROOT, MANIFEST)
        self.assertEqual([], differences)

    def test_semantic_comparator_applies_quantity_specific_tolerances(self) -> None:
        module = self._load_comparator_module()

        def compare(
            expected: float,
            actual: float,
            profile: str,
            path: tuple[str, ...],
        ) -> list[str]:
            return module._compare_values(
                expected,
                actual,
                manifest=MANIFEST,
                profile_name=profile,
                path=path,
            )

        output_path = ("csv", "rows", "0", "CA")
        self.assertEqual([], compare(1.0, 1.0 + 5e-11, "fmf_default", output_path))
        self.assertTrue(compare(1.0, 1.0 + 5e-9, "fmf_default", output_path))

        input_path = ("csv", "rows", "0", "Aref_m2")
        self.assertTrue(compare(1.0, 1.0 + 1e-15, "fmf_default", input_path))

        geometry_path = ("npz", "arrays", "vertices", "values", "0")
        self.assertEqual([], compare(1.0, 1.0 + 5e-13, "newt_algebraic", geometry_path))
        self.assertTrue(compare(1.0, 1.0 + 5e-11, "newt_algebraic", geometry_path))

        cone_path = ("vtp", "cell_data", "Cp_n", "values", "0")
        self.assertEqual(
            [], compare(1.0, 1.0 + 5.05e-8, "newt_tangent_cone", cone_path)
        )
        self.assertTrue(compare(1.0, 1.0 + 8e-8, "newt_tangent_cone", cone_path))

        blank = module._csv_cell("CA", "", roots={})
        numeric_nan = module._csv_cell("CA", "nan", roots={})
        self.assertIsNone(blank)
        self.assertEqual("<numeric-nan>", numeric_nan)
        self.assertNotEqual(blank, numeric_nan)

        integer_difference = module._compare_values(
            2,
            2.00000000001,
            manifest=MANIFEST,
            profile_name="fmf_default",
            path=("csv", "rows", "0", "faces"),
        )
        self.assertTrue(integer_difference)

    def test_mixed_model_tolerances_apply_only_to_affected_values(self) -> None:
        module = self._load_comparator_module()

        def tolerance(profile: str, path: tuple[str, ...]) -> tuple[float, float]:
            return module._tolerance_for_path(MANIFEST, profile, path)

        pm_profile = "newt_prandtl_meyer_mixed"
        pm_panel = ("vtp", "cell_data", "Cp_n", "values", "0")
        newtonian_panel = ("vtp", "cell_data", "Cp_n", "values", "2")
        integrated = ("npz", "arrays", "CA", "values")
        self.assertEqual((1e-9, 0.0), tolerance(pm_profile, pm_panel))
        self.assertEqual((1e-10, 0.0), tolerance(pm_profile, newtonian_panel))
        self.assertEqual((1e-9, 0.0), tolerance(pm_profile, integrated))

        cone_profile = "newt_cone_mixed"
        cone_panel = ("vtp", "cell_data", "C_face_stl", "values", "0", "0")
        algebraic_panel = (
            "vtp",
            "cell_data",
            "C_face_stl",
            "values",
            "2",
            "0",
        )
        cone_total = ("csv", "rows", "0", "CA")
        algebraic_component = ("csv", "rows", "2", "CA")
        self.assertEqual((1e-9, 5e-8), tolerance(cone_profile, cone_panel))
        self.assertEqual((1e-10, 0.0), tolerance(cone_profile, algebraic_panel))
        self.assertEqual((1e-9, 5e-8), tolerance(cone_profile, cone_total))
        self.assertEqual((1e-10, 0.0), tolerance(cone_profile, algebraic_component))

        aref_path = ("npz", "arrays", "Aref_m2", "values")
        mode_a_state = ("npz", "arrays", "S", "values")
        mode_b_state = ("npz", "arrays", "S", "values")
        shielded_panel = ("vtp", "cell_data", "C_face_stl", "values", "2", "0")
        exposed_panel = ("vtp", "cell_data", "C_face_stl", "values", "0", "0")
        self.assertEqual((0.0, 0.0), tolerance("newt_tangent_cone", aref_path))
        self.assertEqual((0.0, 0.0), tolerance("fmf_mode_a", mode_a_state))
        self.assertEqual((1e-10, 0.0), tolerance("fmf_default", mode_b_state))
        self.assertEqual((0.0, 0.0), tolerance("fmf_shielded", shielded_panel))
        self.assertEqual((1e-10, 0.0), tolerance("fmf_shielded", exposed_panel))
        self.assertEqual((0.0, 0.0), tolerance("newt_shielded", shielded_panel))

    def test_capture_environment_and_windows_paths_are_canonical(self) -> None:
        module = self._load_comparator_module()
        with mock.patch.dict(
            os.environ,
            {
                "COLUMNS": "140",
                "FMFSOLVER_SHIELD_CACHE_MAX": "bad",
                "NEWTSOLVER_PARALLEL_CHUNK_CASES": "99",
                "PYTHONPATH": "/tmp/contaminating-path",
            },
        ):
            environment = module._clean_legacy_environment()
        self.assertEqual("80", environment["COLUMNS"])
        self.assertEqual("24", environment["LINES"])
        self.assertNotIn("FMFSOLVER_SHIELD_CACHE_MAX", environment)
        self.assertNotIn("NEWTSOLVER_PARALLEL_CHUNK_CASES", environment)
        self.assertNotIn("PYTHONPATH", environment)

        windows_root = PureWindowsPath(r"C:\Temp\phase1")
        roots = {windows_root: "<fixture-root>"}
        plain = module._normalize_string(
            r"C:\Temp\phase1\stl\plate.stl;C:\Temp\phase1\stl\cube.stl",
            key="stl_path",
            roots=roots,
        )
        self.assertEqual(
            "<fixture-root>/stl/plate.stl;<fixture-root>/stl/cube.stl", plain
        )
        encoded = json.dumps([r"C:\Temp\phase1\stl\plate.stl"])
        normalized_json = module._normalize_string(
            encoded, key="stl_paths_json", roots=roots
        )
        self.assertEqual('["<fixture-root>/stl/plate.stl"]', normalized_json)

    def _load_comparator_module(self):
        script = REPOSITORY_ROOT / "scripts" / "generate_phase1_goldens.py"
        spec = importlib.util.spec_from_file_location("phase1_generator", script)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class LegacyFixtureSemanticIntegrityTests(unittest.TestCase):
    def test_artifact_schemas_and_cross_format_relations(self) -> None:
        for solver in MANIFEST["sources"]:
            for case_id, metadata in _case_metadata(solver).items():
                with self.subTest(solver=solver, case_id=case_id):
                    case = _load_case(solver, case_id)
                    total = _total_row(case)
                    self.assertEqual(case_id, total["case_id"])
                    self.assertEqual(
                        metadata["expected_effective_backend"],
                        total["ray_backend_used"],
                    )
                    self.assertEqual(
                        "<case-signature:path-and-version-dependent>",
                        total["case_signature"],
                    )
                    self.assertEqual("<utc-timestamp>", total["run_started_at_utc"])
                    self.assertEqual("<utc-timestamp>", total["run_finished_at_utc"])
                    self.assertEqual(
                        "<nonnegative-elapsed-seconds>", total["run_elapsed_s"]
                    )
                    self.assertTrue(
                        case["relations"]["case_signature_csv_vtp_recomputed_equal"]
                    )
                    self.assertTrue(case["relations"]["csv_rows_share_run_metadata"])
                    self.assertTrue(case["relations"]["timestamps_utc_and_ordered"])

                    vtp = case["vtp"]
                    npz = case["npz"]["arrays"]
                    self.assertEqual(COMMON_VTP_CELL_ARRAYS, set(vtp["cell_data"]))
                    self.assertTrue(COMMON_VTP_FIELD_ARRAYS <= set(vtp["field_data"]))
                    if solver == "newtsolver":
                        self.assertTrue(
                            {"windward_eq_used", "leeward_eq_used"}
                            <= set(vtp["field_data"])
                        )
                    self.assertTrue(COMMON_NPZ_ARRAYS <= set(npz))
                    if solver == "fmfsolver":
                        self.assertTrue({"S", "Ti_K", "Tw_K"} <= set(npz))

                    for record in [
                        vtp["points"],
                        vtp["faces"],
                        *vtp["cell_data"].values(),
                        *vtp["field_data"].values(),
                        *npz.values(),
                    ]:
                        self.assertEqual(tuple(record["shape"]), _values(record).shape)

                    np.testing.assert_allclose(
                        _values(vtp["cell_data"]["area_m2"]),
                        _values(npz["areas_m2"]),
                        rtol=0.0,
                        atol=1e-12,
                    )
                    np.testing.assert_array_equal(
                        _values(vtp["cell_data"]["shielded"]),
                        _values(npz["shielded"]),
                    )
                    np.testing.assert_array_equal(
                        _values(vtp["cell_data"]["stl_index"]),
                        _values(npz["face_stl_index"]),
                    )
                    profile = MANIFEST["tolerance_profiles"][
                        metadata["tolerance_profile"]
                    ]
                    tolerance = MANIFEST["tolerances"][profile["default"]]
                    np.testing.assert_allclose(
                        _values(vtp["cell_data"]["C_face_stl"]).sum(axis=0),
                        _values(npz["C_force_stl"]),
                        rtol=tolerance["rtol"],
                        atol=tolerance["atol"],
                    )
                    for coefficient in COEFFICIENTS:
                        self.assertTrue(
                            math.isclose(
                                float(total[coefficient]),
                                float(npz[coefficient]["values"]),
                                rel_tol=tolerance["rtol"],
                                abs_tol=tolerance["atol"],
                            ),
                            coefficient,
                        )
                    self.assertEqual(total["faces"], len(_values(npz["areas_m2"])))
                    self.assertEqual(
                        total["shielded_faces"],
                        int(_values(npz["shielded"]).astype(bool).sum()),
                    )

                    rows = case["csv"]["rows"]
                    if "multi_component" in metadata["coverage"]:
                        self.assertEqual(
                            ["total", "component", "component"],
                            [r["scope"] for r in rows],
                        )
                        for coefficient in COEFFICIENTS:
                            component_sum = sum(
                                float(row[coefficient])
                                for row in rows
                                if row["scope"] == "component"
                            )
                            self.assertTrue(
                                math.isclose(
                                    float(total[coefficient]),
                                    component_sum,
                                    rel_tol=tolerance["rtol"],
                                    abs_tol=tolerance["atol"],
                                )
                            )
                    else:
                        self.assertEqual(["total"], [row["scope"] for row in rows])

                    shielded = _values(npz["shielded"]).astype(bool)
                    panel_loads = _values(vtp["cell_data"]["C_face_stl"])
                    if shielded.any():
                        np.testing.assert_array_equal(
                            panel_loads[shielded], np.zeros_like(panel_loads[shielded])
                        )
                    if "shielded" in metadata["coverage"]:
                        np.testing.assert_array_equal(
                            shielded, np.array([False, False, True, True])
                        )
                    else:
                        self.assertFalse(shielded.any())

    def test_canonical_validation_values_are_frozen(self) -> None:
        fmf = _total_row(_load_case("fmfsolver", "fmf_zero_plate"))
        newt = _total_row(_load_case("newtsolver", "newt_zero_newtonian"))
        self.assertAlmostEqual(2.3944907701811076, float(fmf["CA"]), places=12)
        self.assertAlmostEqual(float(fmf["CA"]), float(fmf["CD"]), places=12)
        self.assertAlmostEqual(2.0, float(newt["CA"]), places=12)
        self.assertAlmostEqual(float(newt["CA"]), float(newt["CD"]), places=12)


if __name__ == "__main__":
    unittest.main()
