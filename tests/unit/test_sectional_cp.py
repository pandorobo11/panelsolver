"""Independent analytic segments, discontinuities, and public workflows."""

import csv
import pickle
from unittest.mock import patch

import numpy as np
import pytest

from panelsolver.app.sectional_batch import run_sectional_cases, write_sectional_csv
from panelsolver.app.sectional_definitions import (
    SectionalDefinition,
    read_sectional_definitions,
)
from panelsolver.core.contracts import LocalLoads
from panelsolver.core.sectional_cp import SectionalCpDefinition, compute_cp_sections
from panelsolver.domains import fmf, hypersonic
from panelsolver.postprocess import compute_sectional_cp
from tests.unit.test_postprocess import _solve
from tests.unit.test_sectional_geometry import TRIANGLE, make_mesh


def definition(**changes):
    return SectionalCpDefinition(
        **(
            {
                "axis_origin_stl_m": (0, 0, 0),
                "axis_direction_stl": (1, 0, 0),
                "section_count": 1,
                "start_m": 0.5,
                "stop_m": 0.5,
            }
            | changes
        )
    )


def extract(mesh=None, spec=None, name="cp"):
    mesh = make_mesh() if mesh is None else mesh
    return compute_cp_sections(
        mesh,
        LocalLoads(
            np.zeros((len(mesh.faces), 3)), {name: np.arange(len(mesh.faces)) + 0.3}
        ),
        spec or definition(),
        "test-signature",
    )


def test_analytic_endpoints_and_panel_values():
    mesh = make_mesh([TRIANGLE, [[1, 0, 0], [1, 1, 0], [0, 1, 0]]])
    plane = extract(mesh).planes[0]
    assert plane.status == "ok"
    assert plane.source_face_indices.tolist() == [0, 1]
    np.testing.assert_array_equal(plane.scalar_values, [0.3, 1.3])
    # Each panel owns its segment, including the discontinuous shared endpoint.
    expected = [{(0.5, 0.0, 0.0), (0.5, 0.5, 0.0)}, {(0.5, 0.5, 0.0), (0.5, 1.0, 0.0)}]
    assert [set(map(tuple, s)) for s in plane.endpoints_stl_m] == expected


def test_shared_edge_keeps_both_values():
    mesh = make_mesh([TRIANGLE, [[0, 0, 0], [0, 1, 0], [-1, 0, 0]]])
    plane = extract(mesh, definition(start_m=0.0, stop_m=0.0)).planes[0]
    assert len(plane.scalar_values) == 2
    assert set(map(tuple, plane.endpoints_stl_m[0])) == set(
        map(tuple, plane.endpoints_stl_m[1])
    )
    np.testing.assert_array_equal(plane.scalar_values, [0.3, 1.3])


@pytest.mark.parametrize(
    "section_count,tip_x,plane_index", [(2, 0, 1), (3, 0.2, 1), (1, 0.2, 0)]
)
def test_auto_oblique_plane_keeps_shared_edge(section_count, tip_x, plane_index):
    mesh = make_mesh(
        [
            [[0, 0, 0], [0.1, 0, 0], [0, 0.1, 0]],
            [[tip_x, 0, 1], [0.1, 0, 0], [0, 0.1, 0]],
        ]
    )
    result = extract(
        mesh,
        definition(
            axis_direction_stl=(1, 1, 0),
            section_count=section_count,
            start_m=None,
            stop_m=None,
        ),
    )
    plane = result.planes[plane_index]
    assert plane.status == "ok"
    assert plane.source_face_indices.tolist() == [0, 1]
    np.testing.assert_array_equal(plane.scalar_values, [0.3, 1.3])
    np.testing.assert_array_equal(
        plane.endpoints_stl_m, [[[0.1, 0, 0], [0, 0.1, 0]]] * 2
    )


def test_auto_oblique_coplanar_triangle_fails():
    mesh = make_mesh([[[0.1, 0, 0], [0, 0.1, 0], [0.1, 0, 1]]])
    plane = extract(
        mesh,
        definition(axis_direction_stl=(1, 1, 0), start_m=None, stop_m=None),
    ).planes[0]
    assert plane.status == "failed"
    assert "coplanar" in plane.message
    assert plane.endpoints_stl_m.shape == (0, 2, 3)
    assert plane.scalar_values.size == 0


