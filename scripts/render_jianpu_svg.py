#!/usr/bin/env python3
"""Render a compact, fingered jianpu score as SVG from structured JSON."""

import argparse
import html
import json
from pathlib import Path


def esc(value):
    return html.escape(str(value))


def note_svg(note, x, y, duration, show_finger=True):
    degree = esc(note.get("degree", "?"))
    finger = esc(note.get("finger", "?"))
    octave = int(note.get("octave", 0))
    parts = []
    if show_finger:
        parts.append(f'<text class="finger" x="{x}" y="{y - 30}">{finger}</text>')
    for dot in range(abs(octave)):
        dot_y = y - 14 - dot * 7 if octave > 0 else y + 13 + dot * 7
        parts.append(f'<circle class="octave" cx="{x}" cy="{dot_y}" r="1.8"/>')
    parts.append(f'<text class="degree" x="{x}" y="{y}">{degree}</text>')
    if duration in {"8", "16"}:
        parts.append(f'<line class="duration" x1="{x - 9}" y1="{y + 8}" x2="{x + 9}" y2="{y + 8}"/>')
    if duration == "16":
        parts.append(f'<line class="duration" x1="{x - 9}" y1="{y + 13}" x2="{x + 9}" y2="{y + 13}"/>')
    if duration in {"1", "2"}:
        length = 34 if duration == "2" else 58
        parts.append(f'<line class="duration" x1="{x + 11}" y1="{y - 6}" x2="{x + length}" y2="{y - 6}"/>')
    return "".join(parts)


def event_svg(event, x, y):
    if event.get("rest"):
        return f'<text class="degree" x="{x}" y="{y}">0</text>'
    notes = event.get("notes", [])
    duration = str(event.get("duration", "4"))
    if not notes:
        return f'<text class="degree" x="{x}" y="{y}">?</text>'
    gap = 27
    offset = -gap * (len(notes) - 1) / 2
    is_chord = len(notes) > 1
    items = []
    for i, note in enumerate(notes):
        note_y = y + offset + i * gap
        items.append(note_svg(note, x, note_y, duration, show_finger=not is_chord))
        if is_chord:
            # A chord's fingers must align with its individual degrees. Putting
            # every finger above vertically adjacent notes makes them collide.
            finger = esc(note.get("finger", "?"))
            items.append(f'<text class="finger chord-finger" x="{x - 24}" y="{note_y + 5}">{finger}</text>')
    if event.get("dotted"):
        items.append(f'<circle class="rhythm-dot" cx="{x + 14}" cy="{y - 6}" r="2"/>')
    return "".join(items)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()
    score = json.loads(args.input.read_text(encoding="utf-8"))
    measures = score.get("measures", [])
    per_row = int(score.get("measures_per_row", 4))
    rows = max(1, (len(measures) + per_row - 1) // per_row)
    width, top, row_h = 1240, 120, 210
    height = top + rows * row_h + 40
    css = """text{font-family:'Noto Sans CJK SC','Arial Unicode MS',sans-serif;text-anchor:middle;fill:#111}.title{font-size:28px;font-weight:700}.meta{font-size:16px}.measure{font-size:13px;fill:#555}.hand{font-size:16px;font-weight:700}.degree{font-size:27px}.finger{font-size:14px;fill:#155EEF}.chord-finger{text-anchor:end}.duration{stroke:#111;stroke-width:1.8}.octave,.rhythm-dot{fill:#111}"""
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">', f'<style>{css}</style>']
    out.append(f'<text class="title" x="{width / 2}" y="38">{esc(score.get("title", "Fingered Jianpu"))}</text>')
    meta = "   ".join(filter(None, [score.get("key"), score.get("meter"), score.get("tempo")]))
    out.append(f'<text class="meta" x="{width / 2}" y="68">{esc(meta)}</text>')
    margin, gap = 78, 18
    measure_w = (width - 2 * margin - (per_row - 1) * gap) / per_row
    for i, measure in enumerate(measures):
        row, col = divmod(i, per_row)
        x0 = margin + col * (measure_w + gap)
        y0 = top + row * row_h
        out.append(f'<text class="measure" x="{x0 + 4}" y="{y0 - 14}" text-anchor="start">{esc(measure.get("number", i + 1))}</text>')
        out.append(f'<line class="duration" x1="{x0}" y1="{y0 - 4}" x2="{x0}" y2="{y0 + 142}"/>')
        for hand, y, label in (("right", y0 + 48, "RH"), ("left", y0 + 124, "LH")):
            out.append(f'<text class="hand" x="{x0 - 22}" y="{y}" text-anchor="end">{label}</text>')
            events = measure.get(hand, [])
            step = (measure_w - 26) / max(1, len(events))
            for j, event in enumerate(events):
                out.append(event_svg(event, x0 + 18 + step * (j + 0.5), y))
        out.append(f'<line class="duration" x1="{x0 + measure_w}" y1="{y0 - 4}" x2="{x0 + measure_w}" y2="{y0 + 142}"/>')
    out.append("</svg>")
    args.output.write_text("\n".join(out), encoding="utf-8")
    print(f"Wrote {args.output} with {len(measures)} measures.")


if __name__ == "__main__":
    main()
