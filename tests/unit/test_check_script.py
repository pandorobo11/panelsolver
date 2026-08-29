from __future__ import annotations

import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts.check import Mode, _venv_python, build_plan, main


class CheckScriptTests(unittest.TestCase):
    def test_quick_plan_uses_fast_tests_and_exact_quality_boundary(self) -> None:
        plan = build_plan(Mode.QUICK)

        self.assertEqual(
            [
                "Dependency sync",
                "Ruff format",
                "Ruff lint",
                "Scoped mypy",
                "Fast pytest",
            ],
            [step.name for step in plan],
        )
        self.assertEqual(
            ("uv", "run", "--no-sync", "pytest", "-m", "not slow"), plan[-1].command
        )
        self.assertEqual(
            (
                "uv",
                "run",
                "--no-sync",
                "mypy",
                "src/panelsolver/core/contracts.py",
                "src/panelsolver/core/execution.py",
                "src/panelsolver/models/registry.py",
                "src/panelsolver/app/execution.py",
                "src/panelsolver/api.py",
                "src/panelsolver/__init__.py",
            ),
            plan[-2].command,
        )

    def test_standard_plan_runs_only_the_full_pytest_suite(self) -> None:
        plan = build_plan(Mode.STANDARD)
        pytest_commands = [
            step.command
            for step in plan
            if step.command is not None and "pytest" in step.command
        ]

        self.assertEqual([("uv", "run", "--no-sync", "pytest")], pytest_commands)
        self.assertEqual(9, len(plan))

    def test_full_plan_extends_standard_with_deep_local_checks(self) -> None:
        standard = build_plan(Mode.STANDARD)
        full = build_plan(Mode.FULL)

        self.assertEqual(standard, full[: len(standard)])
        self.assertEqual(
            [
                "Scheduler lifecycle stress",
                "Verify distributions",
                "Installed-wheel smoke in temporary environment",
            ],
            [step.name for step in full[len(standard) :]],
        )

    def test_temporary_python_path_is_platform_specific(self) -> None:
        venv = Path("temporary-venv")

        self.assertEqual(
            venv / "Scripts" / "python.exe",
            _venv_python(venv, "win32"),
        )
        self.assertEqual(venv / "bin" / "python", _venv_python(venv, "linux"))
        self.assertEqual(venv / "bin" / "python", _venv_python(venv, "darwin"))

    @patch("scripts.check.subprocess.run")
    def test_validation_failure_preserves_command_exit_code(self, run) -> None:
        run.side_effect = subprocess.CalledProcessError(23, ["uv", "sync"])

        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            returncode = main(["--quick"])

        self.assertEqual(23, returncode)


if __name__ == "__main__":
    unittest.main()
