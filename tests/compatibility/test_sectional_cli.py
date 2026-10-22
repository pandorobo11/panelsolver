from __future__ import annotations

import csv
import math
import signal
from pathlib import Path
from unittest.mock import patch

import pytest

from panelsolver.app import sectional_cli
from panelsolver.app.sectional_batch import run_sectional_cases
from panelsolver.cli import main
from panelsolver.domains import fmf, hypersonic

ROOT = Path(__file__).parents[2]
HEADER = (
    "section_id,origin_x_stl_m,origin_y_stl_m,origin_z_stl_m,"
    "direction_x_stl,direction_y_stl,direction_z_stl,bin_count,component_ids\n"
)


def _inputs(tmp_path, domain):
    module = fmf if domain == "fmf" else hypersonic
    source = (
        ROOT
        / "examples"
        / domain
        / ("flow_modes.csv" if domain == "fmf" else "basic.csv")
    )
    frame = module.read_cases(source)
    if len(frame) == 1:
        frame = frame.loc[frame.index.repeat(2)].reset_index(drop=True)
    frame["case_id"] = ["case_001", "case_002"]
    cases = tmp_path / "cases.csv"
    frame.to_csv(cases, index=False)
    definitions = tmp_path / "sections.csv"
    definitions.write_text(
        HEADER + '001,0,0,0,0,1,0,3,\n"a,b",0,0,0,1,1,1,2,0\n', encoding="utf-8"
    )
    output = tmp_path / "results.csv"
    return cases, definitions, output


def _args(domain, paths):
    cases, definitions, output = paths
    return [
        domain,
        "sectional-loads",
        "-i",
        str(cases),
        "-d",
        str(definitions),
        "-o",
        str(output),
        "--plain",
    ]


def _rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


@pytest.mark.parametrize("domain", ("fmf", "hypersonic"))
def test_cli_real_batch_independent_filters_and_no_intermediate_artifacts(
    tmp_path, domain
):
    paths = _inputs(tmp_path, domain)
    assert main(_args(domain, paths)) == 0
    all_rows = _rows(paths[2])
    assert len(all_rows) == 2 * (3 + 2) * 2
    assert {row["batch_status"] for row in all_rows} == {"completed"}
    assert len({(row["case_id"], row["section_id"]) for row in all_rows}) == 4
    assert not (tmp_path / "outputs").exists()
    assert (
        main(_args(domain, paths) + ["--cases", "case_002", "--sections", "a,b"]) == 0
    )
    selected = _rows(paths[2])
    expected = [
        r for r in all_rows if r["case_id"] == "case_002" and r["section_id"] == "a,b"
    ]
    assert len(selected) == len(expected) == 4
    assert selected == expected
    if domain == "fmf":
        # Mode B is part of the actual command run, not converted to public Mode A inputs.
        assert {r["case_id"] for r in all_rows} == {"case_001", "case_002"}


@pytest.mark.parametrize(
    ("domain", "scalar_name"),
    (("fmf", "normal_traction_coeff"), ("hypersonic", "cp")),
)
def test_cp_cli_real_batch_columns_filters_and_no_intermediate_artifacts(
    tmp_path, domain, scalar_name
):
    from panelsolver.app.sectional_cp_csv import CP_CSV_COLUMNS

    paths = _inputs(tmp_path, domain)
    paths[1].write_text(
        HEADER.replace("bin_count", "section_count")
        + '001,0,0,0,0,1,0,3,\n"a,b",0,0,0,1,1,1,2,0\n',
        encoding="utf-8",
    )
    args = _args(domain, paths)
    args[1] = "sectional-cp"
    assert main(args) == 0
    with paths[2].open(encoding="utf-8-sig", newline="") as stream:
        assert tuple(next(csv.reader(stream))) == CP_CSV_COLUMNS
    all_rows = _rows(paths[2])
    assert {row["batch_status"] for row in all_rows} == {"completed"}
    assert {row["section_count"] for row in all_rows} == {"3", "2"}
    planes = {(r["case_id"], r["section_id"], r["plane_index"]) for r in all_rows}
    assert planes == {
        (case_id, section_id, str(index))
        for case_id in ("case_001", "case_002")
        for section_id, count in (("001", 3), ("a,b", 2))
        for index in range(count)
    }
    segments = [row for row in all_rows if row["plane_status"] == "ok"]
    assert segments
    assert {row["scalar_name"] for row in segments} == {scalar_name}
    for row in segments:
        for column in (
            "x0_stl_m",
            "y0_stl_m",
            "z0_stl_m",
            "x1_stl_m",
            "y1_stl_m",
            "z1_stl_m",
            "scalar_value",
        ):
            assert math.isfinite(float(row[column]))
    assert not (tmp_path / "outputs").exists()
    assert main(args + ["--cases", "case_002", "--sections", "a,b"]) == 0
    selected = _rows(paths[2])
    expected = [
        r for r in all_rows if r["case_id"] == "case_002" and r["section_id"] == "a,b"
    ]
    assert expected
    assert selected == expected


