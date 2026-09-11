from __future__ import annotations

import contextlib
import io
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from panelsolver import gui as gui_module
from panelsolver.app.gui_bootstrap import (
    _WINDOWS_APP_USER_MODEL_ID,
    _set_windows_app_user_model_id,
    run_gui,
)
from panelsolver.domains.fmf import gui_spec as fmf_solver_spec
from panelsolver.domains.hypersonic import gui_spec as hypersonic_solver_spec


class _FakeWindow:
    def __init__(self, spec) -> None:
        self.spec = spec
        self.shown = False

    def show(self) -> None:
        self.shown = True


class GuiBootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_run_gui_uses_shared_window_and_event_loop(self) -> None:
        made = []

        def factory(spec):
            window = _FakeWindow(spec)
            made.append(window)
            return window

        with (
            patch.object(QtWidgets.QApplication, "exec", return_value=23) as execute,
            patch(
                "panelsolver.app.gui_bootstrap._set_windows_app_user_model_id",
            ) as set_app_id,
            patch.object(
                QtWidgets.QApplication,
                "setWindowIcon",
            ) as set_window_icon,
        ):
            self.assertEqual(23, run_gui(fmf_solver_spec(), window_factory=factory))
        execute.assert_called_once_with()
        set_app_id.assert_not_called()
        set_window_icon.assert_called_once()
        self.assertFalse(set_window_icon.call_args.args[0].isNull())
        self.assertEqual("Panel Solver", self.app.applicationName())
        self.assertEqual("Panel Solver", self.app.applicationDisplayName())
        self.assertEqual("pandorobo11", self.app.organizationName())
        self.assertEqual("pandorobo11.github.io", self.app.organizationDomain())
        self.assertTrue(made[0].shown)
        self.assertEqual("sentman", made[0].spec.model_id)

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
            patch("panelsolver.app.gui_bootstrap.apply_application_theme"),
        ):
            run_gui(
                hypersonic_solver_spec(),
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

    def test_launcher_reuses_specs_with_domain_visible_identity(self) -> None:
        fmf = gui_module.gui_spec_for_domain("fmf")
        hypersonic = gui_module.gui_spec_for_domain("hypersonic")
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
            self.assertEqual(17, gui_module.main(["fmf"]))
            self.assertEqual(17, gui_module.main(["hypersonic"]))
        self.assertEqual(
            ["Panel Solver — FMF", "Panel Solver — Hypersonic"],
            [spec.window_title for spec, _argv in captured],
        )
        self.assertTrue(all(len(argv) == 1 for _spec, argv in captured))

    def test_launcher_without_domain_prints_help_and_exits_zero(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(0, gui_module.main([]))
        help_text = stdout.getvalue()
        self.assertIn("usage: panelsolver-gui", help_text)
        self.assertIn("fmf", help_text)
        self.assertIn("hypersonic", help_text)


if __name__ == "__main__":
    unittest.main()
