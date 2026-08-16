#!/usr/bin/env python3
"""Verify that final PDF and fingering-plan structure agree."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "vendor"))
from pypdf import PdfReader  # type: ignore

from plan_io import load_plan, page_map


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("pdf", type=Path)
    args = parser.parse_args()
    plan = load_plan(args.plan)
    pages = page_map(plan)
    reader = PdfReader(str(args.pdf))
    if len(reader.pages) != len(pages):
        raise ValueError(f"PDF has {len(reader.pages)} pages; plan declares {len(pages)}")
    assigned = [note for note in plan["notes"] if int(note.get("finger", 0)) in {1, 2, 3, 4, 5}]
    anchored = [note for note in assigned if all(key in note for key in ("page", "page_x", "page_y"))]
    if len(anchored) != len(assigned):
        raise ValueError(f"{len(assigned) - len(anchored)} assigned notes lack page coordinates")
    for index, page in enumerate(reader.pages, 1):
        if float(page.mediabox.width) <= 0 or float(page.mediabox.height) <= 0:
            raise ValueError(f"page {index} has invalid dimensions")
    if not args.pdf.read_bytes().endswith(b"%%EOF\n") and b"%%EOF" not in args.pdf.read_bytes()[-64:]:
        raise ValueError("PDF EOF marker missing")
    print(f"Verified {len(reader.pages)} page(s), {len(assigned)} anchored fingering marks.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
