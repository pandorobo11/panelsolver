from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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


def _spec_with_reader(reader):
    spec = gui_visual_smoke.canonical_gui_spec("fmf")
    assert spec.adapters is not None
    return replace(spec, adapters=replace(spec.adapters, read_cases=reader))


def _noninteractive_args(directory: Path, *, row: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        domain="fmf",
        theme=ThemeMode.LIGHT.value,
        input=directory / "input.csv",
        row=row,
        screenshot=directory / "capture.png",
        quit_after_screenshot=True,
    )


class _FakeApplication:
    def __init__(self) -> None:
        self.exit_codes: list[int] = []
        self.quit_called = False

    def processEvents(self, *_args) -> None:
        return None

    def exit(self, code: int) -> None:
        self.exit_codes.append(code)

    def quit(self) -> None:
        self.quit_called = True


class _FakeCaseTable:
    def __init__(self, row_count: int) -> None:
        self._row_count = row_count

    def rowCount(self) -> int:
        return self._row_count

    def selectRow(self, _row: int) -> None:
        return None

    def setCurrentCell(self, _row: int, _column: int) -> None:
        return None

    def setFocus(self, _reason) -> None:
        return None


class _FakeWindow:
    def __init__(self, *, loaded: bool, row_count: int = 1) -> None:
        self.cases_panel = SimpleNamespace(
            load_input_file=lambda *_args, **_kwargs: loaded,
            case_table=_FakeCaseTable(row_count),
            logln=lambda _message: None,
        )
        self.raised = False
        self.activated = False

    def raise_(self) -> None:
        self.raised = True

    def activateWindow(self) -> None:
        self.activated = True


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


