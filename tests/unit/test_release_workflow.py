import json
import os
import re
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


class ReleaseWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def job(self, name: str) -> str:
        match = re.search(
            rf"^  {re.escape(name)}:\n(?P<body>.*?)(?=^  [a-z][a-z0-9_-]*:\n|\Z)",
            self.workflow,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match, f"workflow job {name!r} is missing")
        return match.group("body")

    def job_names(self) -> list[str]:
        return re.findall(
            r"^  ([a-z][a-z0-9_-]*):$",
            self.workflow.split("jobs:\n", 1)[1],
            re.MULTILINE,
        )

    def needs(self, name: str) -> set[str]:
        match = re.search(r"^    needs: \[(.*?)\]$", self.job(name), re.MULTILINE)
        return {item.strip() for item in match.group(1).split(",")} if match else set()

    def test_pr_triggers_and_concurrency_leave_main_and_tags_independent(self) -> None:
        triggers = self.workflow.split("permissions:", 1)[0]
        self.assertRegex(triggers, r"push:\s+branches: \[main\]\s+tags: \[\"v\*\"\]")
        self.assertIn("  pull_request:", triggers)
        self.assertIn(
            "github.event_name == 'pull_request' && format('pr-{0}', github.event.pull_request.number)",
            triggers,
        )
        self.assertIn("|| format('run-{0}', github.run_id)", triggers)
        self.assertIn(
            "cancel-in-progress: ${{ github.event_name == 'pull_request' }}", triggers
        )

    def test_source_tests_start_independently_and_keep_full_platform_coverage(
        self,
    ) -> None:
        source = self.job("test")
        self.assertFalse(self.needs("test"))
        for platform in ("ubuntu-latest", "windows-latest", "macos-15"):
            self.assertIn(f"- {platform}", source)
        self.assertIn("fail-fast: false", source)
        self.assertIn("uv sync --locked --extra rayaccel --group docs", source)
        self.assertIn("if not ray.has_embree else None", source)
        self.assertRegex(source, r"run: uv run --no-sync pytest --durations=30\s*\n")
        self.assertIn("scripts/probe_scheduler_lifecycle.py", source)
        self.assertIn("--iterations 10 --timeout-seconds 90", source)
        for distribution_step in (
            "download-artifact",
            "reinstall-wheel",
            "smoke_installed_wheel.py",
        ):
            self.assertNotIn(distribution_step, source)

    def test_build_job_is_the_only_distribution_producer(self) -> None:
        producers = [name for name in self.job_names() if "uv build" in self.job(name)]
        self.assertEqual(["distribution-build"], producers)
        self.assertEqual(1, self.workflow.count("run: uv build"))

    def test_build_job_verifies_and_uploads_manifested_distributions(self) -> None:
        artifact_job = self.job("distribution-build")
        for check in (
            "verify-distributions",
            "create-release-archives",
            "dry-run",
            "generate_us1976_sentman_table.py --check",
            "generate_docs_angle_response_plots.py --check",
            "mkdocs build --strict",
        ):
            self.assertIn(check, artifact_job)
        self.assertNotIn("smoke_installed_wheel.py", artifact_job)
        self.assertNotIn("reinstall-wheel", artifact_job)
        self.assertIn("create-manifest", artifact_job)
        self.assertIn("verify-manifest", artifact_job)
        self.assertIn("actions/upload-artifact@v4", artifact_job)

    def test_clean_install_uses_the_built_wheel_in_an_empty_environment(self) -> None:
        clean_install = self.job("clean-install")
        self.assertIn("runs-on: ubuntu-latest", clean_install)
        self.assertTrue({"distribution-build", "quality"} <= self.needs("clean-install"))
        self.assertIn("verify-wheel", clean_install)
        self.assertIn("uv venv", clean_install)
        self.assertIn("uv pip install", clean_install)
        self.assertIn('--python "${CLEAN_VENV}/bin/python"', clean_install)
        self.assertIn('"${WHEEL}[rayaccel]"', clean_install)
        self.assertRegex(
            clean_install,
            r'"\$\{CLEAN_VENV\}/bin/python"\s*\\?\s*'
            r'"\$\{GITHUB_WORKSPACE\}/scripts/smoke_installed_wheel\.py"',
        )
        self.assertNotIn("uv sync", clean_install)

    def test_all_consumers_verify_and_reuse_the_uploaded_exact_set(self) -> None:
        for job_name in ("installed-wheel", "clean-install", "release"):
            with self.subTest(job=job_name):
                job = self.job(job_name)
                self.assertIn("actions/download-artifact@v4", job)
                self.assertIn("verify-manifest", job)
                self.assertIn("panelsolver-dist-${{ github.run_id }}", job)
                self.assertIn('--expected-commit "${{ github.sha }}"', job)
                self.assertNotIn("uv build", job)
                self.assertNotIn("mkdocs build", job)
                self.assertNotIn("create-release-archives", job)
        self.assertEqual(
            1, self.job("distribution-build").count("create-release-archives")
        )
        self.assertNotIn("create-release-archives", self.job("release"))

    def test_one_installed_wheel_smoke_owner_per_platform(self) -> None:
        wheel = self.job("installed-wheel")
        self.assertTrue({"distribution-build", "quality"} <= self.needs("installed-wheel"))
        for platform in ("windows-latest", "macos-15"):
            self.assertIn(f"- {platform}", wheel)
        self.assertNotIn("ubuntu-latest", wheel)
        self.assertIn("fail-fast: false", wheel)
        self.assertIn("uv sync --locked --extra rayaccel --group docs", wheel)
        self.assertIn("reinstall-wheel .", wheel)
        self.assertIn(
            "scripts/smoke_installed_wheel.py .\n          --dist-dir dist", wheel
        )
        self.assertIn(
            '--dist-dir "${GITHUB_WORKSPACE}/dist"', self.job("clean-install")
        )
        owners = {
            name
            for name in self.job_names()
            if "smoke_installed_wheel.py" in self.job(name)
        }
        self.assertEqual({"installed-wheel", "clean-install"}, owners)
        for name in owners:
            self.assertEqual(1, self.job(name).count("smoke_installed_wheel.py"))

    def test_required_artifact_gate_fails_closed_for_every_prerequisite(self) -> None:
        gate = self.job("artifact")
        prerequisites = self.needs("artifact")
        self.assertTrue(
            {"quality", "distribution-build", "installed-wheel", "clean-install"}
            <= prerequisites
        )
        self.assertIn("if: ${{ always() }}", gate)
        self.assertIn("NEEDS_RESULTS: ${{ toJSON(needs) }}", gate)
        # Execute the real gate body for every non-success result, including skips
        # caused by a failed build. This tests failure behavior, not a YAML snapshot.
        code = textwrap.dedent(
            gate.split("python - <<'PY'\n", 1)[1].split("          PY", 1)[0]
        )
        success = {name: {"result": "success"} for name in prerequisites}
        cases = [("all succeeded", success, True), ("empty", {}, False)]
        for name in prerequisites:
            for result in ("failure", "cancelled", "skipped"):
                cases.append(
                    (f"{name}: {result}", {**success, name: {"result": result}}, False)
                )
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

    def test_release_requires_source_and_distribution_success(self) -> None:
        release = self.job("release")
        self.assertTrue({"test", "artifact"} <= self.needs("release"))
        self.assertNotIn("always()", release)
        self.assertIn("if: startsWith(github.ref, 'refs/tags/v')", release)
        self.assertIn("verify-manifest", release)

    def test_tag_validation_uses_fetched_protected_main(self) -> None:
        for job_name in ("distribution-build", "release"):
            with self.subTest(job=job_name):
                job = self.job(job_name)
                self.assertIn("git fetch origin main --tags --force", job)
                self.assertIn("refs/remotes/origin/main^{commit}", job)
                self.assertNotIn('EXPECTED_COMMIT="$(git rev-parse HEAD', job)
                self.assertIn("verify-github-state", job)
                self.assertIn("--expected-commit", job)

    def test_tag_validation_jobs_have_minimum_github_api_permissions(self) -> None:
        artifact_job = self.job("distribution-build")
        release_job = self.job("release")
        for job_name, job in (
            ("distribution-build", artifact_job),
            ("release", release_job),
        ):
            with self.subTest(job=job_name):
                self.assertIn("actions: read", job)
                self.assertIn("issues: read", job)
                self.assertIn("pull-requests: read", job)
                self.assertNotIn("write-all", job)
        self.assertIn("contents: read", artifact_job)
        self.assertNotIn("contents: write", artifact_job)
        self.assertIn("contents: write", release_job)
        self.assertEqual(1, self.workflow.count("contents: write"))
        self.assertNotIn("write-all", self.workflow)
        self.assertNotIn("actions: write", self.workflow)
        self.assertNotIn("issues: write", self.workflow)
        self.assertNotIn("pull-requests: write", self.workflow)


if __name__ == "__main__":
    unittest.main()