#!/usr/bin/env python3
"""Smoke the frozen command surface from an installed wheel outside the repo."""

from __future__ import annotations

import argparse
import copy
import csv
import importlib
import importlib.metadata
import importlib.util
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pyvista as pv

from panelsolver.app.csv_writer import CSV_ENCODING

EXPECTED_COMPATIBILITY_ENTRY_POINTS = {
    "fmfsolver": "fmfsolver.app.gui_app:main",
    "fmfsolver-gui": "fmfsolver.app.gui_app:main",
    "fmfsolver-cli": "fmfsolver.app.cli_app:main",
    "newtsolver": "newtsolver.app.gui_app:main",
    "newtsolver-gui": "newtsolver.app.gui_app:main",
    "newtsolver-cli": "newtsolver.app.cli_app:main",
}
EXPECTED_ENTRY_POINTS = {
    "panelsolver": "panelsolver.cli:main",
    "panelsolver-gui": "panelsolver.gui:main",
    **EXPECTED_COMPATIBILITY_ENTRY_POINTS,
}

EXPECTED_PANEL_CORE_ALL = [
    "ATTITUDE_INPUT_VALUES",
    "WINDWARD_EQUATION_VALUES",
    "LEEWARD_EQUATION_VALUES",
    "_resolve_attitude_mode",
    "normalize_windward_equation",
    "normalize_leeward_equation",
    "modified_newtonian_cp_max",
    "_oblique_theta_from_beta",
    "_tangent_wedge_detach_limit",
    "_weak_oblique_shock_beta",
    "tangent_wedge_pressure_coefficient",
    "_tangent_cone_detach_limit",
    "tangent_cone_pressure_coefficient",
    "_prandtl_meyer_nu",
    "_inverse_prandtl_meyer",
    "resolve_attitude_to_vhat",
    "panel_force_density",
    "stl_to_body",
    "rot_y",
]
EXPECTED_PRESSURE_MODELS_ALL = [
    "modified_newtonian_cp_max",
    "_prandtl_meyer_nu",
    "_inverse_prandtl_meyer",
    "prandtl_meyer_pressure_coefficient",
    "_oblique_theta_from_beta",
    "_tangent_wedge_detach_limit",
    "_weak_oblique_shock_beta",
    "tangent_wedge_pressure_coefficient",
    "_tangent_cone_detach_limit",
    "tangent_cone_pressure_coefficient",
]
EXPECTED_EXPORTER_SIGNATURES = {
    "export_vtp": (
        "(out_path: 'str', vertices: 'np.ndarray', faces: 'np.ndarray', "
        "cell_data: 'dict', field_data: 'dict | None' = None)"
    ),
}
EXPECTED_DIRECT_COMPONENT_KEYS = [
    "scope",
    "component_id",
    "component_stl_path",
    "CA",
    "CY",
    "CN",
    "Cl",
    "Cm",
    "Cn",
    "CD",
    "CL",
    "faces",
    "shielded_faces",
    "vtp_path",
]
MESH_WARNING = "[WARN] Mesh is not watertight (trimesh). Continuing anyway."
EXPECTED_CLI_DESCRIPTIONS = {
    "fmfsolver": "Run FMF solver from CSV/XLSX/XLSM input without GUI.",
    "newtsolver": "Run newtsolver from CSV/XLSX/XLSM input without GUI.",
}
_TUNING_PREFIXES = ("PANELSOLVER_", "FMFSOLVER_", "NEWTSOLVER_")
_EXPECTED_GUI_HELP_MENU = ("Documentation", "", "About")


def _smoke_high_level_api(staging: Path, inputs: Path) -> None:
    import panelsolver
    from panelsolver import (
        FMFCase,
        HypersonicCase,
        ResolvedAttitude,
        SolveResult,
        resolve_attitude,
        solve_fmf,
        solve_hypersonic,
    )

    expected_surface = (
        "FMFCase",
        "HypersonicCase",
        "ResolvedAttitude",
        "SolveResult",
        "resolve_attitude",
        "solve_fmf",
        "solve_hypersonic",
    )
    if panelsolver.__all__ != expected_surface:
        raise RuntimeError(f"unexpected stable API surface: {panelsolver.__all__!r}")
    if hasattr(panelsolver, "SentmanCase") or hasattr(panelsolver, "solve_sentman"):
        raise RuntimeError("removed package-root Sentman API aliases remain")
    if not isinstance(resolve_attitude(0.0, 0.0), ResolvedAttitude):
        raise TypeError("resolve_attitude returned an unexpected stable API type")

    common = {
        "stl_paths": (inputs / "stl" / "plate.stl",),
        "stl_scale_m_per_unit": 1.0,
        "attitude": resolve_attitude(0.0, 0.0),
        "Aref_m2": 1.0,
        "moment_reference_stl_m": (0.0, 0.0, 0.0),
        "Lref_Cl_m": 1.0,
        "Lref_Cm_m": 1.0,
        "Lref_Cn_m": 1.0,
    }
    work = staging / "high-level-api"
    work.mkdir()
    previous = Path.cwd()
    os.chdir(work)
    try:
        fmf = solve_fmf(
            FMFCase(
                case_id="api_fmf",
                **common,
                speed_ratio=5.0,
                translational_temperature_k=300.0,
                wall_temperature_k=300.0,
            )
        )
        hypersonic = solve_hypersonic(
            HypersonicCase(
                case_id="api_hypersonic",
                **common,
                mach=6.0,
                gamma=1.4,
            )
        )
    finally:
        os.chdir(previous)
    if not isinstance(fmf, SolveResult) or not isinstance(hypersonic, SolveResult):
        raise TypeError("high-level solve returned an unexpected type")
    if list(work.iterdir()):
        raise RuntimeError("high-level in-memory solve wrote filesystem artifacts")
    for result in (fmf, hypersonic):
        if result.local_loads.n_faces < 1 or len(result.case_signature) != 64:
            raise RuntimeError("high-level solve result is incomplete")


