from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtWidgets

from fmfsolver._frontend import _legacy_gui_spec as legacy_fmf_spec
from newtsolver._frontend import _legacy_gui_spec as legacy_hypersonic_spec
from panelsolver.app.main_window import MainWindow
from panelsolver.docs_site import DocumentationSiteError
from panelsolver.domains.fmf import gui_spec as canonical_fmf_spec
from panelsolver.domains.hypersonic import gui_spec as canonical_hypersonic_spec


class _Cases(QtWidgets.QWidget):
    vtp_loaded = QtCore.Signal(object)
    viewer_clear_requested = QtCore.Signal()
    cases_updated = QtCore.Signal(object)
    input_path_changed = QtCore.Signal(object)
    run_finished = QtCore.Signal()

    def pick_input_file(self) -> None:
        pass

    def load_input_file(self, *_args, **_kwargs) -> bool:
        return True

    def logln(self, _message: str) -> None:
        pass

    def selected_case_rows(self):
        return ()

    def is_running(self) -> bool:
        return False


class _Viewer(QtWidgets.QWidget):
    log_message = QtCore.Signal(str)
    save_selected_images_requested = QtCore.Signal()

    def load_vtp(self, *_args) -> None:
        pass

    def clear_view(self) -> None:
        pass

    def set_case_rows(self, _rows) -> None:
        pass

    def set_input_path(self, _path) -> None:
        pass

    def save_images_for_case_rows(self, _rows) -> None:
        pass


class _Site:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.pages: list[str] = []
        self.closed = False

    def resolve(self, page: str = "index.html") -> Path:
        self.pages.append(page)
        return self.root / page

    def close(self) -> None:
        self.closed = True


class _MissingSite(_Site):
    def resolve(self, page: str = "index.html") -> Path:
        raise DocumentationSiteError(f"missing documentation: {page}")


class HelpMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def _window(self, spec, site) -> MainWindow:
        return MainWindow(
            spec,
            cases_panel=_Cases(),
            viewer_panel=_Viewer(),
            documentation_site=site,
        )

    def test_canonical_and_legacy_guis_share_documentation_and_about_menu(self) -> None:
        with tempfile.TemporaryDirectory(prefix="panel docs ünicode ") as directory:
            root = Path(directory) / "site with spaces"
            root.mkdir(parents=True)
            (root / "index.html").touch()

            specifications = (
                canonical_fmf_spec(),
                legacy_fmf_spec(),
                canonical_hypersonic_spec(),
                legacy_hypersonic_spec(),
            )
            for spec in specifications:
                with self.subTest(product=spec.product_id):
                    site = _Site(root)
                    window = self._window(spec, site)
                    self.assertEqual(
                        ["Documentation", "", "About"],
                        [action.text() for action in window.help_menu.actions()],
                    )
                    opened = []
                    with patch(
                        "panelsolver.app.main_window.QtGui.QDesktopServices.openUrl",
                        side_effect=lambda url, opened_urls=opened: (
                            opened_urls.append(url) or True
                        ),
                    ):
                        window.documentation_action.trigger()
                    self.assertEqual(["index.html"], site.pages)
                    self.assertEqual(
                        [root / "index.html"],
                        [Path(url.toLocalFile()) for url in opened],
                    )
                    window.close()
                    self.assertTrue(site.closed)

    def test_about_uses_panelsolver_version_domain_and_license(self) -> None:
        for spec in (canonical_fmf_spec(), canonical_hypersonic_spec()):
            with self.subTest(domain=spec.domain_name):
                window = self._window(spec, _Site(Path("site")))
                with (
                    patch(
                        "panelsolver.app.main_window.panelsolver_distribution_version",
                        return_value="9.8.7rc1",
                    ),
                    patch("panelsolver.app.main_window.QtWidgets.QMessageBox.about") as about,
                ):
                    window.about_action.trigger()
                message = about.call_args.args[2]
                self.assertIn("Panel Solver", message)
                self.assertIn("version 9.8.7rc1", message)
                self.assertIn(f"Domain: {spec.domain_name}", message)
                self.assertIn("License: Apache-2.0", message)
                window.close()

    def test_missing_or_unopenable_documentation_reports_clear_error(self) -> None:
        for site, message in (
            (_MissingSite(Path("site")), "missing documentation"),
            (_Site(Path("site")), "default browser did not accept"),
        ):
            window = self._window(canonical_fmf_spec(), site)
            with (
                patch(
                    "panelsolver.app.main_window.QtGui.QDesktopServices.openUrl",
                    return_value=False,
                ),
                patch("panelsolver.app.main_window.QtWidgets.QMessageBox.critical") as critical,
            ):
                window.documentation_action.trigger()
            self.assertIn(message, critical.call_args.args[2])
            window.close()


if __name__ == "__main__":
    unittest.main()
