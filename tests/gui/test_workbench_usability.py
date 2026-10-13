"""Usability regressions for the workbench layout, states, and shortcuts."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtGui, QtTest, QtWidgets

from panelsolver.app.gui_components import ElidedPathField
from panelsolver.app.gui_theme import ThemeMode, render_application_qss, resolve_theme
from panelsolver.app.main_window import MainWindow
from panelsolver.app.viewer import ViewerPanel
from tests.gui import test_cases_panel
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

    def test_clear_selection_starts_disabled_until_rows_are_selected(self) -> None:
        _window, panel, _viewer = self.make_window()
        self.assertFalse(panel.btn_clear_selection.isEnabled())
        self.assertTrue(panel.load_input_file("/tmp/input.csv"))
        self.assertFalse(panel.btn_clear_selection.isEnabled())
        panel.case_table.selectRow(1)
        self.assertTrue(panel.btn_clear_selection.isEnabled())

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


if __name__ == "__main__":
    unittest.main()
