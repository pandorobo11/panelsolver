"""Input-table-relative filesystem path policy for application artifacts."""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Mapping
from pathlib import Path

DEFAULT_OUTPUT_DIRECTORY = "outputs"
DEFAULT_IMAGE_DIRECTORY = "images"
_UNSAFE_FILENAME_CHARACTERS = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')


def absolute_input_path(input_path: str | Path) -> Path:
    """Make an input path absolute without following a file symlink."""
    source = Path(input_path).expanduser()
    return source if source.is_absolute() else Path.cwd() / source


def resolve_input_relative_path(
    path: str | Path,
    input_path: str | Path,
) -> Path:
    """Resolve ``path`` against the input table directory when it is relative."""
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve(strict=False)
    base_dir = absolute_input_path(input_path).parent
    return (base_dir / candidate).resolve(strict=False)


def resolve_output_dir(input_path: str | Path) -> Path:
    """Return ``<input_dir>/outputs`` for VTP files and default images."""
    return resolve_input_relative_path(DEFAULT_OUTPUT_DIRECTORY, input_path)


def resolve_case_vtp_path(
    row: Mapping[str, object],
    input_path: str | Path,
) -> Path:
    """Return the planned VTP path for one case row."""
    case_id = str(row.get("case_id", "")).strip()
    return resolve_output_dir(input_path) / f"{case_id}.vtp"


def resolve_image_dir(input_path: str | Path) -> Path:
    """Return ``<input_dir>/outputs/images``."""
    return resolve_output_dir(input_path) / DEFAULT_IMAGE_DIRECTORY


def default_image_filename(identifier: str, scalar_name: str) -> str:
    """Return the common portable machine-field-oriented PNG filename."""
    safe_identifier = _safe_image_filename_component(identifier, fallback="image")
    safe_scalar = _safe_image_filename_component(scalar_name, fallback="scalar")
    return f"{safe_identifier}__{safe_scalar}.png"


def _safe_image_filename_component(value: str, *, fallback: str) -> str:
    """Replace cross-platform unsafe filename characters in one component."""
    sanitized = _UNSAFE_FILENAME_CHARACTERS.sub("_", value)
    sanitized = sanitized.strip().rstrip(". ")
    return sanitized or fallback


def resolve_case_image_path(
    row: Mapping[str, object],
    input_path: str | Path,
    scalar_name: str,
) -> Path:
    """Return the standard image path for a case-associated viewport."""
    case_id = str(row.get("case_id", "")).strip()
    return resolve_image_dir(input_path) / default_image_filename(
        case_id,
        scalar_name,
    )


def resolve_manual_vtp_image_path(
    vtp_path: str | Path,
    scalar_name: str,
) -> Path:
    """Return the standard image path for an unmatched manually opened VTP."""
    source = Path(vtp_path).expanduser()
    return (
        source.parent
        / DEFAULT_IMAGE_DIRECTORY
        / default_image_filename(
            source.stem,
            scalar_name,
        )
    )


def auto_rename_path(
    planned_path: str | Path,
    *,
    path_exists: Callable[[Path], bool] = Path.exists,
    reserved_paths: Collection[Path] = (),
) -> Path:
    """Return a nonexisting path, suffixing ``_2``, ``_3``, ... as needed."""
    path = Path(planned_path)
    reserved = set(reserved_paths)
    if path not in reserved and not path_exists(path):
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        if candidate not in reserved and not path_exists(candidate):
            return candidate
        counter += 1


def default_summary_output_path(input_path: str | Path) -> Path:
    """Return ``<input_dir>/outputs/<input_stem>_result.csv``."""
    source = absolute_input_path(input_path)
    return source.parent / DEFAULT_OUTPUT_DIRECTORY / f"{source.stem}_result.csv"


__all__ = (
    "DEFAULT_IMAGE_DIRECTORY",
    "DEFAULT_OUTPUT_DIRECTORY",
    "absolute_input_path",
    "auto_rename_path",
    "default_image_filename",
    "default_summary_output_path",
    "resolve_case_image_path",
    "resolve_case_vtp_path",
    "resolve_image_dir",
    "resolve_input_relative_path",
    "resolve_manual_vtp_image_path",
    "resolve_output_dir",
)
