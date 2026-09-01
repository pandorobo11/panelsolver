from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from panelsolver.app.viewer_data import ArtifactViewStatus
from scripts import generate_docs_gui_screenshots as generator


class DocsGuiScreenshotGeneratorTests(unittest.TestCase):
    def test_contract_has_exactly_the_two_documented_states(self) -> None:
        self.assertEqual(
            ["gui-overview.png", "gui-result.png"],
            [contract.filename for contract in generator.SCREENSHOTS],
        )
        overview, result = generator.SCREENSHOTS
        self.assertIsNone(overview.selected_case_id)
        self.assertIs(ArtifactViewStatus.EMPTY, overview.artifact_status)
        self.assertIsNone(overview.scalar_name)
        self.assertEqual("newt_pm", result.selected_case_id)
        self.assertIs(ArtifactViewStatus.CURRENT, result.artifact_status)
        self.assertEqual("cp", result.scalar_name)

    def test_workspace_copy_contains_inputs_without_calculation_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = generator._copy_example_workspace(root)

            self.assertEqual(
                root / "examples" / "hypersonic" / "pressure_models.csv",
                input_path,
            )
            self.assertTrue(input_path.is_file())
            self.assertTrue((root / "examples" / "geometry" / "plate.stl").is_file())
            self.assertTrue((root / "examples" / "geometry" / "cube.stl").is_file())
            self.assertFalse((root / "examples" / "hypersonic" / "outputs").exists())

    def test_result_generation_selects_only_newt_pm_with_fixed_run_settings(
        self,
    ) -> None:
        captured = []
        rows = (
            {"case_id": "first"},
            {"case_id": "newt_pm"},
        )

        def run_cases(request):
            captured.append(request)
            return SimpleNamespace(
                calculation_completed_cases=1,
                vtp_saved=1,
                output_issues=(),
            )

        adapters = SimpleNamespace(
            read_cases=lambda _path: rows,
            run_cases=run_cases,
        )
        with tempfile.TemporaryDirectory() as temporary:
            input_path = Path(temporary) / "pressure_models.csv"
            returned = generator._generate_result(
                SimpleNamespace(adapters=adapters),
                input_path,
            )

        self.assertEqual(rows, returned)
        self.assertEqual(1, len(captured))
        request = captured[0]
        self.assertEqual((rows[1],), request.rows)
        self.assertEqual(1, request.workers)
        self.assertEqual(0, request.checkpoint_every_cases)
        self.assertEqual(
            input_path.parent / "outputs" / "docs-screenshot-summary.csv",
            request.output_path,
        )


if __name__ == "__main__":
    unittest.main()
