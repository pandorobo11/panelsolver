#!/usr/bin/env python3
"""Run the canonical cross-platform local validation gate."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MYPY_SCOPE = (
    "src/panelsolver/core/contracts.py",
    "src/panelsolver/core/execution.py",
    "src/panelsolver/models/registry.py",
    "src/panelsolver/app/execution.py",
    "src/panelsolver/api.py",
    "src/panelsolver/__init__.py",
)

Command = tuple[str, ...]
StepAction = Callable[[Path], None]


class Mode(Enum):
    QUICK = "quick"
    STANDARD = "standard"
    FULL = "full"


@dataclass(frozen=True)
class Step:
    name: str
    command: Command | None = None
    action: StepAction | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if (self.command is None) == (self.action is None):
            raise ValueError("a step must define exactly one command or action")


class ValidationFailure(Exception):
    def __init__(
        self,
        step: Step,
        returncode: int,
        command: str | Sequence[str] | None,
        cause: BaseException,
    ) -> None:
        super().__init__(str(cause))
        self.step = step
        self.returncode = returncode
        self.command = command


SYNC_STEP = Step(
    "Dependency sync",
    ("uv", "sync", "--locked", "--extra", "rayaccel", "--group", "docs"),
)
QUALITY_STEPS = (
    Step(
        "Ruff format",
        (
            "uv",
            "run",
            "--no-sync",
            "ruff",
            "format",
            "--check",
            "src",
            "tests",
            "scripts",
            "hatch_build.py",
        ),
    ),
    Step(
        "Ruff lint",
        (
            "uv",
            "run",
            "--no-sync",
            "ruff",
            "check",
            "src",
            "tests",
            "scripts",
            "hatch_build.py",
        ),
    ),
    Step(
        "Scoped mypy",
        ("uv", "run", "--no-sync", "mypy", *MYPY_SCOPE),
    ),
)
FAST_TEST_STEP = Step(
    "Fast pytest",
    ("uv", "run", "--no-sync", "pytest", "-m", "not slow"),
)
FULL_TEST_STEP = Step(
    "Full pytest",
    ("uv", "run", "--no-sync", "pytest"),
)
REPOSITORY_STEPS = (
    Step(
        "Generated US1976 Sentman table",
        (
            "uv",
            "run",
            "--no-sync",
            "python",
            "scripts/generate_us1976_sentman_table.py",
            "--check",
        ),
    ),
    Step(
        "Generated documentation plots",
        (
            "uv",
            "run",
            "--no-sync",
            "python",
            "scripts/generate_docs_angle_response_plots.py",
            "--check",
        ),
    ),
    Step(
        "Strict MkDocs build",
        ("uv", "run", "--no-sync", "mkdocs", "build", "--strict"),
    ),
    Step("Build distributions", ("uv", "build")),
)
SCHEDULER_STEP = Step(
    "Scheduler lifecycle stress",
    (
        "uv",
        "run",
        "--no-sync",
        "python",
        "scripts/probe_scheduler_lifecycle.py",
        "--iterations",
        "10",
        "--timeout-seconds",
        "90",
    ),
)
VERIFY_DISTRIBUTIONS_STEP = Step(
    "Verify distributions",
    (
        "uv",
        "run",
        "--no-sync",
        "python",
        "scripts/release_tools.py",
        "verify-distributions",
        ".",
        "--dist-dir",
        "dist",
    ),
)


def _display_command(command: Sequence[str]) -> str:
    return subprocess.list2cmdline(list(command))


def _run_command(
    command: Command,
    *,
    cwd: Path,
    capture_output: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    print(f"$ {_display_command(command)}", flush=True)
    try:
        return subprocess.run(
            list(command),
            cwd=cwd,
            check=True,
            capture_output=capture_output,
            text=capture_output,
            env=env,
        )
    except subprocess.CalledProcessError as error:
        if error.stdout:
            print(error.stdout, end="", file=sys.stdout)
        if error.stderr:
            print(error.stderr, end="", file=sys.stderr)
        raise


def _venv_python(venv: Path, platform_name: str | None = None) -> Path:
    platform_name = sys.platform if platform_name is None else platform_name
    if platform_name == "win32":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _installed_wheel_smoke(repository: Path) -> None:
    selected = _run_command(
        (
            "uv",
            "run",
            "--no-sync",
            "python",
            "scripts/release_tools.py",
            "verify-wheel",
            ".",
            "--dist-dir",
            "dist",
        ),
        cwd=repository,
        capture_output=True,
    )
    wheel_output = selected.stdout.strip()
    if not wheel_output:
        raise RuntimeError("release_tools.py verify-wheel returned no wheel path")
    wheel = Path(wheel_output.splitlines()[-1])
    if not wheel.is_absolute():
        wheel = repository / wheel
    wheel = wheel.resolve()
    print(wheel_output, flush=True)

    with tempfile.TemporaryDirectory(prefix="panelsolver-wheel-smoke-") as temporary:
        root = Path(temporary)
        venv = root / "venv"
        _run_command(
            ("uv", "venv", "--python", "3.12", str(venv)),
            cwd=repository,
        )
        python = _venv_python(venv)
        _run_command(
            (
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                str(wheel),
            ),
            cwd=repository,
        )
        environment = os.environ.copy()
        environment["QT_QPA_PLATFORM"] = "offscreen"
        _run_command(
            (
                str(python),
                str(repository / "scripts" / "smoke_installed_wheel.py"),
                str(repository),
            ),
            cwd=root,
            env=environment,
        )


INSTALLED_WHEEL_STEP = Step(
    "Installed-wheel smoke in temporary environment",
    action=_installed_wheel_smoke,
)


def build_plan(mode: Mode) -> tuple[Step, ...]:
    quality = (SYNC_STEP, *QUALITY_STEPS)
    if mode is Mode.QUICK:
        return (*quality, FAST_TEST_STEP)

    standard = (*quality, FULL_TEST_STEP, *REPOSITORY_STEPS)
    if mode is Mode.STANDARD:
        return standard
    if mode is Mode.FULL:
        return (
            *standard,
            SCHEDULER_STEP,
            VERIFY_DISTRIBUTIONS_STEP,
            INSTALLED_WHEEL_STEP,
        )
    raise ValueError(f"unsupported validation mode: {mode}")


def _run_step(step: Step, repository: Path) -> None:
    if step.command is not None:
        _run_command(step.command, cwd=repository)
        return
    assert step.action is not None
    step.action(repository)


def run_plan(mode: Mode, repository: Path = REPOSITORY_ROOT) -> None:
    plan = build_plan(mode)
    total_started = time.monotonic()
    succeeded = False
    print(f"Panel Solver local validation: {mode.value}", flush=True)
    print(f"Repository: {repository}", flush=True)
    try:
        for index, step in enumerate(plan, start=1):
            print(f"\n[{index}/{len(plan)}] {step.name}", flush=True)
            step_started = time.monotonic()
            try:
                _run_step(step, repository)
            except subprocess.CalledProcessError as error:
                elapsed = time.monotonic() - step_started
                print(f"FAILED: {step.name} ({elapsed:.2f} s)", file=sys.stderr)
                raise ValidationFailure(
                    step,
                    error.returncode or 1,
                    error.cmd,
                    error,
                ) from error
            except Exception as error:
                elapsed = time.monotonic() - step_started
                print(f"FAILED: {step.name} ({elapsed:.2f} s)", file=sys.stderr)
                returncode = 127 if isinstance(error, FileNotFoundError) else 1
                raise ValidationFailure(
                    step, returncode, step.command, error
                ) from error
            elapsed = time.monotonic() - step_started
            print(f"PASSED: {step.name} ({elapsed:.2f} s)", flush=True)
        succeeded = True
    finally:
        total_elapsed = time.monotonic() - total_started
        status = "PASSED" if succeeded else "FAILED"
        print(f"\n{status}: {mode.value} total ({total_elapsed:.2f} s)", flush=True)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--quick",
        dest="mode",
        action="store_const",
        const=Mode.QUICK,
        help="run formatting, lint, scoped mypy, and the fast pytest suite",
    )
    modes.add_argument(
        "--standard",
        dest="mode",
        action="store_const",
        const=Mode.STANDARD,
        help="run the default push/PR validation gate",
    )
    modes.add_argument(
        "--full",
        dest="mode",
        action="store_const",
        const=Mode.FULL,
        help="add scheduler and installed-distribution validation",
    )
    parser.set_defaults(mode=Mode.STANDARD)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        run_plan(args.mode)
    except ValidationFailure as failure:
        print(f"Validation failed in step: {failure.step.name}", file=sys.stderr)
        if failure.command:
            command = (
                failure.command
                if isinstance(failure.command, str)
                else _display_command(failure.command)
            )
            print(f"Failed command: {command}", file=sys.stderr)
        print(f"Exit code: {failure.returncode}", file=sys.stderr)
        return failure.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
