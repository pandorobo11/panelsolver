from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np

from panelsolver.core import (
    CommonCasePayload,
    ModelCasePayload,
    ResolvedShieldingConfig,
    build_case_signature,
    clear_mesh_cache,
    load_panel_mesh,
)
from panelsolver.models import HypersonicModel, SentmanModel

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "phase1"
GOLDEN_ROOT = FIXTURE_ROOT / "golden"
# Historical schema v1 digests: frozen evidence that current artifacts must
# never auto-match (ADR 0017).
HISTORICAL_V1_SIGNATURES = {
    "fmfsolver/fmf_bank_multicomponent": (
        "7efb199123f26e31f1ea99d605945a82a49432490527635eab2b511b50832af0"
    ),
    "fmfsolver/fmf_beta_sin_boundary": (
        "821f9c91bf72718200fc2ff47eee88f53a9f6e1d7b8ba42a3d0aed0c27caea0d"
    ),
    "fmfsolver/fmf_mode_b_offset": (
        "e1576a0ebfe1a530a09ba505850cb231e7f5d98b3bc29b1e01f54e597f05d848"
    ),
    "fmfsolver/fmf_shield_embree": (
        "5c131170d35fdb77af89eeab86336b6124c44683e125e7c18643aa2381ddc635"
    ),
    "fmfsolver/fmf_shield_rtree": (
        "9095648a49635e0b35097efaa48c5ff314c407f40ca6dff9af520914fda509f8"
    ),
    "fmfsolver/fmf_zero_plate": (
        "73eb1938a618dd3e588b00105be58c5c529990d3acb5018eb34c607fc9b641d5"
    ),
    "newtsolver/newt_bank_multicomponent": (
        "fc537d06b280e9f16c7ecf180268f4c4c1197f80964b968055b596f144a2f16a"
    ),
    "newtsolver/newt_beta_sin_boundary": (
        "117df0b8cf8db4b6c05dd94cb441aaf5f81e25d37ce1935cee9397c862b78855"
    ),
    "newtsolver/newt_modified_offset": (
        "a317db85d9468c94b8c541761fe6c7ce08ab9c36a20647f5b47dbf398ce78c67"
    ),
    "newtsolver/newt_prandtl_meyer": (
        "b2725ebd3ac8bf57164298cee6b310727d07ad355149ca73e86449f2709473af"
    ),
    "newtsolver/newt_shield_embree": (
        "cbdf8d8c951d3497caf254beb4d795abe39a875515337ac705ec649eab612f07"
    ),
    "newtsolver/newt_shield_rtree": (
        "020ca5999e65f0f60f1b0156ccd757b74a8f1a8e3baf4515ac4deff39d3579a0"
    ),
    "newtsolver/newt_tangent_cone": (
        "6cc06fc732e2a8f61eb9ed57952fcafa790ab9a1be44724cdc411586969f672d"
    ),
    "newtsolver/newt_tangent_wedge": (
        "c890d4dc834009dcdf55f5426304599a5f9428ad12814605cb320def5ade757b"
    ),
    "newtsolver/newt_zero_newtonian": (
        "8f40bb70e844d5cb1e9205a80c35fa586492fe68cb3ad67d2f14c8306d7f7461"
    ),
}