def test_explicit_oblique_position_is_not_snapped_to_auto_endpoint():
    mesh = make_mesh([[[0, 0, 0], [0.1, 0, 0], [0, 0.1, 0]]])
    spec = definition(axis_direction_stl=(1, 1, 0), start_m=None, stop_m=None)
    rounded_endpoint = 0.1 * spec.axis_direction_hat_stl[0]
    plane = extract(
        mesh,
        definition(
            axis_direction_stl=(1, 1, 0),
            start_m=rounded_endpoint,
            stop_m=rounded_endpoint,
        ),
    ).planes[0]
    # This float64 lies just beyond the exact projection of the shared edge.
    assert plane.status == "empty"


@pytest.mark.parametrize("location", [1.0, 2.0])
def test_point_and_nonintersection_are_empty(location):
    plane = extract(spec=definition(start_m=location, stop_m=location)).planes[0]
    assert plane.status == "empty"
    assert plane.endpoints_stl_m.shape == (0, 2, 3)


def test_coplanar_failure_does_not_discard_other_planes():
    result = extract(
        spec=definition(
            axis_direction_stl=(0, 0, 1), section_count=3, start_m=-1.0, stop_m=1.0
        )
    )
    assert [p.status for p in result.planes] == ["empty", "failed", "empty"]
    assert "coplanar" in result.planes[1].message


@pytest.mark.parametrize("shift,scale", [(1e9, 1), (0, 1e-60), (0, 1e60)])
def test_translation_and_scale(shift, scale):
    mesh = make_mesh([TRIANGLE * scale + shift])
    plane = extract(
        mesh,
        definition(
            axis_origin_stl_m=(shift, shift, shift), start_m=scale / 2, stop_m=scale / 2
        ),
    ).planes[0]
    assert plane.status == "ok"
    np.testing.assert_allclose(
        (plane.endpoints_stl_m[0] - shift) / scale,
        [[0.5, 0, 0], [0.5, 0.5, 0]],
        rtol=1e-14,
        atol=0,
    )


def test_oblique_plane():
    spec = definition(axis_direction_stl=(1, 1, 0), start_m=0.25, stop_m=0.25)
    plane = extract(spec=spec).planes[0]
    np.testing.assert_allclose(
        plane.endpoints_stl_m @ spec.axis_direction_hat_stl, 0.25, rtol=1e-15
    )
    np.testing.assert_allclose(
        np.sort(plane.endpoints_stl_m[0, :, :2], axis=0),
        [[0, 0], [np.sqrt(2) / 4, np.sqrt(2) / 4]],
        rtol=1e-15,
    )


def test_selection_auto_single_and_pickle():
    mesh = make_mesh([TRIANGLE, TRIANGLE + [2, 0, 0]], ids=[2, 7])
    result = extract(mesh, definition(start_m=None, stop_m=None, component_ids=(7,)))
    assert result.planes[0].position_m == 2.5
    assert result.planes[0].source_face_indices.tolist() == [1]
    restored = pickle.loads(pickle.dumps(result))
    with pytest.raises(ValueError):
        restored.planes[0].endpoints_stl_m[0, 0, 0] = 2


@pytest.mark.parametrize(
    "changes",
    [
        {"section_count": True},
        {"section_count": 0},
        {"section_count": 1.5},
        {"axis_direction_stl": (0, 0, 0)},
        {"axis_origin_stl_m": (True, 0, 0)},
        {"start_m": float("nan")},
        {"stop_m": None},
        {"stop_m": 1},
        {"section_count": 2},
        {"component_ids": (0, 0)},
    ],
)
def test_reject_invalid_definitions(changes):
    with pytest.raises((ValueError, TypeError)):
        definition(**changes)


