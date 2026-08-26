import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pyvista as pv

from panelsolver.app.artifact_io import write_vtp_projection
from panelsolver.core import (
    ArtifactProjectionPolicy,
    CommonCasePayload,
    ContractValueError,
    LocalLoads,
    MeshComponent,
    ModelCasePayload,
    PanelFlowState,
    PanelGeometry,
    PanelMesh,
    assemble_common_results,
    load_panel_mesh,
    project_vtp_artifact,
)

FIXTURE_STL = (
    Path(__file__).parents[1] / "fixtures" / "phase1" / "inputs" / "stl" / "plate.stl"
)


def fixture(
    *,
    source: str = "plate.stl",
    case_id: str = "artifact",
) -> tuple[PanelMesh, object]:
    geometry = PanelGeometry(
        centers_stl_m=[[0.25, 0.25, 0], [0.75, 0.75, 0]],
        normals_out_stl=[[0, 0, 1], [0, 0, 1]],
        areas_m2=[0.5, 0.5],
        component_ids=[0, 0],
    )
    flow = PanelFlowState([1, 0, 0], [False, False])
    loads = LocalLoads(
        [[2, 0, 0], [2, 0, 0]],
        {"cp": [2, 2], "theta_deg": [0, 0]},
    )
    case = CommonCasePayload(
        case_id=case_id,
        Aref_m2=1.0,
        moment_reference_stl_m=[0, 0, 0],
        Lref_Cl_m=1.0,
        Lref_Cm_m=1.0,
        Lref_Cn_m=1.0,
        alpha_t_deg=0.0,
        beta_t_deg=0.0,
    )
    mesh = PanelMesh(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]],
        [[0, 1, 2], [1, 3, 2]],
        geometry,
        [MeshComponent(0, source)],
    )
    results = assemble_common_results(
        case,
        ModelCasePayload("synthetic"),
        geometry,
        flow,
        loads,
    )
    return mesh, results


def results_for_mesh(mesh: PanelMesh, *, case_id: str = "artifact") -> object:
    """Build stable synthetic results aligned with a loaded mesh."""
    face_count = mesh.n_faces
    geometry = mesh.geometry
    case = CommonCasePayload(
        case_id=case_id,
        Aref_m2=1.0,
        moment_reference_stl_m=[0, 0, 0],
        Lref_Cl_m=1.0,
        Lref_Cm_m=1.0,
        Lref_Cn_m=1.0,
        alpha_t_deg=0.0,
        beta_t_deg=0.0,
    )
    return assemble_common_results(
        case,
        ModelCasePayload("synthetic"),
        geometry,
        PanelFlowState([1, 0, 0], np.zeros(face_count, dtype=bool)),
        LocalLoads(
            np.tile([[2.0, 0.0, 0.0]], (face_count, 1)),
            {
                "cp": np.full(face_count, 2.0),
                "theta_deg": np.zeros(face_count),
            },
        ),
    )


