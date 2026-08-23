"""Application bootstrap for the shared Qt GUI."""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from dataclasses import replace
from importlib import resources

from PySide6 import QtGui, QtWidgets

from .main_window import MainWindow
from .solver_spec import SolverGuiAdapters, SolverSpec


class GuiAdaptersUnavailable(RuntimeError):
    """Raised when an explicitly unconfigured GUI specification is invoked."""


_WINDOWS_APP_USER_MODEL_ID = "io.github.pandorobo11.panelsolver"
_APPLICATION_NAME = "Panel Solver"
_ORGANIZATION_NAME = "pandorobo11"
_ORGANIZATION_DOMAIN = "pandorobo11.github.io"


def _set_windows_app_user_model_id() -> None:
    """Give Windows GUI launches a stable taskbar application identity."""
    if sys.platform != "win32":
        return

    import ctypes

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    set_app_id = shell32.SetCurrentProcessExplicitAppUserModelID
    set_app_id.argtypes = [ctypes.c_wchar_p]
    set_app_id.restype = ctypes.c_long
    result = int(set_app_id(_WINDOWS_APP_USER_MODEL_ID))
    if result != 0:
        raise OSError(result, "Could not set the Windows AppUserModelID")


def _application_icon() -> QtGui.QIcon:
    """Load the canonical application icon from the installed package."""
    payload = (
        resources.files("panelsolver")
        .joinpath("assets", "panelsolver.png")
        .read_bytes()
    )
    pixmap = QtGui.QPixmap()
    if not pixmap.loadFromData(payload, "PNG"):
        raise RuntimeError("Could not load the packaged Panel Solver icon")
    return QtGui.QIcon(pixmap)


def _configure_application(application: QtWidgets.QApplication) -> None:
    """Apply the canonical Qt identity to a new or reused application."""
    application.setApplicationName(_APPLICATION_NAME)
    application.setApplicationDisplayName(_APPLICATION_NAME)
    application.setOrganizationName(_ORGANIZATION_NAME)
    application.setOrganizationDomain(_ORGANIZATION_DOMAIN)
    application.setWindowIcon(_application_icon())


def _unavailable_adapters(product_id: str) -> SolverGuiAdapters:
    message = (
        f"{product_id} case I/O and execution adapters are not configured."
    )

    def unavailable(*_args, **_kwargs):
        raise GuiAdaptersUnavailable(message)

    return SolverGuiAdapters(
        read_cases=unavailable,
        build_case_signatures=unavailable,
        run_cases=unavailable,
        validate_output_path=unavailable,
        resolve_velocity_hat_stl=unavailable,
    )


def prepare_gui_spec(spec: SolverSpec) -> SolverSpec:
    """Supply explicit failing adapters only for an unconfigured specification."""
    if not isinstance(spec, SolverSpec):
        raise TypeError("spec must be a SolverSpec")
    if spec.adapters is not None:
        return spec
    return replace(spec, adapters=_unavailable_adapters(spec.product_id))


def create_main_window(
    spec: SolverSpec,
    *,
    window_factory: Callable[[SolverSpec], MainWindow] = MainWindow,
) -> MainWindow:
    """Construct the shared shell from one complete runtime specification."""
    if not callable(window_factory):
        raise TypeError("window_factory must be callable")
    adapters_were_missing = spec.adapters is None
    window = window_factory(prepare_gui_spec(spec))
    if adapters_were_missing:
        window.cases_panel.logln(
            "[ERROR] Case I/O and execution adapters are not configured."
        )
    return window


def run_gui(
    spec: SolverSpec,
    argv: Sequence[str] | None = None,
    *,
    application_factory: Callable[[list[str]], QtWidgets.QApplication] = (
        QtWidgets.QApplication
    ),
    window_factory: Callable[[SolverSpec], MainWindow] = MainWindow,
) -> int:
    """Show the shared window and run the Qt event loop."""
    application = QtWidgets.QApplication.instance()
    if application is None:
        if not callable(application_factory):
            raise TypeError("application_factory must be callable")
        _set_windows_app_user_model_id()
        application = application_factory(list(sys.argv if argv is None else argv))
    _configure_application(application)
    window = create_main_window(spec, window_factory=window_factory)
    window.show()
    return int(application.exec())


__all__ = (
    "GuiAdaptersUnavailable",
    "create_main_window",
    "prepare_gui_spec",
    "run_gui",
)
