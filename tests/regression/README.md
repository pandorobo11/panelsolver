# Regression tests

Golden numerical results captured from the pinned legacy implementations belong
here. `test_legacy_fixture_integrity.py` verifies provenance, source hashes,
tolerance rules, comparator behavior, and pinned reference coefficients.
`test_legacy_runtime_goldens.py` runs every legacy case, including both ray
backends, through the current reader, adapter, execution, Summary CSV, and VTP
path. Focused geometry and canonical-signature regressions complement those
serialized results. The capture data and tolerance manifest are in
`tests/fixtures/phase1`.
