#!/usr/bin/env python3
"""Version-independent distribution verification and release dry-runs."""

from __future__ import annotations

import argparse
import email.parser
import hashlib
import importlib.metadata
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath

_CANONICAL_SEPARATOR = re.compile(r"[-_.]+")
_COMMIT_SHA = re.compile(r"[0-9a-f]{40}")
_DISTRIBUTION_NAME = "panelsolver"
_DIST_MANIFEST_NAME = "panelsolver.dist-manifest"
_DIST_MANIFEST_VERSION = 2
_REPOSITORY_NAME = "pandorobo11/panelsolver"
_ARTIFACT_KINDS = ("wheel", "sdist", "docs", "examples")
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_CI_WORKFLOW = "ci.yml"
_PROTECTED_BRANCH = "main"
_DOCS_LICENSE_DIRECTORY = "THIRD_PARTY_LICENSES"
_RTD_CSS_LICENSES = (
    "MKDOCS-BSD-2-CLAUSE.txt",
    "SPHINX-RTD-THEME-1.2.0-MIT.txt",
    "WYRM-1.0.9-MIT.txt",
    "BOURBON-4.3.4-MIT.txt",
    "BOURBON-NEAT-1.9.1-MIT.txt",
    "FONT-AWESOME-4.7.0-MIT-AND-OFL-1.1.txt",
    "LATO-3.0.0-OFL-1.1.txt",
    "ROBOTO-SLAB-0.10.0-APACHE-2.0.txt",
)
_DOCS_THEME_ASSET_LICENSES = {
    "css/fonts/Roboto-Slab-Bold.woff": (
        "ROBOTO-SLAB-0.10.0-APACHE-2.0.txt",
    ),
    "css/fonts/Roboto-Slab-Bold.woff2": (
        "ROBOTO-SLAB-0.10.0-APACHE-2.0.txt",
    ),
    "css/fonts/Roboto-Slab-Regular.woff": (
        "ROBOTO-SLAB-0.10.0-APACHE-2.0.txt",
    ),
    "css/fonts/Roboto-Slab-Regular.woff2": (
        "ROBOTO-SLAB-0.10.0-APACHE-2.0.txt",
    ),
    "css/fonts/fontawesome-webfont.eot": (
        "FONT-AWESOME-4.7.0-MIT-AND-OFL-1.1.txt",
    ),
    "css/fonts/fontawesome-webfont.svg": (
        "FONT-AWESOME-4.7.0-MIT-AND-OFL-1.1.txt",
    ),
    "css/fonts/fontawesome-webfont.ttf": (
        "FONT-AWESOME-4.7.0-MIT-AND-OFL-1.1.txt",
    ),
    "css/fonts/fontawesome-webfont.woff": (
        "FONT-AWESOME-4.7.0-MIT-AND-OFL-1.1.txt",
    ),
    "css/fonts/fontawesome-webfont.woff2": (
        "FONT-AWESOME-4.7.0-MIT-AND-OFL-1.1.txt",
    ),
    "css/fonts/lato-bold-italic.woff": ("LATO-3.0.0-OFL-1.1.txt",),
    "css/fonts/lato-bold-italic.woff2": ("LATO-3.0.0-OFL-1.1.txt",),
    "css/fonts/lato-bold.woff": ("LATO-3.0.0-OFL-1.1.txt",),
    "css/fonts/lato-bold.woff2": ("LATO-3.0.0-OFL-1.1.txt",),
    "css/fonts/lato-normal-italic.woff": ("LATO-3.0.0-OFL-1.1.txt",),
    "css/fonts/lato-normal-italic.woff2": ("LATO-3.0.0-OFL-1.1.txt",),
    "css/fonts/lato-normal.woff": ("LATO-3.0.0-OFL-1.1.txt",),
    "css/fonts/lato-normal.woff2": ("LATO-3.0.0-OFL-1.1.txt",),
    "css/theme.css": _RTD_CSS_LICENSES,
    "css/theme_extra.css": ("MKDOCS-BSD-2-CLAUSE.txt",),
    "img/favicon.ico": ("MKDOCS-BSD-2-CLAUSE.txt",),
    "js/html5shiv.min.js": ("HTML5SHIV-3.7.3-MIT-OR-GPL-2.0.txt",),
    "js/jquery-3.6.0.min.js": ("JQUERY-3.6.0-MIT.txt",),
    "js/theme.js": (
        "MKDOCS-BSD-2-CLAUSE.txt",
        "SPHINX-RTD-THEME-1.2.0-MIT.txt",
        "WEBPACK-4.46.0-MIT.txt",
        "REQUESTANIMATIONFRAME-POLYFILL-MIT.txt",
    ),
    "js/theme_extra.js": ("MKDOCS-BSD-2-CLAUSE.txt",),
}
_DOCS_THEME_ASSET_SHA256 = {
    "css/fonts/Roboto-Slab-Bold.woff": "9fec87cadbe2413b255f1ec577573a83f1ca2e1c37aa023dbebcd3a7b864636a",
    "css/fonts/Roboto-Slab-Bold.woff2": "1a0c024dd1a267c52d5575469ffe8570d1e84164de7d393cf3414bafd17d7a0c",
    "css/fonts/Roboto-Slab-Regular.woff": "9f32630e2c0c5135bf1e86e36cb65b3932e4410644235bc2bd995e9c7f6ff117",
    "css/fonts/Roboto-Slab-Regular.woff2": "874e42222856d7af03b3f438d21d923a4280d47fe67c48510e2174a1579795ef",
    "css/fonts/fontawesome-webfont.eot": "7bfcab6db99d5cfbf1705ca0536ddc78585432cc5fa41bbd7ad0f009033b2979",
    "css/fonts/fontawesome-webfont.svg": "ad6157926c1622ba4e1d03d478f1541368524bfc46f51e42fe0d945f7ef323e4",
    "css/fonts/fontawesome-webfont.ttf": "aa58f33f239a0fb02f5c7a6c45c043d7a9ac9a093335806694ecd6d4edc0d6a8",
    "css/fonts/fontawesome-webfont.woff": "ba0c59deb5450f5cb41b3f93609ee2d0d995415877ddfa223e8a8a7533474f07",
    "css/fonts/fontawesome-webfont.woff2": "2adefcbc041e7d18fcf2d417879dc5a09997aa64d675b7a3c4b6ce33da13f3fe",
    "css/fonts/lato-bold-italic.woff": "980c8592e5488df256192c999e92db8fd302db8cd8909b7fa266a684e37e45f8",
    "css/fonts/lato-bold-italic.woff2": "c0916a33340d063f7b05679e08031e729d1888444706f04804705da5966d895d",
    "css/fonts/lato-bold.woff": "0e56b17d142eb366c8007031d14e34da48c70b4a9d9a0ca492e696a7bae45e1e",
    "css/fonts/lato-bold.woff2": "ae88fc0d7a961832f809527d30bd3983a6866d42f66a56ade23f543681594db6",
    "css/fonts/lato-normal-italic.woff": "26318a1467a5e5caf10b04cfa942d079632560cd7a29cec565fd1dc9f7ec5081",
    "css/fonts/lato-normal-italic.woff2": "4465765f2f6eddcdad34ffd7cab559e56bc0e75e45e192f85e9562b0771481dc",
    "css/fonts/lato-normal.woff": "5b9025dda4d7688e3311b0c17eddc501133b807def33effaef6593843cf5416e",
    "css/fonts/lato-normal.woff2": "983b0caf336e8542214fc17019a4fc5e0360864b92806ca14d55c1fc1c2c5a0f",
    "css/theme.css": "54c8391152107ac2b225db433700e2a48223977a16fd69ffeeffc7da4cf39808",
    "css/theme_extra.css": "aa215350b1098cf20efeafb8c89eded1c1a5138d252007d1376a2d998d0109dc",
    "img/favicon.ico": "f16b45bd53fbacaa2cd8f22e8482db5c59e0cef9bd21394474a429a18a98ffd0",
    "js/html5shiv.min.js": "3d458f51bc559f7855995e21fd2225c32f660d603970267b376c237bec08232f",
    "js/jquery-3.6.0.min.js": "ff1523fb7389539c84c65aba19260648793bb4f5e29329d2ee8804bc37a3fe6e",
    "js/theme.js": "a64cfe718ca86fb1aac8d2280c0741d69e7afa226e5fffb373740b4d28a87514",
    "js/theme_extra.js": "7b7fe33ea4a7da3b82aa151f747a3a4549d5f1d81bb5776759bc9099d9b50b46",
}
_DOCS_REQUIRED_LICENSES = frozenset(
    license_name
    for license_names in _DOCS_THEME_ASSET_LICENSES.values()
    for license_name in license_names
)
_DOCS_NOTICE_MARKERS = (
    "MkDocs 1.6.1",
    "Sphinx RTD Theme 1.2.0",
    "Wyrm 1.0.9",
    "Bourbon 4.3.4",
    "Bourbon Neat 1.9.1",
    "Font Awesome 4.7.0",
    "Lato 3.0.0",
    "Roboto fontface 0.10.0",
    "jQuery 3.6.0",
    "HTML5 Shiv 3.7.3",
    "webpack 4.46.0",
    "requestAnimationFrame polyfill",
    "Erik Möller",
    "Paul Irish",
    "Tino Zijdel",
)


