"""Launch the real Panel Solver GUI in a reproducible visual-smoke state."""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from panelsolver.app.gui_bootstrap import _configure_application, create_main_window
from panelsolver.app.gui_theme import ThemeMode, apply_application_theme
from panelsolver.app.solver_spec import SolverSpec
from panelsolver.gui import canonical_gui_spec


def _existing_input_path(value: str) -> Path:
    path = Path(value).expanduser().resolve(strict=False)
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"input file does not exist: {value}")
    return path


def _nonnegative_row(value: str) -> int:
    row = int(value)
    if row < 0:
        raise argparse.ArgumentTypeError("row must be zero or greater")
    return row


def _png_output_path(value: str) -> Path:
    path = Path(value).expanduser().resolve(strict=False)
    if path.suffix.lower() != ".png":
        raise argparse.ArgumentTypeError("screenshot path must end in .png")
    return path


def _validate_requested_row(requested_row: int, row_count: int) -> None:
    if requested_row >= row_count:
        valid_range = "none" if row_count == 0 else f"0-{row_count - 1}"
        raise ValueError(
            f"requested row {requested_row} is out of range for "
            f"{row_count} loaded case(s); valid range: {valid_range}"
        )


def build_parser() -> argparse.ArgumentParser:
    """Build the development-only visual-smoke parser."""
    parser = argparse.ArgumentParser(
        description="Launch the real GUI for normal-display visual inspection.",
    )
    parser.add_argument(
        "--domain",
        choices=("fmf", "hypersonic"),
        default="fmf",
        help="flow domain to compose (default: fmf)",
    )
    parser.add_argument(
        "--theme",
        choices=tuple(mode.value for mode in ThemeMode),
        default=ThemeMode.SYSTEM.value,
        help="effective theme request (default: system)",
    )
    parser.add_argument(
        "--input",
        type=_existing_input_path,
        help="optional case input loaded after the window opens",
    )
    parser.add_argument(
        "--row",
        type=_nonnegative_row,
        default=0,
        help="zero-based row selected and focused after loading (default: 0)",
    )
    parser.add_argument(
        "--screenshot",
        type=_png_output_path,
        help=(
            "capture the Qt client area with the real VTK viewport composited "
            "into it; the native title bar is not included"
        ),
    )
    parser.add_argument(
        "--quit-after-screenshot",
        action="store_true",
        help="exit after --screenshot is written",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse and validate visual-smoke arguments."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.quit_after_screenshot and args.screenshot is None:
        parser.error("--quit-after-screenshot requires --screenshot")
    return args


def _is_noninteractive_capture(args: argparse.Namespace) -> bool:
    return args.screenshot is not None and args.quit_after_screenshot


def _preflight_noninteractive_spec(
    spec: SolverSpec,
    args: argparse.Namespace,
) -> SolverSpec:
    """Read non-interactive input once, before any modal GUI can be opened."""
    if not _is_noninteractive_capture(args) or args.input is None:
        return spec
    if spec.adapters is None:
        raise RuntimeError("GUI adapters are not configured")

    rows = tuple(spec.adapters.read_cases(args.input))
    if not rows:
        raise ValueError("input contains no cases")
    if any(not isinstance(row, Mapping) for row in rows):
        raise TypeError("input reader must return mappings")
    rows = tuple(dict(row) for row in rows)
    _validate_requested_row(args.row, len(rows))

    input_path = args.input.resolve(strict=False)
    original_read_cases = spec.adapters.read_cases

    def read_preflighted_cases(path: str | Path):
        requested = Path(path).expanduser().resolve(strict=False)
        if requested == input_path:
            return rows
        return original_read_cases(path)

    adapters = replace(spec.adapters, read_cases=read_preflighted_cases)
    return replace(spec, adapters=adapters)


def capture_main_window(window: QtWidgets.QMainWindow, output_path: Path) -> None:
    """Capture the Qt client area and composite its native VTK viewport."""
    if not isinstance(window, QtWidgets.QMainWindow):
        raise TypeError("window must be a QMainWindow")
    if not isinstance(output_path, Path):
        raise TypeError("output_path must be a Path")

    viewer_panel = getattr(window, "viewer_panel", None)
    plotter = getattr(viewer_panel, "plotter", None)
    interactor = getattr(plotter, "interactor", None)
    if not isinstance(interactor, QtWidgets.QWidget):
        raise TypeError("window viewer must provide a QWidget interactor")
    if interactor.width() <= 0 or interactor.height() <= 0:
        raise RuntimeError("VTK interactor has no drawable area")

    with tempfile.TemporaryDirectory(prefix="panelsolver-gui-capture-") as temp_dir:
        viewport_path = Path(temp_dir) / "viewport.png"
        plotter.screenshot(str(viewport_path))
        viewport = QtGui.QImage(str(viewport_path))
        if viewport.isNull():
            raise RuntimeError("VTK viewport screenshot could not be read")

        client = window.grab()
        viewport_origin = interactor.mapTo(window, QtCore.QPoint(0, 0))
        viewport_rect = QtCore.QRect(viewport_origin, interactor.size())
        painter = QtGui.QPainter(client)
        if not painter.isActive():
            raise RuntimeError("Qt client-area compositor could not start")
        try:
            painter.drawImage(viewport_rect, viewport)
        finally:
            painter.end()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not client.save(str(output_path), "PNG"):
        raise RuntimeError(f"GUI screenshot could not be saved: {output_path}")


def _prepare_representative_state(
    window: QtWidgets.QMainWindow,
    args: argparse.Namespace,
) -> bool:
    """Load and select the requested representative state."""
    if args.input is None:
        return True
    loaded = window.cases_panel.load_input_file(
        args.input,
        remember_directory=False,
    )
    if not loaded:
        return False
    _validate_requested_row(
        args.row,
        window.cases_panel.case_table.rowCount(),
    )
    window.cases_panel.case_table.selectRow(args.row)
    window.cases_panel.case_table.setCurrentCell(args.row, 0)
    window.cases_panel.case_table.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
    return True


def _exit_with_error(
    application: QtWidgets.QApplication,
    message: str,
) -> None:
    print(f"GUI visual-smoke failed: {message}", file=sys.stderr)
    application.exit(1)


def _capture_representative_state(
    application: QtWidgets.QApplication,
    window: QtWidgets.QMainWindow,
    args: argparse.Namespace,
) -> None:
    application.processEvents(
        QtCore.QEventLoop.ProcessEventsFlag.AllEvents,
        50,
    )
    try:
        capture_main_window(window, args.screenshot)
    except Exception as exc:
        _exit_with_error(application, f"screenshot capture failed: {exc}")
        return
    print(f"Saved GUI screenshot: {args.screenshot}")
    if args.quit_after_screenshot:
        application.quit()


def _prepare_and_schedule_capture(
    application: QtWidgets.QApplication,
    window: QtWidgets.QMainWindow,
    args: argparse.Namespace,
) -> None:
    noninteractive = _is_noninteractive_capture(args)
    try:
        prepared = _prepare_representative_state(window, args)
    except Exception as exc:
        if noninteractive:
            _exit_with_error(
                application, f"representative state preparation failed: {exc}"
            )
            return
        window.cases_panel.logln(f"[ERROR] {exc}")
        prepared = False
    finally:
        window.raise_()
        window.activateWindow()

    if noninteractive and not prepared:
        _exit_with_error(application, "representative input could not be loaded")
        return
    if args.screenshot is not None:
        QtCore.QTimer.singleShot(
            300,
            lambda: _capture_representative_state(application, window, args),
        )


def main(argv: list[str] | None = None) -> int:
    """Show one real MainWindow on the normal platform display."""
    args = parse_args(argv)
    spec = canonical_gui_spec(args.domain)
    try:
        spec = _preflight_noninteractive_spec(spec, args)
    except Exception as exc:
        print(
            f"GUI visual-smoke input preparation failed: {exc}",
            file=sys.stderr,
        )
        return 1

    application = QtWidgets.QApplication([sys.argv[0]])
    _configure_application(application)
    apply_application_theme(application, ThemeMode(args.theme))
    window = create_main_window(spec)

    window.show()
    QtCore.QTimer.singleShot(
        300,
        lambda: _prepare_and_schedule_capture(application, window, args),
    )
    return int(application.exec())


if __name__ == "__main__":
    raise SystemExit(main())
