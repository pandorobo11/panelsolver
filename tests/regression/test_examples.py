from __future__ import annotations

import csv
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pyvista as pv

from panelsolver.app import run_and_write_product_cases
from panelsolver.app.csv_writer import CSV_ENCODING
from panelsolver.domains import fmf, hypersonic

REPOSITORY_ROOT = Path(__file__).parents[2]
EXAMPLES_ROOT = REPOSITORY_ROOT / "examples"
COEFFICIENTS = ("CA", "CY", "CN", "Cl", "Cm", "Cn", "CD", "CL")
SENTMAN_ATOL = 1e-10
HYPERSONIC_ATOL = 1e-10
PRANDTL_MEYER_ATOL = 1e-9


class ExampleRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary_directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._temporary_directory.cleanup)
        cls.root = Path(cls._temporary_directory.name) / "examples"
        shutil.copytree(
            EXAMPLES_ROOT,
            cls.root,
            ignore=shutil.ignore_patterns("outputs"),
        )
        cls.frames = {}
        cls.results = {}
        cls.artifacts: dict[str, Path] = {}
        cls.raw_rows: dict[tuple[str, str], tuple[dict[str, str], ...]] = {}

        domains = (
            ("fmf", fmf.read_cases, fmf.RUNTIME_POLICY),
            ("hypersonic", hypersonic.read_cases, hypersonic.RUNTIME_POLICY),
        )
        for domain, reader, policy in domains:
            for table in sorted((cls.root / domain).glob("*.csv")):
                key = (domain, table.stem)
                with table.open(encoding=CSV_ENCODING, newline="") as stream:
                    cls.raw_rows[key] = tuple(csv.DictReader(stream))
                frame = reader(table)
                cls.frames[key] = frame
                result_path = (
                    cls.root / domain / "test-results" / f"{table.stem}_result.csv"
                )
                result = run_and_write_product_cases(
                    tuple(frame.to_dict(orient="records")),
                    policy,
                    result_path,
                    workers=1,
                )
                cls.results[key] = result
                for row, case_result in zip(
                    frame.to_dict(orient="records"), result.cases, strict=True
                ):
                    cls.artifacts[str(row["case_id"])] = Path(case_result.vtp_path)

    def _total_rows(self, domain: str, table: str):
        return tuple(
            row
            for row in self.results[(domain, table)].csv.rows
            if row["scope"] == "total"
        )

    def test_geometry_is_byte_identical_to_phase1_inputs(self) -> None:
        fixture_geometry = (
            REPOSITORY_ROOT / "tests" / "fixtures" / "phase1" / "inputs" / "stl"
        )
        for name in (
            "plate.stl",
            "cube.stl",
            "double_plate.stl",
            "plate_offset_x2.stl",
        ):
            with self.subTest(name=name):
                self.assertEqual(
                    (fixture_geometry / name).read_bytes(),
                    (EXAMPLES_ROOT / "geometry" / name).read_bytes(),
                )

    def test_tables_are_portable_unique_and_canonical(self) -> None:
        case_ids: list[str] = []
        for (domain, table), raw_rows in self.raw_rows.items():
            frame = self.frames[(domain, table)]
            self.assertEqual(len(raw_rows), len(frame), msg=f"{domain}/{table}")
            for raw_row in raw_rows:
                case_ids.append(raw_row["case_id"])
                case_id = raw_row["case_id"].casefold()
                self.assertFalse(case_id.startswith("fmfsolver"))
                self.assertFalse(case_id.startswith("newtsolver"))
                self.assertNotIn("save_npz_on", raw_row)
                for raw_path in raw_row["stl_path"].split(";"):
                    self.assertFalse(Path(raw_path).is_absolute())
                    self.assertTrue(
                        ((self.root / domain) / raw_path).resolve().is_file()
                    )
            for resolved_paths in frame["stl_path"]:
                for resolved_path in str(resolved_paths).split(";"):
                    self.assertTrue(Path(resolved_path).is_file())

        self.assertEqual(len(case_ids), len(set(case_ids)))

    def test_all_cases_run_with_current_summary_and_vtp_outputs(self) -> None:
        expected_case_count = sum(len(frame) for frame in self.frames.values())
        self.assertEqual(expected_case_count, len(self.artifacts))
        for frame in self.frames.values():
            self.assertTrue((frame["save_vtp_on"] == 1).all())
        for artifact in self.artifacts.values():
            self.assertTrue(artifact.is_file())
            self.assertTrue(artifact.resolve().is_relative_to(self.root.resolve()))
        self.assertEqual([], list(self.root.rglob("*.npz")))

        fmf_cell_data = set(pv.read(self.artifacts["fmf_basic"]).cell_data)
        self.assertIn("normal_traction_coeff", fmf_cell_data)
        self.assertIn("tangential_traction_coeff", fmf_cell_data)
        self.assertNotIn("Cp_n", fmf_cell_data)
        hypersonic_cell_data = set(
            pv.read(self.artifacts["hypersonic_basic"]).cell_data
        )
        self.assertIn("cp", hypersonic_cell_data)
        self.assertNotIn("Cp_n", hypersonic_cell_data)

    def test_fmf_flow_modes_resolve_to_matching_coefficients(self) -> None:
        mode_a, mode_b = self._total_rows("fmf", "flow_modes")
        self.assertEqual("A", mode_a["mode"])
        self.assertEqual("B", mode_b["mode"])
        np.testing.assert_allclose(
            [mode_a[name] for name in COEFFICIENTS],
            [mode_b[name] for name in COEFFICIENTS],
            rtol=0.0,
            atol=SENTMAN_ATOL,
        )
        self.assertAlmostEqual(mode_a["out_S"], mode_b["out_S"], delta=SENTMAN_ATOL)
        self.assertAlmostEqual(
            mode_a["out_Ti_K"], mode_b["out_Ti_K"], delta=SENTMAN_ATOL
        )

    def test_ray_shielding_masks_rear_faces_and_halves_force(self) -> None:
        for domain, tolerance in (
            ("fmf", SENTMAN_ATOL),
            ("hypersonic", HYPERSONIC_ATOL),
        ):
            with self.subTest(domain=domain):
                off, on = self._total_rows(domain, "shielding")
                self.assertEqual(0, off["shielded_faces"])
                self.assertEqual(2, on["shielded_faces"])
                np.testing.assert_allclose(
                    [on[name] for name in ("CA", "CY", "CN")],
                    np.multiply(0.5, [off[name] for name in ("CA", "CY", "CN")]),
                    rtol=0.0,
                    atol=tolerance,
                )
                poly = pv.read(self.artifacts[str(on["case_id"])])
                np.testing.assert_array_equal(
                    np.asarray(poly.cell_data["shielded"], dtype=bool),
                    np.array([False, False, True, True]),
                )

    def test_component_rows_sum_to_total_and_follow_stl_order(self) -> None:
        expected_names = ("cube.stl", "plate_offset_x2.stl")
        for domain, tolerance in (
            ("fmf", SENTMAN_ATOL),
            ("hypersonic", PRANDTL_MEYER_ATOL),
        ):
            with self.subTest(domain=domain):
                rows = self.results[(domain, "components")].csv.rows
                total = next(row for row in rows if row["scope"] == "total")
                components = tuple(
                    row for row in rows if row["scope"] == "component"
                )
                self.assertEqual(2, len(components))
                self.assertEqual(
                    expected_names,
                    tuple(Path(str(row["component_stl_path"])).name for row in components),
                )
                np.testing.assert_allclose(
                    [total[name] for name in COEFFICIENTS],
                    [sum(float(row[name]) for row in components) for name in COEFFICIENTS],
                    rtol=0.0,
                    atol=tolerance,
                )

        hypersonic_total = self._total_rows("hypersonic", "components")[0]
        poly = pv.read(self.artifacts[str(hypersonic_total["case_id"])])
        self.assertEqual(
            "modified_newtonian;newtonian",
            str(poly.field_data["windward_eq_used"][0]),
        )
        self.assertEqual(
            "prandtl_meyer;shield",
            str(poly.field_data["leeward_eq_used"][0]),
        )
        np.testing.assert_array_equal(
            np.asarray(poly.cell_data["stl_index"]),
            np.array([0] * 12 + [1] * 2),
        )

    def test_attitude_input_modes_produce_matching_coefficients(self) -> None:
        for domain, tolerance in (
            ("fmf", SENTMAN_ATOL),
            ("hypersonic", HYPERSONIC_ATOL),
        ):
            with self.subTest(domain=domain):
                rows = self._total_rows(domain, "attitude_modes")
                reference = [rows[0][name] for name in COEFFICIENTS]
                for row in rows[1:]:
                    np.testing.assert_allclose(
                        [row[name] for name in COEFFICIENTS],
                        reference,
                        rtol=0.0,
                        atol=tolerance,
                    )

    def test_hypersonic_pressure_models_are_distinct_and_finite(self) -> None:
        rows = self._total_rows("hypersonic", "pressure_models")
        for row in rows:
            self.assertTrue(
                np.isfinite([float(row[name]) for name in COEFFICIENTS]).all()
            )

        windward_ids = ("newt_newtonian", "newt_modified", "newt_wedge", "newt_cone")
        local_cp: list[float] = []
        for case_id in windward_ids:
            poly = pv.read(self.artifacts[case_id])
            cp = np.asarray(poly.cell_data["cp"], dtype=float)
            turning_deg = np.asarray(poly.cell_data["theta_deg"], dtype=float) - 90.0
            self.assertTrue(np.isfinite(cp).all())
            np.testing.assert_allclose(
                turning_deg,
                np.full(turning_deg.shape, 15.0),
                rtol=0.0,
                atol=1e-12,
            )
            local_cp.append(float(cp[0]))
        self.assertEqual(4, len({round(value, 12) for value in local_cp}))

        pm_poly = pv.read(self.artifacts["newt_pm"])
        pm_cp = np.asarray(pm_poly.cell_data["cp"], dtype=float)
        self.assertTrue(np.isfinite(pm_cp).all())
        self.assertTrue((pm_cp < 0.0).any())


if __name__ == "__main__":
    unittest.main()