class ArtifactProjectionTests(unittest.TestCase):
    def _projection(self):
        mesh, results = fixture()
        return project_vtp_artifact(
            mesh,
            results,
            ArtifactProjectionPolicy("beta_tan", "signature", "not_used", "1.0"),
        )

    def test_vtp_write_is_fsynced_replaced_and_leaves_no_temp_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "case001.vtp"
            with (
                patch("panelsolver.app.artifact_io.os.fsync") as fsync,
                patch(
                    "panelsolver.app.artifact_io.os.replace",
                    wraps=os.replace,
                ) as replace,
            ):
                write_vtp_projection(output, self._projection())

            temp_path = Path(replace.call_args.args[0])
            self.assertEqual(".vtp", temp_path.suffix)
            self.assertTrue(temp_path.name.startswith(".case001."))
            self.assertTrue(temp_path.name.endswith(".tmp.vtp"))
            fsync.assert_called_once()
            replace.assert_called_once()
            self.assertTrue(output.is_file())
            self.assertEqual([output], list(Path(temp_dir).iterdir()))
            self.assertEqual("artifact", str(pv.read(output).field_data["case_id"][0]))

    def test_vtp_temp_write_failure_preserves_existing_file_and_cleans_temp(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "case001.vtp"
            output.write_bytes(b"existing-vtp")
            with (
                patch.object(pv.PolyData, "save", side_effect=OSError("disk full")),
                self.assertRaisesRegex(OSError, "disk full"),
            ):
                write_vtp_projection(output, self._projection())

            self.assertEqual(b"existing-vtp", output.read_bytes())
            self.assertEqual([output], list(Path(temp_dir).iterdir()))

    def test_vtp_replace_failure_preserves_existing_file_and_cleans_temp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "case001.vtp"
            output.write_bytes(b"existing-vtp")
            with (
                patch(
                    "panelsolver.app.artifact_io.os.replace",
                    side_effect=OSError("replace denied"),
                ),
                self.assertRaisesRegex(OSError, "replace denied"),
            ):
                write_vtp_projection(output, self._projection())

            self.assertEqual(b"existing-vtp", output.read_bytes())
            self.assertEqual([output], list(Path(temp_dir).iterdir()))

    def test_vtp_fsync_failure_preserves_existing_file_and_cleans_temp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "case001.vtp"
            output.write_bytes(b"existing-vtp")
            with (
                patch(
                    "panelsolver.app.artifact_io.os.fsync",
                    side_effect=OSError("fsync failed"),
                ),
                self.assertRaisesRegex(OSError, "fsync failed"),
            ):
                write_vtp_projection(output, self._projection())

            self.assertEqual(b"existing-vtp", output.read_bytes())
            self.assertEqual([output], list(Path(temp_dir).iterdir()))

    def test_projects_common_and_explicit_product_fields(self) -> None:
        mesh, results = fixture()
        policy = ArtifactProjectionPolicy(
            attitude_input_used="beta_tan",
            case_signature="signature",
            ray_backend_used="not_used",
            solver_version="1.0",
            vtp_field_data={"windward_eq_used": "newtonian"},
        )

        vtp = project_vtp_artifact(mesh, results, policy)

        self.assertEqual(
            sorted(vtp.cell_data),
            list(vtp.cell_data),
        )
        self.assertEqual(
            sorted(vtp.field_data),
            list(vtp.field_data),
        )
        self.assertEqual("newtonian", vtp.field_data["windward_eq_used"][0])
        self.assertEqual('["plate.stl"]', vtp.field_data["stl_paths_json"][0])
        np.testing.assert_array_equal(vtp.faces, [3, 0, 1, 2, 3, 1, 3, 2])
        np.testing.assert_array_equal(
            vtp.cell_data["C_face_stl"], [[1, 0, 0], [1, 0, 0]]
        )
        self.assertFalse(vtp.cell_data["C_face_stl"].flags.writeable)

    def test_unicode_stl_source_writes_and_round_trips_through_vtk(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "日本語ディレクトリ" / "板_日本語.stl"
            source.parent.mkdir()
            shutil.copyfile(FIXTURE_STL, source)
            loaded = load_panel_mesh((source,), 1.0)
            ascii_loaded = load_panel_mesh((FIXTURE_STL,), 1.0)
            self.assertEqual(
                loaded.geometry_fingerprint,
                ascii_loaded.geometry_fingerprint,
            )

            projection = project_vtp_artifact(
                loaded.mesh,
                results_for_mesh(loaded.mesh),
                ArtifactProjectionPolicy(
                    "beta_tan",
                    "signature",
                    "not_used",
                    "1.0",
                ),
            )
            output = Path(temp_dir) / "unicode-path.vtp"
            write_vtp_projection(output, projection)

            stored = str(pv.read(output).field_data["stl_paths_json"][0])
            self.assertTrue(stored.isascii())
            self.assertEqual([str(source.resolve())], json.loads(stored))

    def test_non_ascii_string_fields_round_trip_without_generic_escaping(self) -> None:
        mesh, results = fixture(case_id="ケース")
        projection = project_vtp_artifact(
            mesh,
            results,
            ArtifactProjectionPolicy(
                "beta_tan",
                "signature",
                "not_used",
                "1.0",
                vtp_field_data={"model_note": ["モデル固有の説明"]},
            ),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "unicode-fields.vtp"
            write_vtp_projection(output, projection)
            poly = pv.read(output)

        self.assertEqual("ケース", str(poly.field_data["case_id"][0]))
        self.assertEqual("モデル固有の説明", str(poly.field_data["model_note"][0]))

    def test_ascii_stl_path_json_remains_unchanged_after_vtp_write(self) -> None:
        mesh, results = fixture()
        projection = project_vtp_artifact(
            mesh,
            results,
            ArtifactProjectionPolicy("beta_tan", "signature", "not_used", "1.0"),
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "ascii-fields.vtp"
            write_vtp_projection(output, projection)
            poly = pv.read(output)

        self.assertEqual('["plate.stl"]', str(poly.field_data["stl_paths_json"][0]))

    def test_policy_additions_cannot_override_common_fields(self) -> None:
        mesh, results = fixture()
        with self.assertRaises(ContractValueError):
            project_vtp_artifact(
                mesh,
                results,
                ArtifactProjectionPolicy(
                    "beta_tan",
                    "signature",
                    "not_used",
                    "1.0",
                    vtp_field_data={"case_id": ["other"]},
                ),
            )

    def test_rejects_object_field_arrays_and_geometry_mismatch(self) -> None:
        mesh, results = fixture()
        with self.assertRaises(ContractValueError):
            ArtifactProjectionPolicy(
                "beta_tan",
                "signature",
                "not_used",
                "1.0",
                vtp_field_data={"unsafe": np.array([object()], dtype=object)},
            )

        other_geometry = PanelGeometry(
            centers_stl_m=[[0, 0, 0], [1, 1, 0]],
            normals_out_stl=[[0, 0, 1], [0, 0, 1]],
            areas_m2=[0.5, 0.5],
            component_ids=[0, 0],
        )
        mismatched_mesh = PanelMesh(
            mesh.vertices_stl_m,
            mesh.faces,
            other_geometry,
            [MeshComponent(0, "plate.stl")],
        )
        with self.assertRaises(ContractValueError):
            project_vtp_artifact(
                mismatched_mesh,
                results,
                ArtifactProjectionPolicy(
                    "beta_tan",
                    "signature",
                    "not_used",
                    "1.0",
                ),
            )


if __name__ == "__main__":
    unittest.main()
