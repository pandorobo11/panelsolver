from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtWidgets

from panelsolver.app.gui_theme import (
    SEMANTIC_PROPERTY_NAMES,
    SEMANTIC_TOKEN_NAMES,
    ApplicationThemeManager,
    ThemeMode,
    ThemeResolutionError,
    build_application_palette,
    render_application_qss,
    resolve_theme,
    set_semantic_property,
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

        for theme in (light, dark, system_light, system_dark):
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
        with self.assertRaisesRegex(ThemeResolutionError, "Unknown semantic token"):
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
        for mode in (ThemeMode.LIGHT, ThemeMode.DARK, ThemeMode.SYSTEM):
            qss = render_application_qss(
                resolve_theme(
                    mode,
                    color_scheme=QtCore.Qt.ColorScheme.Light,
                )
            )
            self.assertTrue(qss.strip())
            self.assertNotIn("@{", qss)

        with self.assertRaisesRegex(
            ThemeResolutionError,
            "unknown semantic tokens",
        ):
            render_application_qss(
                resolve_theme(ThemeMode.LIGHT),
                "QWidget { color: @{missing_role}; }",
            )

    def test_qss_leaves_complex_controls_and_item_selection_to_qt(self) -> None:
        for mode in (ThemeMode.LIGHT, ThemeMode.DARK):
            qss = render_application_qss(resolve_theme(mode))
            for control in (
                "QComboBox",
                "QSpinBox",
                "QDoubleSpinBox",
                "QDateEdit",
                "QTimeEdit",
                "QDateTimeEdit",
            ):
                with self.subTest(mode=mode, control=control):
                    self.assertNotIn(control, qss)

            item_view_rule = qss.split("QAbstractItemView {", 1)[1].split("}", 1)[0]
            self.assertNotIn("selection-background-color", item_view_rule)
            self.assertNotIn("selection-color", item_view_rule)

    def test_progress_qss_is_bounded_and_resolves_semantic_statuses(self) -> None:
        for mode in (ThemeMode.LIGHT, ThemeMode.DARK):
            qss = render_application_qss(resolve_theme(mode))
            self.assertIn("QProgressBar {", qss)
            self.assertIn("QProgressBar::chunk {", qss)
            for status in ("info", "success", "warning", "danger"):
                with self.subTest(mode=mode, status=status):
                    self.assertIn(f'QProgressBar[fluentStatus="{status}"]', qss)
            for decorative_treatment in (
                "qlineargradient",
                "qradialgradient",
                "qconicalgradient",
                "animation",
                "image:",
            ):
                self.assertNotIn(decorative_treatment, qss)

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

    def test_focus_rules_keep_the_base_border_width(self) -> None:
        qss = render_application_qss(resolve_theme(ThemeMode.LIGHT))
        self.assertNotIn("border: 2px", qss)
        for selector in (
            "QPushButton:focus, QToolButton:focus",
            "QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus",
            "QAbstractItemView:focus",
        ):
            with self.subTest(selector=selector):
                rule = qss.split(f"{selector} {{", 1)[1].split("}", 1)[0]
                self.assertIn("border: 1px solid", rule)

    def test_palette_populates_active_inactive_and_disabled_groups(self) -> None:
        theme = resolve_theme(ThemeMode.LIGHT)
        palette = build_application_palette(theme)
        groups = (
            QtGui.QPalette.ColorGroup.Active,
            QtGui.QPalette.ColorGroup.Inactive,
            QtGui.QPalette.ColorGroup.Disabled,
        )
        roles = (
            QtGui.QPalette.ColorRole.Window,
            QtGui.QPalette.ColorRole.WindowText,
            QtGui.QPalette.ColorRole.Base,
            QtGui.QPalette.ColorRole.Text,
            QtGui.QPalette.ColorRole.Button,
            QtGui.QPalette.ColorRole.ButtonText,
            QtGui.QPalette.ColorRole.Highlight,
            QtGui.QPalette.ColorRole.HighlightedText,
        )
        for group in groups:
            for role in roles:
                with self.subTest(group=group, role=role):
                    self.assertTrue(palette.color(group, role).isValid())

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

    def test_complex_controls_inherit_light_and_dark_application_palette(self) -> None:
        for mode in (ThemeMode.LIGHT, ThemeMode.DARK):
            theme = resolve_theme(mode)
            palette = build_application_palette(theme)
            self.app.setPalette(palette)
            self.app.setStyleSheet(render_application_qss(theme))
            controls = (
                QtWidgets.QComboBox(),
                QtWidgets.QSpinBox(),
                QtWidgets.QDoubleSpinBox(),
                QtWidgets.QDateEdit(),
                QtWidgets.QTimeEdit(),
                QtWidgets.QDateTimeEdit(),
            )
            for control in controls:
                control.ensurePolished()
                with self.subTest(mode=mode, control=type(control).__name__):
                    self.assertEqual(
                        palette.color(
                            QtGui.QPalette.ColorGroup.Active,
                            QtGui.QPalette.ColorRole.Text,
                        ),
                        control.palette().color(
                            QtGui.QPalette.ColorGroup.Active,
                            QtGui.QPalette.ColorRole.Text,
                        ),
                    )
                    self.assertEqual(
                        palette.color(
                            QtGui.QPalette.ColorGroup.Active,
                            QtGui.QPalette.ColorRole.Highlight,
                        ),
                        control.palette().color(
                            QtGui.QPalette.ColorGroup.Active,
                            QtGui.QPalette.ColorRole.Highlight,
                        ),
                    )
                    self.assertEqual(
                        palette.color(
                            QtGui.QPalette.ColorGroup.Active,
                            QtGui.QPalette.ColorRole.ButtonText,
                        ),
                        control.palette().color(
                            QtGui.QPalette.ColorGroup.Active,
                            QtGui.QPalette.ColorRole.ButtonText,
                        ),
                    )
                    self.assertEqual(
                        palette.color(
                            QtGui.QPalette.ColorGroup.Disabled,
                            QtGui.QPalette.ColorRole.Text,
                        ),
                        control.palette().color(
                            QtGui.QPalette.ColorGroup.Disabled,
                            QtGui.QPalette.ColorRole.Text,
                        ),
                    )
                control.deleteLater()

    def test_semantic_property_helper_preserves_behavior(self) -> None:
        self.assertEqual(
            {"fluentAppearance", "fluentStatus", "fluentBusy", "fluentInvalid"},
            SEMANTIC_PROPERTY_NAMES,
        )
        button = QtWidgets.QPushButton("Run")
        activations: list[bool] = []
        button.clicked.connect(lambda checked=False: activations.append(checked))

        set_semantic_property(button, "fluentAppearance", "primary")
        set_semantic_property(button, "fluentStatus", "info")
        set_semantic_property(button, "fluentBusy", False)
        self.assertEqual("primary", button.property("fluentAppearance"))
        self.assertEqual("info", button.property("fluentStatus"))
        self.assertFalse(button.property("fluentBusy"))
        self.assertTrue(button.isEnabled())
        button.click()
        self.assertEqual([False], activations)

        with self.assertRaisesRegex(ValueError, "Unsupported semantic property"):
            set_semantic_property(button, "unknownProperty", True)
        with self.assertRaisesRegex(ValueError, "Unsupported fluentAppearance"):
            set_semantic_property(button, "fluentAppearance", "large")
        with self.assertRaisesRegex(ValueError, "Unsupported fluentStatus"):
            set_semantic_property(button, "fluentStatus", "running")
        with self.assertRaisesRegex(TypeError, "must be a bool"):
            set_semantic_property(button, "fluentInvalid", "true")

    def test_semantic_property_repolishes_only_when_value_changes(self) -> None:
        class StyleProbeWidget(QtWidgets.QWidget):
            def __init__(self) -> None:
                super().__init__()
                self.style_probe = Mock()

            def style(self):
                return self.style_probe

        widget = StyleProbeWidget()
        set_semantic_property(widget, "fluentStatus", "neutral")
        set_semantic_property(widget, "fluentStatus", "neutral")

        widget.style_probe.unpolish.assert_called_once_with(widget)
        widget.style_probe.polish.assert_called_once_with(widget)

    def test_theme_apply_preserves_application_identity(self) -> None:
        identity = ("Identity", "Display", "Organization", "example.invalid")
        self.app.setApplicationName(identity[0])
        self.app.setApplicationDisplayName(identity[1])
        self.app.setOrganizationName(identity[2])
        self.app.setOrganizationDomain(identity[3])
        instance = QtWidgets.QApplication.instance()
        manager = ApplicationThemeManager(self.app, mode=ThemeMode.LIGHT)

        light = manager.apply()
        dark = manager.set_mode(ThemeMode.DARK)

        self.assertIs(instance, QtWidgets.QApplication.instance())
        self.assertEqual(
            identity,
            (
                self.app.applicationName(),
                self.app.applicationDisplayName(),
                self.app.organizationName(),
                self.app.organizationDomain(),
            ),
        )
        self.assertEqual(ThemeMode.LIGHT, light.effective_mode)
        self.assertEqual(ThemeMode.DARK, dark.effective_mode)
        self.assertNotIn("@{", self.app.styleSheet())
        manager.deleteLater()

    def test_explicit_theme_refreshes_native_roles_on_system_change(self) -> None:
        manager = ApplicationThemeManager(self.app, mode=ThemeMode.DARK)
        manager.apply()

        with patch.object(QtCore.QTimer, "singleShot") as single_shot:
            manager._on_system_preference_changed()

        single_shot.assert_called_once_with(0, manager.apply)
        manager.deleteLater()


if __name__ == "__main__":
    unittest.main()
