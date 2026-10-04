from __future__ import annotations

import os
import re
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtTest, QtWidgets

from panelsolver.app.gui_components import FrozenCaseTable
from panelsolver.app.gui_theme import (
    SEMANTIC_TOKEN_NAMES,
    ApplicationThemeManager,
    ThemeMode,
    ThemeResolutionError,
    build_application_palette,
    render_application_qss,
    resolve_theme,
)


def _relative_luminance(value: str) -> float:
    color = QtGui.QColor(value)
    channels = (color.redF(), color.greenF(), color.blueF())
    linear = tuple(
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    )
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(first: str, second: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


class GuiThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self) -> None:
        self.app.setPalette(QtGui.QPalette(), "QComboBox")
        self._palette = QtGui.QPalette(self.app.palette())
        self._stylesheet = self.app.styleSheet()
        self._identity = (
            self.app.applicationName(),
            self.app.applicationDisplayName(),
            self.app.organizationName(),
            self.app.organizationDomain(),
        )

    def tearDown(self) -> None:
        self.app.setPalette(self._palette)
        self.app.setPalette(QtGui.QPalette(), "QComboBox")
        self.app.setStyleSheet(self._stylesheet)  # fluent-audit: allow test restore
        self.app.setApplicationName(self._identity[0])
        self.app.setApplicationDisplayName(self._identity[1])
        self.app.setOrganizationName(self._identity[2])
        self.app.setOrganizationDomain(self._identity[3])

    def test_light_dark_and_system_resolve_complete_semantic_tokens(self) -> None:
        light = resolve_theme(ThemeMode.LIGHT)
        dark = resolve_theme(ThemeMode.DARK)
        system_light = resolve_theme(
            ThemeMode.SYSTEM,
            color_scheme=QtCore.Qt.ColorScheme.Light,
        )
        system_dark = resolve_theme(
            ThemeMode.SYSTEM,
            color_scheme=QtCore.Qt.ColorScheme.Dark,
        )

        for theme in (light, dark):
            self.assertEqual(SEMANTIC_TOKEN_NAMES, frozenset(theme.tokens))
            self.assertTrue(all(theme.tokens.values()))
            for name, value in theme.tokens.items():
                with self.subTest(theme=theme.effective_mode, token=name):
                    self.assertTrue(QtGui.QColor(value).isValid())

        self.assertEqual(ThemeMode.LIGHT, system_light.effective_mode)
        self.assertEqual(ThemeMode.DARK, system_dark.effective_mode)
        self.assertNotEqual(
            light.value("window_background"),
            dark.value("window_background"),
        )
        with self.assertRaises(ThemeResolutionError):
            light.value("not_a_token")

    def test_unknown_system_scheme_falls_back_to_effective_palette(self) -> None:
        dark_palette = QtGui.QPalette()
        dark_palette.setColor(
            QtGui.QPalette.ColorRole.Window, QtGui.QColor("#101010")
        )  # fluent-audit: allow fixture
        light_palette = QtGui.QPalette()
        light_palette.setColor(
            QtGui.QPalette.ColorRole.Window, QtGui.QColor("#f0f0f0")
        )  # fluent-audit: allow fixture

        self.assertEqual(
            ThemeMode.DARK,
            resolve_theme(
                ThemeMode.SYSTEM,
                system_palette=dark_palette,
                color_scheme=QtCore.Qt.ColorScheme.Unknown,
            ).effective_mode,
        )
        self.assertEqual(
            ThemeMode.LIGHT,
            resolve_theme(
                ThemeMode.SYSTEM,
                system_palette=light_palette,
                color_scheme=QtCore.Qt.ColorScheme.Unknown,
            ).effective_mode,
        )

    def test_high_contrast_path_uses_effective_system_palette(self) -> None:
        palette = QtGui.QPalette()
        palette.setColor(
            QtGui.QPalette.ColorGroup.Active,
            QtGui.QPalette.ColorRole.Window,
            QtGui.QColor("#123456"),  # fluent-audit: allow fixture
        )
        palette.setColor(
            QtGui.QPalette.ColorGroup.Active,
            QtGui.QPalette.ColorRole.Highlight,
            QtGui.QColor("#fedcba"),  # fluent-audit: allow fixture
        )
        palette.setColor(
            QtGui.QPalette.ColorGroup.Disabled,
            QtGui.QPalette.ColorRole.Text,
            QtGui.QColor("#777777"),  # fluent-audit: allow fixture
        )

        theme = resolve_theme(
            ThemeMode.SYSTEM,
            system_palette=palette,
            color_scheme=QtCore.Qt.ColorScheme.Dark,
            high_contrast=True,
        )

        self.assertTrue(theme.uses_system_palette)
        self.assertEqual(
            "#123456", theme.value("window_background")
        )  # fluent-audit: allow fixture
        self.assertEqual(
            "#fedcba", theme.value("focus_border")
        )  # fluent-audit: allow fixture
        self.assertEqual(
            "#777777", theme.value("disabled_text")
        )  # fluent-audit: allow fixture
        self.assertEqual(SEMANTIC_TOKEN_NAMES, frozenset(theme.tokens))

    def test_generated_qss_has_no_unresolved_placeholders(self) -> None:
        for mode in (ThemeMode.LIGHT, ThemeMode.DARK):
            qss = render_application_qss(
                resolve_theme(
                    mode,
                    color_scheme=QtCore.Qt.ColorScheme.Light,
                )
            )
            self.assertTrue(qss.strip())
            self.assertNotIn("@{", qss)
            paths = set(re.findall(r'image: url\("([^"\n]+)"\)', qss))
            self.assertTrue(paths)
            for path in paths:
                self.assertFalse(QtGui.QImage(path).isNull(), path)

        with self.assertRaises(ThemeResolutionError):
            render_application_qss(
                resolve_theme(ThemeMode.LIGHT),
                "QWidget { color: @{missing_role}; }",
            )

    def test_case_cell_paints_selection_without_native_row_background(self) -> None:
        # Windows 11 draws the selection in CE_ItemViewItem, whereas other
        # styles may already fill it in PE_PanelItemViewRow. Exercise the cell
        # alone so that a native row fill cannot conceal missing QSS painting.
        flag = QtWidgets.QStyle.StateFlag
        for mode in (ThemeMode.LIGHT, ThemeMode.DARK):
            theme = resolve_theme(mode)
            self.app.setPalette(build_application_palette(theme))
            self.app.setStyleSheet(render_application_qss(theme))
            table = FrozenCaseTable()
            try:
                for view in (table, table.frozen):
                    view.ensurePolished()
                    for active in (True, False):
                        for enabled in (True, False):
                            with self.subTest(
                                mode=mode,
                                pinned=view is table.frozen,
                                active=active,
                                enabled=enabled,
                            ):
                                view.setEnabled(enabled)
                                option = QtWidgets.QStyleOptionViewItem()
                                option.initFrom(view)
                                option.rect = QtCore.QRect(0, 0, 160, 32)
                                option.state = flag.State_Selected
                                if active:
                                    option.state |= flag.State_Active
                                if enabled:
                                    option.state |= flag.State_Enabled
                                option.showDecorationSelected = True
                                option.viewItemPosition = QtWidgets.QStyleOptionViewItem.ViewItemPosition.OnlyOne
                                image = QtGui.QImage(
                                    160, 32, QtGui.QImage.Format.Format_ARGB32
                                )
                                image.fill(QtCore.Qt.GlobalColor.transparent)
                                painter = QtGui.QPainter(image)
                                try:
                                    view.style().drawControl(
                                        QtWidgets.QStyle.ControlElement.CE_ItemViewItem,
                                        option,
                                        painter,
                                        view,
                                    )
                                finally:
                                    painter.end()
                                token = (
                                    "disabled_background"
                                    if not enabled
                                    else "selection_background"
                                    if active
                                    else "inactive_selection_background"
                                )
                                self.assertEqual(
                                    QtGui.QColor(theme.value(token)),
                                    image.pixelColor(80, 16),
                                )
                    view.setEnabled(True)
            finally:
                table.close()
                table.deleteLater()

    def test_progress_status_text_and_boundaries_have_contrast(self) -> None:
        roles = (
            ("info", "link", "inactive_selection_background"),
            ("success", "success_foreground", "success_background"),
            ("warning", "warning_foreground", "warning_background"),
            ("danger", "danger_foreground", "danger_background"),
        )
        for mode in (ThemeMode.LIGHT, ThemeMode.DARK):
            tokens = resolve_theme(mode).tokens
            for status, border, fill in roles:
                with self.subTest(mode=mode, status=status):
                    self.assertGreaterEqual(
                        _contrast_ratio(tokens["text_primary"], tokens[fill]),
                        4.5,
                    )
                    self.assertGreaterEqual(
                        _contrast_ratio(tokens[border], tokens["control_background"]),
                        3.0,
                    )

    def test_palette_populates_active_inactive_and_disabled_groups(self) -> None:
        theme = resolve_theme(ThemeMode.LIGHT)
        palette = build_application_palette(theme)
        self.assertEqual(
            theme.value("window_background"),
            palette.color(
                QtGui.QPalette.ColorGroup.Active,
                QtGui.QPalette.ColorRole.Window,
            ).name(),
        )
        self.assertEqual(
            theme.value("disabled_text"),
            palette.color(
                QtGui.QPalette.ColorGroup.Disabled,
                QtGui.QPalette.ColorRole.Text,
            ).name(),
        )
        self.assertEqual(
            theme.value("selection_background"),
            palette.color(
                QtGui.QPalette.ColorGroup.Active,
                QtGui.QPalette.ColorRole.Highlight,
            ).name(),
        )
        self.assertEqual(
            theme.value("inactive_selection_background"),
            palette.color(
                QtGui.QPalette.ColorGroup.Inactive,
                QtGui.QPalette.ColorRole.Highlight,
            ).name(),
        )
        self.assertEqual(
            theme.value("selection_text"),
            palette.color(
                QtGui.QPalette.ColorGroup.Active,
                QtGui.QPalette.ColorRole.HighlightedText,
            ).name(),
        )
        self.assertEqual(
            theme.value("inactive_selection_text"),
            palette.color(
                QtGui.QPalette.ColorGroup.Inactive,
                QtGui.QPalette.ColorRole.HighlightedText,
            ).name(),
        )
        self.assertNotEqual(
            palette.color(
                QtGui.QPalette.ColorGroup.Active,
                QtGui.QPalette.ColorRole.Highlight,
            ),
            palette.color(
                QtGui.QPalette.ColorGroup.Inactive,
                QtGui.QPalette.ColorRole.Highlight,
            ),
        )
        self.assertNotEqual(
            palette.color(
                QtGui.QPalette.ColorGroup.Active,
                QtGui.QPalette.ColorRole.Text,
            ),
            palette.color(
                QtGui.QPalette.ColorGroup.Disabled,
                QtGui.QPalette.ColorRole.Text,
            ),
        )

    def test_palette_preserves_native_button_surface_and_text_pairs(self) -> None:
        role = QtGui.QPalette.ColorRole
        group = QtGui.QPalette.ColorGroup
        base_palette = QtGui.QPalette()
        expected = {
            group.Active: ("#fafafa", "#111111"),
            group.Inactive: ("#f0f0f0", "#222222"),
            group.Disabled: ("#e0e0e0", "#777777"),
        }
        for color_group, (surface, foreground) in expected.items():
            base_palette.setColor(color_group, role.Button, QtGui.QColor(surface))
            base_palette.setColor(
                color_group,
                role.ButtonText,
                QtGui.QColor(foreground),
            )

        theme = resolve_theme(ThemeMode.DARK)
        palette = build_application_palette(theme, base_palette=base_palette)

        for color_group, (surface, foreground) in expected.items():
            with self.subTest(group=color_group):
                self.assertEqual(
                    QtGui.QColor(surface),
                    palette.color(color_group, role.Button),
                )
                self.assertEqual(
                    QtGui.QColor(foreground),
                    palette.color(color_group, role.ButtonText),
                )
        self.assertEqual(
            QtGui.QColor(theme.value("text_primary")),
            palette.color(group.Active, role.Text),
        )

    def assert_control_text_palette(self, control, theme) -> None:
        group = QtGui.QPalette.ColorGroup
        role = QtGui.QPalette.ColorRole
        for color_group, color_role, token in (
            (group.Active, role.Text, "text_primary"),
            (group.Active, role.Highlight, "selection_background"),
            (group.Active, role.ButtonText, "text_primary"),
            (group.Disabled, role.Text, "disabled_text"),
        ):
            self.assertEqual(
                QtGui.QColor(theme.value(token)),
                control.palette().color(color_group, color_role),
            )

    def test_combo_uses_semantic_surface_in_both_themes_and_disabled_state(
        self,
    ) -> None:
        role = QtGui.QPalette.ColorRole
        group = QtGui.QPalette.ColorGroup
        combo = QtWidgets.QComboBox()
        combo.addItems(["Cp", "Area"])
        manager = ApplicationThemeManager(self.app)
        for mode in (ThemeMode.LIGHT, ThemeMode.DARK):
            theme = manager.set_mode(mode)
            combo.setEnabled(True)
            combo.ensurePolished()
            self.app.processEvents()
            self.assert_control_text_palette(combo, theme)
            self.assertEqual(
                QtGui.QColor(theme.value("control_background")),
                combo.palette().color(group.Active, role.Base),
            )
            combo.setEnabled(False)
            self.app.processEvents()
            self.assertEqual(
                QtGui.QColor(theme.value("disabled_text")),
                combo.palette().color(role.Text),
            )
            self.assertEqual(
                QtGui.QColor(theme.value("disabled_background")),
                combo.palette().color(role.Base),
            )
            self.assertEqual("Cp", combo.currentText())
        combo.deleteLater()
        manager.deleteLater()

    def test_styled_combo_keeps_keyboard_selection_and_popup_colors(self) -> None:
        combo = QtWidgets.QComboBox()
        combo.addItems(["Cp", "Area", "Shielded"])
        manager = ApplicationThemeManager(self.app)
        for mode in (ThemeMode.LIGHT, ThemeMode.DARK):
            theme = manager.set_mode(mode)
            combo.setCurrentIndex(0)
            combo.show()
            combo.setFocus()
            self.app.processEvents()
            QtTest.QTest.keyClick(combo, QtCore.Qt.Key.Key_Down)
            self.assertEqual("Area", combo.currentText())
            combo.showPopup()
            self.app.processEvents()
            self.assertTrue(combo.view().isVisible())
            self.assertEqual(
                QtGui.QColor(theme.value("text_primary")),
                combo.view().palette().color(QtGui.QPalette.ColorRole.Text),
            )
            QtTest.QTest.keyClick(combo.view(), QtCore.Qt.Key.Key_Down)
            QtTest.QTest.keyClick(combo.view(), QtCore.Qt.Key.Key_Return)
            self.assertEqual("Shielded", combo.currentText())
            combo.hidePopup()
        combo.close()
        manager.deleteLater()

    def test_themed_integer_input_preserves_keyboard_and_step_buttons(self) -> None:
        for mode in (ThemeMode.LIGHT, ThemeMode.DARK):
            theme = resolve_theme(mode)
            self.app.setPalette(build_application_palette(theme))
            self.app.setStyleSheet(render_application_qss(theme))
            spin = QtWidgets.QSpinBox()
            spin.setRange(0, 2_147_483_647)
            spin.resize(140, 30)
            spin.show()
            spin.setFocus()
            self.app.processEvents()
            self.assert_control_text_palette(spin, theme)
            spin.selectAll()
            QtTest.QTest.keyClicks(spin, "2000")
            QtTest.QTest.keyClick(spin, QtCore.Qt.Key.Key_Return)
            self.assertEqual(2000, spin.value())
            option = QtWidgets.QStyleOptionSpinBox()
            spin.initStyleOption(option)
            up = spin.style().subControlRect(
                QtWidgets.QStyle.ComplexControl.CC_SpinBox,
                option,
                QtWidgets.QStyle.SubControl.SC_SpinBoxUp,
                spin,
            )
            QtTest.QTest.mouseClick(
                spin, QtCore.Qt.MouseButton.LeftButton, pos=up.center()
            )
            self.assertEqual(2001, spin.value())
            down = spin.style().subControlRect(
                QtWidgets.QStyle.ComplexControl.CC_SpinBox,
                option,
                QtWidgets.QStyle.SubControl.SC_SpinBoxDown,
                spin,
            )
            self.assertFalse(up.intersects(down))
            self.assertLess(down.center().x(), up.center().x())
            QtTest.QTest.mouseClick(
                spin, QtCore.Qt.MouseButton.LeftButton, pos=down.center()
            )
            self.assertEqual(2000, spin.value())

            spin.close()

    def test_explicit_theme_refreshes_native_roles_on_system_change(self) -> None:
        manager = ApplicationThemeManager(self.app, mode=ThemeMode.DARK)
        manager.apply()

        palette = QtGui.QPalette(self.app.palette())
        palette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor("#efcba9"))
        palette.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor("#123456"))
        with patch.object(self.app.style(), "standardPalette", return_value=palette):
            QtGui.QGuiApplication.styleHints().colorSchemeChanged.emit(
                QtCore.Qt.ColorScheme.Light
            )
            self.app.processEvents()

        self.assertEqual(ThemeMode.DARK, manager.current_theme.effective_mode)
        for role in (
            QtGui.QPalette.ColorRole.Button,
            QtGui.QPalette.ColorRole.ButtonText,
        ):
            self.assertEqual(palette.color(role), self.app.palette().color(role))
        self.assertEqual(
            QtGui.QColor(resolve_theme(ThemeMode.DARK).value("window_background")),
            self.app.palette().color(QtGui.QPalette.ColorRole.Window),
        )
        manager.deleteLater()


if __name__ == "__main__":
    unittest.main()