class GuiVisualSmokeAutomationTests(unittest.TestCase):
    def test_valid_preflight_reuses_rows_without_second_input_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = _noninteractive_args(root)
            calls: list[Path] = []

            def read_cases(path):
                calls.append(Path(path))
                return ({"case_id": "cached"},)

            prepared = gui_visual_smoke._preflight_noninteractive_spec(
                _spec_with_reader(read_cases),
                args,
            )
            self.assertIsNotNone(prepared.adapters)
            assert prepared.adapters is not None
            self.assertEqual([args.input], calls)
            self.assertEqual(
                ({"case_id": "cached"},),
                prepared.adapters.read_cases(args.input),
            )
            self.assertEqual([args.input], calls)

    def test_interactive_capture_does_not_preflight_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = _noninteractive_args(Path(directory))
            args.quit_after_screenshot = False

            def unexpected_read(_path):
                raise AssertionError("interactive input should be read by CasesPanel")

            spec = _spec_with_reader(unexpected_read)
            self.assertIs(
                spec,
                gui_visual_smoke._preflight_noninteractive_spec(spec, args),
            )

    def test_out_of_range_preflight_exits_without_window_or_capture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = _noninteractive_args(root, row=1)
            spec = _spec_with_reader(lambda _path: ({"case_id": "only"},))
            stderr = io.StringIO()
            with (
                patch.object(gui_visual_smoke, "parse_args", return_value=args),
                patch.object(
                    gui_visual_smoke,
                    "canonical_gui_spec",
                    return_value=spec,
                ),
                patch.object(gui_visual_smoke, "create_main_window") as create_window,
                patch.object(gui_visual_smoke, "capture_main_window") as capture,
                contextlib.redirect_stderr(stderr),
            ):
                self.assertEqual(1, gui_visual_smoke.main([]))

            create_window.assert_not_called()
            capture.assert_not_called()
            self.assertFalse(args.screenshot.exists())
            self.assertIn("requested row 1 is out of range", stderr.getvalue())

    def test_input_preflight_failure_avoids_modal_gui_and_capture(self) -> None:
        def fail_read(_path):
            raise ValueError("broken input")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = _noninteractive_args(root)
            spec = _spec_with_reader(fail_read)
            stderr = io.StringIO()
            with (
                patch.object(gui_visual_smoke, "parse_args", return_value=args),
                patch.object(
                    gui_visual_smoke,
                    "canonical_gui_spec",
                    return_value=spec,
                ),
                patch.object(gui_visual_smoke, "create_main_window") as create_window,
                patch.object(gui_visual_smoke, "capture_main_window") as capture,
                contextlib.redirect_stderr(stderr),
            ):
                self.assertEqual(1, gui_visual_smoke.main([]))

            create_window.assert_not_called()
            capture.assert_not_called()
            self.assertFalse(args.screenshot.exists())
            self.assertIn("broken input", stderr.getvalue())

    def test_unexpected_state_preparation_failure_does_not_capture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = _noninteractive_args(Path(directory))
            application = _FakeApplication()
            window = _FakeWindow(loaded=False)
            stderr = io.StringIO()
            with (
                patch.object(gui_visual_smoke, "capture_main_window") as capture,
                contextlib.redirect_stderr(stderr),
            ):
                gui_visual_smoke._prepare_and_schedule_capture(
                    application,
                    window,
                    args,
                )

            capture.assert_not_called()
            self.assertEqual([1], application.exit_codes)
            self.assertFalse(args.screenshot.exists())
            self.assertIn("input could not be loaded", stderr.getvalue())
            self.assertTrue(window.raised)
            self.assertTrue(window.activated)

    def test_capture_failure_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            args = _noninteractive_args(Path(directory))
            application = _FakeApplication()
            window = _FakeWindow(loaded=True)
            stderr = io.StringIO()

            def run_immediately(_delay: int, callback) -> None:
                callback()

            with (
                patch.object(
                    gui_visual_smoke.QtCore.QTimer,
                    "singleShot",
                    side_effect=run_immediately,
                ),
                patch.object(
                    gui_visual_smoke,
                    "capture_main_window",
                    side_effect=RuntimeError("render failed"),
                ) as capture,
                contextlib.redirect_stderr(stderr),
            ):
                gui_visual_smoke._prepare_and_schedule_capture(
                    application,
                    window,
                    args,
                )

            capture.assert_called_once_with(window, args.screenshot)
            self.assertEqual([1], application.exit_codes)
            self.assertFalse(application.quit_called)
            self.assertFalse(args.screenshot.exists())
            self.assertIn("render failed", stderr.getvalue())


class GuiVisualSmokeCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_capture_composites_plotter_viewport_into_client_area(self) -> None:
        window = QtWidgets.QMainWindow()
        central = QtWidgets.QWidget()
        client_color = QtGui.QColor(30, 145, 210)
        palette = central.palette()
        palette.setColor(QtGui.QPalette.ColorRole.Window, client_color)
        central.setPalette(palette)
        central.setAutoFillBackground(True)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(12, 14, 12, 10)
        layout.addSpacing(18)
        viewport_row = QtWidgets.QHBoxLayout()
        viewport_row.addSpacing(36)
        interactor = QtWidgets.QWidget()
        interactor.setFixedSize(80, 60)
        viewport_row.addWidget(interactor)
        viewport_row.addStretch(1)
        layout.addLayout(viewport_row)
        layout.addStretch(1)
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
            viewport_pixel = captured.pixelColor(
                round((origin.x() + interactor.width() / 2) * scale_x),
                round((origin.y() + interactor.height() / 2) * scale_y),
            )
            outside = central.mapTo(window, QtCore.QPoint(3, 3))
            client_pixel = captured.pixelColor(
                round(outside.x() * scale_x),
                round(outside.y() * scale_y),
            )
            self.assertGreater(origin.x(), 36)
            self.assertGreater(origin.y(), 18)
            self.assertEqual(QtGui.QColor(190, 25, 40), viewport_pixel)
            self.assertEqual(client_color, client_pixel)

        self.assertEqual(1, len(screenshot_calls))
        window.close()


if __name__ == "__main__":
    unittest.main()
