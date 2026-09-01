"""Generate the two maintained GUI-guide screenshots on a normal display."""

from __future__ import annotations

import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from panelsolver.app.gui_bootstrap import _configure_application, create_main_window
from panelsolver.app.gui_theme import ThemeMode, apply_application_theme
from panelsolver.app.solver_spec import GuiRunRequest
from panelsolver.app.viewer_data import ArtifactViewStatus
from panelsolver.gui import canonical_gui_spec

try:
    from scripts.gui_visual_smoke import capture_main_window
except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
    from gui_visual_smoke import capture_main_window

ROOT = Path(__file__).resolve().parents[1]
SOURCE_INPUT = ROOT / "examples" / "hypersonic" / "pressure_models.csv"
SOURCE_GEOMETRY = (
    ROOT / "examples" / "geometry" / "plate.stl",
    ROOT / "examples" / "geometry" / "cube.stl",
)
SANITIZED_INPUT_TEXT = "examples/hypersonic/pressure_models.csv"
WINDOW_SIZE = QtCore.QSize(1480, 900)
MAX_IMAGE_WIDTH = 1480


@dataclass(frozen=True, slots=True)
class ScreenshotContract:
    """One documentation screenshot and the real GUI state it must show."""

    filename: str
    selected_case_id: str | None
    artifact_status: ArtifactViewStatus
    scalar_name: str | None


SCREENSHOTS = (
    ScreenshotContract(
        "gui-overview.png",
        None,
        ArtifactViewStatus.EMPTY,
        None,
    ),
    ScreenshotContract(
        "gui-result.png",
        "newt_pm",
        ArtifactViewStatus.CURRENT,
        "cp",
    ),
)


def _copy_example_workspace(destination: Path) -> Path:
    """Copy only the input and geometry needed by the maintained captures."""
    input_path = destination / "examples" / "hypersonic" / SOURCE_INPUT.name
    geometry_dir = destination / "examples" / "geometry"
    input_path.parent.mkdir(parents=True)
    geometry_dir.mkdir(parents=True)
    shutil.copy2(SOURCE_INPUT, input_path)
    for source in SOURCE_GEOMETRY:
        shutil.copy2(source, geometry_dir / source.name)
    return input_path


def _case_row_index(rows, case_id: str) -> int:
    matches = [
        index
        for index, row in enumerate(rows)
        if str(row.get("case_id", "")).strip() == case_id
    ]
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one case_id={case_id!r}; found {matches}")
    return matches[0]


def _generate_result(spec, input_path: Path):
    """Generate newt_pm through the current GUI adapter/runtime path."""
    if spec.adapters is None:
        raise RuntimeError("Hypersonic GUI adapters are not configured")
    rows = tuple(spec.adapters.read_cases(input_path))
    row = rows[_case_row_index(rows, "newt_pm")]
    result = spec.adapters.run_cases(
        GuiRunRequest(
            rows=(row,),
            workers=1,
            checkpoint_every_cases=0,
            output_path=input_path.parent / "outputs" / "docs-screenshot-summary.csv",
            log=lambda _message: None,
            progress=lambda _done, _total: None,
            cancel_requested=lambda: False,
        )
    )
    if result.calculation_completed_cases != 1 or result.vtp_saved != 1:
        raise RuntimeError("newt_pm screenshot calculation did not save one VTP")
    if result.output_issues:
        raise RuntimeError(
            f"newt_pm screenshot calculation had output errors: {result.output_issues}"
        )
    return rows


def _process_events(application: QtWidgets.QApplication) -> None:
    application.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 100)
    application.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 100)


def _prepare_window(application, spec, input_path: Path):
    window = create_main_window(spec)
    window.resize(WINDOW_SIZE)
    window.show()
    _process_events(application)
    window.splitter.setSizes((610, 830))
    if not window.cases_panel.load_input_file(
        input_path,
        remember_directory=False,
    ):
        raise RuntimeError("temporary Hypersonic input could not be loaded")
    window.cases_panel.case_table.clearSelection()
    window.cases_panel.case_table.setCurrentCell(-1, -1)
    _process_events(application)

    # Preserve the real loaded path for matching and layout, but sanitize its
    # visible presentation before any pixels are captured.
    window.cases_panel.input_value.setText(SANITIZED_INPUT_TEXT)
    window.cases_panel.input_value.setToolTip(SANITIZED_INPUT_TEXT)
    window.cases_panel.input_value.setAccessibleDescription(SANITIZED_INPUT_TEXT)
    _process_events(application)
    return window


