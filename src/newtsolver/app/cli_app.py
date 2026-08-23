"""Legacy newtsolver command identity over canonical Hypersonic CLI policy."""

from __future__ import annotations

from dataclasses import replace

from panelsolver.app.cli import run_cli
from panelsolver.domains.hypersonic import CANONICAL_CLI_POLICY

_CLI_POLICY = replace(
    CANONICAL_CLI_POLICY,
    program="newtsolver-cli",
    description="Run newtsolver from CSV/XLSX/XLSM input without GUI.",
)


def main(argv: list[str] | None = None) -> int:
    return run_cli(_CLI_POLICY, argv)
