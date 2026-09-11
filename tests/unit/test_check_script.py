from __future__ import annotations

import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts.check import Mode, _venv_python, build_plan, main


class CheckScriptTests(unittest.TestCase):
    def test_quick_plan_runs_fast_tests_after_dependency_sync(self) -> None:
        plan = build_plan(Mode.QUICK)

        self.assertEqual(("uv", "sync"), plan[0].command[:2])
        self.assertIn("--locked", plan[0].command)
        commands = [step.command for step in plan if step.command is not None]
        for tool in (("ruff", "format"), ("ruff", "check"), ("mypy",)):
            with self.subTest(tool=tool):
                self.assertTrue(
                    any(command[3 : 3 + len(tool)] == tool for command in commands)
                )
        self.assertEqual(
            ("uv", "run", "--no-sync", "pytest", "-m", "not slow"), plan[-1].command
        )

    def test_standard_plan_runs_only_the_full_pytest_suite(self) -> None:
        plan = build_plan(Mode.STANDARD)
        pytest_commands = [
            step.command
            for step in plan
            if step.command is not None and "pytest" in step.command
        ]

        self.assertEqual([("uv", "run", "--no-sync", "pytest")], pytest_commands)

    def test_full_plan_extends_standard_with_deep_local_checks(self) -> None:
        standard = build_plan(Mode.STANDARD)
        full = build_plan(Mode.FULL)

        self.assertEqual(standard, full[: len(standard)])
        commands = [step.command or () for step in full[len(standard) :]]
        self.assertTrue(
            any(
                "scripts/probe_scheduler_lifecycle.py" in command
                for command in commands
            )
        )
        self.assertTrue(any("verify-distributions" in command for command in commands))
        self.assertTrue(any(step.action is not None for step in full[len(standard) :]))

    def test_temporary_python_path_is_platform_specific(self) -> None:
        venv = Path("temporary-venv")

        self.assertEqual(
            venv / "Scripts" / "python.exe",
            _venv_python(venv, "win32"),
        )
        self.assertEqual(venv / "bin" / "python", _venv_python(venv, "linux"))

    @patch("scripts.check.subprocess.run")
    def test_validation_failure_preserves_command_exit_code(self, run) -> None:
        run.side_effect = subprocess.CalledProcessError(23, ["uv", "sync"])

        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            returncode = main(["--quick"])

        self.assertEqual(23, returncode)


if __name__ == "__main__":
    unittest.main()
