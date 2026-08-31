from __future__ import annotations

import pickle
import unittest

from panelsolver.core import (
    CommonCasePayload,
    ResolvedShieldingConfig,
    SignatureError,
    build_case_signature,
    match_case_signature,
)


def _common_case(**updates) -> CommonCasePayload:
    values = {
        "case_id": "case-a",
        "Aref_m2": 2.0,
        "moment_reference_stl_m": [0.1, 0.2, 0.3],
        "Lref_Cl_m": 1.0,
        "Lref_Cm_m": 2.0,
        "Lref_Cn_m": 3.0,
        "alpha_t_deg": 10.0,
        "beta_t_deg": -2.0,
    }
    values.update(updates)
    return CommonCasePayload(**values)


def _shielding(**updates) -> ResolvedShieldingConfig:
    values = {
        "enabled": True,
        "requested_backend": "auto",
        "effective_backend": "embree",
        "batch_size": 64,
    }
    values.update(updates)
    return ResolvedShieldingConfig(**values)


def _signature(**updates):
    values = {
        "geometry_fingerprint": "a" * 64,
        "common_case": _common_case(),
        "model_id": "sentman",
        "model_algorithm_version": "sentman-v1",
        "model_case_payload": {"S": 5.0, "nested": {"x": [1, 2]}},
        "shielding_config": _shielding(),
    }
    values.update(updates)
    return build_case_signature(**values)


class SignatureTests(unittest.TestCase):
    def test_canonical_payload_is_mapping_order_and_pickle_stable(self) -> None:
        first = _signature(
            model_case_payload={"S": 5.0, "nested": {"x": [1, 2]}},
        )
        second = _signature(
            model_case_payload={"nested": {"x": (1, 2)}, "S": 5.0},
        )
        restored = pickle.loads(pickle.dumps(first))

        self.assertEqual(first.digest, second.digest)
        self.assertEqual(first.canonical_payload, second.canonical_payload)
        self.assertEqual(first.digest, restored.digest)
        self.assertEqual(first.canonical_payload, restored.canonical_payload)
        self.assertNotIn("solver_version", first.canonical_payload)
        self.assertNotIn("application_version", first.canonical_payload)

    def test_every_numerical_identity_field_changes_the_digest(self) -> None:
        baseline = _signature().digest
        variants = (
            _signature(geometry_fingerprint="b" * 64),
            _signature(common_case=_common_case(Aref_m2=3.0)),
            _signature(model_id="hypersonic"),
            _signature(model_algorithm_version="sentman-v2"),
            _signature(model_case_payload={"S": 6.0}),
            _signature(
                shielding_config=_shielding(
                    enabled=False,
                    effective_backend="not_used",
                    batch_size=0,
                )
            ),
            _signature(shielding_config=_shielding(requested_backend="rtree")),
            _signature(shielding_config=_shielding(effective_backend="rtree")),
            _signature(shielding_config=_shielding(batch_size=8)),
            _signature(shielding_config=_shielding(algorithm_version="shielding-v2")),
        )
        self.assertTrue(all(item.digest != baseline for item in variants))

    def test_rejects_nonfinite_unsupported_and_invalid_identity(self) -> None:
        invalid_payloads = (
            {"value": float("nan")},
            {"value": float("inf")},
            {"value": object()},
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(SignatureError):
                    _signature(model_case_payload=payload)
        with self.assertRaises(SignatureError):
            _signature(geometry_fingerprint="not-a-digest")
        with self.assertRaises(SignatureError):
            _signature(model_algorithm_version=" version ")

    def test_artifact_matching_accepts_only_the_current_signature(self) -> None:
        current = _signature()
        self.assertTrue(match_case_signature(current.digest, current))
        self.assertFalse(match_case_signature("<invalid-stored>", current))
        self.assertFalse(match_case_signature("0" * 64, current))
        with self.assertRaises(TypeError):
            match_case_signature(current.digest, object())


if __name__ == "__main__":
    unittest.main()
