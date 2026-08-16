#!/usr/bin/env python3
"""Overlay vector fingering on a source PDF, JPEG, or PNG without external tools."""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "vendor"))
from pypdf import PdfReader, PdfWriter  # type: ignore  # bundled dependency
from pypdf.generic import (  # type: ignore
    ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject,
)

from plan_io import finite_number, load_plan, page_map


COLORS = {"RH": (0.09, 0.25, 0.42), "LH": (0.48, 0.14, 0.19)}


def pdf_number(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".")


def escape_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def overlay_pdf(path: Path, dimensions: list[tuple[float, float]], page_commands: list[bytes]) -> None:
    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{4 + i * 2} 0 R" for i in range(len(dimensions)))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(dimensions)} >>".encode())
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
    for i, ((width, height), commands) in enumerate(zip(dimensions, page_commands)):
        content_id = 5 + i * 2
        page = f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {pdf_number(width)} {pdf_number(height)}] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode()
        objects.append(page)
        objects.append(f"<< /Length {len(commands)} >>\nstream\n".encode() + commands + b"\nendstream")
    write_pdf(path, objects)


def write_pdf(path: Path, objects: list[bytes]) -> None:
    payload = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(payload))
        payload.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(payload)
    payload.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode())
    payload.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.write_bytes(payload)


def jpeg_size(data: bytes) -> tuple[int, int, int]:
    index = 2
    while index < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        length = struct.unpack(">H", data[index:index + 2])[0]
        if marker in range(0xC0, 0xC4):
            height, width, components = struct.unpack(">HHB", data[index + 3:index + 8])
            return width, height, components
        index += length
    raise ValueError("unable to determine JPEG dimensions")


