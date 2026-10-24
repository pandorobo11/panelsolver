from __future__ import annotations

import csv
import importlib.metadata
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import pyvista as pv

from panelsolver.app import resolve_output_dir, run_and_write_product_cases
from panelsolver.app.csv_writer import CSV_ENCODING
from panelsolver.domains.fmf import RUNTIME_POLICY as FMF_POLICY
from panelsolver.domains.fmf import build_case_signature as build_fmf_signature
from panelsolver.domains.fmf import read_cases as read_fmf_cases
from panelsolver.domains.hypersonic import RUNTIME_POLICY as NEWT_POLICY
from panelsolver.domains.hypersonic import (
    build_case_signature as build_hypersonic_signature,
)
from panelsolver.domains.hypersonic import read_cases as read_newt_cases
from scripts import smoke_installed_wheel as SMOKE
from tests.current_case_fixtures import read_current_cases

REPOSITORY_ROOT = Path(__file__).parents[2]
FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "phase1"
GOLDEN_ROOT = FIXTURE_ROOT / "golden"
MANIFEST = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))


def _load_comparator_module():
    script = REPOSITORY_ROOT / "scripts" / "generate_phase1_goldens.py"
    spec = importlib.util.spec_from_file_location("phase7_comparator", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the Phase 1 semantic comparator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LegacyRuntimeGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.comparator = _load_comparator_module()

    def test_all_cases_serialize_to_current_csv_and_frozen_vtp_semantics(self) -> None:
        installed_version = importlib.metadata.version("panelsolver")
        products = (
            (
                "fmfsolver",
                "fmfsolver_cases.csv",
                read_fmf_cases,
                build_fmf_signature,
                FMF_POLICY,
                6,
            ),
            (
                "newtsolver",
                "newtsolver_cases.csv",
                read_newt_cases,
                build_hypersonic_signature,
                NEWT_POLICY,
                9,
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            staged = Path(temp_dir) / "fixture"
            shutil.copytree(FIXTURE_ROOT / "inputs", staged)
            for retired_npz in staged.rglob("*.npz"):
                retired_npz.unlink()
            roots = {staged.resolve(): "<fixture-root>"}

            for product, filename, reader, signatures, policy, count in products:
                with self.subTest(product=product):
                    frame = read_current_cases(reader, staged / filename)
                    rows = tuple(frame.to_dict(orient="records"))
                    output = staged / "outputs" / f"{product}_result.csv"
                    result = run_and_write_product_cases(
                        rows,
                        policy,
                        output,
                        vtp_dir=resolve_output_dir(staged / filename),
                        workers=1,
                    )
                    self.assertEqual(count, len(result.cases))
                    actual_csv = self.comparator._read_semantic_csv(
                        output,
                        roots=roots,
                    )
                    with output.open(encoding=CSV_ENCODING, newline="") as stream:
                        raw_csv_rows = list(csv.DictReader(stream))

                    for row in rows:
                        case_id = str(row["case_id"])
                        golden = json.loads(
                            (GOLDEN_ROOT / product / f"{case_id}.json").read_text(
                                encoding="utf-8"
                            )
                        )
                        actual_rows = [
                            csv_row
                            for csv_row in actual_csv["rows"]
                            if csv_row["case_id"] == case_id
                        ]
                        actual = {
                            "csv": {
                                "columns": actual_csv["columns"],
                                "rows": actual_rows,
                            },
                            "vtp": self.comparator._read_vtp(
                                staged / "outputs" / f"{case_id}.vtp",
                                roots=roots,
                            ),
                        }
                        # One schema migration (ADRs 0017 and 0021) is shared with
                        # the installed-wheel smoke; physical values stay frozen.
                        expected = {
                            "csv": {
                                "columns": SMOKE._current_expected_columns(
                                    golden["csv"]["columns"]
                                ),
                                "rows": SMOKE._current_expected_csv_rows(golden),
                            },
                            "vtp": SMOKE._current_expected_vtp(product, golden),
                        }
                        for expected_row in expected["csv"]["rows"]:
                            expected_row["solver_version"] = installed_version
                        expected["vtp"]["field_data"]["solver_version"]["values"] = [
                            installed_version
                        ]
                        differences = self.comparator._compare_values(
                            expected,
                            actual,
                            manifest=MANIFEST,
                            profile_name=golden["provenance"]["tolerance_profile"],
                        )
                        self.assertEqual([], differences)
                        self.assertFalse(
                            (staged / "outputs" / f"{case_id}.npz").exists()
                        )

                        raw_case_rows = [
                            csv_row
                            for csv_row in raw_csv_rows
                            if csv_row["case_id"] == case_id
                        ]
                        self.assertEqual(
                            {installed_version},
                            {csv_row["solver_version"] for csv_row in raw_case_rows},
                        )
                        raw_total = next(
                            csv_row
                            for csv_row in raw_case_rows
                            if csv_row["scope"] == "total"
                        )
                        poly = pv.read(staged / "outputs" / f"{case_id}.vtp")
                        self.assertNotIn("Cp_n", poly.cell_data)
                        vtp_version = str(poly.field_data["solver_version"][0])
                        self.assertEqual(installed_version, vtp_version)
                        self.assertEqual(raw_total["solver_version"], vtp_version)
                        current_signature = signatures(row).digest
                        self.assertEqual(current_signature, raw_total["case_signature"])
                        self.assertEqual(
                            current_signature,
                            str(poly.field_data["case_signature"][0]),
                        )


if __name__ == "__main__":
    unittest.main()
