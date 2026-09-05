"""Workflow regressions for the GUI review prototype."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtTest, QtWidgets

from panelsolver.app.gui_theme import ThemeMode, render_application_qss, resolve_theme
from panelsolver.app.main_window import MainWindow
from panelsolver.app.viewer import ViewerPanel
from panelsolver.app.viewer_data import ArtifactViewState, ArtifactViewStatus
from tests.gui import test_cases_panel
from tests.gui.test_viewer_panel import FakePlotter, FakePoly


class WorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def panel(self):
        return test_cases_panel.CasesPanelTests().make_panel()[0]

    def viewer(self, spec=None):
        spec = spec or self.panel().spec
        return ViewerPanel(spec, plotter_factory=lambda _parent: FakePlotter())

    def test_all_columns_and_pinned_selection_preserve_input_order(self):
        panel = self.panel()
        panel.load_input_file("/tmp/input.csv")
        panel.resize(620, 650)
        panel.show()
        self.app.processEvents()
        table = panel.case_table
        self.assertIs(table.model(), table.frozen.model())
        self.assertIs(table.selectionModel(), table.frozen.selectionModel())
        table.selectRow(1)
        expected = panel.selected_case_rows()
        self.assertTrue(
            all(not table.isColumnHidden(c) for c in range(table.columnCount()))
        )
        self.assertFalse(hasattr(panel, "btn_columns"))
        self.assertFalse(hasattr(panel, "lbl_selection_summary"))
        self.assertNotIn(
            "Cases", [label.text() for label in panel.findChildren(QtWidgets.QLabel)]
        )
        self.assertEqual(expected, panel.selected_case_rows())
        table.horizontalScrollBar().setValue(table.horizontalScrollBar().maximum())
        self.assertEqual(0, table.frozen.columnViewportPosition(0))
        index = table.model().index(0, 0)
        QtTest.QTest.mouseClick(
            table.frozen.viewport(),
            QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.KeyboardModifier.ControlModifier,
            table.frozen.visualRect(index).center(),
        )
        self.assertEqual(
            ["case_b", "case_a"], [r["case_id"] for r in panel.selected_case_rows()]
        )
        panel.btn_clear_selection.click()
        self.assertEqual([], panel.selected_case_rows())
        self.assertEqual(2, len(panel.selected_or_all_case_rows()))
        self.assertEqual("Run scope: all 2 cases", panel.lbl_run_scope.text())
        panel.close()

    def test_frozen_vertical_scroll_and_keyboard_keep_the_same_current_row(self):
        rows = tuple(
            {"case_id": f"case_{n}", "stl_path": "model.stl", "S": 5.0}
            for n in range(80)
        )
        panel = test_cases_panel.CasesPanelTests().make_panel(rows)[0]
        panel.load_input_file("/tmp/scroll-input.csv")
        panel.resize(620, 500)
        panel.show()
        self.app.processEvents()
        table = panel.case_table
        table.setCurrentCell(79, 0)
        table.setFocus()
        QtTest.QTest.keyClick(table, QtCore.Qt.Key.Key_Up)
        self.app.processEvents()
        self.assertEqual(78, table.currentRow())
        self.assertEqual(table.currentIndex(), table.frozen.currentIndex())
        self.assertEqual(table.rowAt(0), table.frozen.rowAt(0))
        self.assertGreater(table.verticalScrollBar().value(), 0)
        panel.close()

    def test_frozen_cells_align_in_both_themes_after_resize_and_scroll(self):
        previous = self.app.styleSheet()
        rows = tuple(
            {"case_id": f"case_{n}", "stl_path": "model.stl"} for n in range(80)
        )
        panel = test_cases_panel.CasesPanelTests().make_panel(rows)[0]
        try:
            panel.load_input_file("/tmp/align.csv")
            panel.show()
            table = panel.case_table
            for mode in (ThemeMode.LIGHT, ThemeMode.DARK):
                self.app.setStyleSheet(render_application_qss(resolve_theme(mode)))
                for height in (500, 650):
                    panel.resize(620, height)
                    table.setRowHeight(1, 45)
                    self.app.processEvents()
                    for value in (0, table.verticalScrollBar().maximum()):
                        table.verticalScrollBar().setValue(value)
                        self.app.processEvents()
                        for row in range(table.rowCount()):
                            main = table.visualRect(table.model().index(row, 0))
                            pinned = table.frozen.visualRect(
                                table.model().index(row, 0)
                            )
                            self.assertEqual(main.height(), pinned.height())
                            self.assertEqual(
                                table.viewport().mapTo(table, main.topLeft()),
                                table.frozen.viewport().mapTo(table, pinned.topLeft()),
                            )
        finally:
            panel.close()
            self.app.setStyleSheet(previous)

    def test_small_window_with_larger_text_keeps_primary_actions_inside_panels(self):
        previous = self.app.font()
        font = self.app.font()
        font.setPointSizeF(font.pointSizeF() * 1.25)
        self.app.setFont(font)
        try:
            panel = self.panel()
            viewer = self.viewer(panel.spec)
            window = MainWindow(
                panel.spec, cases_panel=panel, viewer_panel=viewer, persist_layout=False
            )
            window.resize(1100, 720)
            window.show()
            self.app.processEvents()
            for owner, controls in (
                (
                    panel,
                    (
                        panel.btn_run,
                        panel.btn_clear_selection,
                        panel.spin_checkpoint_every_cases,
                    ),
                ),
                (
                    viewer,
                    (
                        viewer.btn_save_image,
                        viewer.btn_open_vtp,
                        *viewer._camera_buttons,
                        viewer.cmb_cmap,
                        viewer.chk_edges,
                        viewer.chk_overlay_text,
                    ),
                ),
            ):
                for control in controls:
                    origin = control.mapTo(owner, QtCore.QPoint())
                    self.assertGreaterEqual(origin.x(), 0)
                    self.assertLessEqual(origin.x() + control.width(), owner.width())
                    self.assertLessEqual(origin.y() + control.height(), owner.height())
            self.assertLessEqual(window.width(), 1100)
            self.assertLessEqual(window.height(), 720)
            window.close()
        finally:
            self.app.setFont(previous)

    def test_full_input_remains_in_table_without_a_duplicate_details_panel(self):
        panel = self.panel()
        panel.load_input_file("/tmp/input.csv")
        self.assertIn("custom", panel._table_columns)
        self.assertIn("/mesh/first.stl", panel.case_table.item(0, 1).toolTip())
        self.assertFalse(hasattr(panel, "case_details"))
        panel.close()

    def test_diagnostics_count_messages_and_cancellation_survives_progress(self):
        panel = self.panel()
        self.assertFalse(panel.btn_clear_diagnostics.isEnabled())
        panel.logln("[WARN] first")
        panel.logln("[ERROR] second")
        panel.logln("[OK] harmless")
        self.assertIn("1 warnings · 1 errors", panel.btn_diagnostics.text())
        panel.show_diagnostics()
        self.assertTrue(panel.btn_diagnostics.isChecked())
        panel._run_worker = SimpleNamespace(cancel=lambda: None)
        panel.cancel_run()
        panel._on_run_progress(2, 10)
        self.assertIn("Cancelling", panel.progress.format())
        panel.btn_clear_diagnostics.click()
        self.assertEqual("", panel.log.toPlainText())
        self.assertEqual("Hide diagnostics", panel.btn_diagnostics.text())
        self.assertTrue(panel.btn_diagnostics.isChecked())
        self.assertFalse(panel.btn_clear_diagnostics.isEnabled())
        self.assertIn("Cancelling", panel.progress.format())
        panel.logln("[WARN] after clear")
        self.assertIn("1 warnings · 0 errors", panel.btn_diagnostics.text())
        self.assertTrue(panel.btn_clear_diagnostics.isEnabled())
        panel.btn_diagnostics.setChecked(False)
        panel.btn_clear_diagnostics.click()
        self.assertEqual("Show diagnostics", panel.btn_diagnostics.text())
        self.assertTrue(panel.log.isHidden())
        panel._run_worker = None
        panel.close()

    def test_empty_recovery_and_manual_state_do_not_claim_current_result(self):
        viewer = self.viewer()
        self.assertEqual([], viewer.empty_panel.findChildren(QtWidgets.QPushButton))
        self.assertFalse(viewer.cmb_scalar.isEnabled())
        self.assertFalse(viewer.empty_panel.isHidden())
        called = []
        viewer.diagnostics_requested.connect(lambda: called.append(True))
        viewer.set_artifact_view_state(
            ArtifactViewState(ArtifactViewStatus.READ_ERROR, Path("/tmp/bad.vtp"))
        )
        viewer.btn_show_diagnostics.click()
        self.assertEqual([True], called)
        self.assertIn("could not be read", viewer.empty_hint.text())
        viewer.load_vtp("/tmp/manual.vtp", FakePoly({"cp": [0.2, 0.5]}))
        self.assertEqual("Manual VTP", viewer.lbl_artifact_state.text())
        self.assertTrue(viewer.cmb_scalar.isEnabled())
        self.assertTrue(viewer.empty_panel.isHidden())
        viewer.close()

    def test_range_fallback_and_partial_auto_without_duplicate_readout(
        self,
    ):
        viewer = self.viewer()
        poly = FakePoly({"cp": [0.2, 0.5]})
        viewer.load_vtp("/tmp/manual.vtp", poly)
        self.assertFalse(hasattr(viewer, "lbl_range_status"))
        self.assertEqual((0.2, 0.5), viewer.plotter.mesh_calls[0][1]["clim"])
        viewer.edit_vmin.setText("0.1")
        viewer.update_view()
        self.assertEqual((0.1, 0.5), viewer.plotter.mesh_calls[0][1]["clim"])
        viewer.edit_vmax.setText("nan")
        viewer.update_view()
        self.assertEqual((0.2, 0.5), viewer.plotter.mesh_calls[0][1]["clim"])
        self.assertTrue(viewer.edit_vmax.property("fluentInvalid"))
        self.assertEqual([0.2, 0.5], list(poly.cell_data["cp"]))
        viewer.clear_range()
        self.assertFalse(viewer.edit_vmax.property("fluentInvalid"))
        viewer.close()

    def test_window_stops_native_plotter_once_before_teardown(self):
        panel = self.panel()
        viewer = self.viewer(panel.spec)
        calls = []
        viewer.plotter.close = lambda: calls.append("closed")
        window = MainWindow(
            panel.spec, cases_panel=panel, viewer_panel=viewer, persist_layout=False
        )
        window.close()
        window.close()
        self.assertEqual(["closed"], calls)

    def test_layout_roundtrip_reset_and_domain_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = QtCore.QSettings(
                str(Path(directory) / "layout.ini"), QtCore.QSettings.Format.IniFormat
            )
            panel = self.panel()
            viewer = self.viewer(panel.spec)
            window = MainWindow(
                panel.spec,
                cases_panel=panel,
                viewer_panel=viewer,
                layout_settings=settings,
            )
            panel.load_input_file("/tmp/input.csv")
            column = panel._table_columns.index("out_dir")
            panel.case_table.setColumnWidth(column, 211)
            panel.btn_diagnostics.setChecked(True)
            settings.setValue(window._layout_key("display"), False)
            settings.setValue(window._layout_key("details"), True)
            window.close()
            settings.setValue(window._layout_key("column_mode"), 2)
            settings.setValue(
                window._layout_key("columns"),
                '{"out_dir": {"width": 211, "hidden": true}}',
            )
            next_panel = self.panel()
            next_viewer = self.viewer(next_panel.spec)
            next_window = MainWindow(
                next_panel.spec,
                cases_panel=next_panel,
                viewer_panel=next_viewer,
                layout_settings=settings,
            )
            next_panel.load_input_file("/tmp/input.csv")
            self.assertFalse(next_panel.case_table.isColumnHidden(column))
            self.assertEqual(211, next_panel.column_preferences()["out_dir"]["width"])
            self.assertTrue(next_panel.btn_diagnostics.isChecked())
            self.assertFalse(next_viewer.chk_edges.isHidden())
            self.assertFalse(next_viewer.camera_row.isHidden())
            self.assertEqual([], next_panel.selected_case_rows())
            next_window.reset_layout()
            self.assertFalse(next_panel.btn_diagnostics.isChecked())
            self.assertFalse(settings.contains("layout/v1/Hypersonic/columns"))
            next_window.close()