def _smoke_canonical_gui_entrypoint() -> None:
    from PySide6 import QtCore, QtWidgets

    from fmfsolver.gui_spec import solver_spec as legacy_fmf_spec
    from newtsolver.gui_spec import solver_spec as legacy_hypersonic_spec
    from panelsolver import gui as canonical_gui
    from panelsolver.app.gui_bootstrap import _application_icon, create_main_window
    from panelsolver.app.main_window import MainWindow

    class OffscreenViewer(QtWidgets.QWidget):
        log_message = QtCore.Signal(str)
        save_selected_images_requested = QtCore.Signal()

        def load_vtp(self, *_args) -> None:
            pass

        def clear_view(self) -> None:
            pass

        def set_case_rows(self, *_args) -> None:
            pass

        def set_input_path(self, *_args) -> None:
            pass

        def save_images_for_case_rows(self, *_args) -> None:
            pass

    _application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    if _application_icon().isNull():
        raise RuntimeError("installed wheel application icon is not loadable")
    entry = next(
        item
        for item in importlib.metadata.distribution("panelsolver").entry_points
        if item.group == "console_scripts" and item.name == "panelsolver-gui"
    )
    launcher = entry.load()
    expected = {
        "fmf": ("fmf", "sentman", "Panel Solver — FMF"),
        "hypersonic": (
            "hypersonic",
            "hypersonic",
            "Panel Solver — Hypersonic",
        ),
    }
    constructed: list[tuple[str, str, str]] = []

    def verify_help_menu(window, *, identity: str) -> None:
        actions = tuple(action.text() for action in window.help_menu.actions())
        if actions != _EXPECTED_GUI_HELP_MENU:
            raise RuntimeError(f"{identity} GUI Help menu changed: {actions!r}")

    def construct(spec, argv):
        if len(argv) != 1:
            raise RuntimeError(f"canonical GUI leaked dispatcher arguments: {argv!r}")
        window = create_main_window(
            spec,
            window_factory=lambda selected: MainWindow(
                selected,
                viewer_panel=OffscreenViewer(),
            ),
        )
        constructed.append((spec.product_id, spec.model_id, window.windowTitle()))
        verify_help_menu(window, identity="canonical")
        window.close()
        return 0

    original = canonical_gui.run_gui
    canonical_gui.run_gui = construct
    try:
        for domain in expected:
            if launcher([domain]) != 0:
                raise RuntimeError(f"canonical GUI {domain} launcher failed")
    finally:
        canonical_gui.run_gui = original
    if constructed != list(expected.values()):
        raise RuntimeError(f"canonical GUI identity changed: {constructed!r}")

    legacy_expected = (
        ("fmfsolver", "sentman", "Sentman FMF Solver (GUI)"),
        ("newtsolver", "hypersonic", "newtsolver (GUI)"),
    )
    legacy_constructed: list[tuple[str, str, str]] = []
    for spec in (legacy_fmf_spec(), legacy_hypersonic_spec()):
        window = create_main_window(
            spec,
            window_factory=lambda selected: MainWindow(
                selected,
                viewer_panel=OffscreenViewer(),
            ),
        )
        legacy_constructed.append(
            (spec.product_id, spec.model_id, window.windowTitle())
        )
        verify_help_menu(window, identity="legacy")
        window.close()
    if tuple(legacy_constructed) != legacy_expected:
        raise RuntimeError(f"legacy GUI identity changed: {legacy_constructed!r}")


def _smoke_subprocess_environment(staging: Path) -> dict[str, str]:
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(_TUNING_PREFIXES)
    }
    cache_root = staging / "subprocess-cache"
    cache_paths = {
        "XDG_CACHE_HOME": cache_root / "xdg",
        "MPLCONFIGDIR": cache_root / "matplotlib",
        "PYVISTA_USERDATA_PATH": cache_root / "pyvista",
        "LOCALAPPDATA": cache_root / "local-app-data",
    }
    for path in cache_paths.values():
        path.mkdir(parents=True, exist_ok=True)
    environment.update(
        {
            "COLUMNS": "80",
            "LINES": "24",
            "QT_QPA_PLATFORM": "offscreen",
            **{name: str(path) for name, path in cache_paths.items()},
        }
    )
    return environment


def _expected_backend_hint(*, embree: bool) -> str:
    if embree:
        return "[INFO] Ray backend: Embree (ray_pyembree)."
    return (
        "[INFO] Ray backend: rtree (ray_triangle). Optional acceleration is "
        "available: uv sync --extra rayaccel (or pip install "
        '"panelsolver[rayaccel]").'
    )


def _command_path(name: str) -> Path:
    scripts = Path(sys.executable).parent
    suffix = ".exe" if sys.platform == "win32" else ""
    return scripts / f"{name}{suffix}"


