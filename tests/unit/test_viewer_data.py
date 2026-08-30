import hashlib
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pyvista as pv

from panelsolver.app import (
    ArtifactLoadMode,
    ArtifactSignatureCandidates,
    ArtifactViewState,
    ArtifactViewStatus,
    artifact_display_allowed,
    automatic_artifact_view_state,
    discover_scalar_fields,
    field_data_scalar,
    manual_artifact_view_state,
    match_artifact_case,
    resolve_matching_case_row,
    scalar_color_limits,
)
from panelsolver.core import (
    CaseSignature,
    SignatureMatchKind,
    canonical_json,
)


def _signature(label: str) -> CaseSignature:
    envelope = {"fixture": label}
    payload = canonical_json(envelope)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return CaseSignature(digest, payload, envelope)


def _artifact(case_id: object, signature: object, **cell_data):
    return SimpleNamespace(
        field_data={"case_id": [case_id], "case_signature": [signature]},
        cell_data=cell_data,
    )


class ArtifactMatchingTests(unittest.TestCase):
    def test_primary_precedes_legacy_and_case_id_is_also_required(self) -> None:
        primary = _signature("primary")
        legacy = _signature("legacy").digest
        candidates = ArtifactSignatureCandidates(primary, (legacy,))
        primary_match = match_artifact_case(
            _artifact("case", primary.digest),
            {"case_id": "case"},
            candidates,
        )
        self.assertTrue(primary_match.matched)
        self.assertEqual(SignatureMatchKind.PRIMARY, primary_match.signature.kind)

        legacy_match = match_artifact_case(
            _artifact("case", legacy),
            {"case_id": "case"},
            candidates,
        )
        self.assertTrue(legacy_match.matched)
        self.assertEqual(SignatureMatchKind.LEGACY, legacy_match.signature.kind)
        self.assertEqual(0, legacy_match.signature.legacy_index)

        wrong_id = match_artifact_case(
            _artifact("other", primary.digest),
            {"case_id": "case"},
            candidates,
        )
        self.assertFalse(wrong_id.matched)
        self.assertTrue(wrong_id.signature.matched)

    def test_legacy_solver_version_metadata_does_not_control_matching(self) -> None:
        primary = _signature("primary")
        candidates = ArtifactSignatureCandidates(primary)
        for legacy_version in ("1.3.8", "1.0.3"):
            with self.subTest(legacy_version=legacy_version):
                artifact = SimpleNamespace(
                    field_data={
                        "case_id": ["case"],
                        "case_signature": [primary.digest],
                        "solver_version": [legacy_version],
                    }
                )
                self.assertTrue(
                    match_artifact_case(
                        artifact,
                        {"case_id": "case"},
                        candidates,
                    ).matched
                )

    def test_missing_corrupt_or_multivalued_field_data_never_auto_matches(self) -> None:
        primary = _signature("primary")
        candidates = ArtifactSignatureCandidates(primary)
        artifacts = (
            SimpleNamespace(),
            SimpleNamespace(field_data=[]),
            SimpleNamespace(field_data={"case_id": [], "case_signature": []}),
            SimpleNamespace(
                field_data={
                    "case_id": ["case", "other"],
                    "case_signature": [primary.digest],
                }
            ),
        )
        for artifact in artifacts:
            with self.subTest(artifact=artifact):
                match = match_artifact_case(artifact, {"case_id": "case"}, candidates)
                self.assertFalse(match.matched)
                self.assertFalse(
                    artifact_display_allowed(match, ArtifactLoadMode.AUTOMATIC)
                )
        self.assertIsNone(field_data_scalar(SimpleNamespace(), "case_id"))

    def test_real_pyvista_dataset_attributes_are_supported_without_qt(self) -> None:
        primary = _signature("pyvista")
        poly = pv.Plane(i_resolution=1, j_resolution=1)
        poly.field_data["case_id"] = ["case"]
        poly.field_data["case_signature"] = [primary.digest]
        poly.cell_data["model_extra"] = np.array([2.5])
        match = match_artifact_case(
            poly,
            {"case_id": "case"},
            ArtifactSignatureCandidates(primary),
        )
        self.assertTrue(match.matched)
        self.assertEqual("case", field_data_scalar(poly, "case_id"))
        fields = discover_scalar_fields(poly.cell_data, n_cells=poly.n_cells)
        self.assertEqual(("model_extra",), tuple(field.name for field in fields))

    def test_manual_inspection_is_allowed_without_a_matching_row(self) -> None:
        self.assertTrue(artifact_display_allowed(None, ArtifactLoadMode.MANUAL))
        self.assertFalse(artifact_display_allowed(None, ArtifactLoadMode.AUTOMATIC))
        with self.assertRaises(TypeError):
            artifact_display_allowed(None, "manual")

    def test_duplicate_case_ids_resolve_by_signature_in_input_order(self) -> None:
        first = {"case_id": "duplicate", "variant": "first"}
        second = {"case_id": "duplicate", "variant": "second"}
        signatures = {
            "first": ArtifactSignatureCandidates(_signature("first")),
            "second": ArtifactSignatureCandidates(_signature("second")),
        }
        artifact = _artifact("duplicate", signatures["second"].primary.digest)
        resolved = resolve_matching_case_row(
            artifact,
            (first, second),
            lambda row: signatures[str(row["variant"])],
        )
        self.assertIs(second, resolved)
        stale = _artifact("duplicate", _signature("stale").digest)
        self.assertIsNone(
            resolve_matching_case_row(
                stale,
                (first, second),
                lambda row: signatures[str(row["variant"])],
            )
        )

    def test_candidates_validate_primary_and_opaque_legacy_digests(self) -> None:
        with self.assertRaises(TypeError):
            ArtifactSignatureCandidates(object())
        with self.assertRaises(ValueError):
            ArtifactSignatureCandidates(_signature("primary"), ("not-a-digest",))