def _select_result(window, rows) -> None:
    row_index = _case_row_index(rows, "newt_pm")
    table = window.cases_panel.case_table
    table.selectRow(row_index)
    table.setCurrentCell(row_index, 0)
    table.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)


def _assert_window_state(window, contract: ScreenshotContract) -> None:
    selected = window.cases_panel.selected_case_rows()
    selected_ids = tuple(str(row.get("case_id", "")) for row in selected)
    expected_ids = (
        () if contract.selected_case_id is None else (contract.selected_case_id,)
    )
    if selected_ids != expected_ids:
        raise RuntimeError(
            f"unexpected screenshot selection: {selected_ids} != {expected_ids}"
        )
    state = window.viewer_panel.artifact_view_state
    if state.status is not contract.artifact_status:
        raise RuntimeError(
            f"unexpected Viewer provenance: {state.status.value} != "
            f"{contract.artifact_status.value}"
        )
    scalar = window.viewer_panel.cmb_scalar.currentData()
    if scalar != contract.scalar_name:
        raise RuntimeError(
            f"unexpected Viewer scalar: {scalar!r} != {contract.scalar_name!r}"
        )
    if window.cases_panel.btn_diagnostics.isChecked():
        raise RuntimeError("Diagnostics must remain collapsed")
    if window.cases_panel.input_value.text() != SANITIZED_INPUT_TEXT:
        raise RuntimeError("visible input path was not sanitized")


def _normalize_png(path: Path) -> None:
    """Normalize HiDPI grabs to the fixed documentation pixel width."""
    image = QtGui.QImage(str(path))
    if image.isNull():
        raise RuntimeError(f"captured PNG could not be read: {path}")
    if image.width() > MAX_IMAGE_WIDTH:
        image = image.scaledToWidth(
            MAX_IMAGE_WIDTH,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
    image.setDevicePixelRatio(1.0)
    if not image.save(str(path), "PNG"):
        raise RuntimeError(f"normalized PNG could not be saved: {path}")


def _assert_no_private_path_payload(
    path: Path, private_paths: tuple[Path, ...]
) -> None:
    """Reject PNG string payloads containing local path identities."""
    payload = path.read_bytes().lower()
    forbidden = {
        str(value).encode(errors="ignore").lower()
        for value in private_paths
        if str(value)
    }
    leaked = [value for value in forbidden if value and value in payload]
    if leaked:
        raise RuntimeError(f"private path text is embedded in {path.name}")


def main() -> int:
    """Regenerate both committed GUI-guide screenshots."""
    output_dir = ROOT / "docs" / "assets" / "screenshots"
    output_dir.mkdir(parents=True, exist_ok=True)
    spec = canonical_gui_spec("hypersonic")

    with tempfile.TemporaryDirectory(prefix="panelsolver-docs-gui-") as temporary:
        temporary_root = Path(temporary)
        input_path = _copy_example_workspace(temporary_root)
        rows = _generate_result(spec, input_path)

        application = QtWidgets.QApplication.instance()
        if application is None:
            application = QtWidgets.QApplication([sys.argv[0]])
        _configure_application(application)
        apply_application_theme(application, ThemeMode.LIGHT)
        window = _prepare_window(application, spec, input_path)
        try:
            candidate_paths: list[tuple[Path, Path]] = []
            for contract in SCREENSHOTS:
                if contract.selected_case_id is not None:
                    _select_result(window, rows)
                    _process_events(application)
                    window.viewer_panel.plotter.render()
                    _process_events(application)
                _assert_window_state(window, contract)
                candidate = temporary_root / contract.filename
                capture_main_window(window, candidate)
                _normalize_png(candidate)
                _assert_no_private_path_payload(
                    candidate,
                    (temporary_root, ROOT, Path.home()),
                )
                candidate_paths.append((candidate, output_dir / contract.filename))

            for candidate, output in candidate_paths:
                shutil.copyfile(candidate, output)
                print(f"Saved {output.relative_to(ROOT)}")
        finally:
            window.close()
            _process_events(application)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
