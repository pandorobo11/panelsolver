from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from fmfsolver._frontend import _legacy_gui_spec as fmf_solver_spec
from newtsolver._frontend import _legacy_gui_spec as newt_solver_spec
from panelsolver.app import (
    ArtifactSignatureCandidates,
    SolverGuiAdapters,
)
from panelsolver.app.viewer import ViewerPanel
from panelsolver.core import CaseSignature, canonical_json
from tests.path_assertions import assert_paths_equivalent, paths_equivalent


class FakeCamera:
    def __init__(self) -> None:
        self.position = (1.0, 2.0, 3.0)
        self.focal_point = (0.0, 0.0, 0.0)
        self.up = (0.0, 0.0, 1.0)
        self.clipping_range = (0.1, 10.0)
        self.parallel_projection = False
        self.parallel_scale = 2.0


class FakePlotter:
    def __init__(self) -> None:
        self.interactor = QtWidgets.QWidget()
        self.camera = FakeCamera()
        self.mesh_calls: list[tuple[object, dict[str, object]]] = []
        self.text_calls: list[str] = []
        self.view_vectors: list[tuple[float, float, float]] = []
        self.clear_count = 0
        self.render_count = 0
        self.reset_count = 0
        self.parallel_enabled = False
        self.screenshot_calls: list[str] = []
        self.screenshot_error: Exception | None = None

    def enable_parallel_projection(self) -> None:
        self.parallel_enabled = True
        self.camera.parallel_projection = True

    def clear(self) -> None:
        self.clear_count += 1
        self.mesh_calls.clear()

    def render(self) -> None:
        self.render_count += 1

    def add_mesh(self, poly, **kwargs) -> None:
        self.mesh_calls.append((poly, kwargs))

    def add_text(self, text, **_kwargs):
        self.text_calls.append(text)
        return object()

    def remove_actor(self, _actor) -> None:
        return None

    def add_axes(self) -> None:
        return None

    def reset_camera(self) -> None:
        self.reset_count += 1

    def view_vector(self, vector) -> None:
        self.view_vectors.append(tuple(vector))

    def screenshot(self, path: str) -> None:
        if self.screenshot_error is not None:
            raise self.screenshot_error
        self.screenshot_calls.append(path)


class FakePoly:
    def __init__(self, cell_data, field_data=None, indices=None) -> None:
        self.cell_data = {name: np.asarray(value) for name, value in cell_data.items()}
        self.field_data = {} if field_data is None else field_data
        first = next(iter(self.cell_data.values()))
        self.n_cells = len(first) if indices is None else len(indices)
        self._indices = np.arange(len(first)) if indices is None else np.asarray(indices)

    def extract_cells(self, indices):
        selected = self._indices[np.asarray(indices)]
        data = {name: values[selected] for name, values in self.cell_data.items()}
        return FakePoly(data, self.field_data)


def _signature(label: str) -> CaseSignature:
    envelope = {"fixture": label}
    payload = canonical_json(envelope)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return CaseSignature(digest, payload, envelope)


def _adapters(signature: CaseSignature, velocity=(1.0, 0.0, 0.0)):
    return SolverGuiAdapters(
        read_cases=lambda _path: (),
        build_case_signatures=lambda _row: ArtifactSignatureCandidates(signature),
        run_cases=lambda _request: None,
        validate_output_path=lambda out, _input, _rows: Path(out),
        resolve_velocity_hat_stl=lambda _row: velocity,
    )


class ViewerPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def make_viewer(self, *, spec=None, reader=lambda _path: None, **kwargs):
        plotter = FakePlotter()
        viewer = ViewerPanel(
            fmf_solver_spec() if spec is None else spec,
            artifact_reader=reader,
            plotter_factory=lambda _parent: plotter,
            **kwargs,
        )
        return viewer, plotter

    def test_dynamic_scalars_render_shield_groups_and_overlay(self) -> None:
        viewer, plotter = self.make_viewer()
        poly = FakePoly(
            {
                "model_extra": [4.0, 5.0],
                "shielded": [0, 1],
                "normal_traction_coeff": [0.2, 0.4],
            },
            {"case_id": ["case"]},
        )
        loaded = viewer.load_vtp(
            "/tmp/case.vtp",
            poly,
            {"case_id": "case", "S": 5.0, "Ti_K": 300.0},
        )
        self.assertTrue(loaded)
        self.assertEqual(
            ["Normal traction coeff.", "Shielded", "model_extra"],
            [viewer.cmb_scalar.itemText(i) for i in range(viewer.cmb_scalar.count())],
        )
        self.assertEqual("Normal traction coeff.", viewer.cmb_scalar.currentText())
        self.assertEqual("normal_traction_coeff", viewer.cmb_scalar.currentData())
        self.assertEqual(2, len(plotter.mesh_calls))
        self.assertEqual(1.0, plotter.mesh_calls[0][1]["opacity"])
        self.assertEqual(0.30, plotter.mesh_calls[1][1]["opacity"])
        self.assertEqual("jet", plotter.mesh_calls[0][1]["cmap"])
        self.assertEqual(
            "normal_traction_coeff",
            plotter.mesh_calls[0][1]["scalars"],
        )
        self.assertEqual(
            {"title": "Normal traction coeff."},
            plotter.mesh_calls[0][1]["scalar_bar_args"],
        )
        self.assertEqual((0.2, 0.4), plotter.mesh_calls[0][1]["clim"])
        self.assertIn("case_id=case", plotter.text_calls[-1])
        self.assertTrue(plotter.parallel_enabled)

    def test_hypersonic_scalar_label_selects_cp_and_titles_colorbar(self) -> None:
        viewer, plotter = self.make_viewer(spec=newt_solver_spec())
        self.assertTrue(viewer.load_vtp("/tmp/case.vtp", FakePoly({"cp": [0.7]})))
        self.assertEqual("Cp", viewer.cmb_scalar.currentText())
        self.assertEqual("cp", viewer.cmb_scalar.currentData())
        self.assertEqual("cp", plotter.mesh_calls[0][1]["scalars"])
        self.assertEqual(
            {"title": "Cp"},
            plotter.mesh_calls[0][1]["scalar_bar_args"],
        )

    def test_reload_uses_first_available_preferred_scalar(self) -> None:
        viewer, _plotter = self.make_viewer()
        viewer.load_vtp(
            "/tmp/first.vtp",
            FakePoly({"normal_traction_coeff": [1.0]}),
        )
        viewer.load_vtp(
            "/tmp/second.vtp",
            FakePoly({"model_extra": [3.0], "shielded": [0]}),
        )
        self.assertEqual("Shielded", viewer.cmb_scalar.currentText())
        self.assertEqual("shielded", viewer.cmb_scalar.currentData())
        self.assertEqual((0.0, 1.0), viewer._automatic_limits("shielded"))

    def test_redraw_preserves_camera_and_buttons_set_expected_vectors(self) -> None:
        viewer, plotter = self.make_viewer()
        viewer.load_vtp(
            "/tmp/case.vtp",
            FakePoly({"normal_traction_coeff": [1.0]}),
        )
        plotter.camera.position = (9.0, 8.0, 7.0)
        viewer.chk_edges.setChecked(False)
        self.assertEqual((9.0, 8.0, 7.0), plotter.camera.position)
        viewer.btn_view_xp.click()
        viewer.btn_view_iso_2.click()
        self.assertEqual((1, 0, 0), plotter.view_vectors[-2])
        self.assertEqual((1, -1, -1), plotter.view_vectors[-1])

    def test_wind_views_use_only_the_injected_spec_adapter(self) -> None:
        signature = _signature("wind")
        viewer, plotter = self.make_viewer(
            spec=fmf_solver_spec(adapters=_adapters(signature, (2.0, 0.0, 0.0)))
        )
        viewer.load_vtp(
            "/tmp/case.vtp",
            FakePoly({"normal_traction_coeff": [1.0]}),
            {"case_id": "case"},
        )
        viewer.set_view_wind()
        viewer.set_view_wind_reverse()
        self.assertEqual((-1.0, -0.0, -0.0), plotter.view_vectors[-2])
        self.assertEqual((1.0, 0.0, 0.0), plotter.view_vectors[-1])

    def test_manual_stale_artifact_displays_without_case_context(self) -> None:
        current = _signature("current")
        stale = _signature("stale")
        viewer, plotter = self.make_viewer(
            spec=fmf_solver_spec(adapters=_adapters(current))
        )
        viewer.set_case_rows(({"case_id": "case"},))
        poly = FakePoly(
            {"normal_traction_coeff": [1.0]},
            {"case_id": ["case"], "case_signature": [stale.digest]},
        )
        self.assertTrue(viewer.load_vtp("/tmp/stale.vtp", poly))
        self.assertIsNone(viewer._display_case_row)
        self.assertEqual("case_id=case", plotter.text_calls[-1])
        with patch.object(
            QtWidgets.QFileDialog,
            "getSaveFileName",
            return_value=("", ""),
        ) as dialog:
            viewer.save_view_image()
        self.assertEqual(
            Path("/tmp/images/stale__normal_traction_coeff.png"),
            Path(dialog.call_args.args[2]),
        )

    def test_failed_read_and_invalid_cell_data_clear_previous_view(self) -> None:
        def broken(_path):
            raise ValueError("broken")

        viewer, plotter = self.make_viewer(reader=broken)
        viewer.load_vtp(
            "/tmp/good.vtp",
            FakePoly({"normal_traction_coeff": [1.0]}),
        )
        messages: list[str] = []
        viewer.log_message.connect(messages.append)
        self.assertFalse(viewer.load_vtp("/tmp/broken.vtp"))
        self.assertIsNone(viewer._poly)
        self.assertEqual(0, viewer.cmb_scalar.count())
        self.assertIn("Failed to read VTP", messages[-1])
        self.assertGreaterEqual(plotter.clear_count, 2)
        self.assertFalse(
            viewer.load_vtp("/tmp/empty.vtp", SimpleNamespace(cell_data={}, n_cells=0))
        )
        self.assertIn("Invalid VTP cell data", messages[-1])

    def test_dialog_manual_open_and_range_controls(self) -> None:
        poly = FakePoly({"normal_traction_coeff": [1.0, 3.0]})
        viewer, _plotter = self.make_viewer(reader=lambda _path: poly)
        with patch.object(
            QtWidgets.QFileDialog,
            "getOpenFileName",
            return_value=("/tmp/manual.vtp", "VTK"),
        ):
            viewer.open_vtp()
        self.assertEqual(Path("/tmp/manual.vtp"), viewer._loaded_vtp_path)
        viewer.edit_vmin.setText("0")
        viewer.edit_vmax.setText("10")
        self.assertEqual(
            (0.0, 10.0),
            viewer._automatic_limits("normal_traction_coeff"),
        )
        viewer.clear_range()
        self.assertEqual("", viewer.edit_vmin.text())
        self.assertEqual("", viewer.edit_vmax.text())

    def test_single_image_export_cancel_filters_default_and_failure(self) -> None:
        viewer, plotter = self.make_viewer()
        self.assertTrue(
            viewer.load_vtp(
                "/artifacts/case.vtp",
                FakePoly({"normal_traction_coeff": [1.0]}),
            )
        )
        messages = []
        viewer.log_message.connect(messages.append)
        captured = {}

        def cancel(_parent, title, default, filters):
            captured.update(title=title, default=default, filters=filters)
            return ("", "")

        with patch.object(QtWidgets.QFileDialog, "getSaveFileName", side_effect=cancel):
            viewer.save_view_image()
        self.assertEqual("Save View Image", captured["title"])
        self.assertEqual(
            Path("/artifacts/images/case__normal_traction_coeff.png"),
            Path(captured["default"]),
        )
        self.assertEqual(
            "PNG (*.png);;JPEG (*.jpg *.jpeg);;TIFF (*.tif *.tiff)",
            captured["filters"],
        )
        self.assertEqual([], plotter.screenshot_calls)

        with patch.object(
            QtWidgets.QFileDialog,
            "getSaveFileName",
            return_value=("/tmp/view.tiff", "TIFF"),
        ):
            viewer.save_view_image()
        self.assertEqual(["/tmp/view.tiff"], plotter.screenshot_calls)
        self.assertIn("[OK] Saved image: /tmp/view.tiff", messages)

        plotter.screenshot_error = RuntimeError("capture failed")
        with patch.object(
            QtWidgets.QFileDialog,
            "getSaveFileName",
            return_value=("/tmp/fail.png", "PNG"),
        ):
            viewer.save_view_image()
        self.assertIn("Failed to save image: capture failed", messages[-1])

    def test_case_image_default_and_lazy_directory_creation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="single_image_") as directory:
            root = Path(directory)
            input_path = root / "project" / "cases.csv"
            row = {"case_id": "case_001", "out_dir": "results"}
            viewer, plotter = self.make_viewer()
            viewer.set_input_path(input_path)
            viewer.set_case_rows((row,))
            self.assertTrue(
                viewer.load_vtp(
                    str(root / "project" / "results" / "case_001.vtp"),
                    FakePoly({"normal_traction_coeff": [1.0]}),
                    row,
                )
            )
            expected = (
                input_path.parent
                / "results"
                / "images"
                / "case_001__normal_traction_coeff.png"
            )
            self.assertFalse(expected.parent.exists())
            with patch.object(
                QtWidgets.QFileDialog,
                "getSaveFileName",
                return_value=(str(expected), "PNG"),
            ) as dialog:
                viewer.save_view_image()
            assert_paths_equivalent(self, expected, dialog.call_args.args[2])
            self.assertTrue(expected.parent.is_dir())
            self.assertEqual([str(expected)], plotter.screenshot_calls)

    def test_single_directory_failure_does_not_capture(self) -> None:
        viewer, plotter = self.make_viewer(
            make_directory=lambda _path: (_ for _ in ()).throw(
                OSError("read only")
            ),
        )
        messages = []
        viewer.log_message.connect(messages.append)
        viewer.load_vtp(
            "/manual/sample.vtp",
            FakePoly({"normal_traction_coeff": [1.0]}),
        )
        with patch.object(
            QtWidgets.QFileDialog,
            "getSaveFileName",
            return_value=("/manual/images/sample__normal_traction_coeff.png", "PNG"),
        ):
            viewer.save_view_image()
        self.assertEqual([], plotter.screenshot_calls)
        self.assertIn("Failed to create image directory: read only", messages[-1])

    def test_batch_export_orders_current_rows_and_skips_invalid_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="phase6_images_") as directory:
            source_dir = Path(directory) / "artifacts"
            output_dir = Path(directory) / "captures"
            rows = (
                {"case_id": "current_a", "out_dir": str(source_dir)},
                {"case_id": "missing", "out_dir": str(source_dir)},
                {"case_id": "stale", "out_dir": str(source_dir)},
                {"case_id": "broken", "out_dir": str(source_dir)},
                {"case_id": "current_b", "out_dir": str(source_dir)},
            )
            current = _signature("current")
            stale = _signature("stale")
            spec = fmf_solver_spec(adapters=_adapters(current))
            existing = {
                source_dir / f"{row['case_id']}.vtp"
                for row in rows
                if row["case_id"] != "missing"
            }

            def artifact_reader(path):
                case_id = Path(path).stem
                if case_id == "broken":
                    raise ValueError("unreadable")
                digest = stale.digest if case_id == "stale" else current.digest
                return FakePoly(
                    {"normal_traction_coeff": [1.0]},
                    {"case_id": [case_id], "case_signature": [digest]},
                )

            made = []
            events = []
            viewer, plotter = self.make_viewer(
                spec=spec,
                reader=artifact_reader,
                path_exists=lambda path: any(
                    paths_equivalent(path, candidate) for candidate in existing
                ),
                make_directory=lambda path: made.append(path),
                process_events=lambda: events.append("event"),
            )
            messages = []
            viewer.log_message.connect(messages.append)
            contexts = []
            original_load = viewer.load_vtp

            def load_with_context(path, poly=None, case_row=None):
                contexts.append((Path(path).stem, case_row))
                return original_load(path, poly=poly, case_row=case_row)

            with (
                patch.object(
                    QtWidgets.QFileDialog,
                    "getExistingDirectory",
                    return_value=str(output_dir),
                ) as dialog,
                patch.object(viewer, "load_vtp", side_effect=load_with_context),
            ):
                viewer.save_images_for_case_rows(rows)

            assert_paths_equivalent(
                self,
                source_dir / "images",
                dialog.call_args.args[2],
            )
            self.assertEqual(2, len(made))
            assert_paths_equivalent(self, source_dir / "images", made[0])
            assert_paths_equivalent(self, output_dir, made[1])
            self.assertEqual(5, len(events))
            self.assertEqual(2, len(plotter.screenshot_calls))
            for case_id, actual in zip(
                ("current_a", "current_b"),
                plotter.screenshot_calls,
                strict=True,
            ):
                assert_paths_equivalent(
                    self,
                    output_dir / f"{case_id}__normal_traction_coeff.png",
                    actual,
                )
            self.assertEqual(
                [("current_a", rows[0]), ("current_b", rows[4])],
                contexts,
            )
            log_text = "\n".join(messages)
            self.assertIn("VTP not found", log_text)
            self.assertIn("signature mismatch for 'stale'", log_text)
            self.assertIn("Failed to read VTP for 'broken'", log_text)
            self.assertIn("saved=2, skipped=3", messages[-1])

    def test_batch_creates_standard_directory_before_folder_dialog(self) -> None:
        with tempfile.TemporaryDirectory(prefix="batch_standard_dir_") as directory:
            root = Path(directory)
            input_path = root / "project" / "cases.csv"
            row = {"case_id": "one", "out_dir": "results"}
            standard_dir = input_path.parent / "results" / "images"
            viewer, plotter = self.make_viewer()
            viewer.set_input_path(input_path)
            self.assertFalse(standard_dir.exists())

            def cancel(_parent, _title, initial):
                self.assertTrue(standard_dir.is_dir())
                assert_paths_equivalent(self, standard_dir, initial)
                return ""

            with patch.object(
                QtWidgets.QFileDialog,
                "getExistingDirectory",
                side_effect=cancel,
            ) as dialog:
                viewer.save_images_for_case_rows((row,))
            dialog.assert_called_once()
            self.assertTrue(standard_dir.is_dir())
            self.assertEqual([], plotter.screenshot_calls)

    def test_batch_standard_directory_failure_skips_dialog_and_capture(self) -> None:
        row = {"case_id": "one", "out_dir": "/artifacts"}
        viewer, plotter = self.make_viewer(
            make_directory=lambda _path: (_ for _ in ()).throw(
                OSError("read only")
            )
        )
        messages = []
        viewer.log_message.connect(messages.append)
        with patch.object(
            QtWidgets.QFileDialog,
            "getExistingDirectory",
        ) as dialog:
            viewer.save_images_for_case_rows((row,))
        dialog.assert_not_called()
        self.assertEqual([], plotter.screenshot_calls)
        self.assertIn("Failed to create image directory: read only", messages[-1])

    def test_relative_vtp_and_image_paths_use_input_parent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="viewer_input_base_") as directory:
            root = Path(directory)
            row = {"case_id": "one", "out_dir": "outputs"}
            seen = []
            viewer, _plotter = self.make_viewer(
                path_exists=lambda path: seen.append(path) or False,
            )
            viewer.set_input_path(root / "input.csv")
            viewer._display_case_row = row
            assert_paths_equivalent(
                self,
                root / "outputs",
                viewer.default_artifact_dir(),
            )
            with patch.object(
                QtWidgets.QFileDialog,
                "getExistingDirectory",
                return_value="",
            ) as dialog:
                viewer.save_images_for_case_rows((row,))
            assert_paths_equivalent(
                self,
                root / "outputs" / "images",
                dialog.call_args.args[2],
            )
            viewer._save_case_image(row, root / "captures")
            self.assertEqual(1, len(seen))
            assert_paths_equivalent(self, root / "outputs" / "one.vtp", seen[0])

    def test_batch_mixed_output_default_is_input_based_and_order_independent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mixed_images_") as directory:
            root = Path(directory)
            input_path = root / "project" / "cases.csv"
            rows = (
                {"case_id": "one", "out_dir": "first"},
                {"case_id": "two", "out_dir": str(root / "second")},
            )
            expected = input_path.parent / "outputs" / "images"
            for ordered in (rows, tuple(reversed(rows))):
                viewer, _plotter = self.make_viewer()
                viewer.set_input_path(input_path)
                with patch.object(
                    QtWidgets.QFileDialog,
                    "getExistingDirectory",
                    return_value="",
                ) as dialog:
                    viewer.save_images_for_case_rows(ordered)
                assert_paths_equivalent(self, expected, dialog.call_args.args[2])

    def test_batch_auto_rename_avoids_existing_and_same_batch_collisions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rename_images_") as directory:
            root = Path(directory)
            output_dir = root / "images"
            row = {"case_id": "one", "out_dir": str(root)}
            vtp_path = root / "one.vtp"
            base_image = output_dir / "one__cp_raw.png"
            output_dir.mkdir()
            vtp_path.write_text("fixture", encoding="utf-8")
            base_image.write_text("existing image", encoding="utf-8")
            current = _signature("current")
            artifact = FakePoly(
                {"cp:raw": [1.0]},
                {"case_id": ["one"], "case_signature": [current.digest]},
            )
            viewer, plotter = self.make_viewer(
                spec=fmf_solver_spec(adapters=_adapters(current)),
                reader=lambda _path: artifact,
                make_directory=lambda _path: None,
            )
            with patch.object(
                QtWidgets.QFileDialog,
                "getExistingDirectory",
                return_value=str(output_dir),
            ):
                viewer.save_images_for_case_rows((row, row))
            self.assertEqual(2, len(plotter.screenshot_calls))
            for expected, actual in zip(
                (
                    output_dir / "one__cp_raw_2.png",
                    output_dir / "one__cp_raw_3.png",
                ),
                plotter.screenshot_calls,
                strict=True,
            ):
                assert_paths_equivalent(self, expected, actual)
            self.assertEqual(
                "existing image",
                base_image.read_text(encoding="utf-8"),
            )

    def test_image_directory_memory_resets_and_falls_back_when_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="remember_images_") as directory:
            root = Path(directory)
            first_input = root / "first" / "cases.csv"
            second_input = root / "second" / "cases.csv"
            custom_dir = root / "custom"
            custom_dir.mkdir()
            row = {"case_id": "one", "out_dir": "results"}
            viewer, _plotter = self.make_viewer()
            viewer.set_input_path(first_input)
            viewer.set_case_rows((row,))
            viewer.load_vtp(
                str(first_input.parent / "results" / "one.vtp"),
                FakePoly({"normal_traction_coeff": [1.0]}),
                row,
            )
            chosen = custom_dir / "chosen.png"
            with patch.object(
                QtWidgets.QFileDialog,
                "getSaveFileName",
                return_value=(str(chosen), "PNG"),
            ):
                viewer.save_view_image()

            with patch.object(
                QtWidgets.QFileDialog,
                "getSaveFileName",
                return_value=("", ""),
            ) as remembered_dialog:
                viewer.save_view_image()
            self.assertEqual(
                custom_dir / "one__normal_traction_coeff.png",
                Path(remembered_dialog.call_args.args[2]),
            )
            with patch.object(
                QtWidgets.QFileDialog,
                "getExistingDirectory",
                return_value="",
            ) as remembered_batch_dialog:
                viewer.save_images_for_case_rows((row,))
            self.assertEqual(
                custom_dir,
                Path(remembered_batch_dialog.call_args.args[2]),
            )

            manual_vtp = root / "manual" / "sample.vtp"
            viewer.load_vtp(
                str(manual_vtp),
                FakePoly({"normal_traction_coeff": [1.0]}),
            )
            with patch.object(
                QtWidgets.QFileDialog,
                "getSaveFileName",
                return_value=("", ""),
            ) as manual_dialog:
                viewer.save_view_image()
            self.assertEqual(
                manual_vtp.parent
                / "images"
                / "sample__normal_traction_coeff.png",
                Path(manual_dialog.call_args.args[2]),
            )
            viewer.load_vtp(
                str(first_input.parent / "results" / "one.vtp"),
                FakePoly({"normal_traction_coeff": [1.0]}),
                row,
            )

            viewer.set_input_path(second_input)
            with patch.object(
                QtWidgets.QFileDialog,
                "getSaveFileName",
                return_value=("", ""),
            ) as reset_dialog:
                viewer.save_view_image()
            assert_paths_equivalent(
                self,
                second_input.parent
                / "results"
                / "images"
                / "one__normal_traction_coeff.png",
                reset_dialog.call_args.args[2],
            )

            custom_dir.rmdir()
            viewer._last_image_directory = custom_dir
            second_standard_dir = second_input.parent / "results" / "images"
            self.assertFalse(second_standard_dir.exists())
            with patch.object(
                QtWidgets.QFileDialog,
                "getExistingDirectory",
                return_value="",
            ) as missing_batch_dialog:
                viewer.save_images_for_case_rows((row,))
            self.assertTrue(second_standard_dir.is_dir())
            assert_paths_equivalent(
                self,
                second_standard_dir,
                missing_batch_dialog.call_args.args[2],
            )
            with patch.object(
                QtWidgets.QFileDialog,
                "getSaveFileName",
                return_value=("", ""),
            ) as missing_dialog:
                viewer.save_view_image()
            assert_paths_equivalent(
                self,
                second_input.parent
                / "results"
                / "images"
                / "one__normal_traction_coeff.png",
                missing_dialog.call_args.args[2],
            )

    def test_export_buttons_follow_viewport_and_loaded_case_state(self) -> None:
        viewer, _plotter = self.make_viewer()
        self.assertFalse(viewer.btn_save_image.isEnabled())
        self.assertFalse(viewer.btn_save_selected_images.isEnabled())
        viewer.set_input_path("/tmp/cases.csv")
        viewer.set_case_rows(({"case_id": "one"},))
        self.assertFalse(viewer.btn_save_selected_images.isEnabled())
        viewer.set_selected_case_rows(({"case_id": "one"},))
        self.assertTrue(viewer.btn_save_selected_images.isEnabled())
        viewer.load_vtp(
            "/tmp/one.vtp",
            FakePoly({"normal_traction_coeff": [1.0]}),
            {"case_id": "one"},
        )
        self.assertTrue(viewer.btn_save_image.isEnabled())
        viewer.clear_view()
        self.assertFalse(viewer.btn_save_image.isEnabled())
        viewer.set_case_rows(())
        self.assertFalse(viewer.btn_save_selected_images.isEnabled())


if __name__ == "__main__":
    unittest.main()