class ArtifactViewStateTests(unittest.TestCase):
    def test_state_is_immutable_and_validates_required_context(self) -> None:
        state = ArtifactViewState(
            ArtifactViewStatus.MISSING,
            Path("outputs/case.vtp"),
            " case ",
        )
        self.assertEqual("case", state.case_id)
        self.assertTrue(state.path.is_absolute())
        with self.assertRaises(FrozenInstanceError):
            state.status = ArtifactViewStatus.CURRENT
        with self.assertRaises(TypeError):
            ArtifactViewState("missing", "/tmp/case.vtp", "case")
        with self.assertRaises(ValueError):
            ArtifactViewState(ArtifactViewStatus.EMPTY, "/tmp/case.vtp")
        with self.assertRaises(ValueError):
            ArtifactViewState(ArtifactViewStatus.CURRENT, "/tmp/case.vtp")

    def test_automatic_classification_preserves_primary_and_legacy_matches(
        self,
    ) -> None:
        primary = _signature("primary")
        legacy = _signature("legacy").digest
        candidates = ArtifactSignatureCandidates(primary, (legacy,))
        for signature in (primary.digest, legacy):
            with self.subTest(signature=signature):
                state = automatic_artifact_view_state(
                    _artifact("case", signature),
                    {"case_id": "case"},
                    candidates,
                    "/tmp/case.vtp",
                )
                self.assertEqual(ArtifactViewStatus.CURRENT, state.status)
                self.assertEqual("case", state.case_id)

    def test_stale_requires_matching_id_and_valid_nonmatching_digest(self) -> None:
        primary = _signature("primary")
        candidates = ArtifactSignatureCandidates(primary)
        stale = automatic_artifact_view_state(
            _artifact("case", _signature("stale").digest),
            {"case_id": "case"},
            candidates,
            "/tmp/case.vtp",
        )
        self.assertEqual(ArtifactViewStatus.STALE, stale.status)

        mismatches = (
            _artifact("other", _signature("stale").digest),
            SimpleNamespace(field_data={"case_id": ["case"]}),
            _artifact("case", "corrupt-signature"),
            SimpleNamespace(
                field_data={
                    "case_id": ["case"],
                    "case_signature": [primary.digest, primary.digest],
                }
            ),
        )
        for artifact in mismatches:
            with self.subTest(artifact=artifact):
                state = automatic_artifact_view_state(
                    artifact,
                    {"case_id": "case"},
                    candidates,
                    "/tmp/case.vtp",
                )
                self.assertEqual(ArtifactViewStatus.MISMATCHED, state.status)

    def test_manual_state_reports_strict_resolution_without_denial(self) -> None:
        matched = manual_artifact_view_state(
            "/tmp/matched.vtp",
            {"case_id": "case"},
        )
        unmatched = manual_artifact_view_state("/tmp/unmatched.vtp", None)
        self.assertEqual(ArtifactViewStatus.MANUAL_MATCHED, matched.status)
        self.assertEqual("case", matched.case_id)
        self.assertEqual(ArtifactViewStatus.MANUAL_UNMATCHED, unmatched.status)
        self.assertIsNone(unmatched.case_id)


class ScalarDiscoveryTests(unittest.TestCase):
    def test_preferred_available_fields_precede_dynamic_artifact_order(self) -> None:
        fields = discover_scalar_fields(
            {
                "model_extra": np.array([1.0, 2.0]),
                "stl_index": np.array([0, 1], dtype=np.int32),
                "cp": np.array([0.1, 0.2]),
                "shielded": np.array([False, True]),
            },
            n_cells=2,
            preferred=("cp", "missing", "shielded"),
        )
        self.assertEqual(
            ("cp", "shielded", "model_extra", "stl_index"),
            tuple(field.name for field in fields),
        )
        self.assertFalse(fields[0].categorical)
        self.assertTrue(fields[1].categorical)
        self.assertEqual(np.dtype(np.int32), fields[-1].dtype)

    def test_excludes_vectors_strings_shape_mismatches_nonfinite_and_empty(
        self,
    ) -> None:
        fields = discover_scalar_fields(
            {
                "valid": [1, 2],
                "vector": [[1, 2, 3], [4, 5, 6]],
                "string": ["a", "b"],
                "short": [1],
                "nonfinite": [1.0, np.inf],
                "empty": [],
            },
            n_cells=2,
        )
        self.assertEqual(("valid",), tuple(field.name for field in fields))
        with self.assertRaises(ValueError):
            discover_scalar_fields({}, n_cells=0)
        with self.assertRaises(ValueError):
            discover_scalar_fields({}, n_cells=1, preferred=("cp", "cp"))

    def test_color_limits_keep_categorical_zero_one_and_numeric_extrema(self) -> None:
        categorical, numeric = discover_scalar_fields(
            {"shielded": [0, 1], "temperature": [-2.0, 5.0]},
            n_cells=2,
        )
        self.assertEqual((0.0, 1.0), scalar_color_limits(categorical, [1, 1]))
        self.assertEqual((-2.0, 5.0), scalar_color_limits(numeric, [-2.0, 5.0]))
        with self.assertRaises(ValueError):
            scalar_color_limits(numeric, [1.0, np.nan])


if __name__ == "__main__":
    unittest.main()
