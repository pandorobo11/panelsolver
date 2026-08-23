from __future__ import annotations

import importlib.metadata
import pkgutil
import unittest
from pathlib import Path
from unittest.mock import patch

import fmfsolver
import newtsolver
import panelsolver._compat
from fmfsolver._frontend import (
    _build_artifact_signatures as build_fmf_artifact_signatures,
)
from fmfsolver._frontend import _legacy_gui_spec as legacy_fmf_gui_spec
from newtsolver._frontend import (
    _build_artifact_signatures as build_hypersonic_artifact_signatures,
)
from newtsolver._frontend import _legacy_gui_spec as legacy_hypersonic_gui_spec
from panelsolver.domains import fmf, hypersonic
from tests.current_case_fixtures import read_current_cases

INPUTS = Path(__file__).parents[1] / "fixtures" / "phase1" / "inputs"


def _module_inventory(package) -> set[str]:
    return {
        package.__name__,
        *(
            module.name
            for module in pkgutil.walk_packages(
                package.__path__,
                prefix=f"{package.__name__}.",
            )
        ),
    }


class LegacyCommandFrontendTests(unittest.TestCase):
    def test_legacy_packages_contain_only_command_frontend_plumbing(self) -> None:
        expected = {
            "fmfsolver": {
                "fmfsolver",
                "fmfsolver._frontend",
                "fmfsolver.app",
                "fmfsolver.app.cli_app",
                "fmfsolver.app.gui_app",
            },
            "newtsolver": {
                "newtsolver",
                "newtsolver._frontend",
                "newtsolver.app",
                "newtsolver.app.cli_app",
                "newtsolver.app.gui_app",
            },
        }
        self.assertEqual(expected["fmfsolver"], _module_inventory(fmfsolver))
        self.assertEqual(expected["newtsolver"], _module_inventory(newtsolver))
        for package in (fmfsolver, newtsolver):
            self.assertFalse(hasattr(package, "__version__"))
            self.assertFalse(hasattr(package, "__all__"))

    def test_private_compat_keeps_only_signature_recognition(self) -> None:
        self.assertEqual(
            {
                "panelsolver._compat",
                "panelsolver._compat.legacy_signatures",
                "panelsolver._compat.versions",
            },
            _module_inventory(panelsolver._compat),
        )

    def test_legacy_gui_identity_and_artifact_fallback_are_preserved(self) -> None:
        products = (
            (
                legacy_fmf_gui_spec(),
                "fmfsolver",
                "sentman",
                "Sentman FMF Solver (GUI)",
                fmf,
                "fmfsolver_cases.csv",
                build_fmf_artifact_signatures,
            ),
            (
                legacy_hypersonic_gui_spec(),
                "newtsolver",
                "hypersonic",
                "newtsolver (GUI)",
                hypersonic,
                "newtsolver_cases.csv",
                build_hypersonic_artifact_signatures,
            ),
        )
        for spec, product_id, model_id, title, domain, filename, builder in products:
            with self.subTest(product_id=product_id):
                self.assertEqual(product_id, spec.product_id)
                self.assertEqual(model_id, spec.model_id)
                self.assertEqual(title, spec.window_title)
                row = read_current_cases(domain.read_cases, INPUTS / filename).iloc[
                    0
                ].to_dict()
                candidates = builder(row)
                self.assertEqual(
                    domain.build_primary_signatures(row).primary,
                    candidates.primary,
                )
                self.assertGreaterEqual(len(candidates.legacy_signatures), 1)

    def test_all_four_legacy_gui_commands_dispatch_with_legacy_identity(self) -> None:
        entry_points = {
            entry.name: entry
            for entry in importlib.metadata.distribution("panelsolver").entry_points
            if entry.group == "console_scripts"
        }
        expected = {
            "fmfsolver": ("fmfsolver", "Sentman FMF Solver (GUI)"),
            "fmfsolver-gui": ("fmfsolver", "Sentman FMF Solver (GUI)"),
            "newtsolver": ("newtsolver", "newtsolver (GUI)"),
            "newtsolver-gui": ("newtsolver", "newtsolver (GUI)"),
        }
        observed: list[tuple[str, str]] = []

        def capture(spec) -> int:
            observed.append((spec.product_id, spec.window_title))
            return 0

        with patch("panelsolver.app.gui_bootstrap.run_gui", side_effect=capture):
            for name in expected:
                with self.subTest(command=name), self.assertRaises(SystemExit) as caught:
                    entry_points[name].load()()
                self.assertEqual(0, caught.exception.code)
        self.assertEqual(list(expected.values()), observed)


if __name__ == "__main__":
    unittest.main()
