"""Canonical command dispatcher for the shared panel-solver platform."""

from __future__ import annotations

import argparse
import sys

from rich_argparse import RichHelpFormatter

from panelsolver.app.cli import ProductCliPolicy, run_cli
from panelsolver.domains.fmf import CANONICAL_CLI_POLICY as _FMF_POLICY
from panelsolver.domains.hypersonic import (
    CANONICAL_CLI_POLICY as _HYPERSONIC_POLICY,
)

_POLICIES: dict[str, ProductCliPolicy] = {
    "fmf": _FMF_POLICY,
    "hypersonic": _HYPERSONIC_POLICY,
}


def build_parser() -> argparse.ArgumentParser:
    """Build the small model-domain selector parser."""
    parser = argparse.ArgumentParser(
        prog="panelsolver",
        description="Run Panel Solver for an FMF or Hypersonic flow domain.",
        formatter_class=RichHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="domain", metavar="{fmf,hypersonic}")
    subparsers.add_parser(
        "fmf",
        add_help=False,
        help="Sentman free-molecular-flow cases",
    )
    subparsers.add_parser(
        "hypersonic",
        add_help=False,
        help="Hypersonic panel-model cases",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Select a physical flow domain and reuse the shared batch CLI service."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not arguments:
        parser.print_help()
        return 0
    namespace, remaining = parser.parse_known_args(arguments)
    if namespace.domain is None:
        parser.error("a flow domain is required: fmf or hypersonic")
    return run_cli(_POLICIES[namespace.domain], remaining)


__all__ = ("build_parser", "main")
