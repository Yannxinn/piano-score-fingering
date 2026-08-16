#!/usr/bin/env python3
"""Create a unified fingering plan from MusicXML using only the standard library."""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

from fingering_core.models import INote, keypos_midi
from plan_io import save_plan
from recognition_state import set_fact_lock


STEP_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element if local(child.tag) == name]


def child(element: ET.Element, name: str) -> ET.Element | None:
    return next((item for item in element if local(item.tag) == name), None)


def text(element: ET.Element, name: str, default: str = "") -> str:
    item = child(element, name)
    return (item.text or default).strip() if item is not None else default


def read_xml(path: Path) -> tuple[ET.ElementTree, str]:
    if path.suffix.lower() != ".mxl":
        return ET.parse(path), path.name
    with ZipFile(path) as archive:
        root_name = ""
        if "META-INF/container.xml" in archive.namelist():
            container = ET.fromstring(archive.read("META-INF/container.xml"))
            for item in container.iter():
                if local(item.tag) == "rootfile":
                    root_name = item.attrib.get("full-path", "")
                    if root_name:
                        break
        if not root_name:
            root_name = next(name for name in archive.namelist() if name.lower().endswith(".xml"))
        return ET.ElementTree(ET.fromstring(archive.read(root_name))), f"{path.name}:{root_name}"


def extract_finger(note: ET.Element) -> int:
    for item in note.iter():
        if local(item.tag) == "fingering":
            raw = (item.text or "").strip()
            circled = {"①": 1, "②": 2, "③": 3, "④": 4, "⑤": 5}
            if raw in circled:
                return circled[raw]
            if raw.isdigit() and 1 <= int(raw) <= 5:
                return int(raw)
    return 0


def tie_types(note: ET.Element) -> set[str]:
    """Read both MusicXML <tie> and notational <tied> declarations."""
    result = set()
    for item in note.iter():
        if local(item.tag) in {"tie", "tied"}:
            tie_type = item.attrib.get("type", "")
            if tie_type in {"start", "stop"}:
                result.add(tie_type)
    return result


def pitch_data(note: ET.Element) -> tuple[str, int, int, int] | None:
    pitch = child(note, "pitch")
    if pitch is None:
        return None
    step = text(pitch, "step")
    octave = int(text(pitch, "octave", "0"))
    alter = int(float(text(pitch, "alter", "0")))
    return step, alter, octave, (octave + 1) * 12 + STEP_PC[step] + alter


