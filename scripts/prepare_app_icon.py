#!/usr/bin/env python3
"""Prepare and inspect the canonical transparent application icon."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

CANVAS_SIZE = 1024
ARTWORK_SCALE = 0.86


def _metrics(path: Path) -> str:
    with Image.open(path) as image:
        width, height = image.size
        has_alpha = "A" in image.getbands()
        alpha = image.getchannel("A") if has_alpha else None
        bbox = alpha.getbbox() if alpha is not None else image.getbbox()
        nontransparent_pixels = (
            width * height - alpha.histogram()[0]
            if alpha is not None
            else width * height
        )
        if bbox is None:
            bbox_text = "empty"
            width_occupancy = height_occupancy = area_occupancy = 0.0
        else:
            left, top, right, bottom = bbox
            bbox_width = right - left
            bbox_height = bottom - top
            bbox_text = f"({left}, {top}, {right}, {bottom})"
            width_occupancy = bbox_width / width
            height_occupancy = bbox_height / height
            area_occupancy = bbox_width * bbox_height / (width * height)
        return (
            f"{path}: dimensions={width}x{height}, size={path.stat().st_size} bytes, "
            f"mode={image.mode}, alpha={has_alpha}, bbox={bbox_text}, "
            f"occupancy={width_occupancy:.2%}x{height_occupancy:.2%} "
            f"(bbox area {area_occupancy:.2%}, "
            f"nontransparent pixels {nontransparent_pixels / (width * height):.2%})"
        )


def prepare_icon(source: Path, output: Path) -> None:
    """Scale the full source canvas and center it on a transparent square."""
    if source.resolve() == output.resolve():
        raise ValueError("source and output must be different paths")
    with Image.open(source) as loaded:
        image = loaded.convert("RGBA")

    target_extent = round(CANVAS_SIZE * ARTWORK_SCALE)
    factor = min(target_extent / image.width, target_extent / image.height)
    resized_size = (
        round(image.width * factor),
        round(image.height * factor),
    )
    resized = image.resize(resized_size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    offset = (
        (CANVAS_SIZE - resized.width) // 2,
        (CANVAS_SIZE - resized.height) // 2,
    )
    canvas.paste(resized, offset)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG", optimize=True, compress_level=9)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="source icon to inspect or prepare")
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        help="prepared icon path; omit to inspect the source only",
    )
    args = parser.parse_args()

    print(_metrics(args.source))
    if args.output is not None:
        prepare_icon(args.source, args.output)
        print(_metrics(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
