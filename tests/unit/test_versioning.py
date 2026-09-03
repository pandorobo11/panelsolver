from __future__ import annotations

import importlib.metadata
import tomllib
import unittest
from pathlib import Path

import panelsolver
from panelsolver.app.versioning import panelsolver_distribution_version

ROOT = Path(__file__).parents[2]


class VersioningTests(unittest.TestCase):
    def test_project_distribution_and_package_identity(self) -> None:
        with (ROOT / "pyproject.toml").open("rb") as stream:
            project = tomllib.load(stream)["project"]
        self.assertEqual("panelsolver", project["name"])
        self.assertEqual(
            {
                "Homepage": "https://github.com/pandorobo11/panelsolver",
                "Repository": "https://github.com/pandorobo11/panelsolver",
                "Issues": "https://github.com/pandorobo11/panelsolver/issues",
            },
            project["urls"],
        )
        self.assertEqual(
            "panelsolver",
            importlib.metadata.distribution("panelsolver").metadata["Name"],
        )
        self.assertEqual("panelsolver", panelsolver.__name__)

    def test_artifact_version_source_is_installed_distribution_metadata(self) -> None:
        self.assertEqual(
            importlib.metadata.version("panelsolver"),
            panelsolver_distribution_version(),
        )


if __name__ == "__main__":
    unittest.main()
