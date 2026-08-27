from __future__ import annotations

import contextlib
import io
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtWidgets

from fmfsolver._frontend import _legacy_gui_spec as fmf_solver_spec
from fmfsolver.app import gui_app as fmf_gui_app
from newtsolver._frontend import _legacy_gui_spec as newt_solver_spec
from newtsolver.app import gui_app as newt_gui_app
from panelsolver import gui as canonical_gui
from panelsolver.app import GuiRunResult, SolverGuiAdapters
from panelsolver.app.gui_bootstrap import (
    _WINDOWS_APP_USER_MODEL_ID,
    GuiAdaptersUnavailable,
    _application_icon,
    _set_windows_app_user_model_id,
    create_main_window,
    prepare_gui_spec,
    run_gui,
)


class _FakeCases:
    def __init__(self) -> None:
        self.messages = []

    def logln(self, message: str) -> None:
        self.messages.append(message)


class _FakeWindow:
    def __init__(self, spec) -> None:
        self.spec = spec
        self.cases_panel = _FakeCases()
        self.shown = False

    def show(self) -> None:
        self.shown = True


def _adapters() -> SolverGuiAdapters:
    return SolverGuiAdapters(
        read_cases=lambda _path: (),
        build_case_signatures=lambda _row: (),
        run_cases=lambda _request: GuiRunResult(),
        validate_output_path=lambda out, _input, _rows: Path(out),
        resolve_velocity_hat_stl=lambda _row: (1.0, 0.0, 0.0),
    )


class GuiBootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_prepare_preserves_complete_spec_and_adds_only_unavailable_adapters(
        self,
    ) -> None:
        complete = fmf_solver_spec(adapters=_adapters())
        self.assertIs(complete, prepare_gui_spec(complete))

        selected = newt_solver_spec(adapters=None)
        runtime = prepare_gui_spec(selected)
        self.assertIsNot(selected, runtime)
        for field in (
            "product_id",
            "model_id",
            "window_title",
            "case_columns",
            "preferred_scalars",
            "scalar_labels",
            "format_case",
        ):
            self.assertEqual(getattr(selected, field), getattr(runtime, field))
        with self.assertRaisesRegex(GuiAdaptersUnavailable, "not configured"):
            runtime.adapters.read_cases("cases.csv")

    def test_create_window_records_explicit_unconfigured_spec(self) -> None:
        window = create_main_window(
            fmf_solver_spec(adapters=None),
            window_factory=_FakeWindow,
        )
        self.assertEqual("fmfsolver", window.spec.product_id)
        self.assertIsNotNone(window.spec.adapters)
        self.assertIn("not configured", window.cases_panel.messages[-1])

    def test_run_gui_uses_shared_window_and_event_loop(self) -> None:
        made = []

        def factory(spec):
            window = _FakeWindow(spec)
            made.append(window)
            return window

        with (
            patch.object(QtWidgets.QApplication, "exec", return_value=23) as execute,
            patch.object(
                QtWidgets.QApplication,
                "setWindowIcon",
            ) as set_window_icon,
        ):
            self.assertEqual(23, run_gui(fmf_solver_spec(), window_factory=factory))
        execute.assert_called_once_with()
        set_window_icon.assert_called_once()
        self.assertFalse(set_window_icon.call_args.args[0].isNull())
        self.assertEqual("Panel Solver", self.app.applicationName())
        self.assertEqual("Panel Solver", self.app.applicationDisplayName())
        self.assertEqual("pandorobo11", self.app.organizationName())
        self.assertEqual("pandorobo11.github.io", self.app.organizationDomain())
        self.assertTrue(made[0].shown)
        self.assertEqual("sentman", made[0].spec.model_id)

    def test_run_gui_sets_icon_when_reusing_existing_application(self) -> None:
        with (
            patch.object(QtWidgets.QApplication, "instance", return_value=self.app),
            patch.object(QtWidgets.QApplication, "exec", return_value=0),
            patch(
                "panelsolver.app.gui_bootstrap._set_windows_app_user_model_id",
            ) as set_app_id,
            patch.object(
                QtWidgets.QApplication,
                "setWindowIcon",
            ) as set_window_icon,
        ):
            run_gui(fmf_solver_spec(), window_factory=_FakeWindow)

        set_window_icon.assert_called_once()
        self.assertFalse(set_window_icon.call_args.args[0].isNull())
        set_app_id.assert_not_called()

    def test_packaged_application_icon_is_loadable(self) -> None:
        icon = _application_icon()
        self.assertFalse(icon.isNull())
        self.assertTrue(icon.availableSizes())
        self.assertIn(QtCore.QSize(1024, 1024), icon.availableSizes())
        image = icon.pixmap(icon.availableSizes()[0]).toImage()
        self.assertTrue(image.hasAlphaChannel())
        self.assertEqual(0, image.pixelColor(0, 0).alpha())
        self.assertEqual(
            255,
            image.pixelColor(image.width() // 2, image.height() // 2).alpha(),
        )

    def test_windows_app_id_is_skipped_on_other_platforms(self) -> None:
        with (
            patch("panelsolver.app.gui_bootstrap.sys.platform", "linux"),
            patch("ctypes.WinDLL", create=True) as win_dll,
        ):
            _set_windows_app_user_model_id()
        win_dll.assert_not_called()

    def test_windows_app_id_is_set_before_application_creation(self) -> None:
        events = []
        fake_application = MagicMock()
        fake_application.exec.return_value = 0

        def make_application(_argv):
            events.append("application")
            return fake_application

        with (
            patch.object(QtWidgets.QApplication, "instance", return_value=None),
            patch(
                "panelsolver.app.gui_bootstrap._set_windows_app_user_model_id",
                side_effect=lambda: events.append("app-id"),
            ),
            patch(
                "panelsolver.app.gui_bootstrap._application_icon",
                return_value=MagicMock(),
            ),
        ):
            run_gui(
                newt_solver_spec(),
                application_factory=make_application,
                window_factory=_FakeWindow,
            )

        self.assertEqual(["app-id", "application"], events)
        fake_application.setWindowIcon.assert_called_once()

    def test_windows_app_id_uses_stable_identity(self) -> None:
        set_app_id = MagicMock(return_value=0)
        shell32 = MagicMock()
        shell32.SetCurrentProcessExplicitAppUserModelID = set_app_id
        with (
            patch("panelsolver.app.gui_bootstrap.sys.platform", "win32"),
            patch("ctypes.WinDLL", create=True, return_value=shell32),
        ):
            _set_windows_app_user_model_id()
        set_app_id.assert_called_once_with(_WINDOWS_APP_USER_MODEL_ID)

    def test_compatibility_launchers_select_independent_specs_only(self) -> None:
        captured = []

        def fake_run(spec):
            captured.append(spec)
            return len(captured)

        with patch(
            "panelsolver.app.gui_bootstrap.run_gui",
            side_effect=fake_run,
        ):
            with self.assertRaises(SystemExit) as fmf_exit:
                fmf_gui_app.main()
            with self.assertRaises(SystemExit) as newt_exit:
                newt_gui_app.main()
        self.assertEqual(1, fmf_exit.exception.code)
        self.assertEqual(2, newt_exit.exception.code)
        fmf, newt = captured
        self.assertEqual("Sentman FMF Solver (GUI)", fmf.window_title)
        self.assertIsNotNone(fmf.adapters)
        self.assertEqual("sentman", fmf.model_id)
        self.assertIn("S", fmf.case_columns)
        self.assertNotIn("gamma", fmf.case_columns)
        self.assertEqual("newtsolver (GUI)", newt.window_title)
        self.assertIsNotNone(newt.adapters)
        self.assertEqual("hypersonic", newt.model_id)
        self.assertIn("gamma", newt.case_columns)
        self.assertNotIn("S", newt.case_columns)
        self.assertNotEqual(fmf.preferred_scalars, newt.preferred_scalars)
        self.assertIsNot(fmf.format_case, newt.format_case)

    def test_canonical_launcher_reuses_specs_with_domain_visible_identity(self) -> None:
        fmf = canonical_gui.canonical_gui_spec("fmf")
        hypersonic = canonical_gui.canonical_gui_spec("hypersonic")
        self.assertEqual("fmf", fmf.product_id)
        self.assertEqual("sentman", fmf.model_id)
        self.assertEqual("Panel Solver — FMF", fmf.window_title)
        self.assertIsNotNone(fmf.adapters)
        self.assertEqual("hypersonic", hypersonic.product_id)
        self.assertEqual("hypersonic", hypersonic.model_id)
        self.assertEqual("Panel Solver — Hypersonic", hypersonic.window_title)
        self.assertIsNotNone(hypersonic.adapters)

        captured = []
        with patch(
            "panelsolver.gui.run_gui",
            side_effect=lambda spec, argv: captured.append((spec, argv)) or 17,
        ):
            self.assertEqual(17, canonical_gui.main(["fmf"]))
            self.assertEqual(17, canonical_gui.main(["hypersonic"]))
        self.assertEqual(
            ["Panel Solver — FMF", "Panel Solver — Hypersonic"],
            [spec.window_title for spec, _argv in captured],
        )
        self.assertTrue(all(len(argv) == 1 for _spec, argv in captured))

    def test_canonical_launcher_without_domain_prints_help_and_exits_zero(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(0, canonical_gui.main([]))
        help_text = stdout.getvalue()
        self.assertIn("usage: panelsolver-gui", help_text)
        self.assertIn("fmf", help_text)
        self.assertIn("hypersonic", help_text)


if __name__ == "__main__":
    unittest.main()
