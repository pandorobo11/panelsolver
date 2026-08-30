from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtWidgets

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
        self.assertIsNone(args.screenshot)
        self.assertFalse(args.quit_after_screenshot)

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
                "--screenshot",
                "visual.png",
                "--quit-after-screenshot",
            ]
        )

        self.assertEqual(args.domain, "hypersonic")
        self.assertEqual(args.theme, ThemeMode.DARK.value)
        self.assertEqual(args.input, _INPUT_PATH.resolve())
        self.assertEqual(args.row, 2)
        self.assertEqual(args.screenshot, (Path.cwd() / "visual.png").resolve())
        self.assertTrue(args.quit_after_screenshot)

    def test_negative_row_is_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            gui_visual_smoke.build_parser().parse_args(["--row", "-1"])

    def test_screenshot_requires_png_path(self) -> None:
        with self.assertRaises(SystemExit):
            gui_visual_smoke.parse_args(["--screenshot", "visual.jpg"])

    def test_quit_after_screenshot_requires_screenshot(self) -> None:
        with self.assertRaises(SystemExit):
            gui_visual_smoke.parse_args(["--quit-after-screenshot"])

    def test_out_of_range_row_is_reported(self) -> None:
        gui_visual_smoke._validate_requested_row(2, 3)

        with self.assertRaisesRegex(
            ValueError,
            r"requested row 3 is out of range for 3 loaded case\(s\); "
            r"valid range: 0-2",
        ):
            gui_visual_smoke._validate_requested_row(3, 3)


class GuiVisualSmokeCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_capture_composites_plotter_viewport_into_client_area(self) -> None:
        window = QtWidgets.QMainWindow()
        central = QtWidgets.QWidget()
        central.setStyleSheet("background: rgb(255, 255, 255)")
        layout = QtWidgets.QHBoxLayout(central)
        interactor = QtWidgets.QWidget()
        interactor.setMinimumSize(80, 60)
        layout.addWidget(interactor)
        window.setCentralWidget(central)

        screenshot_calls = []

        def save_viewport(path: str) -> None:
            screenshot_calls.append(path)
            viewport = QtGui.QImage(160, 120, QtGui.QImage.Format.Format_RGB32)
            viewport.fill(QtGui.QColor(190, 25, 40))
            self.assertTrue(viewport.save(path, "PNG"))

        window.viewer_panel = SimpleNamespace(
            plotter=SimpleNamespace(
                interactor=interactor,
                screenshot=save_viewport,
            )
        )
        window.resize(240, 140)
        window.show()
        self.app.processEvents()

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "nested" / "capture.png"
            gui_visual_smoke.capture_main_window(window, output_path)

            self.assertTrue(output_path.is_file())
            captured = QtGui.QImage(str(output_path))
            self.assertFalse(captured.isNull())
            origin = interactor.mapTo(window, QtCore.QPoint(0, 0))
            scale_x = captured.width() / window.width()
            scale_y = captured.height() / window.height()
            pixel = captured.pixelColor(
                round((origin.x() + interactor.width() / 2) * scale_x),
                round((origin.y() + interactor.height() / 2) * scale_y),
            )
            self.assertEqual(QtGui.QColor(190, 25, 40), pixel)

        self.assertEqual(1, len(screenshot_calls))
        window.close()


if __name__ == "__main__":
    unittest.main()
