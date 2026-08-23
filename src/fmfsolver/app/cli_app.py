"""Legacy FMF command identity over canonical FMF CLI policy."""

from __future__ import annotations

from dataclasses import replace

from panelsolver.app.cli import run_cli
from panelsolver.domains.fmf import CANONICAL_CLI_POLICY

_CLI_POLICY = replace(
    CANONICAL_CLI_POLICY,
    program="fmfsolver-cli",
    description="Run FMF solver from CSV/XLSX/XLSM input without GUI.",
)


def main(argv: list[str] | None = None) -> int:
    return run_cli(_CLI_POLICY, argv)
