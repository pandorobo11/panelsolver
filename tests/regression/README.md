# Regression tests

Golden numerical results captured from the pinned legacy implementations belong
here. `test_legacy_fixture_integrity.py` verifies provenance, hashes, manifest
coverage, tolerances, comparator behavior, and internal fixture relations.
`test_legacy_runtime_goldens.py` runs every legacy case through the current
reader, adapter, execution, Summary CSV, and VTP path. External geometry/ray
backends and signature compatibility retain focused regressions. The capture
data and tolerance manifest are in `tests/fixtures/phase1`.
