"""Semantic theme foundation for the shared Qt GUI.

The resolved light and dark values are a project-owned subset of the Fluent 2
Web token snapshot from ``@fluentui/react-theme`` 9.2.1 (2026-07-12).  Ordinary
widgets consume the semantic aliases exposed here; they do not select theme-
specific values or embed raw colors.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from importlib import resources
from types import MappingProxyType

from PySide6 import QtCore, QtGui, QtWidgets


class ThemeResolutionError(ValueError):
    """Raised when semantic tokens or the generated QSS cannot be resolved."""


class ThemeMode(str, Enum):
    """Supported internal theme requests.

    No user-facing selector is introduced by this foundation.
    """

    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


@dataclass(frozen=True)
class ResolvedTheme:
    """One immutable set of semantic tokens for an effective theme."""

    requested_mode: ThemeMode
    effective_mode: ThemeMode
    tokens: Mapping[str, str]
    uses_system_palette: bool = False

    def value(self, name: str) -> str:
        """Return one semantic value and fail clearly for an unknown role."""
        try:
            return self.tokens[name]
        except KeyError as exc:
            raise ThemeResolutionError(f"Unknown semantic token: {name!r}") from exc


def _load_theme_tokens() -> dict[ThemeMode, Mapping[str, str]]:
    """Load and validate the packaged, versioned semantic token subset."""
    payload = json.loads(
        resources.files("panelsolver.app")
        .joinpath("gui_theme_tokens.json")
        .read_text(encoding="utf-8")
    )
    if payload.get("schema_version") != 1:
        raise RuntimeError("Unsupported GUI theme token schema")
    themes: dict[ThemeMode, Mapping[str, str]] = {}
    for mode in (ThemeMode.LIGHT, ThemeMode.DARK):
        values = payload.get(mode.value)
        if not isinstance(values, dict) or not values:
            raise RuntimeError(f"Missing semantic tokens for {mode.value}")
        if not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in values.items()
        ):
            raise RuntimeError(f"Invalid semantic tokens for {mode.value}")
        themes[mode] = MappingProxyType(dict(values))
    return themes


_THEME_TOKENS = _load_theme_tokens()
SEMANTIC_TOKEN_NAMES = frozenset(_THEME_TOKENS[ThemeMode.LIGHT])
if SEMANTIC_TOKEN_NAMES != frozenset(_THEME_TOKENS[ThemeMode.DARK]):
    raise RuntimeError("Light and dark semantic token vocabularies differ")

_QSS_PLACEHOLDER_RE = re.compile(r"@\{([A-Za-z_][A-Za-z0-9_]*)\}")
_THEME_MANAGER_ATTRIBUTE = "_panelsolver_theme_manager"


def _qss_color(color: QtGui.QColor) -> str:
    if color.alpha() == 255:
        return color.name(QtGui.QColor.NameFormat.HexRgb)
    return f"rgba({color.red()},{color.green()},{color.blue()},{color.alphaF():.4f})"  # fluent-audit: allow serializer


def _system_palette_tokens(
    palette: QtGui.QPalette,
    base_tokens: Mapping[str, str],
) -> dict[str, str]:
    """Resolve critical roles from an effective system/high-contrast palette."""
    role = QtGui.QPalette.ColorRole
    group = QtGui.QPalette.ColorGroup

    def active(color_role: QtGui.QPalette.ColorRole) -> str:
        return _qss_color(palette.color(group.Active, color_role))

    def inactive(color_role: QtGui.QPalette.ColorRole) -> str:
        return _qss_color(palette.color(group.Inactive, color_role))

    def disabled(color_role: QtGui.QPalette.ColorRole) -> str:
        return _qss_color(palette.color(group.Disabled, color_role))

    placeholder = getattr(role, "PlaceholderText", role.Text)
    resolved = dict(base_tokens)
    resolved.update(
        {
            "window_background": active(role.Window),
            "canvas_background": active(role.Base),
            "secondary_surface": active(role.Window),
            "control_background": active(role.Button),
            "control_hover": active(role.Button),
            "control_pressed": active(role.Button),
            "text_primary": active(role.WindowText),
            "text_secondary": active(role.Text),
            "text_placeholder": active(placeholder),
            "border_control": active(role.Mid),
            "border_hover": active(role.Highlight),
            "border_subtle": active(role.Midlight),
            "selection_background": active(role.Highlight),
            "selection_text": active(role.HighlightedText),
            "inactive_selection_background": inactive(role.Highlight),
            "inactive_selection_text": inactive(role.HighlightedText),
            "brand_background": active(role.Highlight),
            "brand_hover": active(role.Highlight),
            "brand_pressed": active(role.Highlight),
            "brand_selected": active(role.Highlight),
            "brand_text": active(role.HighlightedText),
            "focus_border": active(role.Highlight),
            "disabled_background": disabled(role.Button),
            "disabled_text": disabled(role.Text),
            "disabled_border": disabled(role.Mid),
            "read_only_background": active(role.Base),
            "read_only_text": active(role.Text),
            "link": active(role.Link),
            "link_visited": active(role.LinkVisited),
            "tooltip_background": active(role.ToolTipBase),
            "tooltip_text": active(role.ToolTipText),
        }
    )
    for prefix in ("success", "warning", "danger"):
        resolved[f"{prefix}_background"] = active(role.Base)
        resolved[f"{prefix}_foreground"] = active(role.WindowText)
        resolved[f"{prefix}_border"] = active(role.Highlight)
    resolved.update(
        {
            "danger_action_background": active(role.Highlight),
            "danger_action_hover": active(role.Highlight),
            "danger_action_pressed": active(role.Highlight),
        }
    )
    return resolved


def _palette_is_dark(palette: QtGui.QPalette) -> bool:
    window = palette.color(
        QtGui.QPalette.ColorGroup.Active,
        QtGui.QPalette.ColorRole.Window,
    )
    return window.lightness() < 128


def resolve_theme(
    mode: ThemeMode | str,
    *,
    system_palette: QtGui.QPalette | None = None,
    color_scheme: QtCore.Qt.ColorScheme | None = None,
    high_contrast: bool = False,
) -> ResolvedTheme:
    """Resolve light, dark, or system-following semantic tokens.

    ``high_contrast`` is orthogonal to the public mode vocabulary. It provides
    the effective-system-palette fallback path without adding a preference UI.
    """
    requested = mode if isinstance(mode, ThemeMode) else ThemeMode(mode)
    palette = QtGui.QPalette(system_palette) if system_palette is not None else None

    if requested == ThemeMode.SYSTEM:
        if color_scheme == QtCore.Qt.ColorScheme.Dark:
            effective = ThemeMode.DARK
        elif color_scheme == QtCore.Qt.ColorScheme.Light:
            effective = ThemeMode.LIGHT
        elif palette is not None and _palette_is_dark(palette):
            effective = ThemeMode.DARK
        else:
            effective = ThemeMode.LIGHT
    else:
        effective = requested

    tokens = dict(_THEME_TOKENS[effective])
    uses_system_palette = bool(high_contrast and palette is not None)
    if uses_system_palette:
        tokens = _system_palette_tokens(palette, tokens)

    if frozenset(tokens) != SEMANTIC_TOKEN_NAMES:
        missing = SEMANTIC_TOKEN_NAMES - frozenset(tokens)
        extra = frozenset(tokens) - SEMANTIC_TOKEN_NAMES
        raise ThemeResolutionError(
            f"Semantic token mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    return ResolvedTheme(
        requested_mode=requested,
        effective_mode=effective,
        tokens=MappingProxyType(tokens),
        uses_system_palette=uses_system_palette,
    )


def build_application_palette(
    theme: ResolvedTheme,
    *,
    base_palette: QtGui.QPalette | None = None,
) -> QtGui.QPalette:
    """Build broad Qt roles while retaining native control surface pairs.

    Platform styles can own complex-control surfaces independently of an
    explicit application light/dark request.  In particular, macOS Aqua keeps
    a non-editable ``QComboBox`` aligned with the system appearance.  Preserve
    the base palette's ``Button``/``ButtonText`` pair so that its native surface
    and foreground cannot diverge.  Application-QSS buttons continue to use the
    resolved semantic control tokens.
    """
    palette = (
        QtGui.QPalette(base_palette) if base_palette is not None else QtGui.QPalette()
    )
    token = theme.tokens
    role = QtGui.QPalette.ColorRole
    group = QtGui.QPalette.ColorGroup

    active_roles = {
        role.Window: token["window_background"],
        role.WindowText: token["text_primary"],
        role.Base: token["canvas_background"],
        role.AlternateBase: token["secondary_surface"],
        role.Text: token["text_primary"],
        role.BrightText: token["danger_foreground"],
        role.Highlight: token["selection_background"],
        role.HighlightedText: token["selection_text"],
        role.Link: token["link"],
        role.LinkVisited: token["link_visited"],
        role.ToolTipBase: token["tooltip_background"],
        role.ToolTipText: token["tooltip_text"],
        role.Light: token["canvas_background"],
        role.Midlight: token["border_subtle"],
        role.Mid: token["border_control"],
        role.Dark: token["text_secondary"],
        role.Shadow: token["text_primary"],
    }
    inactive_roles = dict(active_roles)
    inactive_roles.update(
        {
            role.Highlight: token["inactive_selection_background"],
            role.HighlightedText: token["inactive_selection_text"],
        }
    )
    placeholder = getattr(role, "PlaceholderText", None)
    accent = getattr(role, "Accent", None)
    if placeholder is not None:
        active_roles[placeholder] = token["text_placeholder"]
        inactive_roles[placeholder] = token["text_placeholder"]
    if accent is not None:
        active_roles[accent] = token["brand_background"]
        inactive_roles[accent] = token["brand_background"]

    for color_role, value in active_roles.items():
        palette.setColor(group.Active, color_role, QtGui.QColor(value))
    for color_role, value in inactive_roles.items():
        palette.setColor(group.Inactive, color_role, QtGui.QColor(value))

    disabled_roles = {
        role.Window: token["window_background"],
        role.WindowText: token["disabled_text"],
        role.Base: token["disabled_background"],
        role.AlternateBase: token["disabled_background"],
        role.Text: token["disabled_text"],
        role.BrightText: token["disabled_text"],
        role.Highlight: token["disabled_background"],
        role.HighlightedText: token["disabled_text"],
        role.Link: token["disabled_text"],
        role.LinkVisited: token["disabled_text"],
        role.ToolTipBase: token["tooltip_background"],
        role.ToolTipText: token["tooltip_text"],
        role.Light: token["disabled_border"],
        role.Midlight: token["disabled_border"],
        role.Mid: token["disabled_border"],
        role.Dark: token["disabled_text"],
        role.Shadow: token["disabled_text"],
    }
    if placeholder is not None:
        disabled_roles[placeholder] = token["disabled_text"]
    if accent is not None:
        disabled_roles[accent] = token["disabled_text"]
    for color_role, value in disabled_roles.items():
        palette.setColor(group.Disabled, color_role, QtGui.QColor(value))
    return palette


def _qss_template() -> str:
    return (
        resources.files("panelsolver.app")
        .joinpath("gui_theme.qss")
        .read_text(encoding="utf-8")
    )


def render_application_qss(
    theme: ResolvedTheme,
    template: str | None = None,
) -> str:
    """Generate application QSS and reject every unresolved placeholder."""
    source = _qss_template() if template is None else template
    missing: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        value = theme.tokens.get(name)
        if value is None:
            missing.add(name)
            return match.group(0)
        return value

    rendered = _QSS_PLACEHOLDER_RE.sub(replace, source)
    if missing:
        raise ThemeResolutionError(
            f"QSS references unknown semantic tokens: {', '.join(sorted(missing))}"
        )
    leftovers = sorted(set(_QSS_PLACEHOLDER_RE.findall(rendered)))
    if leftovers:
        raise ThemeResolutionError(
            f"QSS contains unresolved placeholders: {', '.join(leftovers)}"
        )
    return rendered


_SEMANTIC_PROPERTIES = MappingProxyType(
    {
        "fluentAppearance": frozenset({"primary", "secondary", "subtle", "danger"}),
        "fluentBusy": bool,
        "fluentInvalid": bool,
    }
)
SEMANTIC_PROPERTY_NAMES = frozenset(_SEMANTIC_PROPERTIES)


def set_semantic_property(
    widget: QtWidgets.QWidget,
    name: str,
    value: object,
) -> None:
    """Set one approved semantic dynamic property and repolish that widget."""
    if not isinstance(widget, QtWidgets.QWidget):
        raise TypeError("widget must be a QWidget")
    if name not in _SEMANTIC_PROPERTIES:
        raise ValueError(f"Unsupported semantic property: {name!r}")
    allowed = _SEMANTIC_PROPERTIES[name]
    if allowed is bool:
        if not isinstance(value, bool):
            raise TypeError(f"{name} must be a bool")
    elif value not in allowed:
        raise ValueError(f"Unsupported {name} value: {value!r}")
    if widget.property(name) == value:
        return
    widget.setProperty(name, value)
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()


class ApplicationThemeManager(QtCore.QObject):
    """Own palette/QSS application and system-preference resolution."""

    theme_changed = QtCore.Signal(object)

    def __init__(
        self,
        application: QtWidgets.QApplication,
        *,
        mode: ThemeMode | str = ThemeMode.SYSTEM,
    ) -> None:
        if not isinstance(application, QtWidgets.QApplication):
            raise TypeError("application must be a QApplication")
        super().__init__(application)
        self.application = application
        self._mode = mode if isinstance(mode, ThemeMode) else ThemeMode(mode)
        self._system_palette = QtGui.QPalette(application.palette())
        self._current_theme: ResolvedTheme | None = None
        self._applying = False
        self._connect_system_signals()

    @property
    def mode(self) -> ThemeMode:
        return self._mode

    @property
    def current_theme(self) -> ResolvedTheme | None:
        return self._current_theme

    def set_mode(self, mode: ThemeMode | str) -> ResolvedTheme:
        requested = mode if isinstance(mode, ThemeMode) else ThemeMode(mode)
        self._mode = requested
        return self.apply()

    def _connect_system_signals(self) -> None:
        hints = QtGui.QGuiApplication.styleHints()
        color_signal = getattr(hints, "colorSchemeChanged", None)
        if color_signal is not None:
            color_signal.connect(self._on_system_preference_changed)
        accessibility_getter = getattr(hints, "accessibility", None)
        if callable(accessibility_getter):
            contrast_signal = getattr(
                accessibility_getter(),
                "contrastPreferenceChanged",
                None,
            )
            if contrast_signal is not None:
                contrast_signal.connect(self._on_system_preference_changed)

    def _on_system_preference_changed(self, *_args: object) -> None:
        style = self.application.style()
        if style is not None:
            self._system_palette = QtGui.QPalette(style.standardPalette())
        # Explicit application themes still retain native complex-control
        # Button/ButtonText roles. Refresh those roles when the system scheme
        # changes even though the requested semantic mode stays fixed.
        QtCore.QTimer.singleShot(0, self.apply)

    @staticmethod
    def _system_high_contrast() -> bool:
        hints = QtGui.QGuiApplication.styleHints()
        accessibility_getter = getattr(hints, "accessibility", None)
        if not callable(accessibility_getter):
            return False
        preference_getter = getattr(
            accessibility_getter(),
            "contrastPreference",
            None,
        )
        if not callable(preference_getter):
            return False
        preference = preference_getter()
        name = getattr(preference, "name", str(preference))
        return "HighContrast" in name

    def apply(self) -> ResolvedTheme:
        """Resolve and atomically apply palette then application QSS."""
        if self._applying and self._current_theme is not None:
            return self._current_theme
        self._applying = True
        try:
            hints = QtGui.QGuiApplication.styleHints()
            theme = resolve_theme(
                self._mode,
                system_palette=self._system_palette,
                color_scheme=hints.colorScheme(),
                high_contrast=(
                    self._mode == ThemeMode.SYSTEM and self._system_high_contrast()
                ),
            )
            palette = build_application_palette(
                theme,
                base_palette=self._system_palette,
            )
            qss = render_application_qss(theme)
            self.application.setPalette(palette)
            self.application.setStyleSheet(qss)  # fluent-audit: allow generated app QSS
            self._current_theme = theme
            self.theme_changed.emit(theme)
            return theme
        finally:
            self._applying = False


def apply_application_theme(
    application: QtWidgets.QApplication,
    mode: ThemeMode | str = ThemeMode.SYSTEM,
) -> ApplicationThemeManager:
    """Apply or reuse the one application-owned theme manager."""
    manager = getattr(application, _THEME_MANAGER_ATTRIBUTE, None)
    if not isinstance(manager, ApplicationThemeManager):
        manager = ApplicationThemeManager(application, mode=mode)
        setattr(application, _THEME_MANAGER_ATTRIBUTE, manager)
    manager.set_mode(mode)
    return manager


__all__ = (
    "SEMANTIC_PROPERTY_NAMES",
    "SEMANTIC_TOKEN_NAMES",
    "ApplicationThemeManager",
    "ResolvedTheme",
    "ThemeMode",
    "ThemeResolutionError",
    "apply_application_theme",
    "build_application_palette",
    "render_application_qss",
    "resolve_theme",
    "set_semantic_property",
)
