#!/usr/bin/env python3
"""Create a non-blocking delivery report for a fingering result."""

from __future__ import annotations

import argparse
from pathlib import Path

from plan_io import load_plan
from validate_recognition import validate_recognition


LEVELS = {
    "complete": "Complete result",
    "review": "Review-required result",
    "partial": "Partial result",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--musicxml", type=Path)
    parser.add_argument("--preview", type=Path)
    parser.add_argument("--collisions", type=int, default=0)
    args = parser.parse_args()

    plan = load_plan(args.plan)
    recognition_errors, recognition_warnings = validate_recognition(plan, strict=True)
    recognition_passed = not recognition_errors
    notes = plan.get("notes", [])
    recognition = plan.get("recognition", {})
    expected = int(recognition.get("expected_note_count", len(notes)))
    expected = max(expected, len(notes), 1)
    assigned = sum(1 for note in notes if int(note.get("finger", 0)) in {1, 2, 3, 4, 5})
    unresolved = int(recognition.get("unresolved_note_count", 0))
    low_confidence = [
        note for note in notes
        if float(note.get("confidence", 1.0)) < 0.8 or note.get("review_reason")
    ]
    coverage = assigned / expected
    requested = str(recognition.get("delivery_level", "complete")).lower()
    if recognition_passed and coverage >= 1 and unresolved == 0 and args.collisions == 0 and not low_confidence:
        level = "complete"
    elif requested == "partial" or coverage < 0.8:
        level = "partial"
    else:
        level = "review"

    artifacts = []
    for label, path in (("PDF", args.pdf), ("MusicXML", args.musicxml), ("PNG preview", args.preview)):
        if path:
            state = "generated" if path.is_file() else "path recorded; file not found"
            artifacts.append(f"- {label}: `{path}` ({state})")
    if not artifacts:
        artifacts.append("- No artifact path was provided")

    review_lines = []
    for note in low_confidence[:30]:
        reason = note.get("review_reason", "low-confidence recognition")
        review_lines.append(f"- `{note.get('note_id', 'unknown')}`: {reason}")
    if len(low_confidence) > 30:
        review_lines.append(f"- {len(low_confidence) - 30} additional low-confidence notes; see the plan")
    if unresolved:
        review_lines.append(f"- {unresolved} notes remain unresolved in the target scope")
    for error in recognition_errors[:30]:
        review_lines.append(f"- Recognition gate failed: {error}")
    if len(recognition_errors) > 30:
        review_lines.append(f"- {len(recognition_errors) - 30} additional recognition-gate errors; see the plan")
    for warning in recognition_warnings[:10]:
        review_lines.append(f"- Recognition warning: {warning}")
    if not review_lines:
        review_lines.append("- None")

    text = "\n".join([
        "# Piano Fingering Delivery Report",
        "",
        f"- Delivery level: {LEVELS[level]}",
        f"- Target scope: {recognition.get('scope', 'all notes in the plan')}",
        f"- Expected notes: {expected}",
        f"- Recognized notes: {len(notes)}",
        f"- Fingered notes: {assigned}",
        f"- Coverage: {coverage:.1%}",
        f"- Unresolved notes: {unresolved}",
        f"- Low-confidence notes: {len(low_confidence)}",
        f"- Label collisions: {max(args.collisions, 0)}",
        f"- Recognition-fact gate: {'passed' if recognition_passed else 'failed (must not be called complete)'}",
        "",
        "## Artifacts",
        "",
        *artifacts,
        "",
        "## Review required",
        "",
        *review_lines,
        "",
        "When the recognition-fact gate fails, deliver only diagnostic/audit artifacts and never generate or claim a complete fingering result.",
        "",
    ])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(f"Created {LEVELS[level]} report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
