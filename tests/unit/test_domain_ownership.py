from __future__ import annotations

import subprocess
import sys
import unittest
from importlib.metadata import version
from pathlib import Path

import pytest

from fmfsolver.app.cli_app import _CLI_POLICY as LEGACY_FMF_CLI_POLICY
from newtsolver.app.cli_app import _CLI_POLICY as LEGACY_HYPERSONIC_CLI_POLICY
from panelsolver.domains import fmf, hypersonic

REPOSITORY_ROOT = Path(__file__).parents[2]
INSTALLED_VERSION = version("panelsolver")


class DomainOwnershipTests(unittest.TestCase):
    def test_canonical_runtime_policies_use_domain_product_ids(self) -> None:
        self.assertEqual("fmf", fmf.CASE_POLICY.product_id)
        self.assertEqual("fmf", fmf.RUNTIME_POLICY.product_id)
        self.assertEqual("hypersonic", hypersonic.CASE_POLICY.product_id)
        self.assertEqual("hypersonic", hypersonic.RUNTIME_POLICY.product_id)

    def test_legacy_cli_frontends_delegate_to_canonical_domain_objects(self) -> None:
        self.assertIs(
            fmf.RUNTIME_POLICY,
            LEGACY_FMF_CLI_POLICY.runtime_policy,
        )
        self.assertIs(
            hypersonic.RUNTIME_POLICY,
            LEGACY_HYPERSONIC_CLI_POLICY.runtime_policy,
        )

    @pytest.mark.slow
    def test_canonical_domain_execution_does_not_load_legacy_or_compat(self) -> None:
        code = f"""
import sys
import tempfile
from pathlib import Path
from panelsolver.domains import fmf, hypersonic
from tests.current_case_fixtures import read_current_cases

inputs = Path({str(REPOSITORY_ROOT)!r}) / 'tests' / 'fixtures' / 'phase1' / 'inputs'
with tempfile.TemporaryDirectory() as temp_dir:
    for domain, filename in (
        (fmf, 'fmfsolver_cases.csv'),
        (hypersonic, 'newtsolver_cases.csv'),
    ):
        row = read_current_cases(domain.read_cases, inputs / filename).iloc[0].to_dict()
        row.update(out_dir=temp_dir, save_vtp_on=0, shielding_on=0, ray_backend='rtree')
        result = domain.run_cases((row,))
        assert len(result.cases) == 1
        assert result.cases[0].csv.rows[0]['solver_version'] == {INSTALLED_VERSION!r}
        candidates = domain.build_primary_signatures(row)
        assert candidates.legacy_signatures == ()

loaded = sorted(
    name for name in sys.modules
    if name.startswith(('fmfsolver', 'newtsolver', 'panelsolver._compat'))
)
assert loaded == [], loaded
"""
        subprocess.run([sys.executable, "-c", code], check=True)


if __name__ == "__main__":
    unittest.main()
