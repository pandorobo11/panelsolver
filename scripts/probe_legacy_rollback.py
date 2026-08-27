#!/usr/bin/env python3
"""Build and exercise exact pinned legacy rollback artifacts read-only."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

from panelsolver.app.csv_writer import CSV_ENCODING

try:
    from release_tools import (
        canonical_distribution_name,
        project_identity,
        select_built_wheel,
        sha256_file,
        wheel_identity,
    )
    from smoke_installed_wheel import (
        EXPECTED_COMPATIBILITY_ENTRY_POINTS,
        EXPECTED_ENTRY_POINTS,
        _prepare_current_inputs,
        _smoke_subprocess_environment,
    )
except ModuleNotFoundError:
    from scripts.release_tools import (
        canonical_distribution_name,
        project_identity,
        select_built_wheel,
        sha256_file,
        wheel_identity,
    )
    from scripts.smoke_installed_wheel import (
        EXPECTED_COMPATIBILITY_ENTRY_POINTS,
        EXPECTED_ENTRY_POINTS,
        _prepare_current_inputs,
        _smoke_subprocess_environment,
    )


@dataclass(frozen=True, slots=True)
class LegacySpec:
    name: str
    repository: str
    commit: str
    version: str
    sample_file: str
    sample_case: str


LEGACY_SPECS = (
    LegacySpec(
        name="fmfsolver",
        repository="https://github.com/pandorobo11/fmfsolver.git",
        commit="b62bc844d02a8f5212e62a53dea3238a1414317d",
        version="1.3.8",
        sample_file="samples/input_template.csv",
        sample_case="baseline_cube_modeA",
    ),
    LegacySpec(
        name="newtsolver",
        repository="https://github.com/pandorobo11/newtsolver.git",
        commit="dc1357d0d50bbedfdc8b3429cab37e6b98b56c70",
        version="1.0.3",
        sample_file="samples/input_template.csv",
        sample_case="satellite_baseline_newtonian",
    ),
)


def _run(
    command: list[str | Path],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(item) for item in command],
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=capture_output,
    )


def _git(repository: Path, *arguments: str) -> str:
    result = _run(
        ["git", "-C", repository, *arguments],
        capture_output=True,
    )
    return result.stdout.strip()


def _resolve_repository(source: str, work: Path, name: str) -> Path:
    local = Path(source).expanduser()
    if local.is_dir():
        if _git(local, "status", "--porcelain"):
            raise RuntimeError(f"legacy source must be clean: {local}")
        return local.resolve()
    clone = work / f"{name}-git"
    _run(["git", "clone", "--filter=blob:none", "--no-checkout", source, clone])
    return clone


def _archive_commit(
    repository: Path,
    spec: LegacySpec,
    destination: Path,
) -> tuple[str, str]:
    resolved = _git(repository, "rev-parse", f"{spec.commit}^{{commit}}")
    if resolved != spec.commit:
        raise RuntimeError(
            f"{spec.name} commit mismatch: expected {spec.commit}, found {resolved}"
        )
    tree = _git(repository, "show", "-s", "--format=%T", spec.commit)
    commit_epoch = _git(repository, "show", "-s", "--format=%ct", spec.commit)
    archive_path = destination.parent / f"{spec.name}.tar"
    _run(
        [
            "git",
            "-C",
            repository,
            "archive",
            "--format=tar",
            "--output",
            archive_path,
            spec.commit,
        ]
    )
    destination.mkdir()
    with tarfile.open(archive_path) as archive:
        archive.extractall(destination, filter="data")
    return tree, commit_epoch


def _build_legacy(
    repository: Path,
    spec: LegacySpec,
    work: Path,
    artifact_dir: Path,
    record_root: Path,
) -> tuple[Path, dict[str, object], Path]:
    source = work / f"{spec.name}-source"
    tree, commit_epoch = _archive_commit(repository, spec, source)
    output = artifact_dir / spec.name
    output.mkdir(parents=True)
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("PANELSOLVER_", "FMFSOLVER_", "NEWTSOLVER_"))
    }
    environment["SOURCE_DATE_EPOCH"] = commit_epoch
    _run(["uv", "build", "--out-dir", output], cwd=source, env=environment)
    wheel = select_built_wheel(source, output)
    name, version = wheel_identity(wheel)
    if canonical_distribution_name(name) != spec.name or version != spec.version:
        raise RuntimeError(f"{spec.name} wheel identity mismatch: {name} {version}")
    record = {
        "repository": spec.repository,
        "commit": spec.commit,
        "tree": tree,
        "source_date_epoch": int(commit_epoch),
        "wheel": str(wheel.relative_to(record_root)),
        "sha256": sha256_file(wheel),
        "metadata_name": name,
        "metadata_version": version,
    }
    return wheel, record, source


def _venv_python(venv: Path) -> Path:
    if sys.platform == "win32":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _command_path(python: Path, name: str) -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    return python.parent / f"{name}{suffix}"


def _assert_commands(
    python: Path,
    expected: dict[str, str] = EXPECTED_ENTRY_POINTS,
) -> list[str]:
    missing = [name for name in expected if not _command_path(python, name).is_file()]
    if missing:
        raise RuntimeError(f"missing installed commands: {missing}")
    return list(expected)


def _assert_distribution(
    python: Path,
    name: str,
    version: str | None,
) -> None:
    code = f"import importlib.metadata as m; value=m.version({name!r}); " + (
        f"assert value == {version!r}, value" if version else "print(value)"
    )
    _run([python, "-c", code])


def _assert_distribution_absent(python: Path, name: str) -> None:
    code = (
        "import importlib.metadata as m; "
        f"assert not any(d.metadata['Name'] == {name!r} for d in m.distributions())"
    )
    _run([python, "-c", code])


def _run_sample(
    python: Path,
    product: str,
    input_path: Path,
    case_id: str,
    output: Path,
    environment: dict[str, str],
    *,
    legacy_cli: bool,
) -> dict[str, object]:
    command = _command_path(python, f"{product}-cli")
    checkpoint_option = (
        "--flush-every-cases" if legacy_cli else "--checkpoint-every-cases"
    )
    _run(
        [
            command,
            "--input",
            input_path,
            "--output",
            output,
            "--workers",
            "1",
            checkpoint_option,
            "0",
            "--cases",
            case_id,
        ],
        cwd=input_path.parent,
        env=environment,
        capture_output=True,
    )
    with output.open(encoding=CSV_ENCODING, newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows or not any(row.get("case_id") == case_id for row in rows):
        raise RuntimeError(f"{product} rollback sample output is missing {case_id}")
    total = next(
        (row for row in rows if row.get("case_id") == case_id),
        None,
    )
    if total is None:
        raise RuntimeError(f"{product} rollback sample output is missing {case_id}")
    coefficients = {
        name: total[name] for name in ("CA", "CY", "CN", "Cl", "Cm", "Cn", "CD", "CL")
    }
    return {
        "case_id": case_id,
        "rows": len(rows),
        "coefficients": coefficients,
    }


def _install(python: Path, *artifacts: Path, no_deps: bool = False) -> None:
    command: list[str | Path] = ["uv", "pip", "install", "--python", python]
    if no_deps:
        command.append("--no-deps")
    command.extend(artifacts)
    _run(command)


def _uninstall(python: Path, *names: str) -> None:
    _run(["uv", "pip", "uninstall", "--python", python, *names])


def _prepare_panel_wheel(
    repository: Path,
    panel_dist: Path,
    supplied_wheel: Path | None,
) -> Path:
    panel_dist.mkdir(parents=True)
    if supplied_wheel is None:
        _run(["uv", "build", "--out-dir", panel_dist], cwd=repository)
    else:
        candidate = supplied_wheel.resolve()
        if not candidate.is_file():
            raise RuntimeError(f"panelsolver candidate wheel is missing: {candidate}")
        copied = panel_dist / candidate.name
        shutil.copy2(candidate, copied)
        if sha256_file(copied) != sha256_file(candidate):
            raise RuntimeError("copied panelsolver candidate wheel hash mismatch")
    return select_built_wheel(repository, panel_dist)


def _stage_current_panel_inputs(repository: Path, work: Path) -> Path:
    """Copy historical samples and adapt only the disposable current input."""
    source = repository / "tests" / "fixtures" / "phase1" / "inputs"
    staged = work / "panel-inputs"
    shutil.copytree(source, staged)
    _prepare_current_inputs(staged)
    return staged


def probe(
    repository: Path,
    artifact_dir: Path,
    sources: dict[str, str],
    panel_wheel: Path | None = None,
) -> dict[str, object]:
    artifact_dir.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="panel_rollback_probe_") as temp_dir:
        work = Path(temp_dir)
        legacy_wheels: dict[str, Path] = {}
        legacy_sources: dict[str, Path] = {}
        legacy_records: dict[str, object] = {}
        for spec in LEGACY_SPECS:
            source = _resolve_repository(sources[spec.name], work, spec.name)
            wheel, record, archive = _build_legacy(
                source,
                spec,
                work,
                artifact_dir / "legacy",
                artifact_dir,
            )
            legacy_wheels[spec.name] = wheel
            legacy_sources[spec.name] = archive
            legacy_records[spec.name] = record

        panel_dist = artifact_dir / "panelsolver"
        panel_wheel = _prepare_panel_wheel(repository, panel_dist, panel_wheel)
        panel_name, panel_version = wheel_identity(panel_wheel)
        expected_panel_name, expected_panel_version = project_identity(repository)
        if (panel_name, panel_version) != (
            expected_panel_name,
            expected_panel_version,
        ):
            raise RuntimeError("panelsolver candidate wheel identity mismatch")

        venv = work / "rollback-venv"
        _run(["uv", "venv", "--python", sys.executable, venv])
        python = _venv_python(venv)
        _install(python, panel_wheel)
        _assert_distribution(python, "panelsolver", panel_version)
        initial_commands = _assert_commands(python)

        _uninstall(python, "panelsolver")
        _assert_distribution_absent(python, "panelsolver")
        _install(
            python,
            legacy_wheels["fmfsolver"],
            legacy_wheels["newtsolver"],
        )
        for spec in LEGACY_SPECS:
            _assert_distribution(python, spec.name, spec.version)
        rollback_commands = _assert_commands(
            python,
            EXPECTED_COMPATIBILITY_ENTRY_POINTS,
        )

        environment = _smoke_subprocess_environment(work / "command-smoke")
        legacy_samples = {
            spec.name: _run_sample(
                python,
                spec.name,
                legacy_sources[spec.name] / spec.sample_file,
                spec.sample_case,
                work / f"{spec.name}-legacy-results.csv",
                environment,
                legacy_cli=True,
            )
            for spec in LEGACY_SPECS
        }

        _uninstall(python, "fmfsolver", "newtsolver")
        _install(python, panel_wheel, no_deps=True)
        _assert_distribution(python, "panelsolver", panel_version)
        returned_commands = _assert_commands(python)
        panel_inputs = _stage_current_panel_inputs(repository, work)
        returned_samples = {
            "fmfsolver": _run_sample(
                python,
                "fmfsolver",
                panel_inputs / "fmfsolver_cases.csv",
                "fmf_zero_plate",
                work / "fmfsolver-return-results.csv",
                environment,
                legacy_cli=False,
            ),
            "newtsolver": _run_sample(
                python,
                "newtsolver",
                panel_inputs / "newtsolver_cases.csv",
                "newt_zero_newtonian",
                work / "newtsolver-return-results.csv",
                environment,
                legacy_cli=False,
            ),
        }

    return {
        "schema": "panelsolver.phase8.rollback.v1",
        "legacy": legacy_records,
        "panel_candidate": {
            "wheel": str(panel_wheel.relative_to(artifact_dir)),
            "sha256": sha256_file(panel_wheel),
            "metadata_name": panel_name,
            "metadata_version": panel_version,
        },
        "verification": {
            "initial_panel_commands": initial_commands,
            "panel_removed_before_legacy_install": True,
            "rollback_commands": rollback_commands,
            "legacy_samples": legacy_samples,
            "legacy_removed_before_panel_return": True,
            "returned_panel_commands": returned_commands,
            "returned_panel_samples": returned_samples,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("--artifact-dir", required=True, type=Path)
    parser.add_argument("--fmf-source", default=LEGACY_SPECS[0].repository)
    parser.add_argument("--newt-source", default=LEGACY_SPECS[1].repository)
    parser.add_argument("--panel-wheel", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repository = args.repository.resolve()
    artifact_dir = args.artifact_dir.resolve()
    record = probe(
        repository,
        artifact_dir,
        {
            "fmfsolver": args.fmf_source,
            "newtsolver": args.newt_source,
        },
        args.panel_wheel,
    )
    record_path = artifact_dir / "rollback-record.json"
    record_path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(record_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