@pytest.mark.parametrize(
    "selector",
    (
        ["--cases", "unknown"],
        ["--sections", "unknown"],
        ["--cases", " , "],
        ["--sections", " "],
    ),
)
def test_unknown_or_empty_selection_fails_before_solve(tmp_path, capsys, selector):
    paths = _inputs(tmp_path, "fmf")
    with patch.object(
        sectional_cli, "run_sectional_cases", side_effect=AssertionError("solve")
    ):
        assert main(_args("fmf", paths) + selector) == 1
    assert "Error:" in capsys.readouterr().err
    assert not paths[2].exists()


def test_invalid_unselected_definition_rejects_entire_file(tmp_path, capsys):
    paths = _inputs(tmp_path, "hypersonic")
    with paths[1].open("a") as stream:
        stream.write("invalid,0,0,0,0,0,0,3,\n")
    with patch.object(
        sectional_cli, "run_sectional_cases", side_effect=AssertionError("solve")
    ):
        assert main(_args("hypersonic", paths) + ["--sections", "001"]) == 1
    assert "invalid" in capsys.readouterr().err


def test_cli_partial_failure_and_save_failure_are_distinct(tmp_path, capsys):
    paths = _inputs(tmp_path, "hypersonic")
    paths[1].write_text(HEADER + "good,0,0,0,0,1,0,3,\nbad,0,0,0,0,1,0,3,99\n")
    assert main(_args("hypersonic", paths)) == 1
    partial = _rows(paths[2])
    assert {row["section_id"] for row in partial} == {"good"}
    assert {row["batch_status"] for row in partial} == {"failed"}
    assert len({(row["case_id"], row["section_id"]) for row in partial}) == 1
    assert "section_id='bad'" in capsys.readouterr().err
    previous = paths[2].read_bytes()
    with patch(
        "panelsolver.app.csv_writer.os.replace", side_effect=OSError("disk failure")
    ):
        assert main(_args("hypersonic", paths)) == 1
    assert "save failed" in capsys.readouterr().err
    assert paths[2].read_bytes() == previous


def test_cli_cooperative_sigint_retains_partial_and_restores_handler(tmp_path, capsys):
    paths = _inputs(tmp_path, "fmf")
    previous = signal.getsignal(signal.SIGINT)

    def request_after_case(*args, **kwargs):
        progress = kwargs["progress_cb"]

        def update(done, total):
            progress(done, total)
            signal.raise_signal(signal.SIGINT)

        return run_sectional_cases(*args, **(kwargs | {"progress_cb": update}))

    with patch.object(
        sectional_cli, "run_sectional_cases", side_effect=request_after_case
    ):
        assert main(_args("fmf", paths)) == 130
    assert signal.getsignal(signal.SIGINT) is previous
    rows = _rows(paths[2])
    assert {row["batch_status"] for row in rows} == {"cancelled"}
    assert len({(row["case_id"], row["section_id"]) for row in rows}) == 2
    assert "partial" in capsys.readouterr().err


@pytest.mark.parametrize("domain", ("fmf", "hypersonic"))
@pytest.mark.parametrize("command", ("sectional-loads", "sectional-cp"))
def test_sectional_help_and_workers_validation(domain, command, capsys):
    with pytest.raises(SystemExit) as caught:
        main([domain, command, "--help"])
    assert caught.value.code == 0
    help_text = capsys.readouterr().out
    assert f"{domain} {command}" in help_text
    for text in (
        "STL",
        "metres",
        "Blank",
        "zero-based",
        "--cases",
        "--sections",
        "--workers",
    ):
        assert text in help_text
    with pytest.raises(SystemExit) as caught:
        main([domain, command, "-i", "x", "-d", "y", "-o", "z", "-j", "0"])
    assert caught.value.code == 2


def test_cli_protects_unselected_stl_and_definition_inputs(tmp_path, capsys):
    paths = _inputs(tmp_path, "hypersonic")
    unselected_stl = tmp_path / "unselected.stl"
    unselected_stl.write_bytes((ROOT / "examples/geometry/plate.stl").read_bytes())
    cases = _rows(paths[0])
    cases[1]["stl_path"] = str(unselected_stl)
    with paths[0].open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(cases[0]))
        writer.writeheader()
        writer.writerows(cases)
    for target in (paths[0], paths[1], unselected_stl):
        original = target.read_bytes()
        args = _args("hypersonic", (paths[0], paths[1], target))
        with patch.object(
            sectional_cli, "run_sectional_cases", side_effect=AssertionError("solve")
        ):
            assert main(args + ["--cases", "case_001"]) == 1
        assert target.read_bytes() == original
        assert "protected" in capsys.readouterr().err


def test_result_schema_matches_documented_column_order():
    from panelsolver.app.sectional_batch import SECTIONAL_CSV_COLUMNS

    source = (ROOT / "docs/reference/sectional-loads-csv.md").read_text()
    block = source.split("<!-- sectional-result-columns -->\n```text\n", 1)[1].split(
        "```", 1
    )[0]
    assert tuple(block.replace("\n", "").split(",")) == SECTIONAL_CSV_COLUMNS
    assert not any("cumulative" in column for column in SECTIONAL_CSV_COLUMNS)
