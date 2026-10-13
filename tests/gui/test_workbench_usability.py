"""Usability regressions for the workbench layout, states, and shortcuts."""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtTest, QtWidgets

from panelsolver.app.gui_components import ElidedPathField, WorkbenchSplitter
from panelsolver.app.gui_theme import ThemeMode, render_application_qss, resolve_theme
from panelsolver.app.main_window import MainWindow
from panelsolver.app.viewer import ViewerPanel
from tests.gui import test_cases_panel
from tests.gui.test_gui_theme import _contrast_ratio
from tests.gui.test_viewer_panel import FakePlotter, FakePoly


class _FakeScalarBar:
    def __init__(self) -> None:
        self.titles: list[str] = []
        self.text_precedes_bar = False

    def SetTitle(self, title: str) -> None:
        self.titles.append(title)

    def SetTextPositionToPrecedeScalarBar(self) -> None:
        self.text_precedes_bar = True


class _ScalarBarPlotter(FakePlotter):
    def __init__(self) -> None:
        super().__init__()
        self.scalar_bars: dict[str, _FakeScalarBar] = {}

    def add_mesh(self, poly, **kwargs) -> None:
        super().add_mesh(poly, **kwargs)
        title = kwargs.get("scalar_bar_args", {}).get("title")
        if title is not None:
            self.scalar_bars.setdefault(title, _FakeScalarBar())

    def clear(self) -> None:
        super().clear()
        self.scalar_bars.clear()


class WorkbenchUsabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def make_window(self, spec_factory=test_cases_panel.fmf_solver_spec):
        panel = test_cases_panel.CasesPanelTests().make_panel(
            spec_factory=spec_factory
        )[0]
        viewer = ViewerPanel(panel.spec, plotter_factory=lambda _parent: FakePlotter())
        window = MainWindow(
            panel.spec,
            cases_panel=panel,
            viewer_panel=viewer,
            persist_layout=False,
        )
        self.addCleanup(window.close)
        return window, panel, viewer

    def test_empty_case_table_offers_input_actions_until_cases_load(self) -> None:
        window, panel, _viewer = self.make_window()
        self.assertIs(panel.empty_cases, panel.case_table_stack.currentWidget())
        self.assertLessEqual(
            panel.case_table_stack.minimumSizeHint().width(),
            panel.case_table.minimumSizeHint().width(),
        )
        self.assertEqual("No cases loaded", panel.lbl_run_scope.text())
        self.assertFalse(panel.btn_clear_selection.isEnabled())
        self.assertFalse(panel.btn_run.isEnabled())
        self.assertIs(window.new_from_example_menu, panel.btn_empty_example.menu())
        self.assertFalse(panel.btn_empty_example.isHidden())
        with patch.object(
            QtWidgets.QFileDialog, "getOpenFileName", return_value=("", "")
        ) as dialog:
            panel.btn_empty_pick_input.click()
        dialog.assert_called_once()

        window.show()
        self.app.processEvents()
        self.assertIs(panel.btn_pick_input, window.focusWidget())

        self.assertTrue(panel.load_input_file("/tmp/input.csv"))
        self.assertIs(panel.case_table, panel.case_table_stack.currentWidget())
        self.assertEqual("Run scope: all 2 cases", panel.lbl_run_scope.text())
        panel.case_table.selectRow(1)
        self.assertEqual("Run scope: 1 of 2 cases selected", panel.lbl_run_scope.text())
        self.assertTrue(panel.btn_clear_selection.isEnabled())
        panel.clear_loaded_cases()
        self.assertIs(panel.empty_cases, panel.case_table_stack.currentWidget())
        self.assertFalse(panel.btn_clear_selection.isEnabled())

    def test_input_path_keeps_file_name_and_full_path(self) -> None:
        field = ElidedPathField()
        self.addCleanup(field.close)
        field.show()
        path = "/Users/example/work/very/long/checkout/workspace/hypersonic/pressure_models.csv"
        tail = "/hypersonic/pressure_models.csv"
        # Size from the platform font: room for the elided tail, not the path.
        metrics = field.fontMetrics()
        needed = metrics.horizontalAdvance(f"…work{tail}")
        width = 40
        field.resize(width, 30)
        while field._available_text_width() < needed:
            width += 4
            field.resize(width, 30)
        self.assertLess(field._available_text_width(), metrics.horizontalAdvance(path))
        field.setText(path)
        self.app.processEvents()
        shown = field.displayed_text()
        self.assertEqual(path, field.text())
        self.assertEqual(path, field.toolTip())
        self.assertTrue(shown.startswith("…"), shown)
        self.assertTrue(shown.endswith(tail), shown)
        self.assertLessEqual(
            field.fontMetrics().horizontalAdvance(shown),
            field._available_text_width(),
        )
        field.resize(2000, 30)
        self.app.processEvents()
        self.assertEqual(path, field.displayed_text())
        QtWidgets.QApplication.clipboard().clear()
        QtTest.QTest.keySequence(field, QtGui.QKeySequence.StandardKey.Copy)
        self.assertEqual(path, QtWidgets.QApplication.clipboard().text())
        field.clear()
        self.assertEqual("", field.text())
        self.assertEqual("", field.displayed_text())

    def drop_event(self, path: str) -> QtGui.QDropEvent:
        mime = QtCore.QMimeData()
        mime.setUrls([QtCore.QUrl.fromLocalFile(path)])
        # QDropEvent does not own its MIME data; keep it alive for the test.
        self._mime_data = [*getattr(self, "_mime_data", []), mime]
        return QtGui.QDropEvent(
            QtCore.QPointF(10, 10),
            QtCore.Qt.DropAction.CopyAction,
            mime,
            QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.KeyboardModifier.NoModifier,
        )

    def test_dropping_a_case_table_or_vtp_opens_it(self) -> None:
        window, panel, viewer = self.make_window()
        self.assertTrue(window.acceptDrops())
        self.assertFalse(panel.input_value.acceptDrops())
        ignored = self.drop_event("/tmp/notes.txt")
        window.dragEnterEvent(ignored)
        self.assertFalse(ignored.isAccepted())

        window.dropEvent(self.drop_event("/tmp/dropped.csv"))
        self.assertEqual(Path("/tmp/dropped.csv"), panel.input_path)

        with patch.object(viewer, "load_vtp") as load_vtp:
            window.dropEvent(self.drop_event("/tmp/result.vtp"))
        load_vtp.assert_called_once_with(str(Path("/tmp/result.vtp")))

    def test_run_menu_shortcuts_follow_run_and_cancel_buttons(self) -> None:
        window, panel, _viewer = self.make_window()
        titles = [action.text() for action in window.menuBar().actions()]
        self.assertEqual(["File", "Run", "View", "Help"], titles)
        self.assertEqual(QtGui.QKeySequence("Ctrl+R"), window.run_action.shortcut())
        self.assertEqual(QtGui.QKeySequence("Ctrl+."), window.cancel_action.shortcut())
        native = window.run_action.shortcut().toString(
            QtGui.QKeySequence.SequenceFormat.NativeText
        )
        self.assertIn(native, panel.btn_run.toolTip())
        self.assertFalse(window.run_action.isEnabled())
        self.assertFalse(window.cancel_action.isEnabled())

        panel.load_input_file("/tmp/input.csv")
        self.assertTrue(window.run_action.isEnabled())
        self.assertFalse(window.cancel_action.isEnabled())
        with patch.object(
            QtWidgets.QFileDialog, "getSaveFileName", return_value=("", "")
        ) as dialog:
            window.run_action.trigger()
        dialog.assert_called_once()
        self.assertIn("[SKIP] Result output canceled.", panel.log.toPlainText())
        panel.case_table.selectRow(0)
        window.run_menu.aboutToShow.emit()
        self.assertEqual("Run Selected Cases", window.run_action.text())

    def test_splitter_handle_draws_a_visible_grip(self) -> None:
        window, _panel, _viewer = self.make_window()
        self.assertIsInstance(window.splitter, WorkbenchSplitter)
        self.assertGreaterEqual(window.splitter.handleWidth(), 9)
        window.show()
        self.app.processEvents()
        image = window.splitter.handle(1).grab().toImage()
        colors = {
            image.pixel(x, y)
            for x in range(image.width())
            for y in range(image.height())
        }
        self.assertGreaterEqual(len(colors), 3)

    def test_colorbar_title_is_drawn_apart_from_tick_labels(self) -> None:
        plotter = _ScalarBarPlotter()
        viewer = ViewerPanel(
            test_cases_panel.newt_solver_spec(),
            plotter_factory=lambda _parent: plotter,
        )
        self.addCleanup(viewer.close)
        viewer.load_vtp("/tmp/case.vtp", FakePoly({"cp": [0.2, 0.5]}))
        options = plotter.mesh_calls[0][1]["scalar_bar_args"]
        self.assertEqual("Cp", options["title"])
        bar = plotter.scalar_bars["Cp"]
        self.assertEqual([""], bar.titles)
        self.assertTrue(bar.text_precedes_bar)
        self.assertEqual("Cp", plotter.text_calls[0])

    def test_scalar_selector_fits_every_known_label(self) -> None:
        previous = self.app.styleSheet()
        self.addCleanup(self.app.setStyleSheet, previous)
        for mode in (ThemeMode.LIGHT, ThemeMode.DARK):
            self.app.setStyleSheet(render_application_qss(resolve_theme(mode)))
            for spec_factory in (
                test_cases_panel.fmf_solver_spec,
                test_cases_panel.newt_solver_spec,
            ):
                with self.subTest(theme=mode, domain=spec_factory.__module__):
                    _window, _panel, viewer = self.make_window(spec_factory)
                    _window.show()
                    self.app.processEvents()
                    combo = viewer.cmb_scalar
                    option = QtWidgets.QStyleOptionComboBox()
                    combo.initStyleOption(option)
                    field = combo.style().subControlRect(
                        QtWidgets.QStyle.ComplexControl.CC_ComboBox,
                        option,
                        QtWidgets.QStyle.SubControl.SC_ComboBoxEditField,
                        combo,
                    )
                    for label in viewer.spec.scalar_labels.values():
                        self.assertGreaterEqual(
                            field.width(),
                            combo.fontMetrics().horizontalAdvance(label),
                            label,
                        )

    def test_idle_status_and_table_focus_use_quiet_theme_roles(self) -> None:
        _window, panel, _viewer = self.make_window()
        self.assertEqual("neutral", panel.progress.property("fluentStatus"))
        for mode in (ThemeMode.LIGHT, ThemeMode.DARK):
            with self.subTest(theme=mode):
                theme = resolve_theme(mode)
                qss = render_application_qss(theme)
                focus = re.search(r"QAbstractItemView:focus \{([^}]*)\}", qss)
                self.assertIsNotNone(focus)
                self.assertIn(theme.value("brand_stroke"), focus.group(1))
                self.assertGreaterEqual(
                    _contrast_ratio(
                        theme.value("brand_stroke"), theme.value("canvas_background")
                    ),
                    3.0,
                )
                idle = re.search(
                    r'QProgressBar\[fluentStatus="neutral"\] \{([^}]*)\}', qss
                )
                self.assertIsNotNone(idle)
                self.assertIn("border-color: transparent", idle.group(1))


if __name__ == "__main__":
    unittest.main()