def test_missing_scalar_and_mismatched_faces():
    with pytest.raises(ValueError):
        compute_cp_sections(
            make_mesh(), LocalLoads(np.zeros((1, 3))), definition(), "x"
        )
    with pytest.raises(ValueError):
        compute_cp_sections(
            make_mesh(), LocalLoads(np.zeros((2, 3)), {"cp": [0, 1]}), definition(), "x"
        )


@pytest.mark.parametrize("domain", ["fmf", "hypersonic"])
def test_public_api_uses_retained_solve(domain):
    solved = _solve(domain)
    with patch(
        "panelsolver.api.execute_case",
        side_effect=AssertionError("must not solve again"),
    ):
        result = compute_sectional_cp(
            solved,
            axis_origin_stl_m=(0, 0, 0),
            axis_direction_stl=(0, 1, 0),
            section_count=3,
            start_m=-0.2,
            stop_m=0.2,
        )
    assert result.case_signature == solved.case_signature
    assert result.scalar_name == (
        "cp" if domain == "hypersonic" else "normal_traction_coeff"
    )
    assert any(p.status == "ok" for p in result.planes)
    for plane in result.planes:
        np.testing.assert_array_equal(
            plane.scalar_values,
            solved.local_loads.cell_scalars[result.scalar_name][
                plane.source_face_indices
            ],
        )


