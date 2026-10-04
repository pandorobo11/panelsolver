"""CSV projection of section segments and explicit empty/failed plane rows."""

from panelsolver.core import CsvProjection
from panelsolver.core.sectional_cp import SectionalCp

CP_PAIR_COLUMNS = (
    "case_id",
    "case_signature",
    "section_id",
    *(f"origin_{a}_stl_m" for a in "xyz"),
    *(f"direction_hat_{a}_stl" for a in "xyz"),
    "selected_component_ids",
    "range_mode",
    "resolved_start_m",
    "resolved_stop_m",
    "section_count",
    "plane_index",
    "position_m",
    "plane_status",
    "message",
    "component_id",
    "face_id",
    *(f"{a}{end}_stl_m" for end in (0, 1) for a in "xyz"),
    "scalar_name",
    "scalar_value",
)
CP_CSV_COLUMNS = (*CP_PAIR_COLUMNS[:3], "batch_status", *CP_PAIR_COLUMNS[3:])


def project_cp_sections(
    result: SectionalCp, case_id: str, section_id: str
) -> CsvProjection:
    definition = result.definition
    common = {
        "case_id": case_id,
        "case_signature": result.case_signature,
        "section_id": section_id,
        "selected_component_ids": ";".join(map(str, result.selected_component_ids)),
        "range_mode": "auto" if definition.start_m is None else "explicit",
        "resolved_start_m": result.planes[0].position_m,
        "resolved_stop_m": result.planes[-1].position_m,
        "section_count": definition.section_count,
        "scalar_name": result.scalar_name,
    }
    for k, a in enumerate("xyz"):
        common[f"origin_{a}_stl_m"] = float(definition.axis_origin_stl_m[k])
        common[f"direction_hat_{a}_stl"] = float(definition.axis_direction_hat_stl[k])
    rows = []
    for i, plane in enumerate(result.planes):
        base = dict(
            common,
            plane_index=i,
            position_m=plane.position_m,
            plane_status=plane.status,
            message=plane.message,
        )
        if plane.status != "ok":
            rows.append({name: base.get(name) for name in CP_PAIR_COLUMNS})
        for j, face in enumerate(plane.source_face_indices):
            row = dict(
                base,
                face_id=int(face),
                component_id=int(plane.component_ids[j]),
                scalar_value=float(plane.scalar_values[j]),
            )
            for end in (0, 1):
                for k, a in enumerate("xyz"):
                    row[f"{a}{end}_stl_m"] = float(plane.endpoints_stl_m[j, end, k])
            rows.append({name: row[name] for name in CP_PAIR_COLUMNS})
    return CsvProjection(CP_PAIR_COLUMNS, tuple(rows))


def project_cp_failure(
    definition, case_id: str, section_id: str, signature: str, message: str
) -> CsvProjection:
    """A definition that could not resolve against this case has no plane index."""
    base = {
        "case_id": case_id,
        "case_signature": signature,
        "section_id": section_id,
        "section_count": definition.section_count,
        "plane_status": "failed",
        "message": message,
        "range_mode": "auto" if definition.start_m is None else "explicit",
    }
    for k, a in enumerate("xyz"):
        base[f"origin_{a}_stl_m"] = float(definition.axis_origin_stl_m[k])
        base[f"direction_hat_{a}_stl"] = float(definition.axis_direction_hat_stl[k])
    return CsvProjection(
        CP_PAIR_COLUMNS, ({name: base.get(name) for name in CP_PAIR_COLUMNS},)
    )
