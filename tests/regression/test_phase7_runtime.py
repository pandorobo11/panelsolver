from __future__ import annotations

import copy
import csv
import importlib.metadata
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import pyvista as pv

from fmfsolver._frontend import (
    _build_artifact_signatures as build_fmf_signatures,
)
from newtsolver._frontend import (
    _build_artifact_signatures as build_newt_signatures,
)
from panelsolver.app import run_and_write_product_cases
from panelsolver.app.csv_writer import CSV_ENCODING
from panelsolver.domains.fmf import RUNTIME_POLICY as FMF_POLICY
from panelsolver.domains.fmf import read_cases as read_fmf_cases
from panelsolver.domains.hypersonic import RUNTIME_POLICY as NEWT_POLICY
from panelsolver.domains.hypersonic import read_cases as read_newt_cases
from tests.current_case_fixtures import read_current_cases

REPOSITORY_ROOT = Path(__file__).parents[2]
FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "phase1"
GOLDEN_ROOT = FIXTURE_ROOT / "golden"
MANIFEST = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
LEGACY_ARTIFACT_VERSIONS = {"1.3.8", "1.0.3"}


def _load_comparator_module():
    script = REPOSITORY_ROOT / "scripts" / "generate_phase1_goldens.py"
    spec = importlib.util.spec_from_file_location("phase7_comparator", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the Phase 1 semantic comparator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Phase7RuntimeGoldenTests(unittest.TestCase):
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
                build_fmf_signatures,
                FMF_POLICY,
                6,
            ),
            (
                "newtsolver",
                "newtsolver_cases.csv",
                read_newt_cases,
                build_newt_signatures,
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
                        expected = {
                            "csv": {
                                "columns": [
                                    name
                                    for name in golden["csv"]["columns"]
                                    if name not in {"save_npz_on", "npz_path"}
                                ],
                                "rows": [
                                    {
                                        name: value
                                        for name, value in expected_row.items()
                                        if name not in {"save_npz_on", "npz_path"}
                                    }
                                    for expected_row in golden["csv"]["rows"]
                                ],
                            },
                            "vtp": copy.deepcopy(golden["vtp"]),
                        }
                        # Phase 1 remains immutable historical evidence. Adjust only
                        # the in-memory expectation for the accepted current artifact
                        # provenance contract.
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
                        self.assertTrue(
                            LEGACY_ARTIFACT_VERSIONS.isdisjoint(
                                csv_row["solver_version"] for csv_row in raw_case_rows
                            )
                        )
                        raw_total = next(
                            csv_row
                            for csv_row in raw_case_rows
                            if csv_row["scope"] == "total"
                        )
                        poly = pv.read(staged / "outputs" / f"{case_id}.vtp")
                        vtp_version = str(poly.field_data["solver_version"][0])
                        self.assertEqual(installed_version, vtp_version)
                        self.assertEqual(raw_total["solver_version"], vtp_version)
                        self.assertNotIn(vtp_version, LEGACY_ARTIFACT_VERSIONS)
                        primary = signatures(row).primary.digest
                        self.assertEqual(primary, raw_total["case_signature"])
                        self.assertEqual(
                            primary,
                            str(poly.field_data["case_signature"][0]),
                        )


if __name__ == "__main__":
    unittest.main()
