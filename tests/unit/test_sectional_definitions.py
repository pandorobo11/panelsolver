from __future__ import annotations

import csv
from copy import deepcopy
from dataclasses import FrozenInstanceError
from unittest.mock import patch

import numpy as np
import pytest

from panelsolver.app.sectional_definitions import (
    SectionalDefinition,
    read_sectional_definitions,
    select_sectional_definitions,
)
from panelsolver.core.sectional import SectionalLoadDefinition

COLUMNS = (
    "section_id",
    "origin_x_stl_m",
    "origin_y_stl_m",
    "origin_z_stl_m",
    "direction_x_stl",
    "direction_y_stl",
    "direction_z_stl",
    "start_m",
    "stop_m",
    "bin_count",
    "component_ids",
)
ROW = dict(
    zip(
        COLUMNS,
        ("right", "2", ".5", "0", ".2", ".9", ".4", "", "", "30", "2"),
        strict=True,
    )
)


def _write(tmp_path, rows, *, columns=COLUMNS, encoding="utf-8"):
    path = tmp_path / "sectional_loads.csv"
    with path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.mark.parametrize("encoding", ("utf-8", "utf-8-sig"))
@pytest.mark.parametrize("reverse", (False, True))
def test_valid_csv_encoding_column_order_and_numerical_handoff(
    tmp_path, encoding, reverse
):
    columns = tuple(reversed(COLUMNS)) if reverse else COLUMNS
    path = _write(
        tmp_path,
        [
            ROW | {"section_id": "  0007  "},
            ROW
            | {
                "section_id": "Cafe\u0301",
                "start_m": "-2e0",
                "stop_m": "+1.5",
                "component_ids": " 5 ; 0 ; 2 ",
            },
            ROW | {"section_id": "right,left", "component_ids": "   "},
        ],
        columns=columns,
        encoding=encoding,
    )
    definitions = read_sectional_definitions(path)
    assert isinstance(definitions, tuple)
    assert tuple(item.section_id for item in definitions) == (
        "0007",
        "Café",
        "right,left",
    )
    assert tuple(item.row_number for item in definitions) == (2, 3, 4)
    first = definitions[0].definition
    assert first.bin_count == 30
    assert first.range_mode == "auto"
    assert first.component_ids == (2,)
    np.testing.assert_array_equal(first.axis_origin_stl_m, (2, 0.5, 0))
    np.testing.assert_allclose(
        first.axis_direction_hat_stl,
        np.array((0.2, 0.9, 0.4)) / np.linalg.norm((0.2, 0.9, 0.4)),
    )
    second = definitions[1].definition
    assert second.range_mode == "explicit"
    assert (second.start_m, second.stop_m) == (-2, 1.5)
    assert second.component_ids == (0, 2, 5)
    assert definitions[2].definition.component_ids is None


@pytest.mark.parametrize(
    "optional",
    (
        (),
        ("start_m",),
        ("stop_m",),
        ("component_ids",),
        ("start_m", "stop_m", "component_ids"),
    ),
)
def test_optional_columns_can_be_omitted_or_blank(tmp_path, optional):
    columns = tuple(column for column in COLUMNS if column not in optional)
    path = _write(
        tmp_path,
        [ROW | {"start_m": "  ", "stop_m": "\t", "component_ids": "  "}],
        columns=columns,
    )
    definition = read_sectional_definitions(path)[0].definition
    assert definition.start_m is None
    assert definition.stop_m is None
    assert definition.component_ids is None


def test_labels_are_text_and_case_sensitive_not_portable_filenames(tmp_path):
    ids = ("000", "0", "A", "a", "right,left", "../wing: ?", "翼")
    definitions = read_sectional_definitions(
        _write(tmp_path, [ROW | {"section_id": value} for value in ids])
    )
    assert tuple(item.section_id for item in definitions) == ids
    assert tuple(
        item.section_id
        for item in select_sectional_definitions(definitions, ("right,left", "000"))
    ) == ("000", "right,left")
    with pytest.raises(ValueError, match="unknown section IDs"):
        select_sectional_definitions(definitions, ("right", "left"))