def png_pixels(data: bytes) -> tuple[int, int, bytes, bytes | None, str]:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("invalid PNG signature")
    pos, compressed = 8, bytearray()
    width = height = bit_depth = color_type = interlace = 0
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        payload = data[pos + 8:pos + 8 + length]
        pos += length + 12
        if kind == b"IHDR":
            width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", payload)
        elif kind == b"IDAT":
            compressed.extend(payload)
        elif kind == b"IEND":
            break
    if bit_depth != 8 or interlace != 0 or color_type not in {0, 2, 4, 6}:
        raise ValueError("PNG must be non-interlaced 8-bit grayscale, RGB, gray-alpha, or RGBA")
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[color_type]
    raw = zlib.decompress(bytes(compressed))
    stride = width * channels
    rows, offset, previous = [], 0, bytearray(stride)
    for _ in range(height):
        filter_type = raw[offset]
        scan = bytearray(raw[offset + 1:offset + 1 + stride])
        offset += stride + 1
        for x in range(stride):
            left = scan[x - channels] if x >= channels else 0
            up = previous[x]
            upper_left = previous[x - channels] if x >= channels else 0
            if filter_type == 1:
                scan[x] = (scan[x] + left) & 255
            elif filter_type == 2:
                scan[x] = (scan[x] + up) & 255
            elif filter_type == 3:
                scan[x] = (scan[x] + ((left + up) // 2)) & 255
            elif filter_type == 4:
                p = left + up - upper_left
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - upper_left)
                predictor = left if pa <= pb and pa <= pc else up if pb <= pc else upper_left
                scan[x] = (scan[x] + predictor) & 255
            elif filter_type != 0:
                raise ValueError(f"unsupported PNG filter {filter_type}")
        rows.append(bytes(scan))
        previous = scan
    pixels = b"".join(rows)
    if color_type in {0, 2}:
        return width, height, pixels, None, "/DeviceGray" if color_type == 0 else "/DeviceRGB"
    color_channels = 1 if color_type == 4 else 3
    color, alpha = bytearray(), bytearray()
    for index in range(0, len(pixels), channels):
        color.extend(pixels[index:index + color_channels])
        alpha.append(pixels[index + color_channels])
    return width, height, bytes(color), bytes(alpha), "/DeviceGray" if color_channels == 1 else "/DeviceRGB"


def image_pdf(image_path: Path, output: Path, dpi: float) -> tuple[float, float]:
    data = image_path.read_bytes()
    suffix = image_path.suffix.lower()
    alpha = None
    if suffix in {".jpg", ".jpeg"}:
        width_px, height_px, components = jpeg_size(data)
        pixels = data
        colorspace = "/DeviceGray" if components == 1 else "/DeviceCMYK" if components == 4 else "/DeviceRGB"
        image_filter = "/DCTDecode"
    elif suffix == ".png":
        width_px, height_px, pixels, alpha, colorspace = png_pixels(data)
        pixels = zlib.compress(pixels)
        if alpha is not None:
            alpha = zlib.compress(alpha)
        image_filter = "/FlateDecode"
    else:
        raise ValueError("image source must be JPEG or PNG")
    width, height = width_px * 72 / dpi, height_px * 72 / dpi
    content = f"q {pdf_number(width)} 0 0 {pdf_number(height)} 0 0 cm /Im0 Do Q".encode()
    smask = " /SMask 6 0 R" if alpha is not None else ""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {pdf_number(width)} {pdf_number(height)}] /Resources << /XObject << /Im0 5 0 R >> >> /Contents 4 0 R >>".encode(),
        f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream",
        f"<< /Type /XObject /Subtype /Image /Width {width_px} /Height {height_px} /ColorSpace {colorspace} /BitsPerComponent 8 /Filter {image_filter}{smask} /Length {len(pixels)} >>\nstream\n".encode() + pixels + b"\nendstream",
    ]
    if alpha is not None:
        objects.append(f"<< /Type /XObject /Subtype /Image /Width {width_px} /Height {height_px} /ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode /Length {len(alpha)} >>\nstream\n".encode() + alpha + b"\nendstream")
    write_pdf(output, objects)
    return width, height


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--dpi", type=float, default=144.0)
    parser.add_argument("--password", default="", help="Password for an encrypted source PDF")
    parser.add_argument("--font-size", type=float, default=10.0)
    parser.add_argument("--offset", type=float, default=20.0)
    args = parser.parse_args()
    plan = load_plan(args.plan)
    source = args.source or Path(str(plan.get("source", {}).get("path", "")))
    if not source.is_absolute():
        source = (args.plan.parent / source).resolve()
    if not source.is_file():
        raise ValueError(f"source not found: {source}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary_image_pdf = args.output.with_suffix(".source-tmp.pdf")
    if source.suffix.lower() in {".jpg", ".jpeg", ".png"}:
        image_pdf(source, temporary_image_pdf, args.dpi)
        source_pdf = temporary_image_pdf
    elif source.suffix.lower() == ".pdf":
        source_pdf = source
    else:
        raise ValueError("source must be PDF, JPEG, or PNG")

    reader = PdfReader(str(source_pdf))
    if reader.is_encrypted and not reader.decrypt(args.password):
        raise ValueError("source PDF is encrypted; provide the correct --password")
    declared = page_map(plan)
    if len(reader.pages) != len(declared):
        raise ValueError(f"source has {len(reader.pages)} pages but plan declares {len(declared)}")
    dimensions: list[tuple[float, float]] = []
    commands: list[list[str]] = [[] for _ in reader.pages]
    source_unit = plan.get("source", {}).get("coordinate_unit", "pdf_point")
    for index, pdf_page in enumerate(reader.pages, 1):
        if int(pdf_page.get("/Rotate", 0) or 0) % 360:
            pdf_page.transfer_rotation_to_content()
        width, height = float(pdf_page.mediabox.width), float(pdf_page.mediabox.height)
        dimensions.append((width, height))
        page = declared[index]
        coordinate_width = finite_number(page["width"], f"page {index}.width")
        coordinate_height = finite_number(page["height"], f"page {index}.height")
        sx, sy = width / coordinate_width, height / coordinate_height
        page_notes = [item for item in plan["notes"] if int(item.get("page", 0)) == index and int(item.get("finger", 0))]
        chord_groups: dict[tuple, list[dict]] = {}
        for item in page_notes:
            key = (
                item.get("part"), item.get("measure_index"), float(item.get("onset", 0)),
                item.get("event_index"), item.get("chord_id"), item.get("hand"),
            )
            chord_groups.setdefault(key, []).append(item)
        for note in page_notes:
            hand = note["hand"]
            key = (
                note.get("part"), note.get("measure_index"), float(note.get("onset", 0)),
                note.get("event_index"), note.get("chord_id"), note.get("hand"),
            )
            chord = sorted(chord_groups[key], key=lambda item: int(item.get("chord_row", 0)))
            stacked = len(chord) > 1 and note.get("chord_label_layout", "stacked") == "stacked"
            if stacked:
                chord_x = note.get("chord_label_x")
                if chord_x is None:
                    chord_x = sum(float(item["page_x"]) for item in chord) / len(chord)
                x = float(chord_x) * sx
            else:
                x = float(note.get("label_x", note["page_x"])) * sx
            anchor_y = float(note["page_y"])
            if source_unit == "pixel_top_left":
                anchor_y = coordinate_height - anchor_y
            y = anchor_y * sy
            size = float(note.get("font_size", args.font_size))
            if stacked:
                anchors = []
                for item in chord:
                    item_y = float(item["page_y"])
                    if source_unit == "pixel_top_left":
                        item_y = coordinate_height - item_y
                    anchors.append(item_y * sy)
                offset = float(note.get("chord_label_offset", note.get("label_offset", args.offset))) * sy
                base = max(anchors) + offset if note["placement"] == "above" else min(anchors) - offset
                y = base + int(note.get("chord_row", 0)) * size * 1.15
            else:
                offset = float(note.get("label_offset", args.offset)) * sy
                y += offset if note["placement"] == "above" else -offset
            red, green, blue = COLORS[hand]
            digit = escape_text(str(int(note["finger"])))
            commands[index - 1].append(
                f"BT /F1 {pdf_number(size)} Tf {pdf_number(red)} {pdf_number(green)} {pdf_number(blue)} rg 1 0 0 1 {pdf_number(x-size*0.28)} {pdf_number(y-size*0.34)} Tm ({digit}) Tj ET"
            )
    overlay = args.output.with_suffix(".overlay-tmp.pdf")
    overlay_pdf(overlay, dimensions, ["\n".join(items).encode() for items in commands])
    overlay_reader = PdfReader(str(overlay))
    writer = PdfWriter()
    for source_page, overlay_page in zip(reader.pages, overlay_reader.pages):
        source_page.merge_page(overlay_page)
        writer.add_page(source_page)
    with args.output.open("wb") as stream:
        writer.write(stream)
    overlay.unlink(missing_ok=True)
    temporary_image_pdf.unlink(missing_ok=True)
    total = sum(len(items) for items in commands)
    print(f"Rendered {len(reader.pages)} page(s), {total} labels: {args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
