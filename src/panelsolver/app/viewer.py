"""Shared Qt/PyVista VTP viewer driven by :class:`SolverSpec`."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np
import pyvista as pv
from PySide6 import QtCore, QtWidgets
from pyvistaqt import QtInteractor

from .path_resolution import (
    absolute_input_path,
    auto_rename_path,
    default_image_filename,
    resolve_batch_image_dir,
    resolve_case_image_path,
    resolve_case_output_dir,
    resolve_case_vtp_path,
    resolve_manual_vtp_image_path,
)
from .solver_spec import CaseRow, SolverSpec
from .viewer_data import (
    ScalarField,
    discover_scalar_fields,
    field_data_scalar,
    match_artifact_case,
    resolve_matching_case_row,
    scalar_color_limits,
)


def _path_exists(path: Path) -> bool:
    return path.exists()


def _make_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _process_gui_events() -> None:
    QtWidgets.QApplication.processEvents(
        QtCore.QEventLoop.ProcessEventsFlag.AllEvents,
        10,
    )


class ViewerPanel(QtWidgets.QWidget):
    """Render VTP cell data without owning product or numerical behavior."""

    log_message = QtCore.Signal(str)
    save_selected_images_requested = QtCore.Signal()

    def __init__(
        self,
        spec: SolverSpec,
        parent=None,
        *,
        artifact_reader: Callable[[str], object] = pv.read,
        plotter_factory: Callable[[QtWidgets.QWidget], object] = QtInteractor,
        path_exists: Callable[[Path], bool] = _path_exists,
        make_directory: Callable[[Path], None] = _make_directory,
        process_events: Callable[[], None] = _process_gui_events,
    ) -> None:
        if not isinstance(spec, SolverSpec):
            raise TypeError("spec must be a SolverSpec")
        if not callable(artifact_reader):
            raise TypeError("artifact_reader must be callable")
        if not callable(plotter_factory):
            raise TypeError("plotter_factory must be callable")
        for name, callback in (
            ("path_exists", path_exists),
            ("make_directory", make_directory),
            ("process_events", process_events),
        ):
            if not callable(callback):
                raise TypeError(f"{name} must be callable")
        super().__init__(parent)
        self.spec = spec
        self._artifact_reader = artifact_reader
        self._path_exists = path_exists
        self._make_directory = make_directory
        self._process_events = process_events
        self._root_layout = QtWidgets.QVBoxLayout(self)
        self._root_layout.setSpacing(6)
        self._root_layout.setContentsMargins(0, 0, 0, 0)

        self.plotter = plotter_factory(self)
        self._enable_parallel_projection()
        interactor = getattr(self.plotter, "interactor", None)
        if not isinstance(interactor, QtWidgets.QWidget):
            raise TypeError("plotter_factory must provide a QWidget interactor")
        self._root_layout.addWidget(interactor, 6)

        self._init_controls()
        self._build_controls_layout()
        self._connect_controls()

        self._case_rows: tuple[CaseRow, ...] = ()
        self._selected_case_rows: tuple[CaseRow, ...] = ()
        self._input_path: Path | None = None
        self._image_directory_input_path: Path | None = None
        self._last_image_directory: Path | None = None
        self._poly: object | None = None
        self._loaded_vtp_path: Path | None = None
        self._display_case_row: CaseRow | None = None
        self._scalar_fields: dict[str, ScalarField] = {}
        self._overlay_actor = None
        self._default_view_vec = (-1, -1, 1)
        self._camera_initialized = False
        self._update_export_controls()

    def _enable_parallel_projection(self) -> None:
        try:
            self.plotter.enable_parallel_projection()
            return
        except Exception:
            pass
        try:
            self.plotter.camera.parallel_projection = True
        except Exception:
            pass

    def _init_controls(self) -> None:
        self.cmb_scalar = QtWidgets.QComboBox()
        self.cmb_scalar.setMinimumWidth(145)
        self.chk_edges = QtWidgets.QCheckBox("Show edges")
        self.chk_edges.setChecked(True)
        self.chk_shield_transparent = QtWidgets.QCheckBox("Shielded transparent")
        self.chk_shield_transparent.setChecked(True)
        self.chk_overlay_text = QtWidgets.QCheckBox("Show info text")
        self.chk_overlay_text.setChecked(True)
        self.cmb_cmap = QtWidgets.QComboBox()
        self.cmb_cmap.addItems(["jet", "viridis", "bwr"])
        self.cmb_cmap.setCurrentText("jet")
        self.edit_vmin = QtWidgets.QLineEdit()
        self.edit_vmax = QtWidgets.QLineEdit()
        self.edit_vmin.setPlaceholderText("vmin (blank=auto)")
        self.edit_vmax.setPlaceholderText("vmax (blank=auto)")
        self.btn_auto_range = QtWidgets.QPushButton("Auto range")
        self.btn_open_vtp = QtWidgets.QPushButton("Open VTP...")
        self.btn_view_xp = QtWidgets.QPushButton("+X")
        self.btn_view_xn = QtWidgets.QPushButton("-X")
        self.btn_view_yp = QtWidgets.QPushButton("+Y")
        self.btn_view_yn = QtWidgets.QPushButton("-Y")
        self.btn_view_zp = QtWidgets.QPushButton("+Z")
        self.btn_view_zn = QtWidgets.QPushButton("-Z")
        self.btn_view_iso_1 = QtWidgets.QPushButton("-X -Y +Z")
        self.btn_view_iso_2 = QtWidgets.QPushButton("+X -Y -Z")
        self.btn_view_wind = QtWidgets.QPushButton("Wind +")
        self.btn_view_wind_rev = QtWidgets.QPushButton("Wind -")
        self.btn_save_image = QtWidgets.QPushButton("Save Image...")
        self.btn_save_selected_images = QtWidgets.QPushButton("Save Selected...")
        self.btn_save_image.setEnabled(False)
        self.btn_save_selected_images.setEnabled(False)

    def _build_controls_layout(self) -> None:
        controls = QtWidgets.QVBoxLayout()
        controls.setSpacing(3)
        controls.setContentsMargins(0, 0, 0, 0)

        display = QtWidgets.QHBoxLayout()
        display.addWidget(QtWidgets.QLabel("Scalar"))
        display.addWidget(self.cmb_scalar)
        display.addSpacing(10)
        display.addWidget(QtWidgets.QLabel("Colormap"))
        display.addWidget(self.cmb_cmap)
        display.addStretch(1)
        display.addWidget(self.btn_open_vtp)

        options = QtWidgets.QHBoxLayout()
        options.addWidget(QtWidgets.QLabel("Display"))
        options.addWidget(self.chk_edges)
        options.addWidget(self.chk_shield_transparent)
        options.addWidget(self.chk_overlay_text)
        options.addStretch(1)

        colorbar = QtWidgets.QHBoxLayout()
        colorbar.addWidget(QtWidgets.QLabel("Colorbar"))
        colorbar.addWidget(self.edit_vmin)
        colorbar.addWidget(self.edit_vmax)
        colorbar.addWidget(self.btn_auto_range)
        colorbar.addStretch(1)

        camera = QtWidgets.QHBoxLayout()
        camera.addWidget(QtWidgets.QLabel("Camera"))
        for button in (
            self.btn_view_xp,
            self.btn_view_xn,
            self.btn_view_yp,
            self.btn_view_yn,
            self.btn_view_zp,
            self.btn_view_zn,
            self.btn_view_iso_1,
            self.btn_view_iso_2,
            self.btn_view_wind,
            self.btn_view_wind_rev,
        ):
            camera.addWidget(button)
        camera.addStretch(1)

        export = QtWidgets.QHBoxLayout()
        export.addWidget(QtWidgets.QLabel("Export"))
        export.addWidget(self.btn_save_image)
        export.addWidget(self.btn_save_selected_images)
        export.addStretch(1)

        controls.addLayout(display)
        controls.addLayout(options)
        controls.addLayout(colorbar)
        controls.addLayout(camera)
        controls.addLayout(export)
        self._root_layout.addLayout(controls)

    def _connect_controls(self) -> None:
        self.btn_open_vtp.clicked.connect(self.open_vtp)
        self.cmb_scalar.currentTextChanged.connect(self.update_view)
        self.chk_edges.toggled.connect(self.update_view)
        self.chk_shield_transparent.toggled.connect(self.update_view)
        self.chk_overlay_text.toggled.connect(self.update_view)
        self.cmb_cmap.currentTextChanged.connect(self.update_view)
        self.edit_vmin.editingFinished.connect(self.update_view)
        self.edit_vmax.editingFinished.connect(self.update_view)
        self.btn_auto_range.clicked.connect(self.clear_range)
        self.btn_view_xp.clicked.connect(lambda: self.set_view_vector((1, 0, 0)))
        self.btn_view_xn.clicked.connect(lambda: self.set_view_vector((-1, 0, 0)))
        self.btn_view_yp.clicked.connect(lambda: self.set_view_vector((0, 1, 0)))
        self.btn_view_yn.clicked.connect(lambda: self.set_view_vector((0, -1, 0)))
        self.btn_view_zp.clicked.connect(lambda: self.set_view_vector((0, 0, 1)))
        self.btn_view_zn.clicked.connect(lambda: self.set_view_vector((0, 0, -1)))
        self.btn_view_iso_1.clicked.connect(lambda: self.set_view_vector((-1, -1, 1)))
        self.btn_view_iso_2.clicked.connect(lambda: self.set_view_vector((1, -1, -1)))
        self.btn_view_wind.clicked.connect(self.set_view_wind)
        self.btn_view_wind_rev.clicked.connect(self.set_view_wind_reverse)
        self.btn_save_image.clicked.connect(self.save_view_image)
        self.btn_save_selected_images.clicked.connect(
            self.save_selected_images_requested.emit
        )

    def logln(self, message: str) -> None:
        self.log_message.emit(message)

    def set_case_rows(self, rows: Sequence[CaseRow] | None) -> None:
        self._case_rows = () if rows is None else tuple(rows)
        self._selected_case_rows = ()
        self._update_export_controls()

    def set_selected_case_rows(self, rows: Sequence[CaseRow] | None) -> None:
        self._selected_case_rows = () if rows is None else tuple(rows)
        self._update_export_controls()

    def set_input_path(self, path: str | Path | None) -> None:
        """Set the input table whose directory anchors relative artifact paths."""
        resolved = None if path is None else absolute_input_path(path)
        if resolved is not None:
            if self._image_directory_input_path != resolved:
                self._last_image_directory = None
            self._image_directory_input_path = resolved
        self._input_path = resolved
        self._update_export_controls()

    def _input_path_context(self) -> Path:
        return self._input_path or (Path.cwd() / "input.csv")

    @QtCore.Slot()
    def clear_view(self) -> None:
        self._poly = None
        self._loaded_vtp_path = None
        self._display_case_row = None
        self._scalar_fields = {}
        self._overlay_actor = None
        self._camera_initialized = False
        self.cmb_scalar.clear()
        try:
            self.plotter.clear()
            self.plotter.render()
        except Exception:
            pass
        self._update_export_controls()

    def clear_range(self) -> None:
        self.edit_vmin.clear()
        self.edit_vmax.clear()
        self.update_view()

    def open_vtp(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open VTP",
            str(self.default_artifact_dir()),
            "VTK PolyData (*.vtp)",
        )
        if path:
            self.load_vtp(path)

    def load_vtp(
        self,
        path: str,
        poly: object | None = None,
        case_row: CaseRow | None = None,
    ) -> bool:
        """Load and render a VTP; manual inspection does not require a match."""
        if poly is None:
            try:
                loaded = self._artifact_reader(path)
            except Exception as exc:
                self.clear_view()
                self.logln(f"[ERROR] Failed to read VTP: {exc}")
                return False
        else:
            loaded = poly
        try:
            fields = discover_scalar_fields(
                loaded.cell_data,
                n_cells=loaded.n_cells,
                preferred=self.spec.preferred_scalars,
            )
        except Exception as exc:
            self.clear_view()
            self.logln(f"[ERROR] Invalid VTP cell data: {exc}")
            return False

        self._loaded_vtp_path = Path(path).expanduser()
        self._poly = loaded
        if case_row is not None:
            self._display_case_row = dict(case_row)
        elif self.spec.adapters is not None:
            self._display_case_row = resolve_matching_case_row(
                loaded,
                self._case_rows,
                self.spec.adapters.build_case_signatures,
            )
        else:
            self._display_case_row = None
        self._set_scalar_fields(fields)
        self.logln(f"[VIEW] Loaded VTP: {path}")
        self.update_view()
        self._update_export_controls()
        return True

    def _set_scalar_fields(self, fields: Sequence[ScalarField]) -> None:
        previous = self._selected_scalar_name()
        self._scalar_fields = {field.name: field for field in fields}
        blocker = QtCore.QSignalBlocker(self.cmb_scalar)
        self.cmb_scalar.clear()
        for name in self._scalar_fields:
            self.cmb_scalar.addItem(self.spec.scalar_labels.get(name, name), name)
        if previous in self._scalar_fields:
            self.cmb_scalar.setCurrentIndex(self.cmb_scalar.findData(previous))
        del blocker

    def _selected_scalar_name(self) -> str | None:
        name = self.cmb_scalar.currentData()
        return name if isinstance(name, str) and name in self._scalar_fields else None

    def default_artifact_dir(self) -> Path:
        if self._loaded_vtp_path is not None:
            return self._loaded_vtp_path.parent
        if self._display_case_row is not None:
            return resolve_case_output_dir(
                self._display_case_row,
                self._input_path_context(),
            )
        return Path.cwd()

    def _update_export_controls(self) -> None:
        self.btn_save_image.setEnabled(
            self._poly is not None and self._selected_scalar_name() is not None
        )
        self.btn_save_selected_images.setEnabled(
            self._input_path is not None
            and bool(self._case_rows)
            and bool(self._selected_case_rows)
        )

    def _standard_view_image_path(self) -> Path | None:
        scalar_name = self._selected_scalar_name()
        if self._poly is None or scalar_name is None:
            return None
        if self._display_case_row is not None:
            return resolve_case_image_path(
                self._display_case_row,
                self._input_path_context(),
                scalar_name,
            )
        if self._loaded_vtp_path is not None:
            return resolve_manual_vtp_image_path(
                self._loaded_vtp_path,
                scalar_name,
            )
        return None

    def _remembered_image_directory(self) -> Path | None:
        candidate = self._last_image_directory
        if candidate is not None and candidate.is_dir():
            return candidate
        return None

    def _view_image_dialog_path(self) -> Path | None:
        standard_path = self._standard_view_image_path()
        if standard_path is None:
            return None
        if self._display_case_row is None:
            return standard_path
        remembered = self._remembered_image_directory()
        if remembered is not None:
            return remembered / standard_path.name
        return standard_path

    def _batch_image_dialog_dir(self, rows: Sequence[CaseRow]) -> Path:
        standard_dir = resolve_batch_image_dir(rows, self._input_path_context())
        remembered = self._remembered_image_directory()
        return remembered if remembered is not None else standard_dir

    def _remember_image_directory(self, directory: Path) -> None:
        if self._input_path is not None:
            self._last_image_directory = directory

    def save_view_image(self) -> None:
        """Capture the displayed viewport without enforcing artifact freshness."""
        default_path = self._view_image_dialog_path()
        if default_path is None:
            self.logln("[WARN] No viewport is available to save.")
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save View Image",
            str(default_path),
            "PNG (*.png);;JPEG (*.jpg *.jpeg);;TIFF (*.tif *.tiff)",
        )
        if not path:
            return
        image_path = Path(path).expanduser()
        try:
            self._make_directory(image_path.parent)
        except Exception as exc:
            self.logln(f"[ERROR] Failed to create image directory: {exc}")
            return
        if self._display_case_row is not None:
            self._remember_image_directory(image_path.parent)
        try:
            self.plotter.screenshot(str(image_path))
        except Exception as exc:
            self.logln(f"[ERROR] Failed to save image: {exc}")
            return
        self.logln(f"[OK] Saved image: {image_path}")

    def save_images_for_case_rows(self, rows: Sequence[CaseRow]) -> None:
        """Save current, exact-matching selected artifacts as ordered PNGs."""
        selected = tuple(rows)
        if not selected:
            self.logln("[WARN] No selected cases.")
            return
        default_dir = self._batch_image_dialog_dir(selected)
        selected_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select Folder to Save Selected Images",
            str(default_dir),
        )
        if not selected_dir:
            return
        output_dir = Path(selected_dir).expanduser()
        try:
            self._make_directory(output_dir)
        except Exception as exc:
            self.logln(f"[ERROR] Failed to create image directory: {exc}")
            return
        self._remember_image_directory(output_dir)

        saved = 0
        skipped = 0
        reserved_paths: set[Path] = set()
        self.logln(f"[SAVE] Batch image export start: {len(selected)} case(s)")
        for row in selected:
            if self._save_case_image(row, output_dir, reserved_paths):
                saved += 1
            else:
                skipped += 1
            try:
                self._process_events()
            except Exception as exc:
                self.logln(f"[ERROR] Failed to process GUI events: {exc}")
        self.logln(f"[SAVE] Batch image export done: saved={saved}, skipped={skipped}")

    def _save_case_image(
        self,
        row: CaseRow,
        output_dir: Path,
        reserved_paths: set[Path] | None = None,
    ) -> bool:
        case_id = str(row.get("case_id", "")).strip()
        if not case_id:
            self.logln("[SKIP] Missing case_id in selected row.")
            return False
        vtp_path = resolve_case_vtp_path(row, self._input_path_context())
        if not self._path_exists(vtp_path):
            self.logln(f"[SKIP] VTP not found: {vtp_path}")
            return False
        try:
            artifact = self._artifact_reader(str(vtp_path))
        except Exception as exc:
            self.logln(f"[ERROR] Failed to read VTP for '{case_id}': {exc}")
            return False
        if self.spec.adapters is None:
            self.logln(f"[ERROR] No artifact matcher adapter for '{case_id}'.")
            return False
        try:
            candidates = self.spec.adapters.build_case_signatures(row)
            matched = match_artifact_case(artifact, row, candidates).matched
        except Exception as exc:
            self.logln(f"[ERROR] Failed to match VTP for '{case_id}': {exc}")
            return False
        if not matched:
            self.logln(f"[SKIP] VTP signature mismatch for '{case_id}': {vtp_path}")
            return False
        if not self.load_vtp(str(vtp_path), poly=artifact, case_row=row):
            return False
        scalar_name = self._selected_scalar_name()
        if scalar_name is None:
            self.logln(f"[SKIP] No scalar is available for '{case_id}'.")
            return False
        reserved = set() if reserved_paths is None else reserved_paths
        image_path = auto_rename_path(
            output_dir / default_image_filename(case_id, scalar_name),
            path_exists=self._path_exists,
            reserved_paths=reserved,
        )
        reserved.add(image_path)
        try:
            self.plotter.screenshot(str(image_path))
        except Exception as exc:
            self.logln(f"[ERROR] Failed to save image for '{case_id}': {exc}")
            return False
        self.logln(f"[OK] Saved image: {image_path}")
        return True

    def set_view_vector(self, vector: tuple[float, float, float]) -> None:
        self.plotter.view_vector(vector)
        self.plotter.render()

    def _current_velocity_hat(self) -> np.ndarray | None:
        if self._display_case_row is None or self.spec.adapters is None:
            return None
        try:
            vector = np.asarray(
                self.spec.adapters.resolve_velocity_hat_stl(self._display_case_row),
                dtype=np.float64,
            )
        except Exception:
            return None
        if vector.shape != (3,) or not np.isfinite(vector).all():
            return None
        norm = float(np.linalg.norm(vector))
        if norm == 0.0:
            return None
        return vector / norm

    def set_view_wind(self) -> None:
        velocity = self._current_velocity_hat()
        if velocity is None:
            self.logln("[WARN] Wind view is unavailable for the displayed VTP.")
            return
        self.set_view_vector(tuple((-velocity).tolist()))

    def set_view_wind_reverse(self) -> None:
        velocity = self._current_velocity_hat()
        if velocity is None:
            self.logln("[WARN] Reverse-wind view is unavailable for the displayed VTP.")
            return
        self.set_view_vector(tuple(velocity.tolist()))

    def _automatic_limits(self, scalar: str) -> tuple[float, float] | None:
        if self._poly is None or scalar not in self._scalar_fields:
            return None
        try:
            automatic = scalar_color_limits(
                self._scalar_fields[scalar],
                self._poly.cell_data[scalar],
            )
        except Exception:
            return None
        minimum_text = self.edit_vmin.text().strip()
        maximum_text = self.edit_vmax.text().strip()
        try:
            minimum = float(minimum_text) if minimum_text else automatic[0]
            maximum = float(maximum_text) if maximum_text else automatic[1]
        except ValueError:
            return automatic
        if not np.isfinite((minimum, maximum)).all():
            return automatic
        if minimum == maximum:
            maximum = minimum + 1.0e-12
        return (minimum, maximum)

    def _update_overlay(self) -> None:
        if self._overlay_actor is not None:
            try:
                self.plotter.remove_actor(self._overlay_actor)
            except Exception:
                pass
            self._overlay_actor = None
        if not self.chk_overlay_text.isChecked():
            return
        if self._display_case_row is not None:
            text = self.spec.format_case(self._display_case_row)
        elif self._poly is not None:
            case_id = field_data_scalar(self._poly, "case_id")
            text = f"case_id={case_id}" if case_id else ""
        else:
            text = ""
        if not text:
            text = "(no case info for displayed VTP)"
        self._overlay_actor = self.plotter.add_text(
            text,
            position="upper_left",
            font_size=10,
        )

    def _capture_camera_state(self) -> dict[str, object] | None:
        try:
            camera = self.plotter.camera
            return {
                "position": tuple(camera.position),
                "focal_point": tuple(camera.focal_point),
                "up": tuple(camera.up),
                "clipping_range": tuple(camera.clipping_range),
                "parallel_projection": bool(camera.parallel_projection),
                "parallel_scale": float(camera.parallel_scale),
            }
        except Exception:
            return None

    def _restore_camera_state(self, state: dict[str, object] | None) -> bool:
        if state is None:
            return False
        try:
            camera = self.plotter.camera
            for name, value in state.items():
                setattr(camera, name, value)
            return True
        except Exception:
            return False

    @QtCore.Slot()
    def update_view(self) -> None:
        if self._poly is None:
            return
        previous_camera = (
            self._capture_camera_state() if self._camera_initialized else None
        )
        self.plotter.clear()
        scalar_name = self._selected_scalar_name()
        common = {
            "scalars": scalar_name,
            "cmap": self.cmb_cmap.currentText(),
            "clim": self._automatic_limits(scalar_name or ""),
            "show_edges": self.chk_edges.isChecked(),
        }
        if scalar_name is not None:
            common["scalar_bar_args"] = {
                "title": self.spec.scalar_labels.get(scalar_name, scalar_name)
            }
        shield = self._shield_mask()
        if shield is None:
            self.plotter.add_mesh(self._poly, opacity=1.0, **common)
        else:
            self._add_shield_groups(shield, common)
        self._update_overlay()
        self.plotter.add_axes()
        if not self._restore_camera_state(previous_camera):
            self.plotter.reset_camera()
            self.plotter.view_vector(self._default_view_vec)
        self._camera_initialized = True
        self.plotter.render()

    def _shield_mask(self) -> np.ndarray | None:
        if self._poly is None:
            return None
        try:
            values = np.asarray(self._poly.cell_data["shielded"])
        except Exception:
            return None
        if values.shape != (self._poly.n_cells,):
            return None
        return values.astype(bool)

    def _add_shield_groups(self, shield: np.ndarray, common: dict[str, object]) -> None:
        for masked, opacity in (
            (False, 1.0),
            (True, 0.30 if self.chk_shield_transparent.isChecked() else 1.0),
        ):
            indices = np.flatnonzero(shield == masked)
            if indices.size == 0:
                continue
            subset = self._poly.extract_cells(indices)
            self.plotter.add_mesh(subset, opacity=opacity, **common)


__all__ = ("ViewerPanel",)