def canonical_distribution_name(value: str) -> str:
    return _CANONICAL_SEPARATOR.sub("-", value).lower()


def project_identity(repository: Path) -> tuple[str, str]:
    with (repository / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]
    return str(project["name"]), str(project["version"])


def wheel_identity(wheel: Path) -> tuple[str, str]:
    with zipfile.ZipFile(wheel) as archive:
        metadata_files = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_files) != 1:
            raise RuntimeError(
                f"expected exactly one METADATA file in {wheel.name}, "
                f"found {len(metadata_files)}"
            )
        metadata = email.parser.BytesParser().parsebytes(
            archive.read(metadata_files[0])
        )
    return str(metadata["Name"] or ""), str(metadata["Version"] or "")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def select_built_wheel(repository: Path, dist_dir: Path | None = None) -> Path:
    directory = dist_dir or repository / "dist"
    wheels = sorted(directory.glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(
            f"expected exactly one wheel in {directory}, found {len(wheels)}: "
            f"{[path.name for path in wheels]}"
        )
    wheel = wheels[0]
    expected_name, expected_version = project_identity(repository)
    actual_name, actual_version = wheel_identity(wheel)
    if canonical_distribution_name(actual_name) != canonical_distribution_name(
        expected_name
    ):
        raise RuntimeError(
            f"wheel name mismatch: metadata={actual_name!r}, "
            f"project={expected_name!r}"
        )
    if actual_version != expected_version:
        raise RuntimeError(
            f"wheel version mismatch: metadata={actual_version!r}, "
            f"project={expected_version!r}"
        )
    return wheel


def select_built_sdist(repository: Path, dist_dir: Path | None = None) -> Path:
    directory = dist_dir or repository / "dist"
    sdists = sorted(directory.glob("*.tar.gz"))
    if len(sdists) != 1:
        raise RuntimeError(
            f"expected exactly one sdist in {directory}, found {len(sdists)}: "
            f"{[path.name for path in sdists]}"
        )
    sdist = sdists[0]
    expected_name, expected_version = project_identity(repository)
    actual_name, actual_version = sdist_identity(sdist)
    if canonical_distribution_name(actual_name) != canonical_distribution_name(
        expected_name
    ):
        raise RuntimeError(
            f"sdist name mismatch: metadata={actual_name!r}, project={expected_name!r}"
        )
    if actual_version != expected_version:
        raise RuntimeError(
            f"sdist version mismatch: metadata={actual_version!r}, "
            f"project={expected_version!r}"
        )
    return sdist


def sdist_identity(sdist: Path) -> tuple[str, str]:
    with tarfile.open(sdist, "r:gz") as archive:
        metadata_members = [
            member
            for member in archive.getmembers()
            if PurePosixPath(member.name).name == "PKG-INFO" and member.isfile()
        ]
        if len(metadata_members) != 1:
            raise RuntimeError(
                f"expected exactly one PKG-INFO file in {sdist.name}, "
                f"found {len(metadata_members)}"
            )
        stream = archive.extractfile(metadata_members[0])
        if stream is None:
            raise RuntimeError(f"could not read PKG-INFO from {sdist.name}")
        metadata = email.parser.BytesParser().parsebytes(stream.read())
    return str(metadata["Name"] or ""), str(metadata["Version"] or "")


def _release_archive_path(repository: Path, kind: str, directory: Path) -> Path:
    _name, version = project_identity(repository)
    filenames = {
        "docs": f"panelsolver-docs-v{version}.zip",
        "examples": f"panelsolver-examples-v{version}.zip",
    }
    try:
        return directory / filenames[kind]
    except KeyError as exc:
        raise ValueError(f"unsupported release archive kind: {kind}") from exc


def _zip_entries(root: Path, *, prefix: str = "") -> list[tuple[str, Path]]:
    entries: list[tuple[str, Path]] = []
    excluded_parts = {".cache", ".pytest_cache", "__pycache__", "outputs"}
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise RuntimeError(f"release archive input must not be a symlink: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        parts = PurePosixPath(relative).parts
        if any(part in excluded_parts or part == ".DS_Store" for part in parts):
            continue
        if path.suffix.casefold() in {".npz", ".xls"}:
            continue
        entries.append((f"{prefix}{relative}", path))
    return entries


def write_deterministic_zip(
    output: Path,
    entries: list[tuple[str, Path]],
) -> Path:
    """Write a platform-neutral ZIP with stable order, metadata, and bytes."""
    names = [name for name, _path in entries]
    if names != sorted(names) or len(names) != len(set(names)):
        raise RuntimeError("deterministic ZIP entries must be sorted and unique")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, path in entries:
            member = PurePosixPath(name)
            if member.is_absolute() or ".." in member.parts or "\\" in name:
                raise RuntimeError(f"unsafe ZIP member name: {name!r}")
            info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, path.read_bytes())
    return output


def verify_offline_documentation_licenses(
    member_names: set[str],
    read_member: Callable[[str], bytes],
) -> None:
    """Require a complete license mapping for every bundled theme asset."""
    theme_prefixes = ("css/", "img/", "js/", "webfonts/")
    actual_assets = {
        name for name in member_names if name.startswith(theme_prefixes)
    }
    expected_assets = set(_DOCS_THEME_ASSET_LICENSES)
    missing_assets = expected_assets - actual_assets
    unknown_assets = actual_assets - expected_assets
    if missing_assets:
        raise RuntimeError(
            "offline documentation is missing audited theme assets: "
            f"{sorted(missing_assets)}"
        )
    if unknown_assets:
        raise RuntimeError(
            "offline documentation has unaudited theme assets: "
            f"{sorted(unknown_assets)}"
        )
    if set(_DOCS_THEME_ASSET_SHA256) != expected_assets:
        raise RuntimeError("offline documentation asset hash inventory is incomplete")
    actual_hashes = {
        name: hashlib.sha256(read_member(name)).hexdigest()
        for name in expected_assets
    }
    changed_assets = {
        name: actual_hash
        for name, actual_hash in actual_hashes.items()
        if actual_hash != _DOCS_THEME_ASSET_SHA256[name]
    }
    if changed_assets:
        raise RuntimeError(
            "offline documentation theme assets changed since the license audit: "
            f"{sorted(changed_assets)}"
        )

    missing_licenses = {
        license_name
        for license_name in _DOCS_REQUIRED_LICENSES
        if f"{_DOCS_LICENSE_DIRECTORY}/{license_name}" not in member_names
    }
    if missing_licenses:
        raise RuntimeError(
            "offline documentation is missing third-party license texts: "
            f"{sorted(missing_licenses)}"
        )
    for license_name in _DOCS_REQUIRED_LICENSES:
        license_path = f"{_DOCS_LICENSE_DIRECTORY}/{license_name}"
        if not read_member(license_path).strip():
            raise RuntimeError(
                f"offline documentation license text is empty: {license_path}"
            )
        if read_member(license_path) == read_member("LICENSE"):
            raise RuntimeError(
                f"third-party license must be distinct from project LICENSE: {license_path}"
            )

    notices = read_member("THIRD_PARTY_NOTICES.md").decode("utf-8")
    missing_markers = [
        marker for marker in _DOCS_NOTICE_MARKERS if marker not in notices
    ]
    if missing_markers:
        raise RuntimeError(
            "offline documentation notices omit audited components: "
            f"{missing_markers}"
        )


def _extract_wheel_documentation(wheel: Path, destination: Path) -> None:
    prefix = "panelsolver/_docs_site/"
    with zipfile.ZipFile(wheel) as archive:
        members = sorted(
            name
            for name in archive.namelist()
            if name.startswith(prefix) and not name.endswith("/")
        )
        if not members:
            raise RuntimeError("wheel contains no bundled documentation site")
        for member in members:
            relative = PurePosixPath(member.removeprefix(prefix))
            if relative.is_absolute() or ".." in relative.parts:
                raise RuntimeError(f"wheel documentation path is unsafe: {member}")
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(member))
    if not (destination / "index.html").is_file():
        raise RuntimeError("wheel documentation site has no index.html")