# Current schema v2 digests, captured from the unchanged implementation at
# be9e4da. ADR 0005 forbids silent field, normalization, or serialization
# changes; an intended change needs a schema-version increment and migration.
CURRENT_V2_SIGNATURES = {
    "fmfsolver/fmf_bank_multicomponent": (
        "58575f5181fa5e4739b779e8779c07fe80cc120dd2ce25f3288cdc7126879c12"
    ),
    "fmfsolver/fmf_beta_sin_boundary": (
        "582a9c1c8adeddba7510e845bedffa57cf639722a824a273bf1625ca5d8edf96"
    ),
    "fmfsolver/fmf_mode_b_offset": (
        "26c357efeac68e5e0facaf24d737ade784b0acaac5061cac65c16e7d58854019"
    ),
    "fmfsolver/fmf_shield_embree": (
        "a91bc9b9c8a868a8de8f6ace6c56cb8a8c119be9d0ddb3a5b46c668837ccb375"
    ),
    "fmfsolver/fmf_shield_rtree": (
        "b75d21aa802e168de14778b63eb28c1a8166db1f8e9b9db8a8ee72880f4b158a"
    ),
    "fmfsolver/fmf_zero_plate": (
        "162f9c2ec843cbef6114ed3e952de6ac505891d455fec76cb3467531e14f3d1b"
    ),
    "newtsolver/newt_bank_multicomponent": (
        "0bcf123e7b589512af95ed94ab9160556ab84c4400777760540109553d973cc7"
    ),
    "newtsolver/newt_beta_sin_boundary": (
        "3e0cb0d50c7df2d17b911928b7e2e7608c407f5ebdbdba9652a01d6ac7abf3b8"
    ),
    "newtsolver/newt_modified_offset": (
        "03abb65e1cd44c2e113a266011ee9a0b9541df1e43a23b838645062209352e78"
    ),
    "newtsolver/newt_prandtl_meyer": (
        "eb5a9e5f953fb7415b45c1031f49618ca7d6f5c5c764914f7dbbf7683c4606d8"
    ),
    "newtsolver/newt_shield_embree": (
        "07f590b15a324a8a97930efab9b956eb72ffb3d8b2f0bd898a004d2fc96bdb6a"
    ),
    "newtsolver/newt_shield_rtree": (
        "d1392dc9b974de699896ed12b0dd22e3bf62842544a418edf3130a839e173afb"
    ),
    "newtsolver/newt_tangent_cone": (
        "8138d75857da60d6ab3a0597184c3435d441f0669ba2c39bf4cfec66c4f37353"
    ),
    "newtsolver/newt_tangent_wedge": (
        "f07272255c77f216a078214a9bb5cf0cbb4b020687119680ddb4a467e6ade3a6"
    ),
    "newtsolver/newt_zero_newtonian": (
        "3af8c1f9077c01fe5f93956a54cc2fd0a8e042c110c7c9ae55dff7948bf1a9c0"
    ),
}


def _array(case: dict, name: str) -> np.ndarray:
    record = case["npz"]["arrays"][name]
    return np.asarray(record["values"]).reshape(record["shape"])


class CaseSignatureCompatibilityTests(unittest.TestCase):
    def test_current_signatures_are_frozen_and_never_match_v1(self) -> None:
        paths = sorted(GOLDEN_ROOT.glob("*/*.json"))
        paths = [path for path in paths if path.name != "contracts.json"]

        for path in paths:
            with self.subTest(solver=path.parent.name, case_id=path.stem):
                golden = json.loads(path.read_text(encoding="utf-8"))
                normalized = golden["normalized_input"]
                source_names = [
                    Path(value).name for value in str(normalized["stl_path"]).split(";")
                ]
                clear_mesh_cache()
                loaded = load_panel_mesh(
                    [FIXTURE_ROOT / "inputs" / "stl" / name for name in source_names],
                    normalized["stl_scale_m_per_unit"],
                )
                common_case = CommonCasePayload(
                    case_id=normalized["case_id"],
                    Aref_m2=normalized["Aref_m2"],
                    moment_reference_stl_m=[
                        normalized["ref_x_m"],
                        normalized["ref_y_m"],
                        normalized["ref_z_m"],
                    ],
                    Lref_Cl_m=normalized["Lref_Cl_m"],
                    Lref_Cm_m=normalized["Lref_Cm_m"],
                    Lref_Cn_m=normalized["Lref_Cn_m"],
                    alpha_stability_deg=float(_array(golden, "alpha_t_deg_resolved")),
                )
                if path.parent.name == "fmfsolver":
                    model = SentmanModel()
                else:
                    model = HypersonicModel()
                model_case = ModelCasePayload(model.model_id, normalized)
                effective_backend = golden["provenance"]["effective_backend"]
                shielding_enabled = bool(normalized["shielding_on"])
                shielding = ResolvedShieldingConfig(
                    enabled=shielding_enabled,
                    requested_backend=normalized["ray_backend"],
                    effective_backend=effective_backend,
                    batch_size=(64 if effective_backend == "embree" else 8)
                    if shielding_enabled
                    else 0,
                )
                signature = build_case_signature(
                    geometry_fingerprint=loaded.geometry_fingerprint,
                    common_case=common_case,
                    velocity_hat_stl=_array(golden, "Vhat_stl").reshape(3),
                    model_id=model.model_id,
                    model_algorithm_version=model.algorithm_version,
                    model_case_payload=model.signature_payload(model_case),
                    shielding_config=shielding,
                )
                signature_key = f"{path.parent.name}/{path.stem}"
                self.assertEqual(2, signature.envelope["schema"]["version"])
                self.assertEqual(
                    loaded.geometry_fingerprint,
                    signature.envelope["geometry"]["fingerprint_sha256"],
                )
                self.assertEqual(CURRENT_V2_SIGNATURES[signature_key], signature.digest)
                self.assertNotEqual(
                    HISTORICAL_V1_SIGNATURES[signature_key], signature.digest
                )


if __name__ == "__main__":
    unittest.main()
