from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtWidgets

from panelsolver.app.main_window import MainWindow
from panelsolver.docs_site import DocumentationSiteError
from panelsolver.domains.fmf import gui_spec as canonical_fmf_spec
from panelsolver.domains.hypersonic import gui_spec as canonical_hypersonic_spec


class _Cases(QtWidgets.QWidget):
    vtp_loaded = QtCore.Signal(object)
    vtp_artifact_invalidated = QtCore.Signal(str)
    viewer_clear_requested = QtCore.Signal()
    cases_updated = QtCore.Signal(object)
    selected_cases_changed = QtCore.Signal(object)
    input_path_changed = QtCore.Signal(object)
    run_finished = QtCore.Signal()

    def __init__(self) -> None:
        super().__init__()
        self.pick_count = 0
        self.loaded = []
        self.messages = []

    def pick_input_file(self) -> None:
        self.pick_count += 1

    def load_input_file(self, path, *, remember_directory=True) -> bool:
        self.loaded.append((Path(path), remember_directory))
        return True

    def logln(self, message: str) -> None:
        self.messages.append(message)

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

    def invalidate_vtp_artifact(self, _path: str) -> None:
        pass

    def set_case_rows(self, _rows) -> None:
        pass

    def set_selected_case_rows(self, _rows) -> None:
        pass

    def set_input_path(self, _path) -> None:
        pass

    def save_images_for_case_rows(self, _rows) -> None:
        pass


class _Site:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path("site")
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


class _Library:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.calls = []

    def copy_example(self, example, destination):
        self.calls.append((example, Path(destination)))
        return self.path


class MainWindowMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def make_window(self, spec, library=None, site=None):
        cases = _Cases()
        window = MainWindow(
            spec,
            cases_panel=cases,
            viewer_panel=_Viewer(),
            documentation_site=site or _Site(),
            example_library=library,
        )
        return window, cases

    def test_open_action_uses_the_same_picker_as_the_screen_button(self) -> None:
        window, cases = self.make_window(canonical_fmf_spec())
        self.assertEqual(
            ["Open Input File...", "New from Example", "", "Exit"],
            [action.text() for action in window.file_menu.actions()],
        )
        window.open_input_action.trigger()
        self.assertEqual(1, cases.pick_count)
        window.close()

    def test_each_domain_lists_only_its_examples(self) -> None:
        expected = {
            "FMF": ["Basic", "Attitude Modes", "Components", "Flow Modes", "Shielding"],
            "Hypersonic": [
                "Basic",
                "Attitude Modes",
                "Components",
                "Pressure Models",
                "Shielding",
            ],
        }
        for spec in (canonical_fmf_spec(), canonical_hypersonic_spec()):
            with self.subTest(product=spec.product_id):
                window, _cases = self.make_window(spec)
                self.assertEqual(
                    expected[spec.domain_name],
                    [action.text() for action in window.example_actions],
                )
                domain = "fmf" if spec.domain_name == "FMF" else "hypersonic"
                self.assertTrue(
                    all(
                        str(action.data()).startswith(f"{domain}/")
                        for action in window.example_actions
                    )
                )
                window.close()

    def test_example_is_copied_then_loaded_without_remembering_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copied_input = root / "fmf" / "basic.csv"
            library = _Library(copied_input)
            window, cases = self.make_window(canonical_fmf_spec(), library)
            with patch.object(
                QtWidgets.QFileDialog,
                "getExistingDirectory",
                return_value=str(root),
            ):
                window.example_actions[0].trigger()
            self.assertEqual(root, library.calls[0][1])
            self.assertEqual([(copied_input, False)], cases.loaded)
            window.close()

    def test_documentation_action_uses_the_bundled_local_page(self) -> None:
        with tempfile.TemporaryDirectory(prefix="panel docs ünicode ") as directory:
            root = Path(directory) / "site with spaces"
            root.mkdir(parents=True)
            (root / "index.html").touch()
            site = _Site(root)
            window, _cases = self.make_window(canonical_fmf_spec(), site=site)
            self.assertEqual(
                ["Documentation", "", "About"],
                [action.text() for action in window.help_menu.actions()],
            )
            opened = []
            with patch(
                "panelsolver.app.main_window.QtGui.QDesktopServices.openUrl",
                side_effect=lambda url: opened.append(url) or True,
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
                window, _cases = self.make_window(spec)
                with (
                    patch(
                        "panelsolver.app.main_window.panelsolver_distribution_version",
                        return_value="9.8.7rc1",
                    ),
                    patch(
                        "panelsolver.app.main_window.QtWidgets.QMessageBox.about"
                    ) as about,
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
            (_MissingSite(), "missing documentation"),
            (_Site(), "default browser did not accept"),
        ):
            with self.subTest(message=message):
                window, _cases = self.make_window(canonical_fmf_spec(), site=site)
                with (
                    patch(
                        "panelsolver.app.main_window.QtGui.QDesktopServices.openUrl",
                        return_value=False,
                    ),
                    patch(
                        "panelsolver.app.main_window.QtWidgets.QMessageBox.critical"
                    ) as critical,
                ):
                    window.documentation_action.trigger()
                self.assertIn(message, critical.call_args.args[2])
                window.close()


if __name__ == "__main__":
    unittest.main()