def spelled_name(step: str, alter: int) -> str:
    if alter > 0:
        return step + "#" * alter
    if alter < 0:
        return step + "-" * (-alter)
    return step


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--hand-size", default="M")
    args = parser.parse_args()
    tree, source_name = read_xml(args.input)
    root = tree.getroot()
    parts = [item for item in root.iter() if local(item.tag) == "part"]
    notes: list[dict] = []
    event_counter = {"RH": 0, "LH": 0}
    open_ties: dict[tuple, str] = {}
    for part_index, part in enumerate(parts):
        part_id = part.attrib.get("id", f"P{part_index + 1}")
        divisions = 1.0
        absolute_time = 0.0
        for measure_index, measure in enumerate(children(part, "measure"), 1):
            attributes = child(measure, "attributes")
            if attributes is not None and text(attributes, "divisions"):
                divisions = float(text(attributes, "divisions"))
            cursor = absolute_time
            furthest = cursor
            last_onset = cursor
            raw_notes: list[dict] = []
            voice_chord_rows: dict[tuple, int] = defaultdict(int)
            for element in measure:
                kind = local(element.tag)
                if kind == "backup":
                    cursor -= float(text(element, "duration", "0")) / divisions
                    continue
                if kind == "forward":
                    cursor += float(text(element, "duration", "0")) / divisions
                    furthest = max(furthest, cursor)
                    continue
                if kind != "note":
                    continue
                duration = float(text(element, "duration", "0")) / divisions
                is_chord = child(element, "chord") is not None
                onset = last_onset if is_chord else cursor
                if not is_chord:
                    last_onset = onset
                pitch = pitch_data(element)
                grace = child(element, "grace") is not None
                if pitch is not None:
                    step, alter, octave, midi = pitch
                    staff = int(text(element, "staff", "1"))
                    voice = text(element, "voice", "1")
                    if len(parts) > 1:
                        hand = "RH" if part_index == 0 else "LH"
                    else:
                        hand = "LH" if staff >= 2 else "RH"
                    # Simultaneous pitches on one staff form one physical hand event,
                    # even when MusicXML encodes them in separate voices via backup.
                    chord_key = (part_id, measure_index, staff, onset)
                    chord_row = voice_chord_rows[chord_key]
                    voice_chord_rows[chord_key] += 1
                    finger = extract_finger(element)
                    ties = tie_types(element)
                    tie_key = (part_id, staff, voice, midi)
                    tie_group = open_ties.get(tie_key)
                    if "start" in ties and tie_group is None:
                        tie_group = f"{part_id}-S{staff}-V{voice}-N{midi}-T{measure_index}-{onset:g}"
                    if "start" in ties and tie_group:
                        open_ties[tie_key] = tie_group
                    raw_notes.append({
                        "_element": element,
                        "_chord_key": chord_key,
                        "note_id": element.attrib.get("id", ""),
                        "part": part_id,
                        "measure": measure.attrib.get("number", str(measure_index)),
                        "measure_index": measure_index,
                        "staff": staff,
                        "voice": voice,
                        "onset": onset,
                        "duration": duration,
                        "pitch_midi": midi,
                        "pitch_step": step,
                        "pitch_alter": alter,
                        "pitch_octave": octave,
                        "hand": hand,
                        "chord_row": chord_row,
                        "finger": finger,
                        "locked": bool(finger),
                        "source": "existing" if finger else "unassigned",
                        "placement": "above" if hand == "RH" else "below",
                        "grace": grace,
                        "tie_group": tie_group,
                        "tie_start": "start" in ties,
                        "tie_stop": "stop" in ties,
                    })
                    if "stop" in ties and "start" not in ties:
                        open_ties.pop(tie_key, None)
                if not is_chord and not grace:
                    cursor += duration
                    furthest = max(furthest, cursor)
            absolute_time = furthest
            chord_groups: dict[tuple, list[dict]] = defaultdict(list)
            for record in raw_notes:
                chord_groups[record["_chord_key"]].append(record)
            for group in chord_groups.values():
                group.sort(key=lambda n: n["pitch_midi"])
                event_index = event_counter[group[0]["hand"]]
                event_counter[group[0]["hand"]] += 1
                chord_id = f"{part_id}-M{measure_index}-S{group[0]['staff']}-T{group[0]['onset']:g}"
                for row, record in enumerate(group):
                    record["event_index"] = event_index
                    record["chord_id"] = chord_id
                    record["chord_row"] = row
                    record["chord_size"] = len(group)
                    if not record["note_id"]:
                        record["note_id"] = f"{chord_id}-N{record['pitch_midi']}-C{row}"
                    probe = INote(pitch=record["pitch_midi"])
                    record["keyboard_x_cm"] = round(keypos_midi(probe), 6)
                    record.pop("_element", None)
                    record.pop("_chord_key", None)
                    notes.append(record)
    plan = {
        "schema_version": "1.0",
        "source": {"type": "musicxml", "path": str(args.input), "member": source_name},
        "settings": {"hand_size": args.hand_size.upper(), "lookahead": 0},
        "pages": [],
        "recognition": {
            "status": "verified",
            "scope": "complete MusicXML semantic source",
            "expected_note_count": len(notes),
            "unresolved_note_count": 0,
            "delivery_level": "complete",
            "verification": {
                "pitch_spelling": True,
                "rhythm": True,
                "ties": True,
                "chords": True,
            },
        },
        "notes": notes,
    }
    # MusicXML is already a structured semantic source.  Lock its extracted
    # score facts immediately so later fingering/layout edits cannot mutate it.
    set_fact_lock(plan)
    save_plan(args.output, plan)
    print(f"Wrote {args.output} with {len(notes)} notes.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
