from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from panelsolver.app.gui_theme import ThemeMode

_SCRIPT_PATH = Path(__file__).parents[2] / "scripts" / "gui_visual_smoke.py"
_INPUT_PATH = Path(__file__).parents[2] / "examples" / "fmf" / "basic.csv"
_SPEC = importlib.util.spec_from_file_location("gui_visual_smoke", _SCRIPT_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Could not load scripts/gui_visual_smoke.py")
gui_visual_smoke = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gui_visual_smoke)


class GuiVisualSmokeParserTests(unittest.TestCase):
    def test_defaults_follow_production_system_theme(self) -> None:
        args = gui_visual_smoke.build_parser().parse_args([])

        self.assertEqual(args.domain, "fmf")
        self.assertEqual(args.theme, ThemeMode.SYSTEM.value)
        self.assertIsNone(args.input)
        self.assertEqual(args.row, 0)

    def test_explicit_domain_theme_input_and_row(self) -> None:
        args = gui_visual_smoke.build_parser().parse_args(
            [
                "--domain",
                "hypersonic",
                "--theme",
                "dark",
                "--input",
                str(_INPUT_PATH),
                "--row",
                "2",
            ]
        )

        self.assertEqual(args.domain, "hypersonic")
        self.assertEqual(args.theme, ThemeMode.DARK.value)
        self.assertEqual(args.input, _INPUT_PATH.resolve())
        self.assertEqual(args.row, 2)

    def test_negative_row_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            gui_visual_smoke.build_parser().parse_args(["--row", "-1"])

    def test_out_of_range_row_is_reported(self) -> None:
        gui_visual_smoke._validate_requested_row(2, 3)

        with self.assertRaisesRegex(
            ValueError,
            r"requested row 3 is out of range for 3 loaded case\(s\); "
            r"valid range: 0-2",
        ):
            gui_visual_smoke._validate_requested_row(3, 3)


if __name__ == "__main__":
    unittest.main()