def _prepare_current_inputs(inputs: Path) -> None:
    """Remove the retired column from staged historical sample evidence."""
    for historical_npz in inputs.rglob("*.npz"):
        historical_npz.unlink()
    for path in (inputs / "fmfsolver_cases.csv", inputs / "newtsolver_cases.csv"):
        with path.open(encoding=CSV_ENCODING, newline="") as stream:
            reader = csv.DictReader(stream)
            rows = list(reader)
            columns = [name for name in (reader.fieldnames or ()) if name != "save_npz_on"]
        with path.open("w", encoding=CSV_ENCODING, newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows({name: row[name] for name in columns} for row in rows)


def _prepare_current_excel_inputs(inputs: Path) -> dict[str, dict[str, Path]]:
    prepared: dict[str, dict[str, Path]] = {}
    for product in ("fmfsolver", "newtsolver"):
        source = inputs / f"{product}_cases.csv"
        frame = pd.read_csv(source, encoding=CSV_ENCODING).iloc[[0]].copy()
        frame["save_vtp_on"] = 0
        xlsx = inputs / f"{product}_cases.xlsx"
        xlsm = inputs / f"{product}_cases.xlsm"
        frame.to_excel(xlsx, index=False, engine="openpyxl")
        shutil.copyfile(xlsx, xlsm)
        prepared[product] = {".xlsx": xlsx, ".xlsm": xlsm}
    return prepared


def _load_phase1_comparator(repository: Path):
    script = repository / "scripts" / "generate_phase1_goldens.py"
    spec = importlib.util.spec_from_file_location("installed_wheel_comparator", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load Phase 1 semantic comparator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validate_cli_help(product: str, help_text: str) -> None:
    required = (
        EXPECTED_CLI_DESCRIPTIONS[product],
        "--input INPUT",
        "--output OUTPUT",
        "--workers WORKERS",
        "--cases CASES [CASES ...]",
        "--checkpoint-every-cases CHECKPOINT_EVERY_CASES",
        "--verbose",
        "--plain",
        "--debug",
    )
    missing = [fragment for fragment in required if fragment not in help_text]
    if f"usage: {product}-cli" not in help_text.casefold():
        missing.insert(0, f"usage: {product}-cli")
    if missing:
        raise RuntimeError(f"{product} help is missing Phase 8 contract: {missing}")


def _smoke_direct_exporters(staging: Path) -> None:
    vertices = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
        dtype=np.float32,
    )
    faces = np.array([[0, 1, 2]], dtype=np.int32)
    cell_data = {"Cp_n": np.array([1.25], dtype=np.float32)}
    field_data = {"case_id": "installed-direct"}
    for product in ("fmfsolver", "newtsolver"):
        module_name = f"{product}.io.exporters"
        module = importlib.import_module(module_name)
        io_module = importlib.import_module(f"{product}.io")
        if hasattr(module, "export_npz") or hasattr(io_module, "export_npz"):
            raise RuntimeError(f"{product} still exports removed NPZ API")
        for name, expected_signature in EXPECTED_EXPORTER_SIGNATURES.items():
            function = getattr(module, name)
            if str(inspect.signature(function)) != expected_signature:
                raise RuntimeError(f"{module_name}.{name} signature changed")
            if function.__name__ != name or function.__module__ != module_name:
                raise RuntimeError(f"{module_name}.{name} identity changed")

        output = staging / "direct-exporters" / product
        vtp_path = output / "direct.vtp"
        result = module.export_vtp(
            out_path=vtp_path,
            vertices=vertices,
            faces=faces,
            cell_data=cell_data,
            field_data=field_data,
        )
        if result is not None:
            raise RuntimeError(f"{module_name}.export_vtp must return None")
        poly = pv.read(vtp_path)
        if list(poly.cell_data) != list(cell_data):
            raise RuntimeError(f"{module_name}.export_vtp cell names changed")
        if list(poly.field_data) != list(field_data):
            raise RuntimeError(f"{module_name}.export_vtp metadata names changed")
        if not np.array_equal(poly.cell_data["Cp_n"], cell_data["Cp_n"]):
            raise RuntimeError(f"{module_name}.export_vtp cell values changed")
        if poly.cell_data["Cp_n"].dtype != cell_data["Cp_n"].dtype:
            raise RuntimeError(f"{module_name}.export_vtp cell dtype changed")
        expected_case_id = np.asarray([field_data["case_id"]])
        if not np.array_equal(poly.field_data["case_id"], expected_case_id):
            raise RuntimeError(f"{module_name}.export_vtp metadata changed")


def _smoke_direct_solver_results(staging: Path, inputs: Path) -> None:
    products = (
        ("fmfsolver", "fmfsolver_cases.csv", 3),
        ("newtsolver", "newtsolver_cases.csv", 6),
    )
    runtime = importlib.import_module("panelsolver.app.runtime")
    for product, filename, multi_index in products:
        runtime_product_id = {
            "fmfsolver": "fmf",
            "newtsolver": "hypersonic",
        }[product]
        reader = importlib.import_module(f"{product}.io.io_cases").read_cases
        solver = importlib.import_module(f"{product}.core.solver")
        source = reader(inputs / filename)
        row = source.iloc[multi_index].to_dict()
        output = staging / "direct-solvers" / product
        row.update(out_dir=str(output), save_vtp_on=0)

        runtime._RAY_ACCEL_HINTED_PRODUCTS.discard(runtime_product_id)
        direct_logs: list[str] = []
        result = solver.run_case(row, direct_logs.append)
        if direct_logs not in ([], [MESH_WARNING]):
            raise RuntimeError(
                f"{product} direct-case logs contain unexpected output: {direct_logs!r}"
            )
        if runtime_product_id in runtime._RAY_ACCEL_HINTED_PRODUCTS:
            raise RuntimeError(f"{product} direct case consumed backend hint")

        owned = LookupError(f"{product} installed hint callback")

        def fail_hint(_message: str, error: BaseException = owned) -> None:
            raise error

        try:
            solver.run_cases(source.iloc[0:0], fail_hint)
        except BaseException as exc:
            if exc is not owned:
                raise RuntimeError(
                    f"{product} empty hint callback identity changed"
                ) from exc
        else:
            raise RuntimeError(f"{product} empty hint callback error was ignored")
        if runtime_product_id in runtime._RAY_ACCEL_HINTED_PRODUCTS:
            raise RuntimeError(f"{product} failed hint callback consumed state")

        empty_logs: list[str] = []
        empty = solver.run_cases(source.iloc[0:0], empty_logs.append)
        if not empty.empty or tuple(empty.shape) != (0, 0):
            raise RuntimeError(f"{product} empty direct batch result changed")
        expected_hint = _expected_backend_hint(
            embree=bool(runtime.trimesh_ray.has_embree),
        )
        if empty_logs != [expected_hint]:
            raise RuntimeError(f"{product} empty backend hint changed: {empty_logs!r}")
        if runtime_product_id not in runtime._RAY_ACCEL_HINTED_PRODUCTS:
            raise RuntimeError(f"{product} successful backend hint was not recorded")
        hot_logs: list[str] = []
        solver.run_cases(source.iloc[0:0], hot_logs.append)
        if hot_logs:
            raise RuntimeError(f"{product} repeated empty hint: {hot_logs!r}")

        components = result["component_rows"]
        expected_sources = row["stl_path"].split(";")
        if any(list(item) != EXPECTED_DIRECT_COMPONENT_KEYS for item in components):
            raise RuntimeError(f"{product} component row schema changed")
        expected_types = (
            str,
            int,
            str,
            float,
            float,
            float,
            float,
            float,
            float,
            float,
            float,
            int,
            int,
            str,
        )
        if any(
            tuple(type(value) for value in item.values()) != expected_types
            for item in components
        ):
            raise RuntimeError(f"{product} component row value types changed")
        if result["component_id"] != "" or type(result["component_id"]) is not str:
            raise RuntimeError(f"{product} total component_id type/blank changed")
        if (
            result["component_stl_path"] != ""
            or type(result["component_stl_path"]) is not str
        ):
            raise RuntimeError(f"{product} total component_stl_path changed")
        if result["vtp_path"] != "" or "npz_path" in result:
            raise RuntimeError(f"{product} disabled total artifact paths changed")
        if [item["component_id"] for item in components] != [0, 1] or not all(
            type(item["component_id"]) is int for item in components
        ):
            raise RuntimeError(f"{product} component IDs changed")
        if [item["component_stl_path"] for item in components] != expected_sources:
            raise RuntimeError(f"{product} component STL order changed")
        if any(item["vtp_path"] != "" for item in components):
            raise RuntimeError(f"{product} component artifact paths changed")


def _smoke_direct_solver_errors(staging: Path, inputs: Path) -> None:
    products = (
        ("fmfsolver", "fmfsolver_cases.csv"),
        ("newtsolver", "newtsolver_cases.csv"),
    )
    for product, filename in products:
        reader = importlib.import_module(f"{product}.io.io_cases").read_cases
        solver = importlib.import_module(f"{product}.core.solver")
        source = reader(inputs / filename)
        cancel_calls = 0

        def cancel() -> bool:
            nonlocal cancel_calls
            cancel_calls += 1
            return True

        try:
            solver.run_cases(
                source.iloc[0:0],
                lambda _message: None,
                cancel_cb=cancel,
            )
        except BaseException as exc:
            if (
                type(exc) is not RuntimeError
                or str(exc) != "Canceled by user."
                or exc.__cause__ is not None
                or exc.__context__ is not None
            ):
                raise RuntimeError(f"{product} empty cancellation changed") from exc
        else:
            raise RuntimeError(f"{product} empty cancellation was ignored")
        if cancel_calls != 1:
            raise RuntimeError(f"{product} empty cancellation callback count changed")

        missing = staging / "direct-errors" / product / "missing.stl"
        try:
            missing.resolve().open("rb")
        except FileNotFoundError as exc:
            expected_missing_message = str(exc)
        else:
            raise RuntimeError("installed-wheel missing-STL fixture exists")
        row = source.iloc[0].to_dict()
        row.update(
            stl_path=str(missing),
            out_dir=str(staging / "direct-errors" / product / "serial"),
            save_vtp_on=1,
        )
        try:
            solver.run_case(row, lambda _message: None)
        except BaseException as exc:
            if (
                type(exc) is not FileNotFoundError
                or str(exc) != expected_missing_message
                or exc.__cause__ is not None
                or exc.__context__ is not None
            ):
                raise RuntimeError(f"{product} serial missing-STL error changed") from exc
        else:
            raise RuntimeError(f"{product} serial missing STL succeeded")

        parallel = source.iloc[[0, 0]].copy().reset_index(drop=True)
        parallel["case_id"] = [f"{product}-missing-0", f"{product}-missing-1"]
        parallel["stl_path"] = str(missing)
        parallel["out_dir"] = [
            str(staging / "direct-errors" / product / "parallel-0"),
            str(staging / "direct-errors" / product / "parallel-1"),
        ]
        parallel["save_vtp_on"] = 1
        try:
            solver.run_cases(parallel, lambda _message: None, workers=2)
        except BaseException as exc:
            expected_first_line = f"[WorkerError] {expected_missing_message}"
            if (
                type(exc) is not RuntimeError
                or str(exc).splitlines()[0] != expected_first_line
                or "FileNotFoundError:" not in str(exc)
                or exc.__cause__ is not None
                or exc.__context__ is not None
            ):
                raise RuntimeError(
                    f"{product} parallel missing-STL error changed"
                ) from exc
        else:
            raise RuntimeError(f"{product} parallel missing STL succeeded")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("--dist-dir", type=Path)
    return parser.parse_args(argv)


def _smoke_packaged_documentation() -> None:
    from panelsolver.docs_site import DocumentationSite

    with DocumentationSite() as site:
        root = site.resolve().parent
        for page in ("index.html", "solvers/fmf.html", "solvers/hypersonic.html"):
            if not site.resolve(page).is_file():
                raise RuntimeError(f"installed documentation page is missing: {page}")
        for legal_name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            if not (root / legal_name).is_file():
                raise RuntimeError(f"installed documentation file is missing: {legal_name}")


def _smoke_packaged_examples(staging: Path) -> None:
    from panelsolver.app import ExampleLibrary
    from panelsolver.domains import fmf, hypersonic

    library = ExampleLibrary()
    for module, domain in ((fmf, "fmf"), (hypersonic, "hypersonic")):
        for example in module.gui_spec().examples:
            destination = (
                staging
                / "packaged-examples"
                / domain
                / Path(example.input_resource).stem
            )
            input_path = library.copy_example(example, destination)
            frame = module.read_cases(input_path)
            if frame.empty:
                raise RuntimeError(f"installed example did not load: {input_path}")
            for raw in frame["stl_path"]:
                for raw_path in str(raw).split(";"):
                    if not Path(raw_path).is_file():
                        raise RuntimeError(
                            f"installed example geometry is missing: {raw_path}"
                        )


def _extract_release_archives(
    repository: Path,
    dist_dir: Path,
    staging: Path,
) -> Path:
    with (repository / "pyproject.toml").open("rb") as stream:
        version = str(tomllib.load(stream)["project"]["version"])
    docs_zip = dist_dir / f"panelsolver-docs-v{version}.zip"
    examples_zip = dist_dir / f"panelsolver-examples-v{version}.zip"
    destinations = (staging / "offline-docs", staging / "release-examples")
    for archive_path, destination in zip((docs_zip, examples_zip), destinations, strict=True):
        with zipfile.ZipFile(archive_path) as archive:
            for name in archive.namelist():
                member = Path(name)
                if member.is_absolute() or ".." in member.parts or "\\" in name:
                    raise RuntimeError(f"unsafe release archive member: {name}")
            archive.extractall(destination)
    if not (destinations[0] / "index.html").is_file():
        raise RuntimeError("docs ZIP does not extract with index.html at its root")
    return destinations[1]


def _smoke_release_examples(
    examples_root: Path,
    staging: Path,
    environment: dict[str, str],
) -> None:
    cases = (
        ("fmf", "basic.csv"),
        ("fmf", "flow_modes.csv"),
        ("fmf", "attitude_modes.csv"),
        ("fmf", "shielding.csv"),
        ("hypersonic", "basic.csv"),
        ("hypersonic", "pressure_models.csv"),
        ("hypersonic", "attitude_modes.csv"),
        ("hypersonic", "shielding.csv"),
    )
    command = _command_path("panelsolver")
    results = staging / "release-example-results"
    results.mkdir()
    for domain, filename in cases:
        result = subprocess.run(
            [
                command,
                domain,
                "--input",
                examples_root / "examples" / domain / filename,
                "--output",
                results / f"{domain}-{Path(filename).stem}.csv",
                "--workers",
                "1",
                "--checkpoint-every-cases",
                "0",
            ],
            cwd=examples_root,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"release example failed: {domain}/{filename}\n"
                f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
            )


def _cli_input_for_available_backends(
    source: Path,
    *,
    product: str,
) -> tuple[Path, set[str]]:
    runtime = importlib.import_module("panelsolver.app.runtime")
    if runtime.trimesh_ray.has_embree:
        return source, set()
    with source.open(encoding=CSV_ENCODING, newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or ())
    excluded = {
        str(row.get("case_id", ""))
        for row in rows
        if str(row.get("ray_backend", "")).strip().casefold() == "embree"
    }
    selected = [row for row in rows if str(row.get("case_id", "")) not in excluded]
    filtered = source.with_name(f"{product}_installed_supported.csv")
    with filtered.open("w", encoding=CSV_ENCODING, newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(selected)
    return filtered, excluded


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repository = args.repository.resolve()
    dist_dir = args.dist_dir.resolve() if args.dist_dir is not None else None
    contracts = repository / "tests" / "fixtures" / "phase1" / "golden"
    installed_version = importlib.metadata.version("panelsolver")
    legacy_artifact_versions = {"1.3.8", "1.0.3"}
    installed = {
        entry.name: entry.value
        for entry in importlib.metadata.distribution("panelsolver").entry_points
        if entry.group == "console_scripts"
    }
    if installed != EXPECTED_ENTRY_POINTS:
        raise RuntimeError(f"Unexpected console scripts: {installed}")
    requirements = importlib.metadata.distribution("panelsolver").requires or ()
    if any("xlrd" in requirement.casefold() for requirement in requirements):
        raise RuntimeError("installed wheel still requires removed xlrd dependency")
    if any(
        requirement.casefold().startswith(("mkdocs", "latex2mathml"))
        for requirement in requirements
    ):
        raise RuntimeError("documentation build dependency leaked into runtime")

    contract_data = {
        product: json.loads(
            (contracts / product / "contracts.json").read_text(encoding="utf-8")
        )
        for product in ("fmfsolver", "newtsolver")
    }
    comparator = _load_phase1_comparator(repository)
    manifest = json.loads(
        (repository / "tests" / "fixtures" / "phase1" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    for product, version in (("fmfsolver", "1.3.8"), ("newtsolver", "1.0.3")):
        package = importlib.import_module(product)
        if package.__all__ != []:
            raise RuntimeError(f"{product} root __all__ changed: {package.__all__!r}")
        if package.__version__ != version:
            raise RuntimeError(f"{product} compatibility version changed")
        for module_name in contract_data[product]["module_paths"]:
            importlib.import_module(module_name)

    panel_core = importlib.import_module("newtsolver.core.panel_core")
    pressure_models = importlib.import_module("newtsolver.core.pressure_models")
    if panel_core.__all__ != EXPECTED_PANEL_CORE_ALL:
        raise RuntimeError("newtsolver.core.panel_core.__all__ changed")
    if pressure_models.__all__ != EXPECTED_PRESSURE_MODELS_ALL:
        raise RuntimeError("newtsolver.core.pressure_models.__all__ changed")
    neutral_core = importlib.import_module("panelsolver.core")
    neutral_app = importlib.import_module("panelsolver.app")
    for name in (
        "legacy_adapter",
        "legacy_mesh",
        "legacy_results",
        "legacy_scheduler",
        "legacy_shielding",
        "legacy_signatures",
    ):
        if importlib.util.find_spec(f"panelsolver.app.{name}") is not None:
            raise RuntimeError(f"compatibility implementation remains in app: {name}")
        if importlib.util.find_spec(f"panelsolver._compat.{name}") is None:
            raise RuntimeError(f"installed wheel is missing private compat module: {name}")
    for module, names in (
        (neutral_core, ("NpzProjection", "project_npz_artifact")),
        (neutral_app, ("write_npz_projection",)),
    ):
        present = [name for name in names if hasattr(module, name)]
        if present:
            raise RuntimeError(f"removed neutral NPZ API remains: {present}")
    removed_cache_api = [
        name
        for name in ("ResultCache", "ResultCacheError", "ResultCacheStats")
        if hasattr(neutral_core, name)
    ]
    if removed_cache_api:
        raise RuntimeError(f"removed result-cache API remains: {removed_cache_api}")
    if importlib.util.find_spec("panelsolver.core.result_cache") is not None:
        raise RuntimeError("removed panelsolver.core.result_cache module remains")
    if "result_cache" in inspect.signature(neutral_core.execute_case).parameters:
        raise RuntimeError("execute_case still accepts removed result_cache keyword")
    if "cache_hit" in neutral_core.CaseExecutionResult.__dataclass_fields__:
        raise RuntimeError("CaseExecutionResult still exposes result-cache state")

    with tempfile.TemporaryDirectory() as temp_dir:
        staging = Path(temp_dir)
        subprocess_environment = _smoke_subprocess_environment(staging)
        os.environ.clear()
        os.environ.update(subprocess_environment)
        _smoke_direct_exporters(staging)
        inputs = staging / "inputs"
        shutil.copytree(
            repository / "tests" / "fixtures" / "phase1" / "inputs",
            inputs,
        )
        _prepare_current_inputs(inputs)
        excel_inputs = _prepare_current_excel_inputs(inputs)
        _smoke_high_level_api(staging, inputs)
        _smoke_packaged_documentation()
        _smoke_packaged_examples(staging)
        _smoke_canonical_gui_entrypoint()
        _smoke_direct_solver_results(staging, inputs)
        _smoke_direct_solver_errors(staging, inputs)
        if dist_dir is not None:
            release_examples = _extract_release_archives(repository, dist_dir, staging)
            _smoke_release_examples(release_examples, staging, subprocess_environment)
        canonical = _command_path("panelsolver")
        canonical_gui = _command_path("panelsolver-gui")
        for arguments in (("--help",), ("fmf", "--help"), ("hypersonic", "--help")):
            gui_help = subprocess.run(
                [canonical_gui, *arguments],
                cwd=staging,
                capture_output=True,
                text=True,
                check=False,
                env=subprocess_environment,
            )
            if gui_help.returncode != 0 or "panelsolver-gui" not in gui_help.stdout:
                raise RuntimeError(
                    f"canonical GUI help failed for {arguments!r}:\n"
                    f"stdout={gui_help.stdout!r}\nstderr={gui_help.stderr!r}"
                )
        canonical_help = subprocess.run(
            [canonical, "--help"],
            cwd=staging,
            capture_output=True,
            text=True,
            check=False,
            env=subprocess_environment,
        )
        canonical_help_required = (
            "Run Panel Solver using a canonical flow-domain selector.",
            "{fmf,hypersonic}",
        )
        if (
            canonical_help.returncode != 0
            or "usage: panelsolver" not in canonical_help.stdout.casefold()
            or any(
                fragment not in canonical_help.stdout
                for fragment in canonical_help_required
            )
        ):
            raise RuntimeError(
                "canonical help failed:\n"
                f"stdout={canonical_help.stdout!r}\nstderr={canonical_help.stderr!r}"
            )
        canonical_cases = {
            "fmf": (
                "fmfsolver",
                "fmf_zero_plate",
                "Run the Sentman free-molecular-flow model from CSV/XLSX/XLSM input.",
            ),
            "hypersonic": (
                "newtsolver",
                "newt_zero_newtonian",
                "Run hypersonic panel models from CSV/XLSX/XLSM input.",
            ),
        }
        for domain, (product, case_id, description) in canonical_cases.items():
            domain_help = subprocess.run(
                [canonical, domain, "--help"],
                cwd=staging,
                capture_output=True,
                text=True,
                check=False,
                env=subprocess_environment,
            )
            if (
                domain_help.returncode != 0
                or f"usage: panelsolver {domain}"
                not in domain_help.stdout.casefold()
                or description not in domain_help.stdout
                or "Input cases file (.csv/.xlsx/.xlsm)" not in domain_help.stdout
                or "--cases CASES [CASES ...]" not in domain_help.stdout
                or "--checkpoint-every-cases" not in domain_help.stdout
                or "--verbose" not in domain_help.stdout
                or "--plain" not in domain_help.stdout
                or "--debug" not in domain_help.stdout
            ):
                raise RuntimeError(
                    f"canonical {domain} help failed:\n"
                    f"stdout={domain_help.stdout!r}\nstderr={domain_help.stderr!r}"
                )
            output = staging / f"canonical_{domain}_results.csv"
            canonical_run = subprocess.run(
                [
                    canonical,
                    domain,
                    "--input",
                    inputs / f"{product}_cases.csv",
                    "--output",
                    output,
                    "--cases",
                    case_id,
                    "--workers",
                    "1",
                    "--checkpoint-every-cases",
                    "0",
                ],
                cwd=staging,
                capture_output=True,
                text=True,
                check=False,
                env=subprocess_environment,
            )
            if canonical_run.returncode != 0 or not output.is_file():
                raise RuntimeError(
                    f"canonical {domain} run failed:\n"
                    f"stdout={canonical_run.stdout!r}\n"
                    f"stderr={canonical_run.stderr!r}"
                )
            header = output.read_text(encoding=CSV_ENCODING).splitlines()[0]
            if "npz" in header.casefold():
                raise RuntimeError(f"canonical {domain} restored NPZ output")
            with output.open(encoding=CSV_ENCODING, newline="") as stream:
                canonical_rows = list(csv.DictReader(stream))
            canonical_versions = {
                row["solver_version"] for row in canonical_rows
            }
            if canonical_versions != {installed_version}:
                raise RuntimeError(
                    f"canonical {domain} artifact version changed: "
                    f"{canonical_versions!r}"
                )
            canonical_total = next(
                row for row in canonical_rows if row["scope"] == "total"
            )
            canonical_vtp = pv.read(canonical_total["vtp_path"])
            if str(canonical_vtp.field_data["solver_version"][0]) != installed_version:
                raise RuntimeError(f"canonical {domain} CSV/VTP versions differ")
            for suffix, input_path in excel_inputs[product].items():
                format_output = (
                    staging / "canonical-format-smoke" / domain / f"{suffix[1:]}.csv"
                )
                format_output.parent.mkdir(parents=True, exist_ok=True)
                format_run = subprocess.run(
                    [
                        canonical,
                        domain,
                        "--input",
                        input_path,
                        "--output",
                        format_output,
                        "--workers",
                        "1",
                        "--checkpoint-every-cases",
                        "0",
                    ],
                    cwd=staging,
                    capture_output=True,
                    text=True,
                    check=False,
                    env=subprocess_environment,
                )
                if format_run.returncode != 0 or not format_output.is_file():
                    raise RuntimeError(
                        f"canonical {domain} {suffix} run failed:\n"
                        f"stdout={format_run.stdout!r}\n"
                        f"stderr={format_run.stderr!r}"
                    )
        for product in ("fmfsolver", "newtsolver"):
            command = _command_path(f"{product}-cli")
            cli_input, excluded_cases = _cli_input_for_available_backends(
                inputs / f"{product}_cases.csv",
                product=product,
            )
            help_result = subprocess.run(
                [command, "--help"],
                cwd=staging,
                capture_output=True,
                text=True,
                check=False,
                env=subprocess_environment,
            )
            if help_result.returncode != 0:
                raise RuntimeError(
                    f"{product} help failed: {help_result.returncode}\n"
                    f"stdout={help_result.stdout!r}\nstderr={help_result.stderr!r}"
                )
            _validate_cli_help(product, help_result.stdout)
            if "Input cases file (.csv/.xlsx/.xlsm)" not in help_result.stdout:
                raise RuntimeError(f"{product} help advertises stale input formats")

            empty_cases = subprocess.run(
                [command, "--input", "cases.csv", "--cases"],
                cwd=staging,
                capture_output=True,
                text=True,
                check=False,
                env=subprocess_environment,
            )
            if empty_cases.returncode != 2 or "expected at least one argument" not in (
                empty_cases.stderr
            ):
                raise RuntimeError(
                    f"{product} explicit empty --cases did not fail in argparse: "
                    f"{empty_cases.returncode}\nstdout={empty_cases.stdout!r}\n"
                    f"stderr={empty_cases.stderr!r}"
                )

            output = staging / f"{product}_results.csv"
            run_result = subprocess.run(
                [
                    command,
                    "--input",
                    cli_input,
                    "--output",
                    output,
                    "--workers",
                    "1",
                    "--checkpoint-every-cases",
                    "0",
                ],
                cwd=staging,
                capture_output=True,
                text=True,
                check=False,
                env=subprocess_environment,
            )
            if run_result.returncode != 0:
                raise RuntimeError(
                    f"{product} sample failed:\n{run_result.stdout}\n{run_result.stderr}"
                )
            with output.open(encoding=CSV_ENCODING, newline="") as stream:
                reader = csv.DictReader(stream)
                rows = list(reader)
                columns = list(reader.fieldnames or ())
            contract = contract_data[product]["cli_run"]
            expected_columns = [
                name
                for name in contract["result_csv_columns"]
                if name not in {"save_npz_on", "npz_path"}
            ]
            if columns != expected_columns:
                raise RuntimeError(f"{product} result columns changed")
            if "save_npz_on" in columns or "npz_path" in columns:
                raise RuntimeError(f"{product} summary retains removed NPZ columns")
            current_versions = {row["solver_version"] for row in rows}
            if current_versions != {installed_version}:
                raise RuntimeError(
                    f"{product} artifact version changed: {current_versions!r}"
                )
            if not legacy_artifact_versions.isdisjoint(current_versions):
                raise RuntimeError(f"{product} emitted a legacy artifact version")
            case_order = [row["case_id"] for row in rows if row["scope"] == "total"]
            expected_case_order = [
                case_id
                for case_id in contract["case_order"]
                if case_id not in excluded_cases
            ]
            if case_order != expected_case_order:
                raise RuntimeError(f"{product} case order changed: {case_order}")
            semantic_csv = comparator._read_semantic_csv(
                output,
                roots={inputs.resolve(): "<fixture-root>"},
            )
            for case_id in case_order:
                vtp_path = inputs / "outputs" / f"{case_id}.vtp"
                if not vtp_path.is_file():
                    raise RuntimeError(f"{product} did not write VTP for {case_id}")
                golden = json.loads(
                    (contracts / product / f"{case_id}.json").read_text(
                        encoding="utf-8"
                    )
                )
                expected = {
                    "csv": {
                        "columns": expected_columns,
                        "rows": [
                            {
                                name: value
                                for name, value in row.items()
                                if name not in {"save_npz_on", "npz_path"}
                            }
                            for row in golden["csv"]["rows"]
                        ],
                    },
                    "vtp": copy.deepcopy(golden["vtp"]),
                }
                for expected_row in expected["csv"]["rows"]:
                    expected_row["solver_version"] = installed_version
                expected["vtp"]["field_data"]["solver_version"]["values"] = [
                    installed_version
                ]
                actual = {
                    "csv": {
                        "columns": semantic_csv["columns"],
                        "rows": [
                            row
                            for row in semantic_csv["rows"]
                            if row["case_id"] == case_id
                        ],
                    },
                    "vtp": comparator._read_vtp(
                        vtp_path,
                        roots={inputs.resolve(): "<fixture-root>"},
                    ),
                }
                actual_csv_versions = {
                    row["solver_version"] for row in actual["csv"]["rows"]
                }
                actual_vtp_version = actual["vtp"]["field_data"][
                    "solver_version"
                ]["values"][0]
                if (
                    actual_csv_versions != {installed_version}
                    or actual_vtp_version != installed_version
                ):
                    raise RuntimeError(
                        f"{product} CSV/VTP distribution versions differ for "
                        f"{case_id}"
                    )
                differences = comparator._compare_values(
                    expected,
                    actual,
                    manifest=manifest,
                    profile_name=golden["provenance"]["tolerance_profile"],
                )
                if differences:
                    raise RuntimeError(
                        f"{product} installed semantics differ for {case_id}: "
                        f"{differences[:5]}"
                    )
            if list(inputs.rglob("*.npz")):
                raise RuntimeError(f"{product} unexpectedly wrote NPZ output")

            for suffix, input_path in excel_inputs[product].items():
                format_output = staging / "format-smoke" / product / f"{suffix[1:]}.csv"
                format_output.parent.mkdir(parents=True, exist_ok=True)
                format_result = subprocess.run(
                    [
                        command,
                        "--input",
                        input_path,
                        "--output",
                        format_output,
                        "--workers",
                        "1",
                        "--checkpoint-every-cases",
                        "0",
                    ],
                    cwd=staging,
                    capture_output=True,
                    text=True,
                    check=False,
                    env=subprocess_environment,
                )
                if format_result.returncode != 0 or not format_output.is_file():
                    raise RuntimeError(
                        f"{product} {suffix} input failed:\n"
                        f"{format_result.stdout}\n{format_result.stderr}"
                    )

            rejected_output = staging / "format-smoke" / product / "xls.csv"
            rejected = subprocess.run(
                [
                    command,
                    "--input",
                    inputs / f"{product}_cases.xls",
                    "--output",
                    rejected_output,
                ],
                cwd=staging,
                capture_output=True,
                text=True,
                check=False,
                env=subprocess_environment,
            )
            rejection_text = f"{rejected.stdout}\n{rejected.stderr}"
            if (
                rejected.returncode == 0
                or rejected_output.exists()
                or "Legacy .xls input is no longer supported" not in rejection_text
                or ".xlsx" not in rejection_text
                or ".csv" not in rejection_text
            ):
                raise RuntimeError(
                    f"{product} legacy .xls migration rejection changed:\n"
                    f"{rejection_text}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
