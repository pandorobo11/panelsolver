"""Launch the real Panel Solver GUI in a reproducible visual-smoke state."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from panelsolver.app.gui_bootstrap import _configure_application, create_main_window
from panelsolver.app.gui_theme import ThemeMode, apply_application_theme
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


def main(argv: list[str] | None = None) -> int:
    """Show one real MainWindow on the normal platform display."""
    args = parse_args(argv)
    application = QtWidgets.QApplication([sys.argv[0]])
    _configure_application(application)
    apply_application_theme(application, ThemeMode(args.theme))
    window = create_main_window(canonical_gui_spec(args.domain))

    def prepare_representative_state() -> None:
        if args.input is not None:
            loaded = window.cases_panel.load_input_file(
                args.input,
                remember_directory=False,
            )
            if loaded:
                try:
                    _validate_requested_row(
                        args.row,
                        window.cases_panel.case_table.rowCount(),
                    )
                except ValueError as exc:
                    window.cases_panel.logln(f"[ERROR] {exc}")
                else:
                    window.cases_panel.case_table.selectRow(args.row)
                    window.cases_panel.case_table.setCurrentCell(args.row, 0)
                    window.cases_panel.case_table.setFocus(
                        QtCore.Qt.FocusReason.OtherFocusReason
                    )
        window.raise_()
        window.activateWindow()
        if args.screenshot is not None:
            QtCore.QTimer.singleShot(300, capture_representative_state)

    def capture_representative_state() -> None:
        application.processEvents(
            QtCore.QEventLoop.ProcessEventsFlag.AllEvents,
            50,
        )
        try:
            capture_main_window(window, args.screenshot)
        except Exception as exc:
            print(f"GUI screenshot failed: {exc}", file=sys.stderr)
            application.exit(1)
            return
        print(f"Saved GUI screenshot: {args.screenshot}")
        if args.quit_after_screenshot:
            application.quit()

    window.show()
    QtCore.QTimer.singleShot(300, prepare_representative_state)
    return int(application.exec())


if __name__ == "__main__":
    raise SystemExit(main())
