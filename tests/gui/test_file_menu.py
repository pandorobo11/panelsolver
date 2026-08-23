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
from panelsolver.domains.fmf import gui_spec as canonical_fmf_spec
from panelsolver.domains.hypersonic import gui_spec as canonical_hypersonic_spec


class _Cases(QtWidgets.QWidget):
    vtp_loaded = QtCore.Signal(object)
    viewer_clear_requested = QtCore.Signal()
    cases_updated = QtCore.Signal(object)
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

    def set_case_rows(self, _rows) -> None:
        pass

    def set_input_path(self, _path) -> None:
        pass

    def save_images_for_case_rows(self, _rows) -> None:
        pass


class _Site:
    def close(self) -> None:
        pass


class _Library:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.calls = []

    def copy_example(self, example, destination):
        self.calls.append((example, Path(destination)))
        return self.path


class FileMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def make_window(self, spec, library=None):
        cases = _Cases()
        window = MainWindow(
            spec,
            cases_panel=cases,
            viewer_panel=_Viewer(),
            documentation_site=_Site(),
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

    def test_each_domain_and_legacy_identity_lists_only_its_examples(self) -> None:
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
        for spec in (
            canonical_fmf_spec(),
            legacy_fmf_spec(),
            canonical_hypersonic_spec(),
            legacy_hypersonic_spec(),
        ):
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


if __name__ == "__main__":
    unittest.main()
