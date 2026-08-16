#!/usr/bin/env python3
"""Generate piano fingering in a unified plan with the bundled solver."""

from __future__ import annotations

import argparse
import copy
import sys
import time
from collections import defaultdict
from pathlib import Path

from fingering_core import Hand, INote
from plan_io import load_plan, note_sort_key, save_plan
from validate_recognition import validate_recognition


CHORD_PATTERNS = {
    1: [1],
    3: [1, 3, 5],
    4: [1, 2, 4, 5],
    5: [1, 2, 3, 4, 5],
}


def parse_measure_range(value: str) -> tuple[int, int]:
    parts = value.split("-", 1)
    try:
        start = int(parts[0])
        end = int(parts[1]) if len(parts) == 2 else start
    except ValueError as exc:
        raise argparse.ArgumentTypeError("measure range must be N or START-END") from exc
    if start < 1 or end < start:
        raise argparse.ArgumentTypeError("measure range must satisfy 1 <= START <= END")
    return start, end


def chord_pattern(members: list[dict], hand_code: str) -> list[int]:
    """Choose an ordered chord shape whose finger span matches its pitch span."""
    if len(members) == 2:
        semitones = abs(int(members[1]["pitch_midi"]) - int(members[0]["pitch_midi"]))
        if semitones <= 2:
            pattern = [1, 2]
        elif semitones <= 4:
            pattern = [1, 3]
        elif semitones <= 5:
            pattern = [1, 4]
        else:
            pattern = [1, 5]
    else:
        pattern = CHORD_PATTERNS[len(members)]
    return list(reversed(pattern)) if hand_code == "LH" else pattern


def _mark_reviewed(record: dict, finger: int, reason: str, transition: str = "lateral_shift") -> None:
    record["finger"] = finger
    record["source"] = "reviewed"
    record["transition_type"] = transition
    record["exception_reason"] = reason


def repair_repeated_triplets(ordered_events: list[list[dict]], hand_code: str) -> None:
    """Use the stable outer-middle-thumb shape for repeated wide descending triplets."""
    singles = [event[0] for event in ordered_events if len(event) == 1]
    by_measure: dict[int, list[dict]] = defaultdict(list)
    for note in singles:
        by_measure[int(note["measure_index"])].append(note)
    for notes in by_measure.values():
        notes.sort(key=note_sort_key)
        if len(notes) < 6:
            continue
        pattern = [5, 3, 1] if hand_code == "RH" else [1, 3, 5]
        # Scan repeated six-note windows instead of requiring the entire
        # measure length to be divisible by three. A pickup or resolution note
        # after two triplets must not disable recognition of the repeated cell.
        for start in range(len(notes) - 5):
            first = notes[start:start + 3]
            second = notes[start + 3:start + 6]

            def intervals(group: list[dict]) -> tuple[int, int] | None:
                pitches = [int(note["pitch_midi"]) for note in group]
                if not pitches[0] > pitches[1] > pitches[2]:
                    return None
                gaps = (pitches[0] - pitches[1], pitches[1] - pitches[2])
                if min(gaps) < 3 or sum(gaps) < 7:
                    return None
                return gaps

            first_intervals = intervals(first)
            second_intervals = intervals(second)
            if first_intervals is None or first_intervals != second_intervals:
                continue
            transpositions = {
                int(b["pitch_midi"]) - int(a["pitch_midi"])
                for a, b in zip(first, second)
            }
            if len(transpositions) != 1 or any(note.get("locked") for note in first + second):
                continue
            for group in (first, second):
                for note, finger in zip(group, pattern):
                    if int(note.get("finger", 0)) != finger:
                        _mark_reviewed(
                            note,
                            finger,
                            "wide repeated triplet uses outer-middle-thumb shape",
                        )


