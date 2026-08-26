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
EXPECTED_SIGNATURES = {
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


def _array(case: dict, name: str) -> np.ndarray:
    record = case["npz"]["arrays"][name]
    return np.asarray(record["values"]).reshape(record["shape"])


class CaseSignatureCompatibilityTests(unittest.TestCase):
    def test_current_signatures_match_the_compatibility_inventory(self) -> None:
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
                    alpha_t_deg=float(_array(golden, "alpha_t_deg_resolved")),
                    beta_t_deg=float(_array(golden, "beta_t_deg_resolved")),
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
                    model_id=model.model_id,
                    model_algorithm_version=model.algorithm_version,
                    model_case_payload=model.signature_payload(model_case),
                    shielding_config=shielding,
                )
                signature_key = f"{path.parent.name}/{path.stem}"
                self.assertEqual(
                    EXPECTED_SIGNATURES[signature_key],
                    signature.digest,
                )


if __name__ == "__main__":
    unittest.main()
