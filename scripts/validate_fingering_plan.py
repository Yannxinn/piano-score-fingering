#!/usr/bin/env python3
"""Validate unified piano fingering data and flag musical review points."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from plan_io import (
    COORDINATE_UNITS,
    HAND_SIZES,
    finite_number,
    load_plan,
    note_sort_key,
    page_map,
)
from validate_recognition import validate_recognition


REQUIRED = {
    "note_id", "part", "measure", "measure_index", "staff", "voice",
    "onset", "duration", "pitch_midi", "event_index", "chord_id",
    "chord_row", "chord_size", "hand", "keyboard_x_cm",
}
TRANSITIONS = {
    "same_position", "thumb_under", "finger_over", "lateral_shift",
    "substitution", "repeated_note", "chord_change", "leap",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--require-coordinates", action="store_true")
    parser.add_argument("--require-verified-anchors", action="store_true")
    args = parser.parse_args()
    plan = load_plan(args.plan)
    errors: list[str] = []
    warnings: list[str] = []
    recognition_errors, recognition_warnings = validate_recognition(plan, strict=True)
    errors.extend(f"recognition gate: {message}" for message in recognition_errors)
    warnings.extend(f"recognition gate: {message}" for message in recognition_warnings)
    pages = page_map(plan)
    source = plan.get("source", {})
    source_type = source.get("type")
    unit = source.get("coordinate_unit")
    require_coordinates = args.require_coordinates or args.require_verified_anchors or source_type in {"pdf", "image"}
    if require_coordinates and unit not in COORDINATE_UNITS:
        errors.append("source.coordinate_unit must be pdf_point or pixel_top_left")

    settings = plan.get("settings", {})
    if str(settings.get("hand_size", "M")).upper() not in HAND_SIZES:
        errors.append("settings.hand_size must be XXS..XXL")
    lookahead = int(settings.get("lookahead", 0))
    if lookahead not in {0, 3, 4, 5, 6, 7, 8, 9}:
        errors.append("settings.lookahead must be 0 or 3..9")

    notes = plan.get("notes", [])
    if not notes:
        errors.append("notes must be a non-empty array")
    seen_ids: set[str] = set()
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    label_boxes: dict[int, list[tuple[float, float, float, float, str]]] = defaultdict(list)
    for index, note in enumerate(notes):
        if not isinstance(note, dict):
            errors.append(f"notes[{index}] must be an object")
            continue
        missing = sorted(REQUIRED - set(note))
        if missing:
            errors.append(f"notes[{index}] missing {missing}")
            continue
        note_id = str(note["note_id"])
        if not note_id or note_id in seen_ids:
            errors.append(f"notes[{index}] duplicate/empty note_id {note_id!r}")
        seen_ids.add(note_id)
        hand = str(note["hand"]).upper()
        if hand not in {"RH", "LH"}:
            errors.append(f"{note_id}: hand must be RH or LH")
            continue
        grouped[(str(note["part"]), hand)].append(note)
        try:
            pitch = int(note["pitch_midi"])
            finger = int(note.get("finger", 0))
            chord_row = int(note["chord_row"])
            chord_size = int(note["chord_size"])
            duration = finite_number(note["duration"], f"{note_id}.duration")
            finite_number(note["keyboard_x_cm"], f"{note_id}.keyboard_x_cm")
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not 0 <= pitch <= 127 or duration < 0:
            errors.append(f"{note_id}: invalid pitch or duration")
        if finger not in {0, 1, 2, 3, 4, 5}:
            errors.append(f"{note_id}: finger must be 0..5")
        if finger == 0 and note.get("source") in {"generated", "reviewed", "existing"}:
            warnings.append(f"{note_id}: assigned source has no finger")
        if not 0 <= chord_row < chord_size:
            errors.append(f"{note_id}: chord_row must be within chord_size")
        placement = note.get("placement")
        if placement not in {"above", "below"}:
            errors.append(f"{note_id}: placement must be above or below")
        if hand == "RH" and placement != "above":
            warnings.append(f"{note_id}: review non-default RH placement")
        if hand == "LH" and placement != "below":
            warnings.append(f"{note_id}: review non-default LH placement")
        transition = note.get("transition_type")
        if transition is not None and transition not in TRANSITIONS:
            errors.append(f"{note_id}: invalid transition_type {transition!r}")
        if require_coordinates:
            try:
                pageno = int(note["page"])
                x = finite_number(note["page_x"], f"{note_id}.page_x")
                y = finite_number(note["page_y"], f"{note_id}.page_y")
                page = pages[pageno]
                width = finite_number(page["width"], f"page {pageno}.width")
                height = finite_number(page["height"], f"page {pageno}.height")
                if not (0 <= x <= width and 0 <= y <= height):
                    errors.append(f"{note_id}: page anchor outside page bounds")
                label_x = finite_number(note.get("label_x", x), f"{note_id}.label_x")
                offset = finite_number(note.get("label_offset", 20), f"{note_id}.label_offset")
                size = finite_number(note.get("font_size", 10), f"{note_id}.font_size")
                if size <= 0 or offset < 0:
                    errors.append(f"{note_id}: invalid label size/offset")
                if unit == "pixel_top_left":
                    label_y = y - offset if placement == "above" else y + offset
                else:
                    label_y = y + offset if placement == "above" else y - offset
                half_width = size * 0.35
                box = (label_x - half_width, label_y - size * 0.4, label_x + half_width, label_y + size * 0.7, note_id)
                if not (0 <= box[0] and box[2] <= width and 0 <= box[1] and box[3] <= height):
                    errors.append(f"{note_id}: label falls outside page bounds")
                label_boxes[pageno].append(box)
                if args.require_verified_anchors:
                    if note.get("anchor_verified") is not True:
                        errors.append(f"{note_id}: page anchor has not passed visual notehead verification")
                    if note.get("anchor_method") not in {"visual_notehead", "detected_notehead", "layout_source"}:
                        errors.append(f"{note_id}: missing valid anchor_method")
            except (KeyError, TypeError, ValueError) as exc:
                errors.append(f"{note_id}: invalid/missing page coordinate ({exc})")

    for pageno, boxes in label_boxes.items():
        for index, first in enumerate(boxes):
            for second in boxes[index + 1:]:
                overlaps = first[0] < second[2] and first[2] > second[0] and first[1] < second[3] and first[3] > second[1]
                if overlaps:
                    errors.append(f"page {pageno}: label collision between {first[4]} and {second[4]}")

    for (_, hand), sequence in grouped.items():
        sequence.sort(key=note_sort_key)
        events: dict[tuple, list[dict]] = defaultdict(list)
        for note in sequence:
            key = (note["measure_index"], float(note["onset"]), note["event_index"], note["chord_id"])
            events[key].append(note)
        ordered_events = []
        for key in sorted(events):
            members = sorted(events[key], key=lambda n: int(n["pitch_midi"]))
            fingers = [int(n.get("finger", 0)) for n in members]
            if any(int(n["chord_size"]) != len(members) for n in members):
                errors.append(f"{hand} event {key}: inconsistent chord_size")
            if [int(n["chord_row"]) for n in members] != list(range(len(members))):
                errors.append(f"{hand} event {key}: chord_row must be low-to-high from 0")
            assigned = [f for f in fingers if f]
            if len(assigned) != len(set(assigned)):
                errors.append(f"{hand} event {key}: chord reuses a finger")
            if len(assigned) == len(members) and len(members) > 1:
                expected = sorted(assigned, reverse=hand == "LH")
                if assigned != expected:
                    errors.append(f"{hand} event {key}: fingers conflict with pitch order")
            ordered_events.append(members)

        for previous_event, current_event in zip(ordered_events, ordered_events[1:]):
            detached = any(note.get("connection") == "detached" for note in current_event)
            detached = detached or any(note.get("transition_type") == "leap" for note in current_event)
            if detached or {len(previous_event), len(current_event)} != {1, 2}:
                continue
            single_event, chord_event = (
                (previous_event, current_event) if len(previous_event) == 1 else (current_event, previous_event)
            )
            single = single_event[0]
            single_pitch = int(single["pitch_midi"])
            chord_pitches = [int(note["pitch_midi"]) for note in chord_event]
            nearest = min(chord_event, key=lambda note: abs(int(note["pitch_midi"]) - single_pitch))
            outside = single_pitch < min(chord_pitches) or single_pitch > max(chord_pitches)
            outer_side = (hand == "LH" and single_pitch < min(chord_pitches)) or (
                hand == "RH" and single_pitch > max(chord_pitches)
            )
            same_finger = int(single.get("finger", 0)) == int(nearest.get("finger", 0)) != 0
            close_shift = abs(int(nearest["pitch_midi"]) - single_pitch) <= 4
            verified_exception = single.get("exception_verified") is True
            if outer_side and int(single.get("finger", 0)) not in {0, 5} and not verified_exception:
                errors.append(
                    f"{single['note_id']}: outer accompaniment note must use finger 5 before/after "
                    "the adjacent dyad, or carry an exception_verified justification"
                )
            if outside and outer_side and same_finger and close_shift:
                errors.append(
                    f"{nearest['note_id']}: finger {nearest['finger']} is reused for a nearby "
                    "single note and the adjacent dyad"
                )

        adjacent_singles = [
            (previous_event[0], current_event[0])
            for previous_event, current_event in zip(ordered_events, ordered_events[1:])
            if len(previous_event) == 1 and len(current_event) == 1
        ]
        for previous, current in adjacent_singles:
            pf, cf = int(previous.get("finger", 0)), int(current.get("finger", 0))
            if not pf or not cf:
                continue
            pd = int(current["pitch_midi"]) - int(previous["pitch_midi"])
            detached = current.get("connection") == "detached" or current.get("transition_type") == "leap"
            if pd and pf == cf and not detached:
                errors.append(f"{current['note_id']}: same finger moves to connected different pitch")
            fd = cf - pf
            reversal = pd * fd * (1 if hand == "RH" else -1) < 0
            exceptional = current.get("transition_type") in {"thumb_under", "finger_over", "lateral_shift", "substitution", "leap"}
            if pd and fd and reversal and not exceptional:
                warnings.append(f"{current['note_id']}: directional reversal needs review")
            if cf == 1 and int(current["pitch_midi"]) % 12 in {1, 3, 6, 8, 10}:
                warnings.append(f"{current['note_id']}: review thumb on black key")

        # Repeated accompaniment positions should not silently change fingers.
        # Alternation and substitution remain valid when they are explicitly
        # identified, but an unexplained change is a phrase-level review point.
        repeated_singles: dict[tuple[int, int], list[dict]] = defaultdict(list)
        event_sizes = {
            (int(event[0]["measure_index"]), int(event[0]["event_index"])): len(event)
            for event in ordered_events
        }
        for event in ordered_events:
            if hand == "LH" and len(event) == 1:
                note = event[0]
                repeated_singles[(int(note["measure_index"]), int(note["pitch_midi"]))].append(note)
        for same_pitch_notes in repeated_singles.values():
            fingers = {int(note.get("finger", 0)) for note in same_pitch_notes if int(note.get("finger", 0))}
            intentional = any(
                note.get("transition_type") in {"repeated_note", "substitution"}
                for note in same_pitch_notes
            )
            event_indices = sorted(int(note["event_index"]) for note in same_pitch_notes)
            measure = int(same_pitch_notes[0]["measure_index"])
            same_accompaniment_slot = any(
                b - a == 3
                and any(event_sizes.get((measure, middle), 1) > 1 for middle in (a + 1, a + 2))
                for a, b in zip(event_indices, event_indices[1:])
            )
            if len(fingers) > 1 and same_accompaniment_slot and not intentional:
                ids = ", ".join(str(note["note_id"]) for note in same_pitch_notes)
                errors.append(f"{ids}: repeated accompaniment pitch changes finger without an explicit reason")

        tied: dict[str, list[dict]] = defaultdict(list)
        for note in sequence:
            if note.get("tie_group"):
                tied[str(note["tie_group"])].append(note)
        for group_id, members in tied.items():
            members.sort(key=note_sort_key)
            fingers = {int(note.get("finger", 0)) for note in members if int(note.get("finger", 0))}
            substitutions = [
                note for note in members
                if note.get("transition_type") == "substitution" and note.get("exception_verified") is True
            ]
            if len(fingers) > 1 and not substitutions:
                ids = ", ".join(str(note["note_id"]) for note in members)
                errors.append(f"{ids}: tie group {group_id} changes finger without a verified substitution")

    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"Validated {len(notes)} notes; {len(warnings)} review warning(s).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