@pytest.mark.parametrize("domain", [fmf, hypersonic])
def test_batch_parser_and_csv(tmp_path, domain):
    path = tmp_path / "definitions.csv"
    path.write_text(
        "section_id,origin_x_stl_m,origin_y_stl_m,origin_z_stl_m,direction_x_stl,direction_y_stl,direction_z_stl,start_m,stop_m,section_count\nspan,0,0,0,0,1,0,-.2,.2,3\n"
    )
    defs = read_sectional_definitions(path, cp=True)
    row = (
        domain.read_cases(f"examples/{domain.RUNTIME_POLICY.product_id}/basic.csv")
        .iloc[0]
        .to_dict()
    )
    from panelsolver.app import sectional_batch

    original = sectional_batch.execute_case
    with patch.object(sectional_batch, "execute_case", wraps=original) as solve:
        result = run_sectional_cases([row], domain.RUNTIME_POLICY, defs)
    assert solve.call_count == 1
    assert result.status == "completed"
    assert result.csv is not None
    target = tmp_path / "result.csv"
    write_sectional_csv(target, result, [path])
    with target.open(encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert "x0_stl_m" in rows[0] and "x1_stl_m" in rows[0]
    assert {r["plane_index"] for r in rows} == {"0", "1", "2"}
    with pytest.raises(ValueError):
        write_sectional_csv(path, result, [path])


def test_failed_planes_continue_in_batch():
    row = hypersonic.read_cases("examples/hypersonic/basic.csv").iloc[0].to_dict()
    defs = (
        SectionalDefinition(
            "cut", definition(section_count=3, start_m=-0.5, stop_m=0.5)
        ),
        SectionalDefinition("empty", definition(start_m=10, stop_m=10)),
    )
    result = run_sectional_cases([row], hypersonic.RUNTIME_POLICY, defs)
    assert result.csv is not None
    assert any(r["section_id"] == "empty" for r in result.csv.rows)


def test_resolution_failure_retains_row_and_continues():
    row = hypersonic.read_cases("examples/hypersonic/basic.csv").iloc[0].to_dict()
    defs = (
        SectionalDefinition("invalid_component", definition(component_ids=(999,))),
        SectionalDefinition("empty", definition(start_m=10, stop_m=10)),
    )
    result = run_sectional_cases([row], hypersonic.RUNTIME_POLICY, defs)
    assert result.status == "failed"
    assert result.completed_pairs == 1
    assert [r["plane_status"] for r in result.csv.rows] == ["failed", "empty"]
    assert result.csv.rows[0]["plane_index"] is None


def test_failed_coplanar_plane_batch_and_following_case():
    row = hypersonic.read_cases("examples/hypersonic/basic.csv").iloc[0].to_dict()
    # The basic example is a flat x=0 plate; cut x=-1,0,1.
    defs = (
        SectionalDefinition(
            "coplanar",
            definition(
                axis_direction_stl=(1, 0, 0), section_count=3, start_m=-1, stop_m=1
            ),
        ),
    )
    result = run_sectional_cases(
        [row, {**row, "case_id": "second"}], hypersonic.RUNTIME_POLICY, defs
    )
    assert result.status == "failed"
    assert result.completed_pairs == 0
    assert [r["plane_status"] for r in result.csv.rows] == [
        "empty",
        "failed",
        "empty",
    ] * 2


@pytest.mark.slow
@pytest.mark.parametrize("domain", [fmf, hypersonic])
def test_cp_spawn_matches_serial(domain):
    row = (
        domain.read_cases(f"examples/{domain.RUNTIME_POLICY.product_id}/basic.csv")
        .iloc[0]
        .to_dict()
    )
    rows = [dict(row, case_id=str(i)) for i in range(3)]
    definitions = (
        SectionalDefinition(
            "cuts",
            definition(
                axis_direction_stl=(0, 1, 0), section_count=3, start_m=-0.2, stop_m=0.2
            ),
        ),
    )
    serial = run_sectional_cases(rows, domain.RUNTIME_POLICY, definitions)
    parallel = run_sectional_cases(rows, domain.RUNTIME_POLICY, definitions, workers=2)
    assert serial.status == parallel.status == "completed"
    assert serial.csv == parallel.csv


def collapsed_loop():
    a, b, c, d = [1, -1e-18, 1], [2, 1, 1], [1, 1, 2], [0, -1, 0]
    return extract(
        make_mesh([[a, b, c], [a, b, d], [a, c, d], [b, c, d]]),
        definition(axis_direction_stl=(0, 1, 0), start_m=0, stop_m=0),
    )


def test_collapsed_segment_preserves_closed_loop_and_values():
    from collections import Counter

    from panelsolver.app.sectional_cp_csv import project_cp_sections

    result = collapsed_loop()
    plane = result.planes[0]
    assert plane.status == "warning"
    assert "Omitted 1 intersection segment(s)" in plane.message
    assert "source face indices: 0" in plane.message
    np.testing.assert_array_equal(plane.source_face_indices, [1, 2, 3])
    np.testing.assert_array_equal(plane.scalar_values, [1.3, 2.3, 3.3])
    # The three surviving segments form a closed loop in the saved coordinates.
    counts = Counter(map(tuple, plane.endpoints_stl_m.reshape(-1, 3)))
    assert len(counts) == 3 and set(counts.values()) == {2}
    assert all(tuple(a) != tuple(b) for a, b in plane.endpoints_stl_m)
    csv_result = project_cp_sections(result, "case", "section")
    assert len(csv_result.rows) == 3
    assert all(r["plane_status"] == "warning" for r in csv_result.rows)
    assert [r["face_id"] for r in csv_result.rows] == [1, 2, 3]


def test_all_collapsed_segments_keep_warning_status_row():
    from panelsolver.app.sectional_cp_csv import project_cp_sections

    triangle = [[1, -1e-18, 1], [2, 1, 1], [1, 1, 2]]
    result = extract(
        make_mesh([triangle, triangle]),
        definition(axis_direction_stl=(0, 1, 0), start_m=0, stop_m=0),
    )
    plane = result.planes[0]
    assert plane.status == "warning"
    assert "Omitted 2 intersection segment(s)" in plane.message
    assert "source face indices: 0;1" in plane.message
    assert plane.endpoints_stl_m.shape == (0, 2, 3)
    rows = project_cp_sections(result, "case", "section").rows
    assert len(rows) == 1
    assert rows[0]["plane_status"] == "warning"
    assert rows[0]["face_id"] is None
    assert rows[0]["scalar_value"] is None
    assert rows[0]["x0_stl_m"] is None


def test_tiny_representable_segment_is_not_omitted():
    result = extract(
        make_mesh([[[0, -1e-18, 0], [1, 1, 0], [0, 1, 1]]]),
        definition(axis_direction_stl=(0, 1, 0), start_m=0, stop_m=0),
    )
    assert result.planes[0].status == "ok"
    np.testing.assert_array_equal(
        result.planes[0].endpoints_stl_m, [[[1e-18, 0, 0], [0, 0, 1e-18]]]
    )


def test_coplanar_failure_still_overrides_omissions():
    result = extract(
        make_mesh(
            [
                [[1, -1e-18, 1], [2, 1, 1], [1, 1, 2]],
                [[0, 0, 0], [1, 0, 0], [0, 0, 1]],
            ]
        ),
        definition(axis_direction_stl=(0, 1, 0), start_m=0, stop_m=0),
    )
    plane = result.planes[0]
    assert plane.status == "failed"
    assert "coplanar" in plane.message and "Omitted 1" in plane.message
    assert plane.source_face_indices.size == 0


def test_warning_batch_completes_and_saves(tmp_path):
    row = hypersonic.read_cases("examples/hypersonic/basic.csv").iloc[0].to_dict()
    result = collapsed_loop()
    logs = []
    with patch(
        "panelsolver.app.sectional_batch.compute_cp_sections", return_value=result
    ):
        batch = run_sectional_cases(
            [row, dict(row, case_id="second")],
            hypersonic.RUNTIME_POLICY,
            (SectionalDefinition("cut", result.definition),),
            logfn=logs.append,
        )
    assert batch.status == "completed"
    assert batch.completed_pairs == batch.completed_cases == 2
    assert not batch.errors
    assert (
        sum("[WARNING]" in line and "source face indices: 0" in line for line in logs)
        == 2
    )
    target = tmp_path / "warning.csv"
    write_sectional_csv(target, batch, [])
    with target.open(encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 6
    assert all(r["plane_status"] == "warning" for r in rows)
    assert all(r["batch_status"] == "completed" for r in rows)


def test_compact_csv_counts_and_diagnostic_serialization():
    from dataclasses import replace

    from panelsolver.app.sectional_cp_csv import CP_CSV_COLUMNS, project_cp_sections

    assert len(CP_CSV_COLUMNS) == 29
    assert CP_CSV_COLUMNS[16:20] == (
        "position_m",
        "plane_status",
        "omitted_segment_count",
        "component_id",
    )
    assert "message" not in CP_CSV_COLUMNS
    warning = collapsed_loop()
    cases = [
        (extract(), 0, "ok"),
        (extract(spec=definition(start_m=2, stop_m=2)), 0, "empty"),
        (warning, 1, "warning"),
        (
            extract(spec=definition(axis_direction_stl=(0, 0, 1), start_m=0, stop_m=0)),
            None,
            "failed",
        ),
    ]
    for result, count, status in cases:
        restored = pickle.loads(pickle.dumps(result))
        assert restored.planes[0].omitted_segment_count == count
        assert restored.planes[0].message == result.planes[0].message
        # The numeric count must not depend on diagnostic text or its length.
        plane = replace(restored.planes[0], message="long diagnostic " * 1000)
        rows = project_cp_sections(
            replace(restored, planes=(plane,)), "case", "cut"
        ).rows
        assert rows
        for row in rows:
            assert row["omitted_segment_count"] == count
            assert row["plane_status"] == status
            assert "message" not in row
            assert "long diagnostic" not in str(row)


def test_cp_failure_details_are_logged_not_exported():
    row = hypersonic.read_cases("examples/hypersonic/basic.csv").iloc[0].to_dict()
    definitions = (
        SectionalDefinition("invalid", definition(component_ids=(999,))),
        SectionalDefinition("coplanar", definition(start_m=0, stop_m=0)),
    )
    logs = []
    batch = run_sectional_cases(
        [row], hypersonic.RUNTIME_POLICY, definitions, logfn=logs.append
    )
    assert batch.status == "failed"
    assert len(batch.errors) == 2
    assert any("section_id='invalid'" in line and "[ERROR]" in line for line in logs)
    assert any("section_id='coplanar'" in line and "coplanar" in line for line in logs)
    assert all(
        r["omitted_segment_count"] is None and "message" not in r
        for r in batch.csv.rows
    )
