"""Launch the real Panel Solver GUI in a reproducible visual-smoke state."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6 import QtCore, QtWidgets

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
    return parser


def main(argv: list[str] | None = None) -> int:
    """Show one real MainWindow on the normal platform display."""
    args = build_parser().parse_args(argv)
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

    window.show()
    QtCore.QTimer.singleShot(300, prepare_representative_state)
    return int(application.exec())


if __name__ == "__main__":
    raise SystemExit(main())