@pytest.mark.parametrize("token", ("30.0", "3e1", "0x1e", "1_0", "True", "", "+", "٣٠"))
def test_integer_count_is_a_decimal_token(tmp_path, token):
    path = _write(tmp_path, [ROW | {"bin_count": token}])
    with pytest.raises(ValueError, match=r"row 2, section_id='right', field bin_count"):
        read_sectional_definitions(path)


@pytest.mark.parametrize(
    "token", ("3.0", "3e0", "True", "0x3", "1_0", "0;", ";0", "0;;1", "0; ;1")
)
def test_component_tokens_require_semicolon_separated_integers(tmp_path, token):
    path = _write(tmp_path, [ROW | {"component_ids": token}])
    with pytest.raises(ValueError, match="field component_ids"):
        read_sectional_definitions(path)


@pytest.mark.parametrize(
    "values,field",
    (
        ({"bin_count": "0"}, "bin_count"),
        ({"bin_count": "-1"}, "bin_count"),
        ({"component_ids": "-1"}, "component_ids"),
        ({"component_ids": "1;01"}, "component_ids"),
        ({"component_ids": str(2**70)}, "component_ids"),
        ({"origin_x_stl_m": "nan"}, "axis_origin_stl_m"),
        ({"direction_z_stl": "inf"}, "axis_direction_stl"),
        ({"origin_z_stl_m": "1e1000"}, "axis_origin_stl_m"),
        (
            {"direction_x_stl": "0", "direction_y_stl": "0", "direction_z_stl": "0"},
            "axis_direction_stl",
        ),
        ({"start_m": "-1"}, "start_m/stop_m"),
        ({"stop_m": "1"}, "start_m/stop_m"),
        ({"start_m": "1", "stop_m": "1"}, "start_m/stop_m"),
        ({"start_m": "2", "stop_m": "1"}, "start_m/stop_m"),
        ({"start_m": "-1", "stop_m": "nan"}, "stop_m"),
    ),
)
def test_a1_owns_numerical_validation(tmp_path, values, field):
    path = _write(tmp_path, [ROW | values])
    with pytest.raises(ValueError) as error:
        read_sectional_definitions(path)
    assert str(path) in str(error.value)
    assert f"row 2, section_id='right', field {field}" in str(error.value)


@pytest.mark.parametrize("field", COLUMNS[1:7])
@pytest.mark.parametrize("token", ("", "   ", "True", "nonsense"))
def test_required_axis_cell_diagnostics_identify_csv_field(tmp_path, field, token):
    with pytest.raises(ValueError, match=f"field {field}"):
        read_sectional_definitions(_write(tmp_path, [ROW | {field: token}]))


@pytest.mark.parametrize("ids", (("same", " same "), ("Café", "Cafe\u0301")))
def test_duplicate_normalized_labels_reject_whole_file(tmp_path, ids):
    path = _write(tmp_path, [ROW | {"section_id": value} for value in ids])
    with pytest.raises(ValueError, match="row 3.*section_id.*duplicate"):
        read_sectional_definitions(path)


@pytest.mark.parametrize("section_id", ("", " ", "\t"))
def test_blank_section_identity_is_rejected(tmp_path, section_id):
    with pytest.raises(ValueError, match="row 2.*field section_id"):
        read_sectional_definitions(_write(tmp_path, [ROW | {"section_id": section_id}]))


@pytest.mark.parametrize(
    "columns,detail",
    (
        (COLUMNS + ("bin_count",), "duplicate"),
        (COLUMNS + ("custom",), "unknown"),
        (COLUMNS + ("case_id",), "unknown"),
        (COLUMNS[1:], "missing"),
    ),
)
def test_invalid_header_is_diagnosed(tmp_path, columns, detail):
    path = _write(tmp_path, [ROW], columns=columns)
    with pytest.raises(ValueError, match=f"row 1.*field header.*{detail}"):
        read_sectional_definitions(path)


