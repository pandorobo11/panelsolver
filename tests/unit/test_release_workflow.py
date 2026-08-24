import re
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

    def test_artifact_job_is_the_only_distribution_producer(self) -> None:
        artifact_job = self.job("artifact")
        producers = [
            name
            for name in ("test", "artifact", "clean-install", "release")
            if "uv build" in self.job(name)
        ]
        self.assertEqual(["artifact"], producers)
        self.assertIn("create-manifest", artifact_job)
        self.assertIn("actions/upload-artifact@v4", artifact_job)

    def test_all_consumers_verify_and_reuse_the_uploaded_exact_set(self) -> None:
        for job_name in ("test", "clean-install", "release"):
            with self.subTest(job=job_name):
                job = self.job(job_name)
                self.assertIn("actions/download-artifact@v4", job)
                self.assertIn("verify-manifest", job)
                self.assertIn("panelsolver-dist-${{ github.run_id }}", job)
        self.assertEqual(1, self.job("artifact").count("create-release-archives"))
        self.assertNotIn("create-release-archives", self.job("release"))

    def test_release_requires_test_artifact_and_clean_install_success(self) -> None:
        release = self.job("release")
        self.assertIn("needs: [test, artifact, clean-install]", release)
        self.assertIn("if: startsWith(github.ref, 'refs/tags/v')", release)
        self.assertIn("verify-manifest", release)

    def test_tag_validation_uses_fetched_protected_main(self) -> None:
        for job_name in ("artifact", "release"):
            with self.subTest(job=job_name):
                job = self.job(job_name)
                self.assertIn("git fetch origin main --tags --force", job)
                self.assertIn("refs/remotes/origin/main^{commit}", job)
                self.assertNotIn('EXPECTED_COMMIT="$(git rev-parse HEAD', job)
                self.assertIn("verify-github-state", job)
                self.assertIn("--expected-commit", job)

    def test_tag_validation_jobs_have_minimum_github_api_permissions(self) -> None:
        artifact_job = self.job("artifact")
        release_job = self.job("release")
        for job_name, job in (("artifact", artifact_job), ("release", release_job)):
            with self.subTest(job=job_name):
                self.assertIn("actions: read", job)
                self.assertIn("issues: read", job)
                self.assertIn("pull-requests: read", job)
                self.assertNotIn("write-all", job)
        self.assertIn("contents: read", artifact_job)
        self.assertNotIn("contents: write", artifact_job)
        self.assertIn("contents: write", release_job)
        self.assertNotIn("actions: write", self.workflow)
        self.assertNotIn("issues: write", self.workflow)
        self.assertNotIn("pull-requests: write", self.workflow)

if __name__ == "__main__":
    unittest.main()
