#!/usr/bin/env python3
"""Generate or verify Phase 1 semantic goldens from pinned legacy commits.

The generator never imports from or writes into a legacy checkout.  It verifies
the checkout, archives the exact commit into a temporary directory, creates
locked base and ray-accelerated environments there, and captures meaning from
CSV, VTP, and NPZ outputs.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import importlib.metadata
import io
import json
import math
import os
import pkgutil
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from panelsolver.app.csv_writer import CSV_ENCODING

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "phase1"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
DEFAULT_GOLDEN_ROOT = FIXTURE_ROOT / "golden"

SOLVER_PREFIX = {"fmfsolver": "fmf", "newtsolver": "newt"}
ENVIRONMENT_PREFIX = {"fmfsolver": "FMFSOLVER", "newtsolver": "NEWTSOLVER"}
RUNTIME_PACKAGES = (
    "numpy",
    "scipy",
    "pandas",
    "trimesh",
    "rtree",
    "pyvista",
    "vtk",
)
TEXT_CSV_COLUMNS = {
    "case_id",
    "stl_path",
    "windward_eq",
    "leeward_eq",
    "attitude_input",
    "ray_backend",
    "out_dir",
    "fixture_note",
    "solver_version",
    "case_signature",
    "run_started_at_utc",
    "run_finished_at_utc",
    "mode",
    "out_attitude_input",
    "scope",
    "component_stl_path",
    "ray_backend_used",
    "vtp_path",
    "npz_path",
}
CSV_INPUT_COLUMNS = {
    "case_id",
    "stl_path",
    "stl_scale_m_per_unit",
    "S",
    "Ti_K",
    "Mach",
    "Altitude_km",
    "Tw_K",
    "gamma",
    "windward_eq",
    "leeward_eq",
    "alpha_deg",
    "beta_or_bank_deg",
    "attitude_input",
    "ref_x_m",
    "ref_y_m",
    "ref_z_m",
    "Aref_m2",
    "Lref_Cl_m",
    "Lref_Cm_m",
    "Lref_Cn_m",
    "shielding_on",
    "ray_backend",
    "out_dir",
    "save_vtp_on",
    "save_npz_on",
    "fixture_note",
}
GEOMETRY_QUANTITY_NAMES = {
    "vertices",
    "points",
    "centers_stl_m",
    "center_x_stl_m",
    "center_y_stl_m",
    "center_z_stl_m",
    "normals_out_stl",
    "areas_m2",
    "area_m2",
    "Vhat_stl",
    "theta_deg",
    "alpha_t_deg_resolved",
    "beta_t_deg_resolved",
}
SIGNATURE_MARKER = "<case-signature:path-and-version-dependent>"
TIMESTAMP_MARKER = "<utc-timestamp>"
ELAPSED_MARKER = "<nonnegative-elapsed-seconds>"
CSV_NAN_MARKER = "<numeric-nan>"
CSV_POSITIVE_INFINITY_MARKER = "<positive-infinity>"
CSV_NEGATIVE_INFINITY_MARKER = "<negative-infinity>"
EMBREE_DISTRIBUTION_MARKER = "<platform-specific-embree-distribution>"
EMBREE_VERSION_MARKER = "<platform-specific-embree-version>"


class Phase1GenerationError(RuntimeError):
    """Raised when a pinned source or generated capture violates the manifest."""


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(
        value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False
    )
    path.write_text(text + "\n", encoding="utf-8")


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str] | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=None if env is None else dict(env),
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
    )
    if completed.returncode != 0:
        detail = ""
        if capture_output:
            detail = f"\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        raise Phase1GenerationError(
            f"Command failed ({completed.returncode}): {' '.join(command)}{detail}"
        )
    return completed


def _git_text(repo: Path, *args: str) -> str:
    result = _run(("git", *args), cwd=repo, capture_output=True)
    return result.stdout.strip()


def _normalized_remote(remote: str) -> str:
    value = remote.strip().removesuffix(".git").rstrip("/")
    if value.startswith("git@github.com:"):
        value = "https://github.com/" + value.split(":", 1)[1]
    return value


def _verify_legacy_checkout(repo: Path, source: Mapping[str, Any]) -> None:
    if not (repo / ".git").exists():
        raise Phase1GenerationError(f"Legacy source is not a Git checkout: {repo}")
    expected_commit = str(source["commit"])
    actual_commit = _git_text(repo, "rev-parse", "HEAD")
    if actual_commit != expected_commit:
        raise Phase1GenerationError(
            f"{repo} HEAD is {actual_commit}; expected pinned commit {expected_commit}."
        )
    tracked_status = _git_text(repo, "status", "--porcelain", "--untracked-files=no")
    if tracked_status:
        raise Phase1GenerationError(
            f"Legacy checkout has tracked modifications: {repo}"
        )
    actual_remote = _normalized_remote(_git_text(repo, "remote", "get-url", "origin"))
    expected_remote = _normalized_remote(str(source["repository"]))
    if actual_remote != expected_remote:
        raise Phase1GenerationError(
            f"{repo} origin is {actual_remote}; expected {expected_remote}."
        )


def _archive_commit(repo: Path, commit: str, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination.parent / f"{destination.name}.tar"
    _run(
        ("git", "archive", "--format=tar", f"--output={archive}", commit),
        cwd=repo,
    )
    with tarfile.open(archive, mode="r") as stream:
        try:
            stream.extractall(destination, filter="data")
        except TypeError:  # pragma: no cover - Python 3.11 fallback for contributors
            stream.extractall(destination)


def _environment_python(environment: Path) -> Path:
    if os.name == "nt":
        return environment / "Scripts" / "python.exe"
    return environment / "bin" / "python"


def _sync_environment(
    source: Path,
    environment: Path,
    *,
    rayaccel: bool,
    python_version: str,
) -> Path:
    env = _clean_legacy_environment()
    env["UV_PROJECT_ENVIRONMENT"] = str(environment)
    # Keep the environment outside the immutable archive. By default the two
    # profiles share a temporary cache; an explicit caller UV_CACHE_DIR is
    # honored for offline/repeated verification.
    env["UV_CACHE_DIR"] = os.environ.get(
        "UV_CACHE_DIR", str(environment.parent / "uv-cache")
    )
    command = ["uv", "sync", "--locked", "--python", python_version]
    if rayaccel:
        command.extend(("--extra", "rayaccel"))
    _run(command, cwd=source, env=env)
    python = _environment_python(environment)
    if not python.exists():
        raise Phase1GenerationError(f"uv did not create expected interpreter: {python}")
    actual_version = _run(
        (
            str(python),
            "-c",
            "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
        ),
        cwd=source,
        env=env,
        capture_output=True,
    ).stdout.strip()
    if actual_version != python_version:
        raise Phase1GenerationError(
            f"uv created Python {actual_version}; expected {python_version}."
        )
    return python


def _run_legacy_suite(python: Path, *, source: Path, scratch: Path) -> dict[str, Any]:
    command = [
        str(python),
        "-m",
        "unittest",
        "discover",
        "-s",
        "tests",
        "-p",
        "test_*.py",
        "-v",
    ]
    env = _clean_legacy_environment()
    env["MPLCONFIGDIR"] = str(scratch / "mpl-test-cache")
    env["XDG_CACHE_HOME"] = str(scratch / "xdg-test-cache")
    completed = _run(command, cwd=source, env=env, capture_output=True)
    transcript = completed.stdout + completed.stderr
    match = re.search(r"Ran (\d+) tests? in ", transcript)
    if match is None or not re.search(r"\nOK(?:\n|$)", transcript):
        raise Phase1GenerationError(
            "Legacy unittest transcript has no successful summary"
        )
    return {
        "command": "python -m unittest discover -s tests -p test_*.py -v",
        "tests_run": int(match.group(1)),
        "status": "passed",
    }


def _clean_legacy_environment() -> dict[str, str]:
    env = os.environ.copy()
    for name in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"):
        env.pop(name, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONHASHSEED"] = "0"
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["COLUMNS"] = "80"
    env["LINES"] = "24"
    for prefix in ENVIRONMENT_PREFIX.values():
        for suffix in (
            "SHIELD_CACHE_MAX",
            "SHIELD_BATCH_SIZE",
            "PARALLEL_CHUNK_CASES",
        ):
            env.pop(f"{prefix}_{suffix}", None)
    return env


def _capture_environment(
    python: Path,
    *,
    source: Path,
    solver: str,
    input_root: Path,
    environment_name: str,
    output: Path,
    probe_only: bool,
) -> None:
    command = [
        str(python),
        str(Path(__file__).resolve()),
        "_capture",
        "--solver",
        solver,
        "--input-root",
        str(input_root),
        "--environment-name",
        environment_name,
        "--output",
        str(output),
    ]
    if probe_only:
        command.append("--probe-only")
    env = _clean_legacy_environment()
    env["MPLCONFIGDIR"] = str(output.parent / "mpl-cache")
    env["XDG_CACHE_HOME"] = str(output.parent / "xdg-cache")
    _run(command, cwd=source, env=env)


def _source_case_index(
    manifest: Mapping[str, Any], solver: str
) -> dict[str, dict[str, Any]]:
    return {str(item["case_id"]): dict(item) for item in manifest["cases"][solver]}


def _build_solver_capture(
    *,
    solver: str,
    legacy_repo: Path,
    source_metadata: Mapping[str, Any],
    manifest: Mapping[str, Any],
    staging_root: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    _verify_legacy_checkout(legacy_repo, source_metadata)
    source = staging_root / solver / "source"
    _archive_commit(legacy_repo, str(source_metadata["commit"]), source)

    base_python = _sync_environment(
        source,
        staging_root / solver / "venv-base",
        rayaccel=False,
        python_version=str(manifest["generation"]["python"]),
    )
    accel_python = _sync_environment(
        source,
        staging_root / solver / "venv-rayaccel",
        rayaccel=True,
        python_version=str(manifest["generation"]["python"]),
    )
    legacy_suite = _run_legacy_suite(
        base_python,
        source=source,
        scratch=staging_root / solver,
    )

    base_inputs = staging_root / solver / "inputs-base"
    accel_inputs = staging_root / solver / "inputs-rayaccel"
    shutil.copytree(FIXTURE_ROOT / "inputs", base_inputs)
    shutil.copytree(FIXTURE_ROOT / "inputs", accel_inputs)

    base_capture_path = staging_root / solver / "capture-base.json"
    accel_capture_path = staging_root / solver / "capture-rayaccel.json"
    _capture_environment(
        base_python,
        source=source,
        solver=solver,
        input_root=base_inputs,
        environment_name="locked",
        output=base_capture_path,
        probe_only=True,
    )
    _capture_environment(
        accel_python,
        source=source,
        solver=solver,
        input_root=accel_inputs,
        environment_name="rayaccel",
        output=accel_capture_path,
        probe_only=False,
    )

    base_capture = _load_json(base_capture_path)
    accel_capture = _load_json(accel_capture_path)
    expected_cases = _source_case_index(manifest, solver)
    actual_ids = set(accel_capture["cases"])
    if actual_ids != set(expected_cases):
        raise Phase1GenerationError(
            f"{solver} case mismatch: expected {sorted(expected_cases)}, got {sorted(actual_ids)}"
        )

    provenance_common = {
        "source_repository": source_metadata["repository"],
        "source_commit": source_metadata["commit"],
        "source_version": source_metadata["version"],
        "source_lock_sha256": hashlib.sha256(
            (source / "uv.lock").read_bytes()
        ).hexdigest(),
        "generation_command": manifest["generation"]["command"],
        "python": manifest["generation"]["python"],
    }
    base_environment, rayaccel_environment = manifest["generation"]["environments"]
    cases: dict[str, dict[str, Any]] = {}
    for case_id, capture in accel_capture["cases"].items():
        case_metadata = expected_cases[case_id]
        total_rows = [
            row for row in capture["csv"]["rows"] if row.get("scope") == "total"
        ]
        if len(total_rows) != 1:
            raise Phase1GenerationError(
                f"{solver}/{case_id} has no unique total CSV row"
            )
        effective = total_rows[0]["ray_backend_used"]
        requested = capture["normalized_input"]["ray_backend"]
        expected_requested = case_metadata["requested_backend"]
        if requested != expected_requested:
            raise Phase1GenerationError(
                f"{solver}/{case_id} requested {requested}; "
                f"expected {expected_requested}."
            )
        expected_effective = case_metadata["expected_effective_backend"]
        if effective != expected_effective:
            raise Phase1GenerationError(
                f"{solver}/{case_id} used {effective}; expected {expected_effective}."
            )
        cases[case_id] = {
            "schema_version": 1,
            "provenance": {
                **provenance_common,
                "environment": rayaccel_environment,
                "case_id": case_id,
                "requested_backend": case_metadata["requested_backend"],
                "effective_backend": effective,
                "tolerance_profile": case_metadata["tolerance_profile"],
                "coverage": case_metadata["coverage"],
            },
            **capture,
        }

    contracts = {
        "schema_version": 1,
        "provenance": {
            **provenance_common,
            "environments": [base_environment, rayaccel_environment],
            "legacy_suite_environment": base_environment,
            "cli_run_environment": rayaccel_environment,
        },
        "package": base_capture["package"],
        "cli": base_capture["cli"],
        "module_paths": base_capture["module_paths"],
        "invalid_inputs": base_capture["invalid_inputs"],
        "legacy_suite": legacy_suite,
        "environments": {
            "locked": base_capture["environment"],
            "rayaccel": accel_capture["environment"],
        },
        "cli_run": accel_capture["cli_run"],
    }
    return contracts, cases


def _write_capture_tree(
    output_root: Path,
    captures: Mapping[str, tuple[dict[str, Any], dict[str, dict[str, Any]]]],
) -> None:
    expected_paths: set[Path] = set()
    for solver, (contracts, cases) in captures.items():
        contract_path = output_root / solver / "contracts.json"
        _write_json(contract_path, contracts)
        expected_paths.add(contract_path)
        for case_id, capture in cases.items():
            case_path = output_root / solver / f"{case_id}.json"
            _write_json(case_path, capture)
            expected_paths.add(case_path)
    if output_root.exists():
        for existing in output_root.rglob("*.json"):
            if existing not in expected_paths:
                existing.unlink()


def _tolerance_for_path(
    manifest: Mapping[str, Any], profile_name: str, path: Sequence[str]
) -> tuple[float, float]:
    profile = manifest["tolerance_profiles"][profile_name]
    tolerance_name = profile["default"]
    semantic_path = "/".join(path)
    if (
        "normalized_input" in path
        or ("csv" in path and "rows" in path and path[-1] in CSV_INPUT_COLUMNS)
        or any(
            fnmatchcase(semantic_path, str(pattern))
            for pattern in manifest.get("exact_numeric_paths", [])
        )
    ):
        tolerance_name = profile["discrete"]
    elif any(part in GEOMETRY_QUANTITY_NAMES for part in path):
        tolerance_name = profile["geometry"]
    else:
        matches = {
            str(override["tolerance"])
            for override in profile.get("path_overrides", [])
            if any(
                fnmatchcase(semantic_path, str(pattern))
                for pattern in override["paths"]
            )
        }
        if len(matches) > 1:
            raise Phase1GenerationError(
                f"Conflicting tolerances {sorted(matches)} for {semantic_path}"
            )
        if matches:
            tolerance_name = matches.pop()
    tolerance = manifest["tolerances"][tolerance_name]
    return float(tolerance["atol"]), float(tolerance["rtol"])


def _compare_values(
    expected: Any,
    actual: Any,
    *,
    manifest: Mapping[str, Any],
    profile_name: str,
    path: tuple[str, ...] = (),
) -> list[str]:
    display = "/".join(path) or "<root>"
    if isinstance(expected, bool) or isinstance(actual, bool):
        return (
            []
            if expected is actual
            else [f"{display}: expected {expected!r}, got {actual!r}"]
        )
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        if isinstance(expected, int):
            if isinstance(actual, int) and expected == actual:
                return []
            return [f"{display}: expected exact integer {expected}, got {actual!r}"]
        atol, rtol = _tolerance_for_path(manifest, profile_name, path)
        expected_float = float(expected)
        actual_float = float(actual)
        if not math.isfinite(expected_float) or not math.isfinite(actual_float):
            return [
                (f"{display}: non-finite numeric comparison {expected!r} != {actual!r}")
            ]
        difference = abs(actual_float - expected_float)
        limit = atol + rtol * abs(expected_float)
        if difference <= limit:
            return []
        return [
            (
                f"{display}: expected {expected!r}, got {actual!r} "
                f"(difference={difference}, limit={limit}, "
                f"atol={atol}, rtol={rtol})"
            )
        ]
    if type(expected) is not type(actual):
        return [
            f"{display}: type mismatch {type(expected).__name__} != {type(actual).__name__}"
        ]
    if isinstance(expected, dict):
        differences: list[str] = []
        expected_keys = set(expected)
        actual_keys = set(actual)
        if expected_keys != actual_keys:
            missing = sorted(expected_keys - actual_keys)
            extra = sorted(actual_keys - expected_keys)
            differences.append(f"{display}: missing keys={missing}, extra keys={extra}")
        for key in sorted(expected_keys & actual_keys):
            differences.extend(
                _compare_values(
                    expected[key],
                    actual[key],
                    manifest=manifest,
                    profile_name=profile_name,
                    path=(*path, str(key)),
                )
            )
        return differences
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return [f"{display}: length {len(expected)} != {len(actual)}"]
        differences = []
        for index, (expected_item, actual_item) in enumerate(
            zip(expected, actual, strict=True)
        ):
            differences.extend(
                _compare_values(
                    expected_item,
                    actual_item,
                    manifest=manifest,
                    profile_name=profile_name,
                    path=(*path, str(index)),
                )
            )
        return differences
    return (
        []
        if expected == actual
        else [f"{display}: expected {expected!r}, got {actual!r}"]
    )


def compare_capture_trees(
    expected_root: Path,
    actual_root: Path,
    manifest: Mapping[str, Any],
) -> list[str]:
    """Return semantic differences between two generated golden directories."""
    expected_files = {
        path.relative_to(expected_root) for path in expected_root.rglob("*.json")
    }
    actual_files = {
        path.relative_to(actual_root) for path in actual_root.rglob("*.json")
    }
    differences: list[str] = []
    if expected_files != actual_files:
        differences.append(
            "golden file set differs: "
            f"missing={sorted(str(p) for p in expected_files - actual_files)}, "
            f"extra={sorted(str(p) for p in actual_files - expected_files)}"
        )
    for relative in sorted(expected_files & actual_files):
        expected = _load_json(expected_root / relative)
        actual = _load_json(actual_root / relative)
        profile_name = "fmf_default"
        if relative.name != "contracts.json":
            profile_name = expected["provenance"]["tolerance_profile"]
        differences.extend(
            f"{relative}: {message}"
            for message in _compare_values(
                expected,
                actual,
                manifest=manifest,
                profile_name=profile_name,
            )
        )
    return differences


def _generate(args: argparse.Namespace) -> int:
    manifest = _load_json(MANIFEST_PATH)
    repos = {
        "fmfsolver": Path(args.fmf_repo).expanduser().resolve(),
        "newtsolver": Path(args.newt_repo).expanduser().resolve(),
    }
    output_root = Path(args.output).expanduser().resolve()
    with tempfile.TemporaryDirectory(prefix="panel-solvers-phase1-") as temp:
        staging_root = Path(temp)
        captures = {
            solver: _build_solver_capture(
                solver=solver,
                legacy_repo=repos[solver],
                source_metadata=manifest["sources"][solver],
                manifest=manifest,
                staging_root=staging_root,
            )
            for solver in ("fmfsolver", "newtsolver")
        }
        generated_root = staging_root / "generated"
        _write_capture_tree(generated_root, captures)
        if args.check:
            differences = compare_capture_trees(output_root, generated_root, manifest)
            if differences:
                print("Phase 1 golden verification failed:", file=sys.stderr)
                for difference in differences[:200]:
                    print(f"- {difference}", file=sys.stderr)
                if len(differences) > 200:
                    print(
                        f"- ... {len(differences) - 200} more differences",
                        file=sys.stderr,
                    )
                return 1
            print(f"Phase 1 semantic goldens match: {output_root}")
            return 0
        _write_capture_tree(output_root, captures)
        print(f"Generated Phase 1 semantic goldens: {output_root}")
    return 0


def _normalize_string(value: str, *, key: str, roots: Mapping[Path, str]) -> str:
    if key == "stl_paths_json":
        try:
            paths = json.loads(value)
        except json.JSONDecodeError as exc:
            raise Phase1GenerationError(f"Invalid stl_paths_json: {value!r}") from exc
        if not isinstance(paths, list) or not all(
            isinstance(path, str) for path in paths
        ):
            raise Phase1GenerationError(
                f"stl_paths_json is not a string list: {value!r}"
            )
        normalized_paths = [_normalize_rooted_text(path, roots=roots) for path in paths]
        return json.dumps(normalized_paths, ensure_ascii=True, separators=(",", ":"))

    text = _normalize_rooted_text(value, roots=roots)
    if "case_signature" in key:
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise Phase1GenerationError(f"Invalid case signature value: {value!r}")
        return SIGNATURE_MARKER
    if key in {"run_started_at_utc", "run_finished_at_utc"}:
        _parse_utc_timestamp(value)
        return TIMESTAMP_MARKER
    return text


def _normalize_rooted_text(value: str, *, roots: Mapping[Path, str]) -> str:
    text = value
    replaced = False
    for root, marker in sorted(
        roots.items(), key=lambda item: len(str(item[0])), reverse=True
    ):
        variants = {str(root), root.as_posix()}
        for variant in sorted(variants, key=len, reverse=True):
            if variant in text:
                text = text.replace(variant, marker)
                replaced = True
    if replaced:
        text = text.replace("\\", "/")
    return text


def _parse_utc_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise Phase1GenerationError(f"Invalid UTC timestamp: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise Phase1GenerationError(f"Timestamp is not UTC: {value!r}")
    return parsed


def _normalize_scalar(value: Any, *, key: str, roots: Mapping[Path, str]) -> Any:
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            value = value.item()
        except ValueError:
            pass
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if not math.isfinite(value):
            return "+inf" if value > 0 else "-inf"
        return value
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, Path):
        value = str(value)
    if isinstance(value, str):
        return _normalize_string(value, key=key, roots=roots)
    if is_dataclass(value) and not isinstance(value, type):
        return _normalize_mapping(asdict(value), roots=roots)
    return value


def _normalize_mapping(
    value: Mapping[str, Any], *, roots: Mapping[Path, str]
) -> dict[str, Any]:
    return {
        str(key): _normalize_value(item, key=str(key), roots=roots)
        for key, item in value.items()
    }


def _normalize_value(value: Any, *, key: str, roots: Mapping[Path, str]) -> Any:
    if isinstance(value, Mapping):
        return _normalize_mapping(value, roots=roots)
    if isinstance(value, (list, tuple)):
        return [_normalize_value(item, key=key, roots=roots) for item in value]
    return _normalize_scalar(value, key=key, roots=roots)


def _array_record(
    name: str, value: Any, *, roots: Mapping[Path, str]
) -> dict[str, Any]:
    import numpy as np

    array = np.asarray(value)
    if array.dtype.kind in {"f", "c"} and not np.all(np.isfinite(array)):
        raise Phase1GenerationError(f"Array {name!r} contains NaN or infinity")
    logical_dtype = (
        "string" if array.dtype.kind in {"O", "S", "U"} else str(array.dtype)
    )
    raw_values = array.tolist()
    values = _normalize_value(raw_values, key=name, roots=roots)
    return {
        "dtype": logical_dtype,
        "shape": list(array.shape),
        "values": values,
    }


def _csv_cell(column: str, value: str, *, roots: Mapping[Path, str]) -> Any:
    if value == "":
        return None
    if column == "case_signature":
        return _normalize_string(value, key=column, roots=roots)
    if column in {"run_started_at_utc", "run_finished_at_utc"}:
        return _normalize_string(value, key=column, roots=roots)
    if column == "run_elapsed_s":
        elapsed = float(value)
        if not math.isfinite(elapsed) or elapsed < 0.0:
            raise Phase1GenerationError(f"Invalid elapsed time: {value!r}")
        return ELAPSED_MARKER
    if column in TEXT_CSV_COLUMNS:
        return _normalize_string(value, key=column, roots=roots)
    if re.fullmatch(r"[-+]?\d+", value):
        return int(value)
    try:
        numeric = float(value)
    except ValueError:
        return _normalize_string(value, key=column, roots=roots)
    if not math.isfinite(numeric):
        if math.isnan(numeric):
            return CSV_NAN_MARKER
        return (
            CSV_POSITIVE_INFINITY_MARKER
            if numeric > 0
            else CSV_NEGATIVE_INFINITY_MARKER
        )
    return numeric


def _read_semantic_csv(path: Path, *, roots: Mapping[Path, str]) -> dict[str, Any]:
    with path.open("r", encoding=CSV_ENCODING, newline="") as stream:
        reader = csv.DictReader(stream)
        columns = list(reader.fieldnames or [])
        rows = [
            {column: _csv_cell(column, row[column], roots=roots) for column in columns}
            for row in reader
        ]
    return {"columns": columns, "rows": rows}


def _read_vtp(path: Path, *, roots: Mapping[Path, str]) -> dict[str, Any]:
    import pyvista as pv

    poly = pv.read(path)
    return {
        "points": _array_record("points", poly.points, roots=roots),
        "faces": _array_record("faces", poly.faces, roots=roots),
        "cell_data": {
            name: _array_record(name, poly.cell_data[name], roots=roots)
            for name in poly.cell_data
        },
        "field_data": {
            name: _array_record(name, poly.field_data[name], roots=roots)
            for name in poly.field_data
        },
    }


def _read_npz(path: Path, *, roots: Mapping[Path, str]) -> dict[str, Any]:
    import numpy as np

    with np.load(path, allow_pickle=True) as archive:
        arrays = {
            name: _array_record(name, archive[name], roots=roots)
            for name in archive.files
        }
    return {"arrays": arrays}


@contextlib.contextmanager
def _temporary_environment(name: str, value: str | None) -> Iterator[None]:
    old = os.environ.get(name)
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old


def _call_contract(fn: Callable[[], Any]) -> dict[str, Any]:
    try:
        value = fn()
    except Exception as exc:  # intentional behavior capture at a public boundary
        return {
            "status": "error",
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
    return {"status": "ok", "value": value}


def _capture_environment_contract(
    *,
    solver: str,
    environment_name: str,
    shielding: Any,
    scheduler: Any,
) -> dict[str, Any]:
    prefix = ENVIRONMENT_PREFIX[solver]
    cache_name = f"{prefix}_SHIELD_CACHE_MAX"
    batch_name = f"{prefix}_SHIELD_BATCH_SIZE"
    chunk_name = f"{prefix}_PARALLEL_CHUNK_CASES"

    def under(name: str, value: str | None, fn: Callable[[], Any]) -> dict[str, Any]:
        with _temporary_environment(name, value):
            return _call_contract(fn)

    import trimesh
    from trimesh import ray as trimesh_ray

    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))

    def resolve_backend(name: str) -> dict[str, Any]:
        def call() -> dict[str, str]:
            if solver == "fmfsolver":
                fingerprint = shielding._mesh_geometry_fingerprint(mesh)
                intersector, effective = shielding._resolve_intersector(
                    mesh, name, fingerprint
                )
            else:
                intersector, effective = shielding._resolve_intersector(mesh, name)
            return {
                "effective": effective,
                "intersector_module": type(intersector).__module__,
            }

        return _call_contract(call)

    packages: dict[str, str | None] = {}
    for package in RUNTIME_PACKAGES:
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    embree_distributions: dict[str, str] = {}
    for package in ("embreex", "embreex4"):
        try:
            embree_distributions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            pass
    if len(embree_distributions) > 1:
        raise Phase1GenerationError(
            f"Multiple Embree distributions are installed: {embree_distributions}"
        )
    embree_binding = {
        "available": bool(embree_distributions),
        "distribution": (EMBREE_DISTRIBUTION_MARKER if embree_distributions else None),
        "version": EMBREE_VERSION_MARKER if embree_distributions else None,
    }

    return {
        "name": environment_name,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "packages": packages,
        "embree_binding": embree_binding,
        "trimesh_has_embree": bool(trimesh_ray.has_embree),
        "backend_selection": {
            "auto": resolve_backend("auto"),
            "rtree": resolve_backend("rtree"),
            "embree": resolve_backend("embree"),
        },
        "variables": {
            cache_name: {
                "precedence": "module import/global for mask cache; resolver reads environment",
                "import_time_value": int(shielding._SHIELD_CACHE_MAX),
                "unset": under(cache_name, None, shielding._resolve_shield_cache_max),
                "valid_3": under(cache_name, "3", shielding._resolve_shield_cache_max),
                "invalid": under(
                    cache_name, "bad", shielding._resolve_shield_cache_max
                ),
            },
            batch_name: {
                "precedence": "explicit argument > environment > backend default",
                "unset_rtree": under(
                    batch_name,
                    None,
                    lambda: shielding._resolve_batch_size("rtree", None),
                ),
                "unset_embree": under(
                    batch_name,
                    None,
                    lambda: shielding._resolve_batch_size("embree", None),
                ),
                "valid_17": under(
                    batch_name,
                    "17",
                    lambda: shielding._resolve_batch_size("rtree", None),
                ),
                "explicit_5_over_env": under(
                    batch_name,
                    "17",
                    lambda: shielding._resolve_batch_size("rtree", 5),
                ),
                "invalid": under(
                    batch_name,
                    "bad",
                    lambda: shielding._resolve_batch_size("rtree", None),
                ),
            },
            chunk_name: {
                "precedence": "explicit scheduler argument > environment > default",
                "unset": under(
                    chunk_name, None, scheduler.resolve_parallel_chunk_cases
                ),
                "valid_5": under(
                    chunk_name, "5", scheduler.resolve_parallel_chunk_cases
                ),
                "invalid": under(
                    chunk_name, "bad", scheduler.resolve_parallel_chunk_cases
                ),
            },
        },
    }


def _capture_invalid_inputs(
    *,
    solver: str,
    input_root: Path,
    read_cases: Callable[[str], Any],
    roots: Mapping[Path, str],
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    prefix = SOLVER_PREFIX[solver] + "_"
    for path in sorted((input_root / "invalid").glob(f"{prefix}*.csv")):
        try:
            frame = read_cases(str(path))
        except Exception as exc:  # structured legacy contract capture
            issues = []
            for issue in getattr(exc, "issues", []):
                issue_value = asdict(issue) if is_dataclass(issue) else vars(issue)
                issues.append(_normalize_mapping(issue_value, roots=roots))
            results[path.name] = {
                "stage": "read_cases",
                "status": "error",
                "error_type": type(exc).__name__,
                "message": _normalize_string(
                    str(exc), key="error_message", roots=roots
                ),
                "issues": issues,
            }
        else:
            results[path.name] = {
                "stage": "read_cases",
                "status": "accepted",
                "rows": len(frame),
            }
    return results


def _module_paths(solver: str, source_root: Path) -> list[str]:
    package_path = source_root / "src" / solver
    paths = [solver]
    paths.extend(
        module.name
        for module in pkgutil.walk_packages([str(package_path)], prefix=f"{solver}.")
    )
    return sorted(paths)


def _solver_imports(solver: str) -> dict[str, Any]:
    if solver == "fmfsolver":
        from fmfsolver.core import parallel_scheduler, shielding
        from fmfsolver.core import solver as solver_module
        from fmfsolver.io.csv_out import write_results_csv
        from fmfsolver.io.io_cases import read_cases

        from fmfsolver.app import cli_app  # isort: skip
    else:
        from newtsolver.core import parallel_scheduler, shielding
        from newtsolver.core import solver as solver_module
        from newtsolver.io.csv_out import write_results_csv
        from newtsolver.io.io_cases import read_cases

        from newtsolver.app import cli_app  # isort: skip

    return {
        "cli_app": cli_app,
        "parallel_scheduler": parallel_scheduler,
        "shielding": shielding,
        "solver_module": solver_module,
        "read_cases": read_cases,
        "write_results_csv": write_results_csv,
    }


def _capture_valid_cases(
    *,
    solver: str,
    input_root: Path,
    api: Mapping[str, Any],
    roots: Mapping[Path, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    input_path = input_root / f"{solver}_cases.csv"
    result_path = input_root / f"{solver}_results.csv"
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        exit_code = api["cli_app"].main(
            [
                "--input",
                str(input_path),
                "--output",
                str(result_path),
                "--workers",
                "1",
                "--flush-every-cases",
                "0",
            ]
        )
    if exit_code != 0:
        raise Phase1GenerationError(f"{solver} CLI returned {exit_code}")

    semantic_csv = _read_semantic_csv(result_path, roots=roots)
    with result_path.open("r", encoding=CSV_ENCODING, newline="") as stream:
        raw_csv_rows = list(csv.DictReader(stream))
    normalized_cases = api["read_cases"](str(input_path))
    cases: dict[str, Any] = {}
    for _, row in normalized_cases.iterrows():
        import numpy as np
        import pyvista as pv

        raw = row.to_dict()
        case_id = str(raw["case_id"])
        out_dir = Path(str(raw["out_dir"]))
        csv_rows = [item for item in semantic_csv["rows"] if item["case_id"] == case_id]
        raw_case_rows = [item for item in raw_csv_rows if item["case_id"] == case_id]
        if len(raw_case_rows) != len(csv_rows):
            raise Phase1GenerationError(
                f"{solver}/{case_id} raw and semantic CSV row counts differ"
            )
        raw_total_rows = [item for item in raw_case_rows if item["scope"] == "total"]
        if len(raw_total_rows) != 1:
            raise Phase1GenerationError(
                f"{solver}/{case_id} has no unique raw total row"
            )
        poly = pv.read(out_dir / f"{case_id}.vtp")
        field_signature = np.asarray(poly.field_data["case_signature"]).reshape(-1)[0]
        if isinstance(field_signature, bytes):
            field_signature = field_signature.decode("utf-8")
        recomputed_signature = api["solver_module"].build_case_signature(raw)
        signatures = {str(item["case_signature"]) for item in raw_case_rows}
        signatures.update((str(field_signature), str(recomputed_signature)))
        if len(signatures) != 1:
            raise Phase1GenerationError(
                f"{solver}/{case_id} CSV, VTP and recomputed signatures differ"
            )
        metadata_columns = (
            "case_signature",
            "run_started_at_utc",
            "run_finished_at_utc",
            "run_elapsed_s",
        )
        for column in metadata_columns:
            if len({item[column] for item in raw_case_rows}) != 1:
                raise Phase1GenerationError(
                    f"{solver}/{case_id} CSV rows disagree on {column}"
                )
        for raw_csv_row in raw_case_rows:
            started = _parse_utc_timestamp(raw_csv_row["run_started_at_utc"])
            finished = _parse_utc_timestamp(raw_csv_row["run_finished_at_utc"])
            if finished < started:
                raise Phase1GenerationError(
                    f"{solver}/{case_id} timestamps are reversed"
                )
            elapsed = float(raw_csv_row["run_elapsed_s"])
            if not math.isfinite(elapsed) or elapsed < 0.0:
                raise Phase1GenerationError(
                    f"{solver}/{case_id} has invalid elapsed time"
                )
        cases[case_id] = {
            "normalized_input": _normalize_mapping(raw, roots=roots),
            "csv": {
                "columns": semantic_csv["columns"],
                "rows": csv_rows,
            },
            "vtp": _read_vtp(out_dir / f"{case_id}.vtp", roots=roots),
            "npz": _read_npz(out_dir / f"{case_id}.npz", roots=roots),
            "relations": {
                "case_signature_csv_vtp_recomputed_equal": True,
                "csv_rows_share_run_metadata": True,
                "timestamps_utc_and_ordered": True,
            },
        }
    cli_run = {
        "exit_code": exit_code,
        "stdout": _normalize_string(stdout.getvalue(), key="cli_stdout", roots=roots),
        "result_csv_columns": semantic_csv["columns"],
        "case_order": [
            str(case_id) for case_id in normalized_cases["case_id"].tolist()
        ],
    }
    return cases, cli_run


def _capture(args: argparse.Namespace) -> int:
    solver = args.solver
    input_root = Path(args.input_root).resolve()
    output = Path(args.output).resolve()
    source_root = Path.cwd().resolve()
    roots = {
        input_root: "<fixture-root>",
        source_root: "<legacy-source>",
    }
    api = _solver_imports(solver)
    project = tomllib.loads(
        (source_root / "pyproject.toml").read_text(encoding="utf-8")
    )
    package_module = __import__(solver)
    capture: dict[str, Any] = {
        "package": {
            "name": project["project"]["name"],
            "version": project["project"]["version"],
            "scripts": project["project"].get("scripts", {}),
            "package_all": list(getattr(package_module, "__all__", [])),
        },
        "cli": {
            "help": api["cli_app"].build_parser().format_help(),
            "program": api["cli_app"].build_parser().prog,
        },
        "module_paths": _module_paths(solver, source_root),
        "environment": _capture_environment_contract(
            solver=solver,
            environment_name=args.environment_name,
            shielding=api["shielding"],
            scheduler=api["parallel_scheduler"],
        ),
        "invalid_inputs": _capture_invalid_inputs(
            solver=solver,
            input_root=input_root,
            read_cases=api["read_cases"],
            roots=roots,
        ),
        "cases": {},
        "cli_run": None,
    }
    if not args.probe_only:
        cases, cli_run = _capture_valid_cases(
            solver=solver,
            input_root=input_root,
            api=api,
            roots=roots,
        )
        capture["cases"] = cases
        capture["cli_run"] = cli_run
    _write_json(output, capture)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate Phase 1 semantic goldens from immutable legacy commits."
    )
    parser.add_argument("--fmf-repo", required=True, help="Pinned fmfsolver checkout")
    parser.add_argument("--newt-repo", required=True, help="Pinned newtsolver checkout")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_GOLDEN_ROOT),
        help="Golden output directory",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Regenerate in a temporary directory and compare semantically",
    )
    return parser


def _build_capture_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--solver", choices=tuple(SOLVER_PREFIX), required=True)
    parser.add_argument("--input-root", required=True)
    parser.add_argument("--environment-name", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--probe-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if values and values[0] == "_capture":
        return _capture(_build_capture_parser().parse_args(values[1:]))
    return _generate(_build_parser().parse_args(values))


if __name__ == "__main__":
    raise SystemExit(main())
