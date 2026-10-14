#!/usr/bin/env python3
"""Plot the sphere-cone example cell scalars from both domains without interpolation."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pyvista as pv
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
from mpl_toolkits.mplot3d import proj3d
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

ROOT = Path(__file__).resolve().parents[1]


def plot(examples_root: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11})
    fig = plt.figure(figsize=(15, 12), facecolor="white")
    fig.subplots_adjust(
        left=0.01, right=0.88, bottom=0.065, top=0.88, wspace=0, hspace=0.12
    )
    cmap = plt.get_cmap("viridis")
    rows = (
        ("hypersonic", "cp", "Hypersonic: Cp", 2.0),
        ("fmf", "normal_traction_coeff", "FMF: normal traction coefficient", 3.0),
        (
            "fmf",
            "tangential_traction_coeff",
            "FMF: tangential traction coefficient",
            1.5,
        ),
    )
    for row, (domain, scalar, label, upper) in enumerate(rows):
        norm = Normalize(0, upper)
        axes = []
        for col, alpha in enumerate((0, 15, 30)):
            case_id = f"{domain}_sphere_cone_a{alpha:02d}"
            mesh = pv.read(
                examples_root / domain / "outputs/sphere_cone" / f"{case_id}.vtp"
            )
            if str(mesh.field_data["case_id"][0]) != case_id:
                raise ValueError("VTP case identity does not match the example")
            values = np.asarray(mesh.cell_data[scalar])
            triangles = mesh.points[mesh.faces.reshape(-1, 4)[:, 1:]]
            if (
                not np.all(np.isfinite(values))
                or values.min() < 0
                or values.max() > upper
            ):
                raise ValueError(f"Unexpected {scalar} range")
            if float(mesh.field_data["alpha_deg"][0]) != alpha:
                raise ValueError("VTP attitude does not match plot label")
            ax = fig.add_subplot(3, 3, row * 3 + col + 1, projection="3d")
            axes.append(ax)
            surface = Poly3DCollection(
                triangles,
                facecolors=cmap(norm(values)),
                edgecolors="none",
                linewidths=0,
                antialiased=False,
                rasterized=True,
            )
            ax.add_collection3d(surface)
            ax.set(xlim=(-0.15, 1.4), ylim=(-0.65, 0.65), zlim=(-0.65, 0.65))
            ax.set_box_aspect((1.55, 1.3, 1.3), zoom=1.35)
            ax.set_proj_type("ortho")
            ax.view_init(elev=-20, azim=-135)
            ax.set_axis_off()
            ax.set_title(f"alpha = {alpha} deg", pad=-5, fontsize=13)
            velocity = np.array(
                [float(mesh.field_data[f"velocity_hat_{a}_stl"][0]) for a in "xyz"]
            )
            # Project the true flow vector into the camera, but place its key
            # outside the surface so it cannot obscure the scalar colors.
            projected = np.array(
                proj3d.proj_transform(
                    [0, velocity[0]], [0, velocity[1]], [0, velocity[2]], ax.get_proj()
                )[:2]
            )
            direction = projected[:, 1] - projected[:, 0]
            direction = 0.18 * direction / np.linalg.norm(direction)
            origin = np.array([0.67, 0.92])
            ax.annotate(
                "",
                xy=origin + direction,
                xytext=origin,
                xycoords="axes fraction",
                arrowprops={"arrowstyle": "->", "color": "#333333"},
            )
            ax.text2D(0.67, 0.80, "Flow", transform=ax.transAxes, fontsize=10)
        fig.colorbar(
            ScalarMappable(norm=norm, cmap=cmap),
            ax=axes,
            fraction=0.018,
            pad=0.015,
            shrink=0.72,
            label=label,
        )
    fig.suptitle("Sphere-cone: angle effects", fontsize=22, y=0.985)
    fig.text(
        0.46,
        0.922,
        "Hypersonic: Mach 6, gamma = 1.4, Modified Newtonian / zero leeward Cp\n"
        "FMF: Sentman, S = 5, Ti = Tw = 300 K  |  All cases: beta = 0 deg",
        ha="center",
        fontsize=12,
    )
    fig.text(
        0.46,
        0.015,
        "Same geometry and camera; fixed color scale within each row. Cell values without interpolation.\n"
        "Idealized panel-model examples; the two domains represent different flow regimes.",
        ha="center",
        fontsize=11,
        color="#444444",
    )
    for suffix in ("png", "pdf"):
        path = output_dir / f"sphere_cone_angle_effects.{suffix}"
        fig.savefig(path, dpi=180)
        print(path)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--examples-root",
        type=Path,
        default=ROOT / "examples",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs/sphere_cone",
    )
    args = parser.parse_args()
    plot(args.examples_root, args.output_dir)


if __name__ == "__main__":
    main()
