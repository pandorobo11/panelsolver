from __future__ import annotations

import os
import unittest

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

    def test_semantic_property_helper_preserves_behavior(self) -> None:
        self.assertEqual(
            {"fluentAppearance", "fluentBusy", "fluentInvalid"},
            SEMANTIC_PROPERTY_NAMES,
        )
        button = QtWidgets.QPushButton("Run")
        activations: list[bool] = []
        button.clicked.connect(lambda checked=False: activations.append(checked))

        set_semantic_property(button, "fluentAppearance", "primary")
        set_semantic_property(button, "fluentBusy", False)
        self.assertEqual("primary", button.property("fluentAppearance"))
        self.assertFalse(button.property("fluentBusy"))
        self.assertTrue(button.isEnabled())
        button.click()
        self.assertEqual([False], activations)

        with self.assertRaisesRegex(ValueError, "Unsupported semantic property"):
            set_semantic_property(button, "unknownProperty", True)
        with self.assertRaisesRegex(ValueError, "Unsupported fluentAppearance"):
            set_semantic_property(button, "fluentAppearance", "large")
        with self.assertRaisesRegex(TypeError, "must be a bool"):
            set_semantic_property(button, "fluentInvalid", "true")

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


if __name__ == "__main__":
    unittest.main()
