"""Shared sectional definition CSV parsing and independent batch selection."""

from __future__ import annotations

import csv
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from panelsolver.core.errors import ContractError, ContractValueError
from panelsolver.core.sectional import SectionalLoadDefinition

from .csv_writer import CSV_ENCODING

_ORIGIN_FIELDS = tuple(f"origin_{axis}_stl_m" for axis in "xyz")
_DIRECTION_FIELDS = tuple(f"direction_{axis}_stl" for axis in "xyz")
_REQUIRED_FIELDS = (
    "section_id",
    *_ORIGIN_FIELDS,
    *_DIRECTION_FIELDS,
    "bin_count",
)
_OPTIONAL_FIELDS = ("start_m", "stop_m", "component_ids")
_INTEGER = re.compile(r"[+-]?[0-9]+\Z")


def _normalize_id(value: str) -> str:
    if not isinstance(value, str):
        raise ContractValueError("section_id", "must be text")
    section_id = unicodedata.normalize("NFC", value.strip())
    if not section_id:
        raise ContractValueError("section_id", "must not be blank")
    return section_id


@dataclass(frozen=True, slots=True, eq=False)
class SectionalDefinition:
    """A file/batch label attached to one immutable numerical definition."""

    section_id: str
    definition: SectionalLoadDefinition
    row_number: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "section_id", _normalize_id(self.section_id))
        if not isinstance(self.definition, SectionalLoadDefinition):
            raise ContractValueError("definition", "must be a SectionalLoadDefinition")

    def __deepcopy__(self, memo: dict[int, object]) -> SectionalDefinition:
        # Run snapshots can safely share this immutable numerical definition.
        return self


def _float_token(token: str, field: str) -> float:
    try:
        return float(token)
    except (ValueError, OverflowError) as exc:
        raise ContractValueError(field, "must be a real number") from exc


def _integer_token(token: str, field: str) -> int:
    if not _INTEGER.fullmatch(token):
        raise ContractValueError(field, "must use decimal integer notation")
    try:
        return int(token)
    except ValueError as exc:
        raise ContractValueError(field, "integer token is too large") from exc


def _parse_definition(row: dict[str, str]) -> SectionalLoadDefinition:
    for name in _REQUIRED_FIELDS:
        if not row[name]:
            raise ContractValueError(name, "required cell is blank")
    component_text = row.get("component_ids", "")
    components = (
        tuple(
            _integer_token(token.strip(), "component_ids")
            for token in component_text.split(";")
        )
        if component_text
        else None
    )
    # Float conversion is lexical only. A1 owns finite-value, axis, count,
    # range-pair and component numerical validation, including overflow.
    return SectionalLoadDefinition(
        axis_origin_stl_m=np.array(
            [_float_token(row[name], name) for name in _ORIGIN_FIELDS]
        ),
        axis_direction_stl=np.array(
            [_float_token(row[name], name) for name in _DIRECTION_FIELDS]
        ),
        bin_count=_integer_token(row["bin_count"], "bin_count"),
        start_m=(
            _float_token(row["start_m"], "start_m") if row.get("start_m") else None
        ),
        stop_m=(_float_token(row["stop_m"], "stop_m") if row.get("stop_m") else None),
        component_ids=components,
    )


def read_sectional_definitions(path: str | Path) -> tuple[SectionalDefinition, ...]:
    """Read and validate the entire v1 CSV before any selection or physical solve.

    Numeric constraints are delegated to A1. Mesh-dependent component existence
    and range resolution remain the per-case batch service's responsibility.
    Diagnostics include the filename, physical CSV row, identity when present,
    and field. Blank physical lines are ignored, but a file needs definitions.
    """
    source = Path(path)
    definitions: list[SectionalDefinition] = []
    seen: set[str] = set()
    row_number = 1
    section_id = ""
    try:
        with source.open(encoding=CSV_ENCODING, newline="") as stream:
            reader = csv.reader(stream, strict=True)
            header = next(reader, None)
            if not header:
                raise ContractValueError("header", "definition CSV is empty")
            if len(header) != len(set(header)):
                duplicates = sorted({name for name in header if header.count(name) > 1})
                raise ContractValueError("header", f"duplicate columns: {duplicates}")
            unknown = set(header) - set(_REQUIRED_FIELDS) - set(_OPTIONAL_FIELDS)
            missing = set(_REQUIRED_FIELDS) - set(header)
            if unknown:
                raise ContractValueError(
                    "header", f"unknown columns: {sorted(unknown)}"
                )
            if missing:
                raise ContractValueError(
                    "header", f"missing columns: {sorted(missing)}"
                )
            while True:
                row_number = reader.line_num + 1
                section_id = ""
                cells = next(reader, None)
                if cells is None:
                    break
                if not cells:
                    continue
                id_position = header.index("section_id")
                if id_position < len(cells):
                    section_id = unicodedata.normalize(
                        "NFC", cells[id_position].strip()
                    )
                if len(cells) != len(header):
                    raise ContractValueError(
                        "row", f"expected {len(header)} cells; got {len(cells)}"
                    )
                row = dict(zip(header, (cell.strip() for cell in cells), strict=True))
                section_id = _normalize_id(row["section_id"])
                if section_id in seen:
                    raise ContractValueError(
                        "section_id", "duplicate identity after trim/NFC normalization"
                    )
                definition = _parse_definition(row)
                definitions.append(
                    SectionalDefinition(section_id, definition, row_number)
                )
                seen.add(section_id)
            if not definitions:
                raise ContractValueError("definitions", "file contains no definitions")
    except ContractError as exc:
        identity = f", section_id={section_id!r}" if section_id else ""
        raise ValueError(
            f"{source}: row {row_number}{identity}, field {exc.field}: {exc.detail}"
        ) from exc
    except (csv.Error, UnicodeError) as exc:
        raise ValueError(f"{source}: row {row_number}, field CSV: {exc}") from exc
    return tuple(definitions)


def select_sectional_definitions(
    definitions: Sequence[SectionalDefinition], section_ids: Sequence[str] | None
) -> tuple[SectionalDefinition, ...]:
    """Select exact normalized labels while preserving definition-file order.

    None selects all. An explicit selection must contain at least one known ID;
    comma characters are literal parts of labels, not another separator.
    """
    available = tuple(definitions)
    if section_ids is None:
        return available
    if isinstance(section_ids, (str, bytes)):
        raise TypeError("section_ids must be a sequence of section labels")
    selected = {_normalize_id(value) for value in section_ids}
    if not selected:
        raise ValueError("section_ids must select at least one definition")
    unknown = selected - {item.section_id for item in available}
    if unknown:
        raise ValueError(f"unknown section IDs: {sorted(unknown)}")
    return tuple(item for item in available if item.section_id in selected)


__all__ = (
    "SectionalDefinition",
    "read_sectional_definitions",
    "select_sectional_definitions",
)
