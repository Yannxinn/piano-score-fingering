#!/usr/bin/env python3
"""Create enlarged anchor contact sheets from a unified plan and page images."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

from plan_io import load_plan, page_map


def crop_with_padding(image: Image.Image, x: float, y: float, width: int, height: int) -> Image.Image:
    left, top = int(round(x - width / 2)), int(round(y - height / 2))
    canvas = Image.new("RGB", (width, height), "white")
    box = (max(0, left), max(0, top), min(image.width, left + width), min(image.height, top + height))
    if box[2] > box[0] and box[3] > box[1]:
        canvas.paste(image.crop(box), (box[0] - left, box[1] - top))
    return canvas


def main() -> int:
    global Image, ImageDraw, ImageFont
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as exc:
        raise ValueError(
            "anchor contact sheets require the host's optional image-view runtime; "
            "continue with direct page zoom when Pillow is unavailable"
        ) from exc
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("-o", "--output-dir", type=Path, required=True)
    parser.add_argument("--crop-width", type=int, default=72)
    parser.add_argument("--crop-height", type=int, default=56)
    parser.add_argument("--scale", type=int, default=3)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--rows", type=int, default=5)
    args = parser.parse_args()
    plan = load_plan(args.plan)
    pages = page_map(plan)
    notes: dict[int, list[dict]] = defaultdict(list)
    for note in plan["notes"]:
        if all(key in note for key in ("page", "page_x", "page_y")):
            notes[int(note["page"])].append(note)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    font, per_sheet = ImageFont.load_default(), args.columns * args.rows
    for page_number, members in sorted(notes.items()):
        page_info = pages[page_number]
        image_path = Path(str(page_info.get("image", "")))
        if not image_path.is_absolute():
            image_path = (args.plan.parent / image_path).resolve()
        if not image_path.is_file():
            raise ValueError(f"page {page_number}: audit image not found: {image_path}")
        source = Image.open(image_path).convert("RGB")
        if plan["source"].get("coordinate_unit") == "pdf_point":
            sx, sy = source.width / float(page_info["width"]), source.height / float(page_info["height"])
        else:
            sx = sy = 1.0
        cell_w, cell_h = args.crop_width * args.scale + 16, args.crop_height * args.scale + 36
        for sheet_index in range(max(1, (len(members) + per_sheet - 1) // per_sheet)):
            subset = members[sheet_index * per_sheet:(sheet_index + 1) * per_sheet]
            sheet = Image.new("RGB", (cell_w * args.columns, cell_h * args.rows), "#eeeeee")
            draw = ImageDraw.Draw(sheet)
            for local_index, note in enumerate(subset):
                col, row = local_index % args.columns, local_index // args.columns
                ox, oy = col * cell_w, row * cell_h
                x = float(note["page_x"]) * sx
                y = float(note["page_y"])
                if plan["source"].get("coordinate_unit") == "pdf_point":
                    y = float(page_info["height"]) - y
                y *= sy
                color = "#174f85" if note["hand"] == "RH" else "#8b2635"
                crop = crop_with_padding(source, x, y, args.crop_width, args.crop_height)
                mark = ImageDraw.Draw(crop)
                cx, cy = crop.width // 2, crop.height // 2
                mark.line((cx - 8, cy, cx + 8, cy), fill=color)
                mark.line((cx, cy - 8, cx, cy + 8), fill=color)
                crop = crop.resize((args.crop_width * args.scale, args.crop_height * args.scale), Image.Resampling.NEAREST)
                sheet.paste(crop, (ox + 8, oy + 28))
                draw.text((ox + 8, oy + 8), f"m{note['measure']} {note['note_id'][-14:]} {note['hand']} f{note.get('finger', 0)}", fill=color, font=font)
            output = args.output_dir / f"page-{page_number:02d}-audit-{sheet_index + 1:02d}.png"
            sheet.save(output)
            print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