def create_release_archives(
    repository: Path,
    dist_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Create deterministic docs and examples ZIPs from current release inputs."""
    directory = dist_dir or repository / "dist"
    with tempfile.TemporaryDirectory(prefix="panelsolver-wheel-docs-") as temporary:
        docs_site = Path(temporary) / "site"
        _extract_wheel_documentation(
            select_built_wheel(repository, directory),
            docs_site,
        )
        docs_zip = write_deterministic_zip(
            _release_archive_path(repository, "docs", directory),
            _zip_entries(docs_site),
        )

    examples = repository / "examples"
    example_entries = _zip_entries(examples, prefix="examples/")
    example_entries.extend(
        (name, repository / name)
        for name in ("LICENSE", "THIRD_PARTY_NOTICES.md")
    )
    example_entries.sort(key=lambda item: item[0])
    examples_zip = write_deterministic_zip(
        _release_archive_path(repository, "examples", directory),
        example_entries,
    )
    _verify_release_zip("docs", docs_zip)
    _verify_release_zip("examples", examples_zip)
    return docs_zip, examples_zip


def _verify_release_zip(kind: str, archive_path: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if names != sorted(names) or len(names) != len(set(names)):
            raise RuntimeError(f"{kind} ZIP members must be sorted and unique")
        for info in infos:
            member = PurePosixPath(info.filename)
            if member.is_absolute() or ".." in member.parts or "\\" in info.filename:
                raise RuntimeError(f"{kind} ZIP contains an unsafe member")
            if info.date_time != _ZIP_TIMESTAMP:
                raise RuntimeError(f"{kind} ZIP has a non-deterministic timestamp")
            if info.create_system != 3 or info.external_attr >> 16 != 0o100644:
                raise RuntimeError(f"{kind} ZIP has non-normalized permissions")
            if info.compress_type != zipfile.ZIP_STORED:
                raise RuntimeError(f"{kind} ZIP has non-normalized compression")
        if kind == "docs":
            required = {"index.html", "LICENSE", "THIRD_PARTY_NOTICES.md"}
        elif kind == "examples":
            required = {
                "LICENSE",
                "THIRD_PARTY_NOTICES.md",
                "examples/README.md",
                "examples/fmf/basic.csv",
                "examples/fmf/flow_modes.csv",
                "examples/fmf/attitude_modes.csv",
                "examples/fmf/shielding.csv",
                "examples/hypersonic/basic.csv",
                "examples/hypersonic/pressure_models.csv",
                "examples/hypersonic/attitude_modes.csv",
                "examples/hypersonic/shielding.csv",
                "examples/geometry/plate.stl",
            }
            if any(
                part in {"outputs", "__pycache__", ".cache", ".pytest_cache"}
                for name in names
                for part in PurePosixPath(name).parts
            ) or any(PurePosixPath(name).suffix.casefold() in {".npz", ".xls"} for name in names):
                raise RuntimeError("examples ZIP contains excluded generated or legacy files")
        else:
            raise ValueError(f"unsupported release archive kind: {kind}")
        missing = required - set(names)
        if missing:
            raise RuntimeError(f"{kind} ZIP is missing required members: {sorted(missing)}")
        if kind == "docs":
            verify_offline_documentation_licenses(set(names), archive.read)


def _verify_docs_zip_matches_wheel(wheel: Path, docs_zip: Path) -> None:
    prefix = "panelsolver/_docs_site/"
    with zipfile.ZipFile(wheel) as wheel_archive, zipfile.ZipFile(
        docs_zip
    ) as docs_archive:
        wheel_members = {
            name.removeprefix(prefix): wheel_archive.read(name)
            for name in wheel_archive.namelist()
            if name.startswith(prefix) and not name.endswith("/")
        }
        docs_members = {
            name: docs_archive.read(name)
            for name in docs_archive.namelist()
            if not name.endswith("/")
        }
    if wheel_members != docs_members:
        raise RuntimeError("docs ZIP content does not exactly match wheel documentation")


def _validated_commit_sha(value: str) -> str:
    normalized = value.strip().lower()
    if _COMMIT_SHA.fullmatch(normalized) is None:
        raise RuntimeError(f"expected a full 40-character commit SHA, found {value!r}")
    return normalized


def create_dist_manifest(
    repository: Path,
    commit_sha: str,
    output: Path,
    dist_dir: Path | None = None,
) -> dict[str, object]:
    directory = dist_dir or repository / "dist"
    wheel = select_built_wheel(repository, directory)
    sdist = select_built_sdist(repository, directory)
    docs_zip = _release_archive_path(repository, "docs", directory)
    examples_zip = _release_archive_path(repository, "examples", directory)
    _verify_release_zip("docs", docs_zip)
    _verify_release_zip("examples", examples_zip)
    metadata_name, metadata_version = wheel_identity(wheel)
    manifest: dict[str, object] = {
        "schema": {
            "name": _DIST_MANIFEST_NAME,
            "version": _DIST_MANIFEST_VERSION,
        },
        "github_commit_sha": _validated_commit_sha(commit_sha),
        "artifacts": [
            {
                "kind": "wheel",
                "filename": wheel.name,
                "sha256": sha256_file(wheel),
                "metadata": {
                    "name": metadata_name,
                    "version": metadata_version,
                },
            },
            {
                "kind": "sdist",
                "filename": sdist.name,
                "sha256": sha256_file(sdist),
            },
            {
                "kind": "docs",
                "filename": docs_zip.name,
                "sha256": sha256_file(docs_zip),
            },
            {
                "kind": "examples",
                "filename": examples_zip.name,
                "sha256": sha256_file(examples_zip),
            },
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return verify_dist_manifest(repository, output, directory, commit_sha)


def _manifest_artifact(
    value: object,
    *,
    field: str,
    directory: Path,
    expected_kind: str,
) -> tuple[Path, dict[str, object]]:
    if not isinstance(value, dict):
        raise TypeError(f"manifest {field} must be an object")
    allowed_keys = {"kind", "filename", "sha256"}
    if expected_kind == "wheel":
        allowed_keys.add("metadata")
    if set(value) != allowed_keys:
        raise RuntimeError(f"manifest {field} fields are invalid: {sorted(value)}")
    if value.get("kind") != expected_kind:
        raise RuntimeError(
            f"manifest {field} kind mismatch: {value.get('kind')!r}"
        )
    filename = value.get("filename")
    expected_hash = value.get("sha256")
    if not isinstance(filename, str) or Path(filename).name != filename:
        raise RuntimeError(f"manifest {field} filename is invalid: {filename!r}")
    if not isinstance(expected_hash, str) or re.fullmatch(
        r"[0-9a-f]{64}", expected_hash
    ) is None:
        raise RuntimeError(f"manifest {field} SHA-256 is invalid")
    artifact = directory / filename
    if not artifact.is_file():
        raise RuntimeError(f"manifest {field} file is missing: {artifact}")
    actual_hash = sha256_file(artifact)
    if actual_hash != expected_hash:
        raise RuntimeError(
            f"manifest {field} hash mismatch: expected {expected_hash}, "
            f"found {actual_hash}"
        )
    return artifact, value


def verify_dist_manifest(
    repository: Path,
    manifest_path: Path,
    dist_dir: Path | None = None,
    expected_commit: str | None = None,
) -> dict[str, object]:
    directory = dist_dir or repository / "dist"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"could not read distribution manifest: {error}") from error
    if not isinstance(manifest, dict):
        raise TypeError("distribution manifest must be a JSON object")
    if set(manifest) != {"schema", "github_commit_sha", "artifacts"}:
        raise RuntimeError("distribution manifest has unexpected or missing fields")
    schema = manifest.get("schema")
    if schema != {
        "name": _DIST_MANIFEST_NAME,
        "version": _DIST_MANIFEST_VERSION,
    }:
        raise RuntimeError(f"unsupported distribution manifest schema: {schema!r}")
    commit_sha = manifest.get("github_commit_sha")
    if not isinstance(commit_sha, str):
        raise TypeError("manifest github_commit_sha must be a string")
    commit_sha = _validated_commit_sha(commit_sha)
    if expected_commit is not None:
        expected = _validated_commit_sha(expected_commit)
        if commit_sha != expected:
            raise RuntimeError(
                "manifest commit mismatch: "
                f"manifest={commit_sha}, checkout={expected}"
            )

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise TypeError("manifest artifacts must be an array")
    if len(artifacts) != len(_ARTIFACT_KINDS):
        raise RuntimeError(
            f"manifest must contain exactly {len(_ARTIFACT_KINDS)} artifacts"
        )
    kinds = [item.get("kind") if isinstance(item, dict) else None for item in artifacts]
    if kinds != list(_ARTIFACT_KINDS):
        raise RuntimeError(
            f"manifest artifact kinds/order mismatch: found={kinds}, "
            f"expected={list(_ARTIFACT_KINDS)}"
        )
    entries = {
        kind: _manifest_artifact(
            value,
            field=kind,
            directory=directory,
            expected_kind=kind,
        )
        for kind, value in zip(_ARTIFACT_KINDS, artifacts, strict=True)
    }
    filenames = [entry[0].name for entry in entries.values()]
    if len(filenames) != len(set(filenames)):
        raise RuntimeError("manifest artifact filenames must be unique")

    wheel = entries["wheel"][0]
    sdist = entries["sdist"][0]
    selected_wheel = select_built_wheel(repository, directory)
    selected_sdist = select_built_sdist(repository, directory)
    if wheel != selected_wheel or sdist != selected_sdist:
        raise RuntimeError("manifest does not identify the selected distributions")

    for kind in ("docs", "examples"):
        artifact = entries[kind][0]
        if artifact != _release_archive_path(repository, kind, directory):
            raise RuntimeError(f"manifest {kind} filename does not match project version")
        _verify_release_zip(kind, artifact)
    _verify_docs_zip_matches_wheel(wheel, entries["docs"][0])

    expected_files = set(filenames)
    if manifest_path.resolve().parent == directory.resolve():
        expected_files.add(manifest_path.name)
    actual_files = {
        path.name
        for path in directory.iterdir()
        if path.is_file() and path.name != ".gitignore"
    }
    if actual_files != expected_files:
        missing = sorted(expected_files - actual_files)
        extra = sorted(actual_files - expected_files)
        raise RuntimeError(
            f"distribution artifact set mismatch: missing={missing}, extra={extra}"
        )

    wheel_entry = entries["wheel"][1]
    metadata = wheel_entry.get("metadata")
    if not isinstance(metadata, dict):
        raise TypeError("manifest wheel metadata must be an object")
    actual_name, actual_version = wheel_identity(wheel)
    expected_name, expected_version = project_identity(repository)
    if metadata.get("name") != actual_name or metadata.get("version") != actual_version:
        raise RuntimeError(
            "manifest wheel METADATA mismatch: "
            f"manifest={metadata!r}, wheel={{'name': {actual_name!r}, "
            f"'version': {actual_version!r}}}"
        )
    if canonical_distribution_name(actual_name) != canonical_distribution_name(
        expected_name
    ) or actual_version != expected_version:
        raise RuntimeError(
            "wheel METADATA project mismatch: "
            f"wheel={actual_name!r} {actual_version!r}, "
            f"project={expected_name!r} {expected_version!r}"
        )
    return manifest


def verify_lock_version(repository: Path, version: str) -> None:
    with (repository / "uv.lock").open("rb") as stream:
        packages = tomllib.load(stream)["package"]
    matches = [item for item in packages if item.get("name") == _DISTRIBUTION_NAME]
    if len(matches) != 1 or matches[0].get("version") != version:
        found = [item.get("version") for item in matches]
        raise RuntimeError(
            f"uv.lock panelsolver version mismatch: expected {version}, found {found}"
        )


def expected_tag(version: str) -> str:
    return f"v{version}"


def hypothetical_next_version(version: str) -> str:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
    if match is None:
        raise RuntimeError(f"cannot derive a dry-run version from {version!r}")
    major, minor, patch = (int(item) for item in match.groups())
    return f"{major}.{minor}.{patch + 1}.dev0"


def verify_tag(tag: str, version: str) -> None:
    expected = expected_tag(version)
    if tag != expected:
        raise RuntimeError(f"tag/version mismatch: tag={tag}, expected={expected}")


def _git_output(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f"git {' '.join(arguments)} failed in {repository}: {detail}"
        )
    return result.stdout.strip()


def verify_tag_target(
    repository: Path,
    tag: str,
    expected_commit: str | None = None,
) -> str:
    reference = f"refs/tags/{tag}"
    object_type = _git_output(repository, "cat-file", "-t", reference)
    if object_type != "tag":
        raise RuntimeError(
            f"release tag {tag!r} must be annotated; object type is {object_type!r}"
        )

    peeled_commit = _git_output(repository, "rev-parse", f"{reference}^{{}}")
    expected = expected_commit or "HEAD"
    resolved_expected = _git_output(
        repository,
        "rev-parse",
        "--verify",
        f"{expected}^{{commit}}",
    )
    if peeled_commit != resolved_expected:
        raise RuntimeError(
            "release tag target mismatch: "
            f"tag={peeled_commit}, expected={resolved_expected}"
        )
    return peeled_commit


def verify_release_tag(
    repository: Path,
    tag: str,
    expected_commit: str | None = None,
) -> str:
    name, version = project_identity(repository)
    if canonical_distribution_name(name) != _DISTRIBUTION_NAME:
        raise RuntimeError(f"unexpected project name: {name}")
    verify_tag(tag, version)
    verify_lock_version(repository, version)
    release_notes(repository, version)
    return verify_tag_target(repository, tag, expected_commit)


def release_notes(repository: Path, version: str) -> str:
    changelog = (repository / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = re.compile(
        rf"^## \[{re.escape(version)}\](?: - .+)?$",
        re.MULTILINE,
    )
    match = heading.search(changelog)
    if match is None:
        raise RuntimeError(f"CHANGELOG.md has no release section for {version}")
    start = match.end()
    next_heading = re.search(r"^## ", changelog[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(changelog)
    notes = changelog[start:end].strip()
    if not notes:
        raise RuntimeError(f"CHANGELOG.md release section {version} is empty")
    return notes + "\n"


def reinstall_built_wheel(repository: Path, dist_dir: Path | None = None) -> Path:
    wheel = select_built_wheel(repository, dist_dir)
    subprocess.run(
        ["uv", "pip", "uninstall", _DISTRIBUTION_NAME],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["uv", "pip", "install", "--no-deps", str(wheel)],
        cwd=repository,
        check=True,
    )
    installed = importlib.metadata.version(_DISTRIBUTION_NAME)
    expected = project_identity(repository)[1]
    if installed != expected:
        raise RuntimeError(
            f"installed distribution version mismatch: {installed} != {expected}"
        )
    return wheel


def verify_wheel_contents(repository: Path, wheel: Path) -> None:
    """Verify packaged docs, legal files, identity, and publication metadata."""
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        required_docs = {
            "panelsolver/_docs_site/index.html",
            "panelsolver/_docs_site/solvers/fmf.html",
            "panelsolver/_docs_site/solvers/hypersonic.html",
            "panelsolver/_docs_site/LICENSE",
            "panelsolver/_docs_site/THIRD_PARTY_NOTICES.md",
        }
        missing = required_docs - names
        if missing:
            raise RuntimeError(
                f"wheel is missing packaged documentation: {sorted(missing)}"
            )
        required_examples = {
            "panelsolver/_examples/fmf/basic.csv",
            "panelsolver/_examples/hypersonic/basic.csv",
            "panelsolver/_examples/geometry/plate.stl",
        }
        missing_examples = required_examples - names
        if missing_examples:
            raise RuntimeError(
                f"wheel is missing packaged examples: {sorted(missing_examples)}"
            )
        docs_prefix = "panelsolver/_docs_site/"
        docs_names = {
            name.removeprefix(docs_prefix)
            for name in names
            if name.startswith(docs_prefix) and not name.endswith("/")
        }
        verify_offline_documentation_licenses(
            docs_names,
            lambda name: archive.read(f"{docs_prefix}{name}"),
        )
        metadata_files = [
            name for name in names if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_files) != 1:
            raise RuntimeError("wheel must contain exactly one METADATA file")
        metadata = email.parser.BytesParser().parsebytes(
            archive.read(metadata_files[0])
        )
        license_prefix = metadata_files[0].removesuffix("METADATA") + "licenses/"
        for legal_name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
            if f"{license_prefix}{legal_name}" not in names:
                raise RuntimeError(f"wheel is missing license file {legal_name}")
        for license_name in _DOCS_REQUIRED_LICENSES:
            license_path = (
                f"{license_prefix}{_DOCS_LICENSE_DIRECTORY}/{license_name}"
            )
            if license_path not in names:
                raise RuntimeError(
                    f"wheel metadata is missing third-party license {license_name}"
                )

    expected_name, expected_version = project_identity(repository)
    if (
        canonical_distribution_name(str(metadata["Name"] or ""))
        != canonical_distribution_name(expected_name)
        or str(metadata["Version"] or "") != expected_version
    ):
        raise RuntimeError("wheel METADATA does not match project identity")
    if metadata["License-Expression"] != "Apache-2.0":
        raise RuntimeError("wheel License-Expression must be Apache-2.0")
    if not metadata.get_all("Author") and not metadata.get_all("Maintainer"):
        raise RuntimeError("wheel METADATA must identify an author or maintainer")
    project_urls = metadata.get_all("Project-URL", [])
    if not any(
        "https://github.com/pandorobo11/panelsolver" in value
        for value in project_urls
    ):
        raise RuntimeError("wheel METADATA has no canonical repository URL")
    runtime_requirements = metadata.get_all("Requires-Dist", [])
    build_only = ("mkdocs", "latex2mathml")
    if any(
        canonical_distribution_name(requirement.split(maxsplit=1)[0]).startswith(name)
        for requirement in runtime_requirements
        for name in build_only
    ):
        raise RuntimeError("documentation build dependencies leaked into runtime")


def verify_sdist_contents(repository: Path, sdist: Path) -> None:
    """Verify inputs needed for an isolated documentation-bearing wheel rebuild."""
    with tarfile.open(sdist, "r:gz") as archive:
        names = archive.getnames()
    roots = {PurePosixPath(name).parts[0] for name in names if name}
    if len(roots) != 1:
        raise RuntimeError(f"sdist must have one archive root, found {sorted(roots)}")
    root = next(iter(roots))
    required = {
        f"{root}/pyproject.toml",
        f"{root}/LICENSE",
        f"{root}/THIRD_PARTY_NOTICES.md",
        f"{root}/mkdocs.yml",
        f"{root}/src/panelsolver_docs_math.py",
        f"{root}/hatch_build.py",
        f"{root}/docs/index.md",
        f"{root}/docs/solvers/fmf.md",
        f"{root}/docs/solvers/hypersonic.md",
        f"{root}/src/panelsolver/docs_site.py",
        f"{root}/src/panelsolver/models/_sentman_atmosphere_data.py",
        f"{root}/scripts/generate_us1976_sentman_table.py",
        f"{root}/tools/reference/pdas/bigtables_v1_5.py",
        f"{root}/examples/README.md",
        f"{root}/examples/fmf/basic.csv",
        f"{root}/examples/hypersonic/basic.csv",
    }
    missing = required - set(names)
    if missing:
        raise RuntimeError(f"sdist is missing required source files: {sorted(missing)}")


def _script_path(venv: Path, name: str) -> Path:
    suffix = ".exe" if sys.platform == "win32" else ""
    directory = "Scripts" if sys.platform == "win32" else "bin"
    return venv / directory / f"{name}{suffix}"


def _smoke_rebuilt_wheel(repository: Path, wheel: Path, root: Path) -> None:
    venv = root / "venv"
    subprocess.run(
        ["uv", "venv", "--python", sys.executable, str(venv)],
        check=True,
    )
    python = _venv_python(venv)
    subprocess.run(
        ["uv", "pip", "install", "--python", str(python), str(wheel)],
        check=True,
    )
    smoke = (
        "import importlib.metadata as m; "
        "from panelsolver import (FMFCase, HypersonicCase, ResolvedAttitude, "
        "SolveResult, resolve_attitude, solve_fmf, solve_hypersonic); "
        "from panelsolver.docs_site import DocumentationSite; "
        "assert m.version('panelsolver') == "
        f"{project_identity(repository)[1]!r}; "
        "site=DocumentationSite(); assert site.resolve().is_file(); "
        "assert site.resolve('solvers/fmf.html').is_file(); site.close()"
    )
    subprocess.run([str(python), "-c", smoke], cwd=root, check=True)
    for command, arguments in (
        ("panelsolver", ("--help",)),
        ("panelsolver", ("fmf", "--help")),
        ("panelsolver", ("hypersonic", "--help")),
        ("panelsolver-gui", ("--help",)),
    ):
        subprocess.run(
            [str(_script_path(venv, command)), *arguments],
            cwd=root,
            check=True,
        )


def verify_built_distributions(
    repository: Path,
    dist_dir: Path | None = None,
) -> None:
    """Inspect wheel/sdist and install an isolated wheel rebuilt from the sdist."""
    directory = dist_dir or repository / "dist"
    wheel = select_built_wheel(repository, directory)
    sdist = select_built_sdist(repository, directory)
    verify_wheel_contents(repository, wheel)
    verify_sdist_contents(repository, sdist)
    with tempfile.TemporaryDirectory(prefix="panelsolver-sdist-rebuild-") as temporary:
        root = Path(temporary)
        extracted = root / "source"
        extracted.mkdir()
        with tarfile.open(sdist, "r:gz") as archive:
            archive.extractall(extracted, filter="data")
        source_roots = [path for path in extracted.iterdir() if path.is_dir()]
        if len(source_roots) != 1:
            raise RuntimeError(
                "extracted sdist must have exactly one source root: "
                f"{source_roots}"
            )
        source_root = source_roots[0]
        subprocess.run(
            [
                sys.executable,
                "scripts/generate_us1976_sentman_table.py",
                "--check",
            ],
            cwd=source_root,
            check=True,
        )
        rebuilt_dir = root / "dist"
        subprocess.run(
            [
                "uv",
                "build",
                "--wheel",
                "--out-dir",
                str(rebuilt_dir),
                str(sdist.resolve()),
            ],
            cwd=root,
            check=True,
        )
        rebuilt_wheel = select_built_wheel(repository, rebuilt_dir)
        verify_wheel_contents(repository, rebuilt_wheel)
        _smoke_rebuilt_wheel(repository, rebuilt_wheel, root)


def is_prerelease(version: str) -> bool:
    """Infer GitHub prerelease state from a PEP 440 alpha, beta, or RC marker."""
    return re.search(r"(?:a|b|rc)\d+", version, re.IGNORECASE) is not None


def _github_api_json(endpoint: str) -> object:
    result = subprocess.run(
        ["gh", "api", endpoint],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"GitHub API request failed for {endpoint}: {detail}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"GitHub API returned invalid JSON for {endpoint}") from exc


def verify_github_release_state(
    repository_name: str = _REPOSITORY_NAME,
    expected_commit: str | None = None,
) -> None:
    """Require the canonical repository, green main, and zero open trackers."""
    if repository_name != _REPOSITORY_NAME:
        raise RuntimeError(
            f"release repository mismatch: {repository_name!r} != {_REPOSITORY_NAME!r}"
        )
    repository = _github_api_json(f"repos/{repository_name}")
    if not isinstance(repository, dict) or repository.get("full_name") != _REPOSITORY_NAME:
        raise RuntimeError("GitHub API did not resolve the canonical repository")
    queries = {
        "issue": f"search/issues?q=repo:{repository_name}+is:issue+is:open&per_page=1",
        "pull request": f"search/issues?q=repo:{repository_name}+is:pr+is:open&per_page=1",
    }
    counts: dict[str, int] = {}
    for kind, endpoint in queries.items():
        payload = _github_api_json(endpoint)
        if not isinstance(payload, dict) or not isinstance(payload.get("total_count"), int):
            raise TypeError(f"GitHub {kind} query returned an invalid payload")
        counts[kind] = payload["total_count"]
    if counts != {"issue": 0, "pull request": 0}:
        raise RuntimeError(
            "release requires zero open non-PR issues and zero open pull requests: "
            f"issues={counts['issue']}, pull_requests={counts['pull request']}"
        )
    if expected_commit is not None:
        commit = _validated_commit_sha(expected_commit)
        runs = _github_api_json(
            f"repos/{repository_name}/actions/workflows/{_CI_WORKFLOW}/runs"
            f"?branch={_PROTECTED_BRANCH}&event=push&head_sha={commit}&per_page=100"
        )
        if not isinstance(runs, dict) or not isinstance(runs.get("workflow_runs"), list):
            raise RuntimeError("GitHub exact-main CI query returned an invalid payload")
        if any(not isinstance(run, dict) for run in runs["workflow_runs"]):
            raise RuntimeError("GitHub exact-main CI query returned an invalid run")
        main_push_runs = [
            run
            for run in runs["workflow_runs"]
            if run.get("event") == "push"
            and run.get("head_branch") == _PROTECTED_BRANCH
            and run.get("head_sha") == commit
        ]
        if not main_push_runs:
            raise RuntimeError(f"exact-main CI has no main push workflow run for {commit}")
        if any(
            not isinstance(run.get(field), int)
            for run in main_push_runs
            for field in ("run_number", "run_attempt", "id")
        ):
            raise RuntimeError("GitHub exact-main CI run ordering fields are invalid")
        accepted = max(
            main_push_runs,
            key=lambda run: (run["run_number"], run["run_attempt"], run["id"]),
        )
        if accepted.get("status") != "completed" or accepted.get("conclusion") != "success":
            summary = {
                "id": accepted.get("id"),
                "run_number": accepted.get("run_number"),
                "run_attempt": accepted.get("run_attempt"),
                "status": accepted.get("status"),
                "conclusion": accepted.get("conclusion"),
            }
            raise RuntimeError(
                f"latest exact-main CI run is not successful: {summary}"
            )


def _replace_version(repository: Path, old: str, new: str) -> None:
    pyproject = repository / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    old_line = f'version = "{old}"'
    new_line = f'version = "{new}"'
    if text.count(old_line) != 1:
        raise RuntimeError("project.version was not uniquely replaceable")
    pyproject.write_text(text.replace(old_line, new_line), encoding="utf-8")

    lock = repository / "uv.lock"
    text = lock.read_text(encoding="utf-8")
    pattern = re.compile(
        rf'(\[\[package\]\]\nname = "{_DISTRIBUTION_NAME}"\nversion = ")[^"]+("\n)'
    )
    text, replacements = pattern.subn(rf"\g<1>{new}\g<2>", text)
    if replacements != 1:
        raise RuntimeError("uv.lock project version was not uniquely replaceable")
    lock.write_text(text, encoding="utf-8")

    changelog = repository / "CHANGELOG.md"
    text = changelog.read_text(encoding="utf-8")
    marker = "## [Unreleased]\n"
    dry_run_notes = (
        f"{marker}\n## [{new}] - DRY RUN\n\n"
        "- Verify version-independent build, install, notes, and tag checks.\n"
    )
    if text.count(marker) != 1:
        raise RuntimeError("CHANGELOG.md Unreleased section was not uniquely found")
    changelog.write_text(text.replace(marker, dry_run_notes), encoding="utf-8")


def _venv_python(venv: Path) -> Path:
    if sys.platform == "win32":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def dry_run(repository: Path, version: str | None = None) -> None:
    current_name, current_version = project_identity(repository)
    version = version or hypothetical_next_version(current_version)
    if version == current_version:
        raise RuntimeError("dry-run version must differ from project.version")
    if canonical_distribution_name(current_name) != _DISTRIBUTION_NAME:
        raise RuntimeError(f"unexpected project name: {current_name}")

    with tempfile.TemporaryDirectory(prefix="panel_release_dry_run_") as temp_dir:
        root = Path(temp_dir)
        checkout = root / "checkout"
        shutil.copytree(
            repository,
            checkout,
            ignore=shutil.ignore_patterns(
                ".git",
                ".hatch-build",
                ".venv",
                ".reference",
                "__pycache__",
                "dist",
                "outputs",
                "site",
            ),
        )
        _replace_version(checkout, current_version, version)
        verify_lock_version(checkout, version)
        verify_tag(expected_tag(version), version)
        release_notes(checkout, version)

        dist_dir = root / "dist"
        subprocess.run(
            ["uv", "build", "--out-dir", str(dist_dir)],
            cwd=checkout,
            check=True,
        )
        wheel = select_built_wheel(checkout, dist_dir)
        sdist = select_built_sdist(checkout, dist_dir)
        verify_wheel_contents(checkout, wheel)
        verify_sdist_contents(checkout, sdist)
        create_release_archives(checkout, dist_dir)
        create_dist_manifest(checkout, "0" * 40, dist_dir / "manifest.json", dist_dir)

        venv = root / "venv"
        subprocess.run(
            ["uv", "venv", "--python", sys.executable, str(venv)],
            check=True,
        )
        python = _venv_python(venv)
        subprocess.run(
            ["uv", "pip", "install", "--python", str(python), "--no-deps", str(wheel)],
            check=True,
        )
        subprocess.run(
            [
                str(python),
                "-c",
                (
                    "import importlib.metadata as m; "
                    f"assert m.version('{_DISTRIBUTION_NAME}') == {version!r}"
                ),
            ],
            cwd=root,
            check=True,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("verify-wheel", "reinstall-wheel"):
        selected = subparsers.add_parser(command)
        selected.add_argument("repository", type=Path)
        selected.add_argument("--dist-dir", type=Path)
    create_manifest = subparsers.add_parser("create-manifest")
    create_manifest.add_argument("repository", type=Path)
    create_manifest.add_argument("--commit-sha", required=True)
    create_manifest.add_argument("--output", required=True, type=Path)
    create_manifest.add_argument("--dist-dir", type=Path)
    verify_manifest = subparsers.add_parser("verify-manifest")
    verify_manifest.add_argument("repository", type=Path)
    verify_manifest.add_argument("--manifest", required=True, type=Path)
    verify_manifest.add_argument("--dist-dir", type=Path)
    verify_manifest.add_argument("--expected-commit")
    archives = subparsers.add_parser("create-release-archives")
    archives.add_argument("repository", type=Path)
    archives.add_argument("--dist-dir", type=Path)
    distributions = subparsers.add_parser("verify-distributions")
    distributions.add_argument("repository", type=Path)
    distributions.add_argument("--dist-dir", type=Path)
    tag = subparsers.add_parser("verify-tag")
    tag.add_argument("repository", type=Path)
    tag.add_argument("tag")
    tag.add_argument("--expected-commit")
    notes = subparsers.add_parser("release-notes")
    notes.add_argument("repository", type=Path)
    notes.add_argument("--output", required=True, type=Path)
    github_state = subparsers.add_parser("verify-github-state")
    github_state.add_argument("repository", type=Path)
    github_state.add_argument("--repository-name", default=_REPOSITORY_NAME)
    github_state.add_argument("--expected-commit")
    prerelease = subparsers.add_parser("prerelease")
    prerelease.add_argument("repository", type=Path)
    probe = subparsers.add_parser("dry-run")
    probe.add_argument("repository", type=Path)
    probe.add_argument("--version")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repository = args.repository.resolve()
    if args.command == "verify-wheel":
        print(select_built_wheel(repository, args.dist_dir))
    elif args.command == "reinstall-wheel":
        print(reinstall_built_wheel(repository, args.dist_dir))
    elif args.command == "create-manifest":
        manifest = create_dist_manifest(
            repository,
            args.commit_sha,
            args.output,
            args.dist_dir,
        )
        print(json.dumps(manifest, sort_keys=True))
    elif args.command == "verify-manifest":
        manifest = verify_dist_manifest(
            repository,
            args.manifest,
            args.dist_dir,
            args.expected_commit,
        )
        print(json.dumps(manifest, sort_keys=True))
    elif args.command == "create-release-archives":
        print("\n".join(str(path) for path in create_release_archives(repository, args.dist_dir)))
    elif args.command == "verify-distributions":
        verify_built_distributions(repository, args.dist_dir)
    elif args.command == "verify-tag":
        print(verify_release_tag(repository, args.tag, args.expected_commit))
    elif args.command == "release-notes":
        _name, version = project_identity(repository)
        args.output.write_text(release_notes(repository, version), encoding="utf-8")
    elif args.command == "verify-github-state":
        verify_github_release_state(args.repository_name, args.expected_commit)
    elif args.command == "prerelease":
        _name, version = project_identity(repository)
        print("true" if is_prerelease(version) else "false")
    else:
        dry_run(repository, args.version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
