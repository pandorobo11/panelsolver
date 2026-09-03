"""Top-level GUI dispatcher using flow-domain names."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable

from panelsolver.app.gui_bootstrap import run_gui
from panelsolver.app.solver_spec import SolverSpec
from panelsolver.domains.fmf import gui_spec as _fmf_spec
from panelsolver.domains.hypersonic import gui_spec as _hypersonic_spec

_DOMAIN_SPECS: dict[str, Callable[[], SolverSpec]] = {
    "fmf": _fmf_spec,
    "hypersonic": _hypersonic_spec,
}


def build_parser() -> argparse.ArgumentParser:
    """Build the GUI flow-domain selector parser."""
    parser = argparse.ArgumentParser(
        prog="panelsolver-gui",
        description="Launch the Panel Solver GUI for an FMF or Hypersonic flow domain.",
    )
    subparsers = parser.add_subparsers(dest="domain", metavar="{fmf,hypersonic}")
    subparsers.add_parser(
        "fmf",
        help="Free-molecular-flow domain using the Sentman model",
    )
    subparsers.add_parser(
        "hypersonic",
        help="Hypersonic domain using Newtonian-family panel methods",
    )
    return parser


def gui_spec_for_domain(domain: str) -> SolverSpec:
    """Return the GUI composition for one flow domain."""
    try:
        factory = _DOMAIN_SPECS[domain]
    except KeyError as exc:
        raise ValueError(f"unknown flow domain: {domain!r}") from exc
    return factory()


def main(argv: list[str] | None = None) -> int:
    """Select a flow domain and launch the existing shared GUI shell."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not arguments:
        parser.print_help()
        return 0
    namespace = parser.parse_args(arguments)
    if namespace.domain is None:
        parser.error("a flow domain is required: fmf or hypersonic")
    return run_gui(gui_spec_for_domain(namespace.domain), argv=[sys.argv[0]])


__all__ = ("build_parser", "gui_spec_for_domain", "main")
