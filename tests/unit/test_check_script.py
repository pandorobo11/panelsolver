from __future__ import annotations

import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from scripts.check import Mode, _venv_python, build_plan, main


class CheckScriptTests(unittest.TestCase):
    def test_modes_keep_required_checks_once_in_execution_order(self) -> None:
        common = ("sync", "format", "lint", "mypy", "pytest")
        repository = ("us1976", "plots", "docs", "build")
        deep = ("scheduler", "distributions", "installed-wheel")
        modes = (
            (Mode.QUICK, common, ("-m", "not slow")),
            (Mode.STANDARD, common + repository, ()),
            (Mode.FULL, common + repository + deep, ()),
        )
        command_kinds = {
            ("uv", "sync"): "sync",
            ("uv", "run", "--no-sync", "ruff", "format"): "format",
            ("uv", "run", "--no-sync", "ruff", "check"): "lint",
            ("uv", "run", "--no-sync", "mypy"): "mypy",
            ("uv", "run", "--no-sync", "pytest"): "pytest",
            ("uv", "run", "--no-sync", "mkdocs", "build"): "docs",
            ("uv", "build"): "build",
        }
        scripts = {
            "scripts/generate_us1976_sentman_table.py": "us1976",
            "scripts/generate_docs_angle_response_plots.py": "plots",
            "scripts/probe_scheduler_lifecycle.py": "scheduler",
            "scripts/release_tools.py": "distributions",
        }
        for mode, expected, pytest_options in modes:
            with self.subTest(mode=mode.value):
                observed = []
                for step in build_plan(mode):
                    command = step.command
                    if command is None:
                        self.assertTrue(callable(step.action))
                        observed.append("installed-wheel")
                        continue
                    matches = [
                        kind
                        for prefix, kind in command_kinds.items()
                        if command[: len(prefix)] == prefix
                    ]
                    if command[:4] == ("uv", "run", "--no-sync", "python"):
                        matches.append(scripts.get(command[4]))
                    self.assertEqual(1, len(matches), command)
                    kind = matches[0]
                    self.assertIsNotNone(kind, command)
                    observed.append(kind)
                    if kind == "sync":
                        self.assertIn("--locked", command)
                        self.assertEqual(
                            "rayaccel", command[command.index("--extra") + 1]
                        )
                        self.assertEqual("docs", command[command.index("--group") + 1])
                    elif kind in {"format", "us1976", "plots"}:
                        self.assertIn("--check", command)
                    elif kind == "pytest":
                        self.assertEqual(pytest_options, command[4:])
                    elif kind == "docs":
                        self.assertIn("--strict", command)
                    elif kind == "distributions":
                        self.assertIn("verify-distributions", command)
                # Exact semantic stages protect required checks, ordering and
                # duplicate execution without fixing names or argument layout.
                self.assertEqual(expected, tuple(observed))

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