def repair_repeated_accompaniment_pitch(ordered_events: list[list[dict]], hand_code: str) -> None:
    """Keep the same finger for the repeated bass slot of an accompaniment cell."""
    if hand_code != "LH":
        return
    by_measure: dict[int, list[list[dict]]] = defaultdict(list)
    for event in ordered_events:
        by_measure[int(event[0]["measure_index"])].append(event)
    for events in by_measure.values():
        measure_floor = min(int(note["pitch_midi"]) for event in events for note in event)
        event_sizes = {int(event[0]["event_index"]): len(event) for event in events}
        singles = [event[0] for event in events if len(event) == 1]
        by_pitch: dict[int, list[dict]] = defaultdict(list)
        for note in singles:
            by_pitch[int(note["pitch_midi"])].append(note)
        for pitch, notes in by_pitch.items():
            if pitch != measure_floor:
                continue
            by_event = {int(note["event_index"]): note for note in notes}
            for event_index, first in list(by_event.items()):
                second = by_event.get(event_index + 3)
                if second is None:
                    continue
                if not any(event_sizes.get(middle, 1) > 1 for middle in (event_index + 1, event_index + 2)):
                    continue
                if any(note.get("transition_type") in {"substitution", "repeated_note"} for note in (first, second)):
                    continue
                locked = [note for note in (first, second) if note.get("locked")]
                if len(locked) == 2 and int(first.get("finger", 0)) != int(second.get("finger", 0)):
                    # Preserve source anchors; the validator will require review.
                    continue
                target = int(locked[0].get("finger", 0)) if locked else 5
                for note in (first, second):
                    if not note.get("locked") and int(note.get("finger", 0)) != target:
                        _mark_reviewed(
                            note,
                            target,
                            "same-pitch repeated bass slot keeps one stable finger",
                            "same_position",
                        )


