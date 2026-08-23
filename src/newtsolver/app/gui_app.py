"""newtsolver selector for the shared graphical application."""

from __future__ import annotations

from typing import NoReturn

from panelsolver.app import gui_bootstrap

from .._frontend import _legacy_gui_spec


def main() -> NoReturn:
    """Launch the shared GUI with the pinned newtsolver specification."""
    raise SystemExit(gui_bootstrap.run_gui(_legacy_gui_spec()))
