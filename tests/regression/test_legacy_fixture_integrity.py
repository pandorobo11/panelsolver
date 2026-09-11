from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import unittest
from fnmatch import fnmatchcase
from pathlib import Path, PureWindowsPath
from unittest import mock

REPOSITORY_ROOT = Path(__file__).parents[2]
FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "phase1"
GOLDEN_ROOT = FIXTURE_ROOT / "golden"
MANIFEST = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))


def _load_case(solver: str, case_id: str) -> dict:
    return json.loads(
        (GOLDEN_ROOT / solver / f"{case_id}.json").read_text(encoding="utf-8")
    )


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

    def test_capture_environment_and_windows_paths_are_normalized(self) -> None:
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
    def test_validation_reference_values_are_frozen(self) -> None:
        fmf = _total_row(_load_case("fmfsolver", "fmf_zero_plate"))
        newt = _total_row(_load_case("newtsolver", "newt_zero_newtonian"))
        self.assertAlmostEqual(2.3944907701811076, float(fmf["CA"]), places=12)
        self.assertAlmostEqual(float(fmf["CA"]), float(fmf["CD"]), places=12)
        self.assertAlmostEqual(2.0, float(newt["CA"]), places=12)
        self.assertAlmostEqual(float(newt["CA"]), float(newt["CD"]), places=12)


if __name__ == "__main__":
    unittest.main()