@pytest.mark.parametrize(
    "content", ("", "\ufeff", ",".join(COLUMNS) + "\n", ",".join(COLUMNS) + "\n\n")
)
def test_empty_definition_file_rejected(tmp_path, content):
    path = tmp_path / "empty.csv"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="empty|no definitions"):
        read_sectional_definitions(path)


@pytest.mark.parametrize("row", (("right", "2"), tuple(ROW.values()) + ("extra",)))
def test_mismatched_row_length_is_rejected(tmp_path, row):
    path = tmp_path / "bad-row.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        writer.writerow(row)
    with pytest.raises(ValueError, match="row 2.*field row.*cells"):
        read_sectional_definitions(path)


def test_malformed_csv_and_non_utf8_include_file_and_row(tmp_path):
    path = tmp_path / "invalid.csv"
    path.write_text(",".join(COLUMNS) + '\n"unterminated', encoding="utf-8")
    with pytest.raises(ValueError, match="invalid.csv.*row 2.*field CSV"):
        read_sectional_definitions(path)
    path.write_bytes(b"\xff")
    with pytest.raises(ValueError, match="invalid.csv.*field CSV"):
        read_sectional_definitions(path)


def test_all_rows_are_validated_even_before_selection(tmp_path):
    path = _write(tmp_path, [ROW, ROW | {"section_id": "unselected", "bin_count": "0"}])
    with pytest.raises(ValueError, match="row 3, section_id='unselected'.*bin_count"):
        select_sectional_definitions(read_sectional_definitions(path), ("right",))


def test_selector_preserves_input_order_normalizes_ids_and_rejects_unknown(tmp_path):
    definitions = read_sectional_definitions(
        _write(
            tmp_path,
            [ROW | {"section_id": value} for value in ("third", "Café", "first")],
        )
    )
    assert select_sectional_definitions(definitions, None) == definitions
    selected = select_sectional_definitions(
        definitions, ("first", " Cafe\u0301 ", "first")
    )
    assert tuple(item.section_id for item in selected) == ("Café", "first")
    for value in ((), ("missing",), ("",), "first"):
        with pytest.raises((ValueError, TypeError)):
            select_sectional_definitions(definitions, value)


def test_reader_does_not_resolve_mesh_or_repeat_numerical_checks(tmp_path):
    # Unknown mesh IDs and an enormous count are mesh-dependent resolution work.
    path = _write(tmp_path, [ROW | {"component_ids": "999", "bin_count": str(2**70)}])
    with patch(
        "panelsolver.core.sectional.resolve_sectional_load_spec",
        side_effect=AssertionError("mesh resolution"),
    ):
        definition = read_sectional_definitions(path)[0].definition
    assert definition.component_ids == (999,)
    assert definition.bin_count == 2**70


def test_immutable_normalized_definition_has_no_caller_aliases():
    origin = np.array([0.0, 0.0, 0.0])
    direction = np.array([0.0, 1.0, 0.0])
    components = [2, 0]
    numerical = SectionalLoadDefinition(origin, direction, 3, component_ids=components)
    labelled = SectionalDefinition(" Cafe\u0301 ", numerical)
    origin[:] = 99
    direction[:] = 0
    components.clear()
    assert labelled.section_id == "Café"
    assert labelled.row_number == 0
    assert labelled.definition.component_ids == (0, 2)
    for snapshot in (labelled, deepcopy(labelled)):
        np.testing.assert_array_equal(snapshot.definition.axis_origin_stl_m, (0, 0, 0))
        for array in (
            snapshot.definition.axis_origin_stl_m,
            snapshot.definition.axis_direction_stl,
            snapshot.definition.axis_direction_hat_stl,
        ):
            with pytest.raises(ValueError):
                array.setflags(write=True)
        with pytest.raises(FrozenInstanceError):
            snapshot.section_id = "edited"


def test_blank_physical_lines_keep_correct_row_numbers(tmp_path):
    path = _write(tmp_path, [ROW])
    content = path.read_text(encoding="utf-8")
    path.write_text(content.replace("\n", "\n\n", 1), encoding="utf-8")
    assert read_sectional_definitions(path)[0].row_number == 3
