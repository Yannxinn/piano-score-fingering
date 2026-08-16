#!/usr/bin/env python3
"""Run offline regression tests for the bundled fingering core and XML pipeline."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
from generate_fingering_plan import (  # noqa: E402
    chord_pattern,
    repair_extreme_turning_points,
    repair_stepwise_neighbor_turns,
    repair_repeated_accompaniment_pitch,
    repair_repeated_triplets,
    repair_single_chord_connections,
    repair_tied_notes,
)
from fingering_core import Hand, INote, keypos, keypos_midi  # noqa: E402
from validate_recognition import validate_recognition  # noqa: E402
from manage_recognition import create_review_queue  # noqa: E402
from recognition_state import score_facts_hash, set_fact_lock, verify_fact_lock  # noqa: E402
from build_measure_review_manifest import build_manifest  # noqa: E402
CASES = {
    "test_scales.xml": 276,
    "test_chords.xml": 218,
    "test_octaves.xml": 216,
    "test_multivoice.xml": 5,
    "test_ties.xml": 2,
}


def run(*args: str) -> None:
    subprocess.run([sys.executable, *args], check=True)


def main() -> int:
    keyboard_positions = [keypos_midi(INote(pitch=pitch)) for pitch in range(21, 109)]
    if any(right <= left for left, right in zip(keyboard_positions, keyboard_positions[1:])):
        raise ValueError("MIDI-to-keyboard physical coordinates must increase strictly across every octave")
    if abs(keypos(INote(name="C-", octave=4)) - keypos(INote(name="B", octave=3))) > 1e-9:
        raise ValueError("enharmonic spellings must resolve to the same physical key")
    print("PASS monotonic MIDI-to-keyboard geometry")

    minor_third = [{"pitch_midi": 60}, {"pitch_midi": 63}]
    major_second = [{"pitch_midi": 60}, {"pitch_midi": 62}]
    perfect_fifth = [{"pitch_midi": 60}, {"pitch_midi": 67}]
    if chord_pattern(minor_third, "LH") != [3, 1]:
        raise ValueError("LH minor third must default to 3-1, not 5-1")
    if chord_pattern(minor_third, "RH") != [1, 3]:
        raise ValueError("RH minor third must default to 1-3")
    if chord_pattern(major_second, "LH") != [2, 1]:
        raise ValueError("LH second must use adjacent 2-1 fingers")
    if chord_pattern(perfect_fifth, "LH") != [5, 1]:
        raise ValueError("LH perfect fifth must retain the 5-1 span")
    print("PASS interval-aware dyad fingering")

    triplets = []
    for index, pitch in enumerate([67, 63, 58, 69, 65, 60]):
        triplets.append([{
            "note_id": f"triplet-{index}", "measure_index": 16,
            "onset": index / 4, "event_index": index, "pitch_midi": pitch,
            "finger": [5, 4, 1][index % 3], "locked": False,
        }])
    repair_repeated_triplets(triplets, "RH")
    triplet_fingers = [event[0]["finger"] for event in triplets]
    if triplet_fingers != [5, 3, 1, 5, 3, 1]:
        raise ValueError(f"wide descending triplets must use 5-3-1: {triplet_fingers}")
    print("PASS repeated wide-triplet fingering")

    triplets_with_resolution = []
    for index, pitch in enumerate([74, 70, 67, 74, 70, 67, 74]):
        triplets_with_resolution.append([{
            "note_id": f"triplet-tail-{index}", "measure_index": 4,
            "onset": index, "event_index": index, "pitch_midi": pitch,
            "finger": 4, "locked": False,
        }])
    repair_repeated_triplets(triplets_with_resolution, "RH")
    if [event[0]["finger"] for event in triplets_with_resolution[:6]] != [5, 3, 1, 5, 3, 1]:
        raise ValueError("a trailing resolution note must not hide two repeated wide triplets")
    print("PASS repeated triplet detection with trailing resolution")

    turning_point = [
        [{"note_id": "apex-a", "measure_index": 52, "pitch_midi": 77,
          "finger": 1, "locked": False}],
        [{"note_id": "apex-b", "measure_index": 52, "pitch_midi": 94,
          "finger": 3, "locked": False}],
        [{"note_id": "apex-c", "measure_index": 52, "pitch_midi": 84,
          "finger": 1, "locked": False}],
    ]
    repair_extreme_turning_points(turning_point, "RH")
    if turning_point[1][0]["finger"] != 5:
        raise ValueError("isolated RH upper apex must land on finger 5")
    print("PASS extreme turning-point outer finger")

    neighbour_turn = [
        [{"note_id": f"turn-{index}", "measure_index": 29, "pitch_midi": pitch,
          "finger": 4, "locked": False}]
        for index, pitch in enumerate((79, 81, 82, 81))
    ]
    repair_stepwise_neighbor_turns(neighbour_turn, "RH")
    if [event[0]["finger"] for event in neighbour_turn] != [1, 2, 3, 2]:
        raise ValueError("RH stepwise upper-neighbour turn must use 1-2-3-2")
    print("PASS stepwise neighbour-turn fingering")

    single = {"note_id": "bass", "measure_index": 3, "pitch_midi": 55, "finger": 3, "locked": False}
    chord = [
        {"note_id": "chord-low", "measure_index": 3, "pitch_midi": 57, "finger": 3, "locked": False},
        {"note_id": "chord-high", "measure_index": 3, "pitch_midi": 60, "finger": 1, "locked": False},
    ]
    repair_single_chord_connections([[single], chord], "LH")
    if single["finger"] != 5 or [note["finger"] for note in chord] != [3, 1]:
        raise ValueError("LH bass must prepare a following 3-1 dyad with finger 5")
    print("PASS single-to-chord finger reservation")

    wide_single = {"note_id": "wide-bass", "measure_index": 7, "pitch_midi": 50, "finger": 5, "locked": False}
    wide_dyad = [
        {"note_id": "wide-low", "measure_index": 7, "pitch_midi": 53, "finger": 5, "locked": False},
        {"note_id": "wide-high", "measure_index": 7, "pitch_midi": 62, "finger": 1, "locked": False},
    ]
    repair_single_chord_connections([[wide_single], wide_dyad], "LH")
    if [note["finger"] for note in wide_dyad] != [3, 1]:
        raise ValueError("wide LH dyad next to finger-5 bass must reserve 5 and use 3-1")
    print("PASS wide single-to-dyad finger reservation")

    no_literal_conflict = {"note_id": "bass-4", "measure_index": 3, "pitch_midi": 55, "finger": 4, "locked": False}
    adjacent_dyad = [
        {"note_id": "dyad-low", "measure_index": 3, "pitch_midi": 59, "finger": 2, "locked": False},
        {"note_id": "dyad-high", "measure_index": 3, "pitch_midi": 60, "finger": 1, "locked": False},
    ]
    repair_single_chord_connections([[no_literal_conflict], adjacent_dyad], "LH")
    if no_literal_conflict["finger"] != 5:
        raise ValueError("LH outer accompaniment bass must use 5 even without a literal finger collision")
    print("PASS whole-hand single-to-dyad connection")

    tied = [
        [{"note_id": "tie-a", "measure_index": 1, "onset": 0, "event_index": 1,
          "pitch_midi": 69, "finger": 2, "locked": False, "tie_group": "t1"}],
        [{"note_id": "tie-b", "measure_index": 1, "onset": 1, "event_index": 2,
          "pitch_midi": 69, "finger": 3, "locked": False, "tie_group": "t1"}],
    ]
    repair_tied_notes(tied, "RH")
    if [event[0]["finger"] for event in tied] != [2, 2]:
        raise ValueError("tied same pitch must preserve its finger")
    print("PASS tied-note finger continuity")

    visual_plan = {
        "source": {"type": "image", "coordinate_unit": "pixel_top_left"},
        "recognition": {
            "expected_note_count": 1,
            "unresolved_note_count": 0,
            "verification": {gate: True for gate in (
                "scope_complete", "staff_geometry", "pitch_geometry", "accidentals",
                "rhythm", "ties", "chords", "anchors",
            )},
            "systems": [{
                "system_id": "s1", "page": 1, "staff": 1, "clef": "treble",
                "staff_line_y": [100, 110, 120, 130, 140],
            }],
        },
        "notes": [{
            "note_id": "geom", "pitch_step": "E", "pitch_alter": 0,
            "pitch_octave": 5, "pitch_midi": 76, "page_y": 105,
            "keyboard_x_cm": keypos_midi(INote(pitch=76)),
            "anchor_verified": True, "pitch_geometry_verified": True,
            "staff_geometry_id": "s1", "measure_index": 1, "onset": 0,
            "hand": "RH",
        }],
    }
    set_fact_lock(visual_plan)
    geometry_errors, _ = validate_recognition(visual_plan, strict=True)
    if geometry_errors:
        raise ValueError(f"valid pitch geometry was rejected: {geometry_errors}")
    visual_plan["notes"][0]["pitch_step"] = "D"
    visual_plan["notes"][0]["pitch_midi"] = 74
    geometry_errors, _ = validate_recognition(visual_plan, strict=True)
    if not any("page_y implies" in error for error in geometry_errors):
        raise ValueError("pitch/page-y mismatch did not block recognition")
    print("PASS visual pitch-geometry hard gate")

    keyboard_plan = copy.deepcopy(visual_plan)
    keyboard_plan["notes"][0]["pitch_step"] = "E"
    keyboard_plan["notes"][0]["pitch_midi"] = 76
    keyboard_plan["notes"][0]["keyboard_x_cm"] = 999.0
    set_fact_lock(keyboard_plan)
    keyboard_errors, _ = validate_recognition(keyboard_plan, strict=True)
    if not any("expected physical key centre" in error for error in keyboard_errors):
        raise ValueError("pitch/keyboard-coordinate mismatch did not block recognition")
    print("PASS pitch-to-keyboard geometry hard gate")

    policy_plan = copy.deepcopy(visual_plan)
    policy_plan["recognition"]["confidence_policy"] = {"require_independent_passes": 2}
    policy_plan["notes"][0]["recognition_passes"] = 1
    set_fact_lock(policy_plan)
    policy_errors, _ = validate_recognition(policy_plan, strict=True)
    if not any("independent recognition passes" in error for error in policy_errors):
        raise ValueError("single-pass visual recognition was not blocked by confidence policy")
    duplicate_policy_note = dict(policy_plan["notes"][0])
    duplicate_policy_note["note_id"] = "geom-policy-duplicate"
    duplicate_policy_note["confidence"] = 0.5
    policy_plan["notes"][0]["confidence"] = 0.5
    policy_plan["notes"].append(duplicate_policy_note)
    queue = create_review_queue(policy_plan)
    scoped = [item for item in queue if str(item.get("review_id", "")).startswith("scope:")]
    if len(scoped) != 1 or len(scoped[0].get("note_ids", [])) != 2:
        raise ValueError("visual review queue did not compact note issues by page/measure/hand")
    print("PASS independent visual-pass gate and compact review queue")

    symbol_plan = copy.deepcopy(visual_plan)
    symbol_plan["notes"][0].update({
        "pitch_step": "E", "pitch_midi": 76, "page": 1,
        "measure_index": 35, "event_index": 1, "chord_id": "rest-like",
    })
    symbol_plan["recognition"]["confidence_policy"] = {
        "require_notehead_shape_evidence": True,
        "require_sparse_rest_checks": True,
        "sparse_event_threshold": 1,
    }
    set_fact_lock(symbol_plan)
    symbol_errors, _ = validate_recognition(symbol_plan, strict=True)
    if not any("notehead-shape evidence" in error for error in symbol_errors):
        raise ValueError("rest-like candidate without notehead shape evidence was not blocked")
    if not any("note-vs-rest" in error for error in symbol_errors):
        raise ValueError("sparse candidate without note-vs-rest review was not blocked")
    symbol_plan["notes"][0].update({
        "symbol_class": "notehead",
        "notehead_shape_verified": True,
        "sparse_symbol_verified": True,
    })
    set_fact_lock(symbol_plan)
    symbol_errors, _ = validate_recognition(symbol_plan, strict=True)
    if symbol_errors:
        raise ValueError(f"verified sparse notehead was rejected: {symbol_errors}")
    print("PASS rest-symbol exclusion and sparse-region hard gate")

    visual_plan["notes"][0]["pitch_step"] = "E"
    visual_plan["notes"][0]["pitch_midi"] = 76
    set_fact_lock(visual_plan)
    visual_plan["recognition"]["event_count_checks"] = [{
        "page": 1, "measure": 1, "hand": "RH", "expected_noteheads": 1,
    }]
    duplicate = dict(visual_plan["notes"][0])
    duplicate["note_id"] = "geom-duplicate"
    visual_plan["notes"].append(duplicate)
    visual_plan["recognition"]["expected_note_count"] = 2
    count_errors, _ = validate_recognition(visual_plan, strict=True)
    if not any("visually verified 1 noteheads" in error for error in count_errors):
        raise ValueError("local visual notehead count did not reject a phantom note")
    visual_plan["notes"].pop()
    visual_plan["recognition"]["expected_note_count"] = 1
    set_fact_lock(visual_plan)
    print("PASS local visual notehead-count gate")

    evidence_plan = {
        "schema_version": "1.0",
        "source": {"type": "image", "path": "source.png", "coordinate_unit": "pixel_top_left"},
        "recognition": {
            "expected_note_count": 1,
            "unresolved_note_count": 0,
            "verification": {gate: True for gate in (
                "scope_complete", "staff_geometry", "pitch_geometry", "accidentals",
                "rhythm", "ties", "chords", "anchors",
            )},
            "confidence_policy": {
                "require_measure_region_coverage": True,
                "require_measure_symbol_checks": True,
                "require_rest_inventory": True,
                "require_direct_notehead_anchors": True,
            },
            "measure_scope": [
                {"page": 1, "measure_start": 1, "measure_end": 2, "hands": ["RH"]},
            ],
            "systems": [{
                "system_id": "s1", "page": 1, "staff": 1, "clef": "treble",
                "staff_line_y": [100, 110, 120, 130, 140],
            }],
            "measure_regions": [
                {"region_id": "p1-m1-rh", "page": 1, "measure": 1, "hand": "RH",
                 "bbox": [0, 80, 200, 160], "evidence_crop": "crops/p1-m1-rh.png"},
                {"region_id": "p1-m2-rh", "page": 1, "measure": 2, "hand": "RH",
                 "bbox": [200, 80, 400, 160], "evidence_crop": "crops/p1-m2-rh.png"},
            ],
            "measure_symbol_checks": [
                {"region_id": "p1-m1-rh", "page": 1, "measure": 1, "hand": "RH",
                 "expected_noteheads": 1, "expected_rests": 0, "duration_verified": True,
                 "source": "independent_visual_review", "evidence_crop": "crops/p1-m1-rh.png",
                 "verified": True},
                {"region_id": "p1-m2-rh", "page": 1, "measure": 2, "hand": "RH",
                 "expected_noteheads": 0, "expected_rests": 1, "duration_verified": True,
                 "source": "independent_visual_review", "evidence_crop": "crops/p1-m2-rh.png",
                 "verified": True},
            ],
        },
        "notes": [{
            "note_id": "direct-note", "pitch_step": "E", "pitch_alter": 0,
            "pitch_octave": 5, "pitch_midi": 76, "page": 1, "page_x": 100, "page_y": 105,
            "keyboard_x_cm": keypos_midi(INote(pitch=76)),
            "anchor_verified": True, "anchor_method": "visual_notehead",
            "pitch_geometry_verified": True, "staff_geometry_id": "s1", "measure_index": 1,
            "onset": 0, "duration": 1, "hand": "RH", "chord_size": 1,
            "symbol_class": "notehead", "notehead_shape_verified": True,
            "origin": "direct_visual_notehead",
        }],
        "rests": [{
            "rest_id": "whole-rest", "page": 1, "measure_index": 2, "hand": "RH",
            "page_x": 300, "page_y": 120, "rest_type": "whole", "duration": 4,
            "symbol_class": "rest", "rest_shape_verified": True,
        }],
    }
    set_fact_lock(evidence_plan)
    evidence_errors, _ = validate_recognition(evidence_plan, strict=True)
    if evidence_errors:
        raise ValueError(f"valid per-measure visual evidence was rejected: {evidence_errors}")

    manifest = build_manifest(evidence_plan, Path("evidence-plan.json"))
    if len(manifest["reviews"]) != 2:
        raise ValueError("measure review manifest did not enumerate every declared region")
    if any(item["expected_noteheads"] is not None or item["verified"] for item in manifest["reviews"]):
        raise ValueError("review manifest copied plan counts into independent evidence fields")

    missing_check = copy.deepcopy(evidence_plan)
    missing_check["recognition"]["measure_symbol_checks"].pop()
    set_fact_lock(missing_check)
    missing_errors, _ = validate_recognition(missing_check, strict=True)
    if not any("exactly one independent measure_symbol_check" in error for error in missing_errors):
        raise ValueError("rest-only measure without an independent check was not blocked")

    missing_region = copy.deepcopy(evidence_plan)
    missing_region["recognition"]["measure_regions"].pop()
    missing_region["recognition"]["measure_symbol_checks"].pop()
    set_fact_lock(missing_region)
    region_errors, _ = validate_recognition(missing_region, strict=True)
    if not any("target scope has no measure_region" in error for error in region_errors):
        raise ValueError("target measure omitted from the visual region inventory was not blocked")

    phantom = copy.deepcopy(evidence_plan)
    phantom_note = dict(phantom["notes"][0])
    phantom_note.update({
        "note_id": "phantom-on-rest", "measure_index": 2, "page_x": 300,
        "page_y": 105, "origin": "direct_visual_notehead",
    })
    phantom["notes"].append(phantom_note)
    phantom["recognition"]["expected_note_count"] = 2
    set_fact_lock(phantom)
    phantom_errors, _ = validate_recognition(phantom, strict=True)
    if not any("p1-m2-rh: raw crop has 0 notehead(s), but plan contains 1" in error for error in phantom_errors):
        raise ValueError("phantom note in a verified whole-rest measure was not blocked")

    wrong_rest = copy.deepcopy(evidence_plan)
    wrong_rest["rests"].clear()
    set_fact_lock(wrong_rest)
    rest_errors, _ = validate_recognition(wrong_rest, strict=True)
    if not any("raw crop has 1 rest(s), but plan contains 0" in error for error in rest_errors):
        raise ValueError("missing rest inventory entry was not blocked")

    inferred_member = copy.deepcopy(evidence_plan)
    inferred_member["notes"][0]["origin"] = "inferred_pattern"
    set_fact_lock(inferred_member)
    inferred_errors, _ = validate_recognition(inferred_member, strict=True)
    if not any("inferred chord members are forbidden" in error for error in inferred_errors):
        raise ValueError("pattern-inferred visual note was not blocked")

    evidence_plan["recognition"]["measure_symbol_checks"][1]["expected_rests"] = 0
    if not any("changed after locking" in error for error in verify_fact_lock(evidence_plan)):
        raise ValueError("measure evidence mutation after locking was not detected")
    print("PASS all-measure source evidence, rest inventory, and no-inference gates")

    locked_digest = score_facts_hash(visual_plan)
    visual_plan["notes"][0]["page_x"] = 321
    if not any("changed after locking" in error for error in verify_fact_lock(visual_plan)):
        raise ValueError("score-fact mutation after locking was not detected")
    visual_plan["notes"][0].pop("page_x")
    if score_facts_hash(visual_plan) != locked_digest or verify_fact_lock(visual_plan):
        raise ValueError("restored score facts did not recover the valid lock")
    print("PASS immutable recognition fact lock")

    repeated_bass = [
        [{"note_id": "bass-1", "measure_index": 8, "event_index": 1,
          "pitch_midi": 48, "finger": 4, "locked": False}],
        [{"note_id": "dyad-2a", "measure_index": 8, "event_index": 2,
          "pitch_midi": 55, "finger": 3, "locked": False},
         {"note_id": "dyad-2b", "measure_index": 8, "event_index": 2,
          "pitch_midi": 60, "finger": 1, "locked": False}],
        [{"note_id": "dyad-3a", "measure_index": 8, "event_index": 3,
          "pitch_midi": 55, "finger": 3, "locked": False},
         {"note_id": "dyad-3b", "measure_index": 8, "event_index": 3,
          "pitch_midi": 60, "finger": 1, "locked": False}],
        [{"note_id": "bass-4", "measure_index": 8, "event_index": 4,
          "pitch_midi": 48, "finger": 5, "locked": False}],
    ]
    repair_repeated_accompaniment_pitch(repeated_bass, "LH")
    if repeated_bass[0][0]["finger"] != 5 or repeated_bass[3][0]["finger"] != 5:
        raise ValueError("same-pitch repeated LH bass slot must retain finger 5")
    print("PASS repeated-bass same-pitch consistency")

    unlocked = [INote(pitch=60, x=60, time=0, duration=1, fingering=5, is_anchor=False, measure=1)]
    unlocked_solver = Hand(unlocked, side="right", size="M")
    unlocked_solver.autodepth = False
    unlocked_solver.depth = 3
    unlocked_solver.generate(1, 1)
    if int(unlocked[0].fingering) == 5:
        raise ValueError("unlocked legacy fingering was incorrectly treated as an anchor")
    locked = [INote(pitch=60, x=60, time=0, duration=1, fingering=5, is_anchor=True, measure=1)]
    locked_solver = Hand(locked, side="right", size="M")
    locked_solver.autodepth = False
    locked_solver.depth = 3
    locked_solver.generate(1, 1)
    if int(locked[0].fingering) != 5:
        raise ValueError("locked fingering anchor was not preserved")
    print("PASS locked-only anchoring")

    short_phrase = [
        INote(
            pitch=60 + index,
            x=60.0 + index * 1.8,
            time=index * 0.25,
            duration=0.25,
            measure=1,
            noteID=index,
        )
        for index in range(9)
    ]
    short_solver = Hand(short_phrase, side="right", size="M")
    short_solver.autodepth = False
    short_solver.depth = 5
    short_solver.generate(1, 1)
    short_fingers = [int(note.fingering) for note in short_phrase]
    if any(finger not in {1, 2, 3, 4, 5} for finger in short_fingers):
        raise ValueError(f"short phrase contains unassigned finger: {short_fingers}")
    print("PASS short-phrase manual-lookahead tail assignment")

    scale_phrase_pitches = [67, 69, 70, 72, 73, 74, 77, 74, 70]
    scale_phrase = [
        INote(
            pitch=pitch,
            x=keypos_midi(INote(pitch=pitch)),
            time=index,
            duration=1,
            measure=1,
            noteID=index,
        )
        for index, pitch in enumerate(scale_phrase_pitches)
    ]
    scale_solver = Hand(scale_phrase, side="right", size="M")
    scale_solver.max_auto_depth = 8
    scale_solver.verbose = False
    scale_solver.generate(1, 1)
    scale_fingers = [int(note.fingering) for note in scale_phrase]
    if scale_fingers[:8] != [1, 2, 3, 1, 2, 3, 5, 3]:
        raise ValueError(f"ascending scale/apex phrase did not choose a prepared hand shape: {scale_fingers}")
    print("PASS ergonomic scale crossing and apex preparation")
    with tempfile.TemporaryDirectory(prefix="piano-fingering-test-") as directory:
        temp = Path(directory)
        for filename, expected in CASES.items():
            source = ROOT / "assets" / "tests" / filename
            plan = temp / f"{filename}.plan.json"
            fingered = temp / f"{filename}.fingered.json"
            output = temp / f"{filename}.output.musicxml"
            run(str(SCRIPTS / "create_plan_from_musicxml.py"), str(source), "-o", str(plan))
            run(str(SCRIPTS / "generate_fingering_plan.py"), str(plan), "-o", str(fingered))
            run(str(SCRIPTS / "validate_fingering_plan.py"), str(fingered))
            run(str(SCRIPTS / "apply_fingerings.py"), str(source), str(fingered), "-o", str(output))
            if filename == "test_ties.xml":
                tied_plan = json.loads(fingered.read_text(encoding="utf-8"))
                tied_notes = tied_plan["notes"]
                if len({note.get("tie_group") for note in tied_notes}) != 1:
                    raise ValueError("MusicXML tie was not preserved as one tie_group")
                if len({int(note["finger"]) for note in tied_notes}) != 1:
                    raise ValueError("MusicXML tie changed finger after generation")
            root = ET.parse(output).getroot()
            count = sum(1 for item in root.iter() if item.tag.rsplit("}", 1)[-1] == "fingering")
            if count != expected:
                raise ValueError(f"{filename}: expected {expected} fingerings, found {count}")
            print(f"PASS {filename}: {count} notes")
    print("All offline self-tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
