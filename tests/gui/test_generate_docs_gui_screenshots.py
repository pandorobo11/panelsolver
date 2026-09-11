from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from scripts import generate_docs_gui_screenshots as generator


class DocsGuiScreenshotGeneratorTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
