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
import pkgutil
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

    from fmfsolver._frontend import _legacy_gui_spec as legacy_fmf_spec
    from newtsolver._frontend import _legacy_gui_spec as legacy_hypersonic_spec
    from panelsolver import gui as canonical_gui
    from panelsolver.app import gui_bootstrap
    from panelsolver.app.gui_bootstrap import _application_icon, create_main_window
    from panelsolver.app.main_window import MainWindow

    class OffscreenViewer(QtWidgets.QWidget):
        log_message = QtCore.Signal(str)
        save_selected_images_requested = QtCore.Signal()

        def load_vtp(self, *_args) -> None:
            pass

        def clear_view(self) -> None:
            pass

        def invalidate_vtp_artifact(self, _path: str) -> None:
            pass

        def set_case_rows(self, *_args) -> None:
            pass

        def set_selected_case_rows(self, *_args) -> None:
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

    legacy_commands = {
        "fmfsolver": legacy_expected[0],
        "fmfsolver-gui": legacy_expected[0],
        "newtsolver": legacy_expected[1],
        "newtsolver-gui": legacy_expected[1],
    }
    legacy_dispatched: list[tuple[str, str, str]] = []

    def capture_legacy(spec) -> int:
        legacy_dispatched.append((spec.product_id, spec.model_id, spec.window_title))
        return 0

    entry_points = {
        item.name: item
        for item in importlib.metadata.distribution("panelsolver").entry_points
        if item.group == "console_scripts"
    }
    original_run_gui = gui_bootstrap.run_gui
    gui_bootstrap.run_gui = capture_legacy
    try:
        for command in legacy_commands:
            try:
                entry_points[command].load()()
            except SystemExit as exc:
                if exc.code != 0:
                    raise RuntimeError(f"legacy GUI command failed: {command}") from exc
            else:
                raise RuntimeError(f"legacy GUI command did not exit: {command}")
    finally:
        gui_bootstrap.run_gui = original_run_gui
    if legacy_dispatched != list(legacy_commands.values()):
        raise RuntimeError(f"legacy GUI dispatch changed: {legacy_dispatched!r}")


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


def _record_array(record: dict[str, object]) -> np.ndarray:
    return np.asarray(record["values"]).reshape(record["shape"])


def _float_array_record(value: np.ndarray) -> dict[str, object]:
    array = np.asarray(value)
    return {
        "dtype": f"float{array.dtype.itemsize * 8}",
        "shape": list(array.shape),
        "values": array.tolist(),
    }


def _current_expected_vtp(product: str, golden: dict[str, object]) -> dict[str, object]:
    expected = copy.deepcopy(golden["vtp"])
    cell_data = expected["cell_data"]
    legacy_normal = cell_data.pop("Cp_n")
    if product == "newtsolver":
        cell_data["cp"] = legacy_normal
        return expected
    if product != "fmfsolver":
        raise ValueError(f"unknown installed-smoke product: {product!r}")

    cell_data["normal_traction_coeff"] = legacy_normal
    normals_out_stl = _record_array(
        golden["npz"]["arrays"]["normals_out_stl"]
    )
    velocity_hat_stl = _record_array(golden["npz"]["arrays"]["Vhat_stl"])
    normal_dot_velocity = normals_out_stl @ velocity_hat_stl
    tangent_stl = (
        velocity_hat_stl[None, :]
        - normal_dot_velocity[:, None] * normals_out_stl
    )
    tangent_norm = np.linalg.norm(tangent_stl, axis=1)
    tangent_hat_stl = np.zeros_like(tangent_stl)
    defined = tangent_norm > 1.0e-12
    tangent_hat_stl[defined] = (
        tangent_stl[defined]
        / tangent_norm[defined, None]
    )
    c_face_stl = _record_array(golden["vtp"]["cell_data"]["C_face_stl"])
    area_m2 = _record_array(golden["vtp"]["cell_data"]["area_m2"])
    aref_m2 = golden["normalized_input"]["Aref_m2"]
    traction_coeff_stl = c_face_stl * (aref_m2 / area_m2)[:, None]
    tangential_traction_coeff = np.einsum(
        "ij,ij->i",
        traction_coeff_stl,
        tangent_hat_stl,
    )
    cell_data["tangential_traction_coeff"] = _float_array_record(
        tangential_traction_coeff
    )
    return expected


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
    expected_frontend_modules = {
        "fmfsolver": {
            "fmfsolver._frontend",
            "fmfsolver.app",
            "fmfsolver.app.cli_app",
            "fmfsolver.app.gui_app",
        },
        "newtsolver": {
            "newtsolver._frontend",
            "newtsolver.app",
            "newtsolver.app.cli_app",
            "newtsolver.app.gui_app",
        },
    }
    for product in ("fmfsolver", "newtsolver"):
        package = importlib.import_module(product)
        if hasattr(package, "__all__") or hasattr(package, "__version__"):
            raise RuntimeError(f"{product} still advertises a direct-Python API")
        modules = {
            module.name
            for module in pkgutil.walk_packages(
                package.__path__,
                prefix=f"{product}.",
            )
        }
        if modules != expected_frontend_modules[product]:
            raise RuntimeError(f"unexpected {product} module inventory: {modules!r}")

    neutral_core = importlib.import_module("panelsolver.core")
    neutral_app = importlib.import_module("panelsolver.app")
    for name in ("legacy_adapter", "legacy_mesh", "legacy_results", "legacy_scheduler", "legacy_shielding"):
        if importlib.util.find_spec(f"panelsolver.app.{name}") is not None:
            raise RuntimeError(f"compatibility implementation remains in app: {name}")
        if importlib.util.find_spec(f"panelsolver._compat.{name}") is not None:
            raise RuntimeError(f"removed private compat module remains: {name}")
    if importlib.util.find_spec("panelsolver._compat.legacy_signatures") is None:
        raise RuntimeError("legacy artifact signature fallback is missing")
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
                    "vtp": _current_expected_vtp(product, golden),
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
