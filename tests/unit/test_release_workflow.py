import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


class ReleaseWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # BaseLoader leaves GitHub's YAML `on` key and expression strings intact.
        # PyYAML is already supplied by the locked documentation toolchain.
        cls.workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8"), yaml.BaseLoader)
        cls.jobs = cls.workflow["jobs"]

    def runs(self, name: str) -> list[str]:
        return [step["run"] for step in self.jobs[name]["steps"] if "run" in step]

    def commands(self, name: str) -> list[str]:
        return [" ".join(run.split()) for run in self.runs(name)]

    def needs(self, name: str) -> set[str]:
        return set(self.jobs[name].get("needs", ()))

    def action(self, name: str, action: str) -> dict:
        steps = [
            step
            for step in self.jobs[name]["steps"]
            if step.get("uses", "").split("@", 1)[0] == action
        ]
        self.assertEqual(1, len(steps), (name, action))
        return steps[0]

    def test_triggers_and_concurrency_keep_main_and_tags_independent(self) -> None:
        triggers = self.workflow["on"]
        self.assertEqual(["main"], triggers["push"]["branches"])
        self.assertEqual(["v*"], triggers["push"]["tags"])
        self.assertIn("pull_request", triggers)
        concurrency = self.workflow["concurrency"]
        self.assertIn(
            "github.event_name == 'pull_request' && format('pr-{0}', github.event.pull_request.number)",
            concurrency["group"],
        )
        self.assertIn("|| format('run-{0}', github.run_id)", concurrency["group"])
        self.assertEqual(
            "${{ github.event_name == 'pull_request' }}",
            concurrency["cancel-in-progress"],
        )

    def test_source_and_installed_checks_keep_platform_coverage(self) -> None:
        self.assertFalse(self.needs("test"))
        self.assertEqual(
            {"ubuntu", "windows", "macos"},
            {
                os.split("-", 1)[0]
                for os in self.jobs["test"]["strategy"]["matrix"]["os"]
            },
        )
        self.assertEqual(
            {"windows", "macos"},
            {
                os.split("-", 1)[0]
                for os in self.jobs["installed-wheel"]["strategy"]["matrix"]["os"]
            },
        )
        self.assertTrue(self.jobs["clean-install"]["runs-on"].startswith("ubuntu-"))
        for name in ("test", "installed-wheel"):
            self.assertEqual("false", self.jobs[name]["strategy"]["fail-fast"])
            self.assertIn("${{ matrix.os }}", self.jobs[name]["runs-on"])
            sync = next(
                command for command in self.commands(name) if "uv sync" in command
            )
            self.assertTrue({"--locked", "rayaccel", "docs"} <= set(shlex.split(sync)))
        source = self.commands("test")
        pytest_command = next(command for command in source if " pytest" in command)
        pytest_arguments = shlex.split(pytest_command)
        pytest_arguments = pytest_arguments[pytest_arguments.index("pytest") + 1 :]
        for argument in pytest_arguments:
            self.assertTrue(argument.startswith("--durations="), pytest_command)
        smoke_owners = {
            name
            for name in self.jobs
            if any(
                "smoke_installed_wheel.py" in command for command in self.commands(name)
            )
        }
        self.assertEqual({"installed-wheel", "clean-install"}, smoke_owners)
        for name in smoke_owners:
            self.assertTrue({"quality", "distribution-build"} <= self.needs(name))
            smoke = [
                command
                for command in self.commands(name)
                if "smoke_installed_wheel.py" in command
            ]
            self.assertEqual(1, len(smoke))
            self.assertIn("--dist-dir", shlex.split(smoke[0]))
        self.assertTrue(
            any(
                "reinstall-wheel" in command
                for command in self.commands("installed-wheel")
            )
        )

    def test_quality_job_keeps_mandatory_checks(self) -> None:
        commands = [shlex.split(command) for command in self.commands("quality")]
        for required in (
            ["uv", "sync"],
            ["uv", "run", "--no-sync", "ruff", "format"],
            ["uv", "run", "--no-sync", "ruff", "check"],
            ["uv", "run", "--no-sync", "mypy"],
        ):
            matches = [
                command for command in commands if command[: len(required)] == required
            ]
            self.assertEqual(1, len(matches), required)
            if required[-1] == "sync":
                self.assertIn("--locked", matches[0])
            elif required[-1] == "format":
                self.assertIn("--check", matches[0])

    def test_embree_preflight_requires_an_available_backend(self) -> None:
        command = next(run for run in self.runs("test") if "ray.has_embree" in run)
        arguments = shlex.split(command)
        code = arguments[arguments.index("-c") + 1]
        for available in (False, True):
            with self.subTest(has_embree=available):
                # Replace only the external dependency, then execute the actual
                # workflow body with normal Python exit semantics.
                setup = (
                    "import sys, types; "
                    "trimesh = types.ModuleType('trimesh'); "
                    "trimesh.__version__ = 'test'; "
                    f"trimesh.ray = types.SimpleNamespace(has_embree={available}); "
                    "sys.modules['trimesh'] = trimesh; "
                )
                run = subprocess.run(
                    [sys.executable, "-c", setup + code],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                self.assertEqual(available, run.returncode == 0, run.stderr)

    def test_scheduler_stress_keeps_required_repetitions(self) -> None:
        command = next(
            run for run in self.runs("test") if "probe_scheduler_lifecycle.py" in run
        )
        arguments = shlex.split(command)
        start = arguments.index("scripts/probe_scheduler_lifecycle.py") + 1
        parser = argparse.ArgumentParser()
        parser.add_argument("--iterations", type=int, required=True)
        parser.add_argument("--timeout-seconds", type=float, required=True)
        options = parser.parse_args(arguments[start:])
        self.assertGreaterEqual(options.iterations, 10)
        self.assertGreaterEqual(options.timeout_seconds, 90)

    def test_build_once_and_consumers_verify_the_same_commit_bound_set(self) -> None:
        producers = [
            name
            for name in self.jobs
            for command in self.commands(name)
            if shlex.split(command)[:2] == ["uv", "build"]
        ]
        self.assertEqual(["distribution-build"], producers)
        build = self.commands("distribution-build")
        for required in (
            "generate_us1976_sentman_table.py --check",
            "generate_docs_angle_response_plots.py --check",
            "mkdocs build --strict",
            "verify-distributions",
            "create-release-archives",
            "dry-run",
        ):
            self.assertTrue(any(required in command for command in build), required)
        create = next(command for command in build if "create-manifest" in command)
        self.assertIn('--commit-sha "${{ github.sha }}"', create)
        upload = self.action("distribution-build", "actions/upload-artifact")["with"]
        self.assertEqual("error", upload["if-no-files-found"])
        self.assertEqual("dist", upload["path"])
        self.assertIn("${{ github.run_id }}", upload["name"])
        for name in (
            "distribution-build",
            "installed-wheel",
            "clean-install",
            "release",
        ):
            with self.subTest(job=name):
                commands = self.commands(name)
                manifest = [
                    command for command in commands if "verify-manifest" in command
                ]
                self.assertEqual(1, len(manifest))
                self.assertIn('--expected-commit "${{ github.sha }}"', manifest[0])
                if name == "distribution-build":
                    continue
                downloaded = self.action(name, "actions/download-artifact")["with"]
                self.assertEqual(upload["name"], downloaded["name"])
                self.assertEqual(upload["path"], downloaded["path"])
                for forbidden in (
                    "uv build",
                    "mkdocs build",
                    "create-release-archives",
                ):
                    self.assertFalse(any(forbidden in command for command in commands))

    def test_clean_install_uses_verified_wheel_outside_checkout(self) -> None:
        commands = self.commands("clean-install")
        install = next(command for command in commands if "uv venv" in command)
        for required in (
            "verify-wheel",
            "uv pip install",
            '"${WHEEL}[rayaccel]"',
            "smoke_installed_wheel.py",
        ):
            self.assertIn(required, install)
        # Installation and the smoke must use the same fresh interpreter, not
        # the active checkout's environment; the smoke runs from RUNNER_TEMP.
        self.assertIn('CLEAN_VENV="${RUNNER_TEMP}/panelsolver-clean"', install)
        self.assertIn('--python "${CLEAN_VENV}/bin/python"', install)
        self.assertRegex(
            install,
            r'"\$\{CLEAN_VENV\}/bin/python"\s*\\?\s*"\$\{GITHUB_WORKSPACE\}/scripts/smoke_installed_wheel\.py"',
        )
        self.assertLess(install.index("uv venv"), install.index("uv pip install"))
        self.assertLess(
            install.index('cd "${RUNNER_TEMP}"'),
            install.index("smoke_installed_wheel.py"),
        )
        self.assertFalse(any("uv sync" in command for command in commands))
        self.assertNotIn("--system-site-packages", install)

    def test_required_gate_fails_closed_and_release_depends_on_it(self) -> None:
        gate = self.jobs["artifact"]
        prerequisites = self.needs("artifact")
        self.assertTrue(
            {"quality", "distribution-build", "installed-wheel", "clean-install"}
            <= prerequisites
        )
        self.assertEqual("${{ always() }}", gate["if"])
        step = next(
            step for step in gate["steps"] if "NEEDS_RESULTS" in step.get("env", {})
        )
        self.assertEqual("${{ toJSON(needs) }}", step["env"]["NEEDS_RESULTS"])
        code = textwrap.dedent(
            step["run"].split("python - <<'PY'\n", 1)[1].rsplit("PY", 1)[0]
        )
        success = {name: {"result": "success"} for name in sorted(prerequisites)}
        cases = [("all succeeded", success, True), ("empty", {}, False)]
        name = next(reversed(success))
        for result in ("failure", "cancelled", "skipped"):
            cases.append((result, {**success, name: {"result": result}}, False))
        for label, results, expected_success in cases:
            with self.subTest(result=label):
                run = subprocess.run(
                    [sys.executable, "-c", code],
                    env={**os.environ, "NEEDS_RESULTS": json.dumps(results)},
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(expected_success, run.returncode == 0, run.stderr)
        self.assertTrue({"test", "artifact"} <= self.needs("release"))
        self.assertEqual(
            "startsWith(github.ref, 'refs/tags/v')", self.jobs["release"]["if"]
        )

    def test_tag_validation_uses_fetched_protected_main(self) -> None:
        for name in ("distribution-build", "release"):
            with self.subTest(job=name):
                script = next(run for run in self.runs(name) if "verify-tag" in run)
                lines = re.sub(r"\\\n\s*", " ", script).splitlines()
                fetched = False
                variables = {}
                validated = set()
                for line in lines:
                    tokens = shlex.split(line)
                    if tokens[:3] == ["git", "fetch", "origin"]:
                        self.assertIn("main", tokens)
                        self.assertIn("--tags", tokens)
                        fetched = True
                    assignment = (
                        re.fullmatch(r"(\w+)=\$\((.+)\)", tokens[0])
                        if len(tokens) == 1
                        else None
                    )
                    if assignment:
                        command = shlex.split(assignment[2])
                        if command[:2] == ["git", "rev-parse"]:
                            self.assertTrue(
                                fetched, "resolve protected main after fetching it"
                            )
                            variables[assignment[1]] = command[-1]
                    for check in ("verify-tag", "verify-github-state"):
                        if check not in tokens:
                            continue
                        self.assertTrue(fetched)
                        argument = tokens[tokens.index("--expected-commit") + 1]
                        reference = variables.get(
                            argument.lstrip("$").strip("{}"), argument
                        )
                        self.assertIn(
                            reference,
                            {
                                "origin/main",
                                "origin/main^{commit}",
                                "refs/remotes/origin/main",
                                "refs/remotes/origin/main^{commit}",
                            },
                        )
                        validated.add(check)
                self.assertEqual({"verify-tag", "verify-github-state"}, validated)

    def test_release_jobs_have_only_required_github_permissions(self) -> None:
        self.assertEqual({"contents": "read"}, self.workflow["permissions"])
        for name, job in self.jobs.items():
            permissions = job.get("permissions", self.workflow["permissions"])
            self.assertIsInstance(permissions, dict)
            self.assertFalse(
                any(
                    value == "write" and (name != "release" or key != "contents")
                    for key, value in permissions.items()
                )
            )
        api_reads = {"actions": "read", "issues": "read", "pull-requests": "read"}
        self.assertEqual(
            {"contents": "read", **api_reads},
            self.jobs["distribution-build"]["permissions"],
        )
        self.assertEqual(
            {"contents": "write", **api_reads}, self.jobs["release"]["permissions"]
        )


if __name__ == "__main__":
    unittest.main()