def repair_tied_notes(ordered_events: list[list[dict]], hand_code: str) -> None:
    """A notated tie keeps one finger unless a verified substitution says otherwise."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for event in ordered_events:
        for note in event:
            if note.get("tie_group"):
                groups[str(note["tie_group"])].append(note)
    for group_id, notes in groups.items():
        notes.sort(key=note_sort_key)
        locked = [note for note in notes if note.get("locked") and int(note.get("finger", 0))]
        if len({int(note["finger"]) for note in locked}) > 1:
            # Preserve source markings; the validator will reject the conflict.
            continue
        target = int(locked[0]["finger"]) if locked else int(notes[0].get("finger", 0) or 0)
        if not target:
            continue
        for note in notes:
            verified_substitution = (
                note.get("transition_type") == "substitution"
                and note.get("exception_verified") is True
            )
            if note.get("locked") or verified_substitution:
                continue
            if int(note.get("finger", 0)) != target:
                _mark_reviewed(
                    note,
                    target,
                    f"tie group {group_id} preserves one finger",
                    "same_position",
                )


def repair_extreme_turning_points(ordered_events: list[list[dict]], hand_code: str) -> None:
    """Land isolated octave-scale turning points on the appropriate outer finger."""
    singles = [(position, event[0]) for position, event in enumerate(ordered_events) if len(event) == 1]
    for (left_position, previous), (middle_position, current), (right_position, following) in zip(
        singles, singles[1:], singles[2:]
    ):
        if middle_position - left_position != 1 or right_position - middle_position != 1:
            continue
        if len({int(previous["measure_index"]), int(current["measure_index"]), int(following["measure_index"])}) != 1:
            continue
        before = int(previous["pitch_midi"])
        pitch = int(current["pitch_midi"])
        after = int(following["pitch_midi"])
        upper_apex = min(pitch - before, pitch - after) >= 7
        lower_apex = min(before - pitch, after - pitch) >= 7
        if not upper_apex and not lower_apex:
            continue
        if hand_code == "RH":
            target = 5 if upper_apex else 1
        else:
            target = 1 if upper_apex else 5
        if current.get("locked") or int(current.get("finger", 0)) == target:
            continue
        _mark_reviewed(
            current,
            target,
            "isolated octave-scale turning point lands on the outer finger",
            "leap",
        )
        current["rule_id"] = "B3"


def repair_stepwise_neighbor_turns(ordered_events: list[list[dict]], hand_code: str) -> None:
    """Keep a four-note upper-neighbour turn in one adjacent-finger hand shape."""
    singles = [(position, event[0]) for position, event in enumerate(ordered_events) if len(event) == 1]
    for window in zip(singles, singles[1:], singles[2:], singles[3:]):
        positions = [item[0] for item in window]
        notes = [item[1] for item in window]
        if positions != list(range(positions[0], positions[0] + 4)):
            continue
        if len({int(note["measure_index"]) for note in notes}) != 1:
            continue
        pitches = [int(note["pitch_midi"]) for note in notes]
        if not (
            pitches[0] < pitches[1] < pitches[2]
            and pitches[3] == pitches[1]
            and pitches[1] - pitches[0] <= 2
            and pitches[2] - pitches[1] <= 2
        ):
            continue
        pattern = [1, 2, 3, 2] if hand_code == "RH" else [5, 4, 3, 4]
        if any(note.get("locked") for note in notes):
            continue
        for index, (note, finger) in enumerate(zip(notes, pattern)):
            note["finger"] = finger
            note["source"] = "reviewed"
            note["exception_reason"] = "stepwise upper-neighbour turn keeps one adjacent-finger hand shape"
            note["rule_id"] = "B5"
            if index == 0:
                note["transition_type"] = "lateral_shift"


def repair_final_melodic_invariants(ordered_events: list[list[dict]], hand_code: str) -> None:
    """Recheck hard melodic constraints after every structural repair.

    Chord and accompaniment repairs intentionally run after the first melodic
    pass.  They can therefore reintroduce a same-finger move between different
    pitches.  This final pass either chooses a neighbouring finger or records a
    genuine reposition across intervening events/rests.  Stable repeated
    figures (for example 5-3-1 triplets) are preserved by moving the preceding
    note when possible rather than corrupting the repeated shape.
    """
    melodic = [(position, event[0]) for position, event in enumerate(ordered_events) if len(event) == 1]
    for (previous_position, previous), (current_position, current) in zip(melodic, melodic[1:]):
        previous_finger = int(previous.get("finger", 0))
        current_finger = int(current.get("finger", 0))
        pitch_delta = int(current["pitch_midi"]) - int(previous["pitch_midi"])
        if not pitch_delta or not previous_finger or previous_finger != current_finger:
            continue
        if current.get("connection") == "detached" or current.get("transition_type") == "leap":
            continue

        # Chords or other events between the two single notes break literal
        # finger continuity.  Keep the stable outer finger and make the reset
        # explicit so the validator does not mistake it for legato motion.
        if (
            current_position - previous_position > 1
            or int(current["measure_index"]) - int(previous["measure_index"]) > 1
            or (
                int(current["measure_index"]) != int(previous["measure_index"])
                and abs(pitch_delta) >= 7
            )
        ):
            current["transition_type"] = "leap"
            current["exception_reason"] = "hand position resets after intervening events or rests"
            current["source"] = "reviewed"
            continue

        natural_sign = 1 if (pitch_delta > 0) == (hand_code == "RH") else -1
        reason = str(current.get("exception_reason", ""))
        preserve_current = any(token in reason for token in ("repeated triplet", "stable hand", "tie group"))

        if preserve_current and not previous.get("locked"):
            candidate = current_finger - natural_sign
            if not 1 <= candidate <= 5:
                candidate = current_finger + natural_sign
            if 1 <= candidate <= 5:
                _mark_reviewed(
                    previous,
                    candidate,
                    "prepare the following stable repeated figure without reusing one finger on a new pitch",
                )
                current["transition_type"] = "lateral_shift"
                current["exception_reason"] = "phrase boundary resets into the stable repeated figure"
                current["source"] = "reviewed"
                continue

        if not current.get("locked"):
            candidate = previous_finger + natural_sign
            if not 1 <= candidate <= 5:
                candidate = previous_finger - natural_sign
            if 1 <= candidate <= 5:
                transition = "lateral_shift"
                if candidate == 1:
                    transition = "thumb_under"
                elif previous_finger == 1:
                    transition = "finger_over"
                _mark_reviewed(
                    current,
                    candidate,
                    "final invariant: connected different pitches must not reuse one finger",
                    transition,
                )


def repair_single_chord_connections(ordered_events: list[list[dict]], hand_code: str) -> None:
    """Prevent a single bass/melody note from stealing a finger used by the next chord."""
    for previous, current in zip(ordered_events, ordered_events[1:]):
        if len(previous) == len(current) or {len(previous), len(current)} != {1, 2}:
            continue
        single_event, chord_event = (previous, current) if len(previous) == 1 else (current, previous)
        single = single_event[0]
        if single.get("connection") == "detached" or single.get("transition_type") == "leap":
            continue
        single_pitch = int(single["pitch_midi"])
        chord_pitches = [int(item["pitch_midi"]) for item in chord_event]
        single_finger = int(single.get("finger", 0))
        outside_below = single_pitch < min(chord_pitches)
        outside_above = single_pitch > max(chord_pitches)
        outer_side = (hand_code == "LH" and outside_below) or (hand_code == "RH" and outside_above)
        if not outer_side:
            continue
        outer_finger = 5 if (hand_code == "LH") == outside_below else 1
        verified_exception = single.get("exception_verified") is True
        # Broken-chord accompaniment needs a stable outer finger even when no
        # literal finger-number conflict exists. This evaluates the horizontal
        # single-to-dyad connection, not just each event in isolation.
        if not single.get("locked") and not verified_exception and single_finger != outer_finger:
            _mark_reviewed(
                single,
                outer_finger,
                "outer accompaniment note prepares the adjacent dyad with a stable hand position",
                "same_position",
            )
            single_finger = outer_finger
        if not single.get("locked"):
            single_finger = int(single.get("finger", 0))

        conflicts = [item for item in chord_event if int(item.get("finger", 0)) == single_finger and int(item["pitch_midi"]) != single_pitch]
        if not conflicts:
            continue
        if conflicts and not any(item.get("locked") for item in chord_event):
            span = max(chord_pitches) - min(chord_pitches)
            inner = 4 if span <= 7 else 3
            replacement = [inner, 1] if hand_code == "LH" else [1, inner]
            for item, finger in zip(chord_event, replacement):
                _mark_reviewed(
                    item,
                    finger,
                    "reserve the outer finger for the adjacent single note",
                    "chord_change",
                )

    # Once a repeated accompaniment dyad has been narrowed to reserve finger 5,
    # keep the identical hand shape for every occurrence in that measure.
    shapes: dict[tuple[int, tuple[int, ...]], list[list[dict]]] = defaultdict(list)
    for event in ordered_events:
        if len(event) == 2:
            key = (
                int(event[0]["measure_index"]),
                tuple(int(item["pitch_midi"]) for item in event),
            )
            shapes[key].append(event)
    for (_, pitches), events in shapes.items():
        span = max(pitches) - min(pitches)
        inner = 4 if span <= 7 else 3
        target = [inner, 1] if hand_code == "LH" else [1, inner]
        if len(events) < 2 or not any([int(item.get("finger", 0)) for item in event] == target for event in events):
            continue
        for event in events:
            if any(item.get("locked") for item in event):
                continue
            for item, finger in zip(event, target):
                if int(item.get("finger", 0)) != finger:
                    _mark_reviewed(
                        item,
                        finger,
                        "keep the repeated accompaniment dyad in one stable hand shape",
                        "chord_change",
                    )

    # Normalizing the last dyad of one measure can expose a new conflict with the
    # first bass note of the next measure, so close that boundary once more.
    for previous, current in zip(ordered_events, ordered_events[1:]):
        if {len(previous), len(current)} != {1, 2}:
            continue
        single_event, chord_event = (previous, current) if len(previous) == 1 else (current, previous)
        single = single_event[0]
        single_pitch = int(single["pitch_midi"])
        chord_pitches = [int(item["pitch_midi"]) for item in chord_event]
        outer_side = (hand_code == "LH" and single_pitch < min(chord_pitches)) or (
            hand_code == "RH" and single_pitch > max(chord_pitches)
        )
        nearest = min(chord_event, key=lambda item: abs(int(item["pitch_midi"]) - single_pitch))
        if (
            outer_side
            and int(single.get("finger", 0)) == int(nearest.get("finger", 0))
            and int(single.get("finger", 0)) != 0
            and abs(int(nearest["pitch_midi"]) - single_pitch) <= 4
            and not single.get("locked")
        ):
            _mark_reviewed(
                single,
                5,
                "reserve finger 5 across the measure boundary before the adjacent dyad",
            )


def postprocess(records: list[dict], hand_code: str) -> None:
    """Repair deterministic structural problems before musical review."""
    events: dict[tuple, list[dict]] = defaultdict(list)
    for record in records:
        events[(record["measure_index"], record["onset"], record["event_index"], record["chord_id"])].append(record)
    ordered_events: list[list[dict]] = []
    for key in sorted(events):
        members = sorted(events[key], key=lambda item: int(item["pitch_midi"]))
        if 1 < len(members) <= 5 and not any(item.get("locked") for item in members):
            pattern = chord_pattern(members, hand_code)
            old = [int(item.get("finger", 0)) for item in members]
            if old != pattern:
                for item, finger in zip(members, pattern):
                    item["finger"] = finger
                    item["source"] = "reviewed"
                    item["transition_type"] = "chord_change"
                    item["exception_reason"] = "normalize chord to an ordered hand shape matched to its pitch span"
        ordered_events.append(members)

    melodic = [event[0] for event in ordered_events if len(event) == 1]
    for previous, current in zip(melodic, melodic[1:]):
        previous_finger = int(previous.get("finger", 0))
        current_finger = int(current.get("finger", 0))
        pitch_delta = int(current["pitch_midi"]) - int(previous["pitch_midi"])
        if not pitch_delta or not previous_finger or not current_finger:
            continue
        if previous_finger == current_finger and not current.get("locked"):
            natural_sign = 1 if (pitch_delta > 0) == (hand_code == "RH") else -1
            candidate = previous_finger + natural_sign
            if not 1 <= candidate <= 5:
                candidate = previous_finger - natural_sign
            current["finger"] = candidate
            current["source"] = "reviewed"
            current["transition_type"] = "lateral_shift"
            current["exception_reason"] = "avoid same finger on connected different pitches"
            current_finger = candidate
        finger_delta = current_finger - previous_finger
        reversal = pitch_delta * finger_delta * (1 if hand_code == "RH" else -1) < 0
        if reversal and not current.get("transition_type"):
            if current_finger == 1:
                current["transition_type"] = "thumb_under"
                current["exception_reason"] = "thumb-under transition selected by the solver"
            elif previous_finger == 1:
                current["transition_type"] = "finger_over"
                current["exception_reason"] = "finger-over transition selected by the solver"
            else:
                current["transition_type"] = "lateral_shift"
                current["exception_reason"] = "phrase-level hand reposition selected by the solver"

    # These phrase/event repairs must run last: the melodic pass above may otherwise
    # overwrite a bass finger that was deliberately reserved for an adjacent chord.
    repair_repeated_triplets(ordered_events, hand_code)
    repair_single_chord_connections(ordered_events, hand_code)
    repair_repeated_accompaniment_pitch(ordered_events, hand_code)
    repair_tied_notes(ordered_events, hand_code)
    repair_extreme_turning_points(ordered_events, hand_code)
    repair_stepwise_neighbor_turns(ordered_events, hand_code)
    repair_final_melodic_invariants(ordered_events, hand_code)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--ignore-existing", action="store_true")
    parser.add_argument("--preserve-posture-memory", action="store_true")
    parser.add_argument(
        "--max-auto-depth",
        type=int,
        default=8,
        choices=range(4, 10),
        metavar="4-9",
        help="cap automatic look-ahead depth (default: 8; use 9 for a slower exhaustive final pass)",
    )
    parser.add_argument("--changed-only", action="store_true", help="infer the latest recognition patch scope and recompute only affected measures")
    parser.add_argument("--quiet", action="store_true", help="suppress periodic progress and timing messages")
    parser.add_argument(
        "--measure-range",
        type=parse_measure_range,
        help="recompute only N or START-END while retaining nearby phrase context",
    )
    parser.add_argument(
        "--context-measures",
        type=int,
        default=1,
        help="neighbouring measures used as read-only context with --measure-range (default: 1)",
    )
    args = parser.parse_args()
    if args.context_measures < 0:
        parser.error("--context-measures must be non-negative")
    if args.changed_only and args.measure_range:
        parser.error("--changed-only and --measure-range cannot be used together")
    started_at = time.perf_counter()
    plan = load_plan(args.input)
    recognition_errors, recognition_warnings = validate_recognition(plan, strict=True)
    for warning in recognition_warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    if recognition_errors:
        for error in recognition_errors:
            print(f"ERROR: recognition gate: {error}", file=sys.stderr)
        print("ERROR: fingering generation blocked until score facts pass recognition validation", file=sys.stderr)
        return 1
    settings = plan["settings"]
    hand_size = str(settings.get("hand_size", "M")).upper()
    lookahead = int(settings.get("lookahead", 0))
    by_hand: dict[str, list[dict]] = defaultdict(list)
    target_range = args.measure_range
    if args.changed_only:
        history = plan.get("recognition", {}).get("patch_history", [])
        if not history:
            parser.error("--changed-only requires recognition.patch_history")
        scope = history[-1].get("scope", {})
        explicit = {int(value) for value in scope.get("measures", [])}
        if explicit:
            affected = explicit
        else:
            pages = {int(value) for value in scope.get("pages", [])}
            hands = {str(value).upper() for value in scope.get("hands", [])}
            affected = {
                int(note["measure_index"])
                for note in plan.get("notes", [])
                if (not pages or int(note.get("page", 0)) in pages)
                and (not hands or str(note.get("hand", "")).upper() in hands)
            }
        if not affected:
            parser.error("latest recognition patch scope does not resolve to any measures")
        target_range = (min(affected), max(affected))
        if not args.quiet:
            print(f"Incremental regeneration: measures {target_range[0]}-{target_range[1]}", file=sys.stderr, flush=True)
    if target_range:
        context_start = max(1, target_range[0] - args.context_measures)
        context_end = target_range[1] + args.context_measures
    else:
        context_start = context_end = 0
    read_only_context: dict[str, dict] = {}
    for record in plan["notes"]:
        measure = int(record["measure_index"])
        if target_range and not context_start <= measure <= context_end:
            continue
        if target_range and not target_range[0] <= measure <= target_range[1]:
            read_only_context[str(record["note_id"])] = copy.deepcopy(record)
        by_hand[record["hand"]].append(record)

    for hand_code, records in by_hand.items():
        records.sort(key=note_sort_key)
        sequence: list[INote] = []
        for record in records:
            finger = 0 if args.ignore_existing else int(record.get("finger", 0) or 0)
            note = INote(
                name=record.get("pitch_step"),
                pitch=int(record["pitch_midi"]),
                octave=int(record.get("pitch_octave", 0)),
                x=float(record["keyboard_x_cm"]),
                time=float(record["onset"]),
                duration=float(record["duration"]),
                fingering=finger,
                is_anchor=bool(finger and record.get("locked", False)),
                measure=int(record["measure_index"]),
                staff=int(record["staff"]),
                chordnr=int(record["chord_row"]),
                NinChord=int(record["chord_size"]),
                chordID=hash(str(record["chord_id"])) & 0x7FFFFFFF,
                noteID=len(sequence),
                isChord=int(record["chord_size"]) > 1,
                isBlack=int(record["pitch_midi"]) % 12 in {1, 3, 6, 8, 10},
            )
            sequence.append(note)
        if not sequence:
            continue
        solver = Hand(sequence, side="right" if hand_code == "RH" else "left", size=hand_size)
        solver.verbose = False
        solver.preserve_posture_memory = args.preserve_posture_memory
        solver.max_auto_depth = args.max_auto_depth
        if lookahead:
            solver.autodepth = False
            solver.depth = lookahead
        first_measure = min(int(item["measure_index"]) for item in records)
        last_measure = max(int(item["measure_index"]) for item in records)
        hand_started = time.perf_counter()
        last_bucket = -1

        def show_progress(done: int, total: int, measure: int) -> None:
            nonlocal last_bucket
            bucket = min(10, (done * 10) // max(1, total))
            if bucket <= last_bucket:
                return
            last_bucket = bucket
            print(
                f"{hand_code} {bucket * 10:3d}% ({done}/{total}, measure {measure})",
                file=sys.stderr,
                flush=True,
            )

        solver.generate(
            first_measure,
            last_measure - first_measure + 1,
            show_progress=None if args.quiet else show_progress,
        )
        if not args.quiet:
            print(
                f"{hand_code} solved in {time.perf_counter() - hand_started:.2f}s "
                f"(cache {solver.cache_hits} hit/{solver.cache_misses} miss)",
                file=sys.stderr,
                flush=True,
            )
        for record, note in zip(records, sequence):
            existing = int(record.get("finger", 0) or 0)
            if existing and record.get("locked") and not args.ignore_existing:
                record["source"] = "existing"
            else:
                record["finger"] = int(note.fingering)
                record["source"] = "generated"
                record["locked"] = False
            record["cost"] = round(float(note.cost), 6)
            record["placement"] = "above" if hand_code == "RH" else "below"
        postprocess(records, hand_code)
    for record in plan["notes"]:
        original = read_only_context.get(str(record.get("note_id")))
        if original is not None:
            record.clear()
            record.update(original)
    save_plan(args.output, plan)
    if target_range:
        changed = sum(
            1 for note in plan["notes"]
            if target_range[0] <= int(note["measure_index"]) <= target_range[1]
        )
        print(
            f"Wrote {args.output}; recomputed {changed} note(s) in measures "
            f"{target_range[0]}-{target_range[1]} with read-only context."
        )
    else:
        print(f"Wrote {args.output} with fingering for {len(plan['notes'])} notes.")
    if not args.quiet:
        print(f"Total generation time: {time.perf_counter() - started_at:.2f}s", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
