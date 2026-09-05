"""Workflow regressions for the GUI review prototype."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtTest, QtWidgets

from panelsolver.app.gui_components import FlowLayout
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

    def layout_diagnostics(self, window):
        panel, viewer = window.cases_panel, window.viewer_panel
        objects = {
            "window": window,
            "cases": panel,
            "viewer": viewer,
            "settings": panel.settings_row,
            "execution": panel.execution_row,
            "workers": panel.spin_workers,
            "checkpoint": panel.spin_checkpoint_every_cases,
        }
        objects.update(
            (name, getattr(viewer, name))
            for name in (
                "controls_chrome",
                "scalar_row",
                "colorbar_row",
                "display_row",
                "camera_row",
                "camera_axis_group",
                "export_row",
                "cmb_scalar",
                "cmb_cmap",
                "edit_vmin",
                "btn_view_xp",
            )
        )
        lines = [
            f"style={self.app.style().objectName()}, font={self.app.font().toString()}"
        ]
        for name, obj in objects.items():
            minimum = (
                obj.minimumSizeHint()
                if isinstance(obj, QtWidgets.QWidget)
                else obj.minimumSize()
            )
            lines.append(
                f"{name}: hint={obj.sizeHint().width()}, minimum={minimum.width()}, "
                f"actual={obj.geometry().width()}"
            )
        return "\n".join(lines)

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
            self.assert_small_window_controls_fit()
        finally:
            self.app.setFont(previous)

    def test_small_window_with_native_styles_themes_and_text_sizes(self):
        previous_font = self.app.font()
        previous_qss = self.app.styleSheet()
        # Unwrap QStyleSheetStyle before recording the platform style name.
        self.app.setStyleSheet("")
        previous_style = self.app.style().objectName()
        try:
            for style in dict.fromkeys((previous_style, "Windows")):
                self.app.setStyle(style)
                for mode in (None, ThemeMode.LIGHT, ThemeMode.DARK):
                    self.app.setStyleSheet(
                        ""
                        if mode is None
                        else render_application_qss(resolve_theme(mode))
                    )
                    for scale in (1.0, 1.25):
                        with self.subTest(style=style, theme=mode, scale=scale):
                            font = self.app.font()
                            font.setPointSizeF(previous_font.pointSizeF() * scale)
                            self.app.setFont(font)
                            self.assert_small_window_controls_fit()
        finally:
            self.app.setStyle(previous_style)
            self.app.setStyleSheet(previous_qss)
            self.app.setFont(previous_font)

    def assert_small_window_controls_fit(self):
        panel = self.panel()
        viewer = self.viewer(panel.spec)
        window = MainWindow(
            panel.spec,
            cases_panel=panel,
            viewer_panel=viewer,
            persist_layout=False,
        )
        try:
            window.resize(1100, 720)
            window.show()
            self.app.processEvents()
            diagnostics = self.layout_diagnostics(window)
            self.assertLessEqual(window.minimumSizeHint().width(), 1100, diagnostics)
            self.assertLessEqual(window.width(), 1100, diagnostics)
            self.assertLessEqual(window.height(), 720, diagnostics)
            for owner, controls in (
                (
                    panel,
                    (
                        panel.btn_run,
                        panel.btn_clear_selection,
                        panel.spin_workers,
                        panel.spin_checkpoint_every_cases,
                    ),
                ),
                (
                    viewer,
                    (
                        viewer.btn_save_image,
                        viewer.btn_save_selected_images,
                        viewer.btn_open_vtp,
                        *viewer._camera_buttons,
                        viewer.cmb_scalar,
                        viewer.cmb_cmap,
                        viewer.edit_vmin,
                        viewer.edit_vmax,
                        viewer.btn_auto_range,
                        viewer.chk_edges,
                        viewer.chk_shield_transparent,
                        viewer.chk_overlay_text,
                    ),
                ),
            ):
                for control in controls:
                    self.assertTrue(control.isVisible(), diagnostics)
                    rect = QtCore.QRect(
                        control.mapTo(owner, QtCore.QPoint()),
                        control.size(),
                    )
                    self.assertTrue(owner.rect().contains(rect), diagnostics)
            self.assert_flow_groups_fit(viewer)
            self.assert_flow_groups_fit(panel)
        finally:
            window.close()

    def assert_flow_groups_fit(self, viewer):
        for flow in viewer.findChildren(FlowLayout):
            rectangles = []
            for index in range(flow.count()):
                item = flow.itemAt(index)
                if item.isEmpty():
                    continue
                rect = item.geometry()
                self.assertTrue(
                    flow.parentWidget().rect().contains(rect),
                    (flow.parentWidget().rect(), rect),
                )
                self.assertFalse(any(rect.intersects(other) for other in rectangles))
                rectangles.append(rect)

    def test_camera_pairs_wrap_when_native_buttons_have_large_minimum_widths(self):
        viewer = self.viewer()
        group = viewer.camera_axis_group
        group.setParent(None)
        try:
            # Isolate the axis group from platform-dependent selector/export hints.
            # Six 160px buttons cannot share this width, but each +/- pair can.
            for button in viewer._camera_axis_buttons:
                button.setMinimumWidth(160)
            group.resize(400, 200)
            group.show()
            self.app.processEvents()
            self.assertLessEqual(group.minimumSizeHint().width(), 400)
            self.assertEqual(group.width(), 400)
            self.assert_flow_groups_fit(group)
            axes = viewer._camera_axis_buttons
            for positive, negative in zip(axes[::2], axes[1::2], strict=True):
                self.assertEqual(
                    positive.mapTo(group, QtCore.QPoint()).y(),
                    negative.mapTo(group, QtCore.QPoint()).y(),
                )
            self.assertLess(
                axes[0].mapTo(group, QtCore.QPoint()).y(),
                axes[2].mapTo(group, QtCore.QPoint()).y(),
            )
        finally:
            group.close()
            viewer.close()

    def test_themed_control_heights_and_header_units_at_larger_text(self):
        previous_style, previous_font = self.app.styleSheet(), self.app.font()
        try:
            for mode in (ThemeMode.LIGHT, ThemeMode.DARK):
                self.app.setStyleSheet(render_application_qss(resolve_theme(mode)))
                for scale in (1.0, 1.25):
                    font = self.app.font()
                    font.setPointSizeF(previous_font.pointSizeF() * scale)
                    self.app.setFont(font)
                    panel = self.panel()
                    viewer = self.viewer(panel.spec)
                    window = MainWindow(
                        panel.spec,
                        cases_panel=panel,
                        viewer_panel=viewer,
                        persist_layout=False,
                    )
                    panel.load_input_file("/tmp/input.csv")
                    window.show()
                    self.app.processEvents()
                    controls = (
                        panel.spin_workers,
                        panel.spin_checkpoint_every_cases,
                        panel.input_value,
                        viewer.cmb_scalar,
                        viewer.cmb_cmap,
                        viewer.edit_vmin,
                        viewer.edit_vmax,
                        viewer.btn_open_vtp,
                        viewer.btn_view_xp,
                        viewer.btn_save_image,
                    )
                    for control in controls:
                        self.assertEqual(
                            panel.btn_run.height(),
                            control.height(),
                            type(control).__name__,
                        )
                    col = panel._table_columns.index("stl_scale_m_per_unit")
                    item = panel.case_table.horizontalHeaderItem(col)
                    self.assertEqual("STL scale\n[m/STL unit]", item.text())
                    self.assertEqual("STL scale [m/STL unit]", item.toolTip())
                    self.assertGreaterEqual(
                        panel.case_table.columnWidth(col),
                        panel.case_table.horizontalHeader().sectionSizeHint(col),
                    )
                    panel.restore_columns(
                        {
                            "shielding_on": {"width": 40},
                            "save_vtp_on": {"width": 40},
                        }
                    )
                    for presentation in panel.spec.case_column_presentations:
                        index = panel._table_columns.index(presentation.name)
                        self.assertGreaterEqual(
                            panel.case_table.columnWidth(index),
                            panel._header_width(index),
                            presentation.name,
                        )
                    self.assertFalse(panel.case_table.showGrid())
                    self.assertFalse(panel.case_table.frozen.showGrid())
                    window.close()
        finally:
            self.app.setFont(previous_font)
            self.app.setStyleSheet(previous_style)

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
