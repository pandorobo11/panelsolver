#!/usr/bin/env python3
"""Generate the shared sphere-cone STL and FMF/Hypersonic angle-effect tables."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]


def profile(refinement: int = 1) -> np.ndarray:
    """Return (x, radius) meridians in metres, from nose to rear-axis point."""
    theta = np.deg2rad(15.0)
    psi = np.linspace(0, np.pi / 2 - theta, 25 * refinement)
    nose = np.column_stack((0.2 * (1 - np.cos(psi)), 0.2 * np.sin(psi)))
    x_join, r_join = nose[-1]
    x_base = x_join + (0.5 - r_join) / np.tan(theta)
    cone = np.column_stack(
        (
            np.linspace(x_join, x_base, 25 * refinement),
            np.linspace(r_join, 0.5, 25 * refinement),
        )
    )
    return np.vstack((nose, cone[1:], [x_base, 0]))


def make_mesh(profile: np.ndarray, sections: int = 96) -> trimesh.Trimesh:
    mesh = trimesh.creation.revolve(profile[:, [1, 0]], sections=sections)
    mesh.vertices = mesh.vertices[:, [2, 0, 1]]
    mesh.fix_normals()
    if not mesh.is_volume or not np.all(mesh.area_faces > 0):
        raise ValueError("Expected a closed outward-oriented, nondegenerate mesh")
    return mesh


def generate(destination: Path, refinement: int = 1) -> None:
    geometry = destination / "geometry"
    geometry.mkdir(parents=True, exist_ok=True)
    meridian = profile(refinement)
    mesh = make_mesh(meridian, 96 * refinement)
    mesh.export(geometry / "sphere_cone.stl")
    for domain in ("fmf", "hypersonic"):
        cases = destination / domain
        cases.mkdir(parents=True, exist_ok=True)
        flow = (
            {"S": 5, "Ti_K": 300, "Tw_K": 300}
            if domain == "fmf"
            else {
                "Mach": 6,
                "gamma": 1.4,
                "windward_eq": "modified_newtonian",
                "leeward_eq": "shield",
            }
        )
        rows = [
            {
                "case_id": f"{domain}_sphere_cone_a{alpha:02d}",
                "stl_path": "../geometry/sphere_cone.stl",
                "stl_scale_m_per_unit": 1,
                **flow,
                "alpha_deg": alpha,
                "beta_or_bank_deg": 0,
                "attitude_input": "beta_sin",
                "ref_x_m": 0,
                "ref_y_m": 0,
                "ref_z_m": 0,
                "Aref_m2": np.pi * 0.5**2,
                "Lref_Cl_m": 1,
                "Lref_Cm_m": 1,
                "Lref_Cn_m": 1,
                "shielding_on": 0,
                "save_vtp_on": 1,
            }
            for alpha in (0, 15, 30)
        ]
        with (cases / "sphere_cone.csv").open(
            "w", newline="", encoding="utf-8"
        ) as stream:
            writer = csv.DictWriter(
                stream, fieldnames=list(rows[0]), lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
    print(f"sphere_cone: {len(mesh.faces)} faces, length={meridian[-1, 0]:.6f} m")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=ROOT / "examples")
    parser.add_argument("--refinement", type=int, default=1, choices=(1, 2, 4))
    args = parser.parse_args()
    generate(args.destination, args.refinement)


if __name__ == "__main__":
    main()
