---
name: piano-score-fingering-v2
description: Read piano scores from images, PDFs, MusicXML, MXL, or MuseScore files; preserve the page coordinates of every notehead; generate playable two-hand fingering with the bundled dynamic hand-position search; and deliver an annotated PDF or fingered MusicXML. Use for piano-score recognition, automatic fingering, coordinate-accurate score annotation, fingering review, and practice guidance without requiring PianoPlayer, MuseScore, ReportLab, or online OMR services.
---

# Piano Score Fingering 2.0

Complete the workflow when the host can read files, inspect score pages, run Python, and write output files. Use only the bundled scripts and capabilities already present in the host. Do not require the user to install software, Python packages, browser extensions, or online recognition services.

## Accuracy gates and delivery levels

Never generate fingering from unverified score facts merely to produce an output. Always create inspectable artifacts. Deliver one of these outcomes:

1. **Complete**: process the full requested range and deliver PDF/MusicXML plus a report.
2. **Review required**: all performance semantics are verified, but non-semantic layout or musical-preference warnings remain; deliver the fingering result and report.
3. **Partial**: only when the full range cannot be recognized reliably. Complete at least one whole measure or full system and label every output as a partial experiment.

Block fingering whenever pitch, clef, accidental, rhythm, hand, chord membership, tie, voice, or notehead identity is unresolved. On failure, still deliver the recognition plan, anchor audit, and error report. Historical outputs may reveal prior error types, but must never become recognition truth or a fingering target for a new task.

Load references only when needed: use [references/professional-fingering-rules.md](references/professional-fingering-rules.md) for musical review, [references/fingering-plan-schema.md](references/fingering-plan-schema.md) when creating or repairing a visual recognition plan, and [references/common-fingering-errors.md](references/common-fingering-errors.md) when a validator or user identifies a matching error. Keep [NOTICE.txt](NOTICE.txt) with every redistributed copy.

## Choose the input path

### PDF or image

1. Make one complete recognition draft. Declare `measure_scope`, then create one `measure_region` for every page + measure + hand, including rest-only measures.
2. Classify symbols before reading pitch and rhythm. Put noteheads in `notes` and rests in `rests`; never treat stems, beams, barlines, dots, text, or rectangular rest marks as notes.
3. Record the true center of every visible notehead with `origin=direct_visual_notehead`. Locate every member of a touching chord separately and set `chord_member_verified=true`. Never infer a missing member from spacing or a repeated accompaniment pattern.
4. Use `pdf_point` coordinates with a bottom-left origin for PDFs and `pixel_top_left` with a top-left origin for images. Write standard MusicXML as the semantic source and a unified `fingering-plan.json` for identities and coordinates.
5. Perform an independent measure-level structure pass from source crops. Count visible noteheads and rests before comparing with the draft. Recheck only anomalous measures.

The second pass verifies measure/hand note counts, accidentals, same-position neighbors, ties, rests, and chord members; it does not regenerate the whole draft. Build a review manifest:

```bash
python3 scripts/build_measure_review_manifest.py build fingering-plan.json -o measure-review.json
python3 scripts/build_measure_review_manifest.py apply fingering-plan.json measure-review.json -o review-plan.json
```

Inspect each `evidence_crop` before filling `expected_noteheads`, `expected_rests`, and `duration_verified`. Do not derive expected counts from current plan entries. Verified notes require `recognition_passes=2`, `symbol_class=notehead`, and `notehead_shape_verified=true`. Record rests separately with their type, duration, and `rest_shape_verified=true`.

### Recognition fact lifecycle

Maintain one traceable source of truth:

`draft -> review -> verified -> locked`

Create a compact exception queue, review at most two local rounds, and leave unresolved items open rather than looping over the full score:

```bash
python3 scripts/manage_recognition.py queue fingering-plan.json -o review-queue.json --plan-output review-plan.json
python3 scripts/manage_recognition.py freeze review-plan.json -o locked-plan.json
python3 scripts/manage_recognition.py status locked-plan.json
```

The lock stores a SHA-256 digest of score facts. Fingering, color, type size, and label position may change after locking; pitch, rhythm, voice, chords, ties, staff geometry, and notehead coordinates may not. Every generator run recomputes the digest and blocks silent changes.

When a later recognition error is found, patch only the affected page, measure, and hand:

```bash
python3 scripts/manage_recognition.py patch locked-plan.json correction.json -o review-plan.json
python3 scripts/manage_recognition.py confirm review-plan.json --gates pitch_geometry rhythm chords anchors -o verified-plan.json
python3 scripts/manage_recognition.py freeze verified-plan.json -o locked-plan-v2.json
```

Never edit a locked plan and simply recalculate its digest.

### Execution budget and stop conditions

- Allow one full recognition draft, one independent structure pass, and at most two local review rounds.
- Run full-score fingering search once. After locking, patch and recompute only affected measures; do not rerun the whole score with `--ignore-existing`.
- Perform one final full-page visual inspection. Earlier checks use anomalous measure crops. Layout changes rerender only affected pages.
- Stop after two failed automatic correction rounds and deliver the audit plus a review-required result. During work longer than 60 seconds, report stage, hand, measure, and percentage.
- Let scripts perform deterministic checks; show the model only the compact review queue, not repeated full plans and page images.

### Hard recognition gate

For every system, record five `staff_line_y` values, its clef, and stable `system_id`. Bind every note through `staff_geometry_id`. Every scoped measure/hand needs exactly one `measure_symbol_check`, including rest-only measures with zero noteheads. Verify scope, staff geometry, pitch geometry, accidentals, rhythm, ties, chord membership, and anchors before setting the corresponding gate to `true`.

Run before any fingering calculation:

```bash
python3 scripts/validate_recognition.py fingering-plan.json
```

The validator derives the natural pitch from clef and staff geometry, then checks spelling, MIDI, ties, geometry, review state, and the fact lock. `--allow-review` is diagnostic only and never authorizes generation. An anchor is valid only when its center crosses a real oval notehead, not a rest block, stem, or beam.

Do not redraw a supplied PDF/image or replace it with image generation. Overlay vector finger numbers on the original page.

### MusicXML, MXL, and MuseScore

```bash
python3 scripts/create_plan_from_musicxml.py input.musicxml -o fingering-plan.json
```

MXL is supported directly. If MusicXML has no layout coordinates, always deliver fingered MusicXML and add PDF only when the host can render a verifiable score page. Do not claim that this Skill contains a full MusicXML engraving engine or require MuseScore. Read `.mscx` as XML and convert its semantics; read `.mscz` only when the host can unpack it, otherwise ask for MusicXML export.

## Unified identity and coordinates

Use a single plan throughout. Every note must have a stable `note_id` and separate:

- `keyboard_x_cm`: physical key-center position used by the fingering algorithm;
- `page_x/page_y`: original notehead center used by the overlay;
- MusicXML identity: `part + measure_index + staff + voice + onset + pitch_midi + chord_row`.

For PDF/image delivery run:

```bash
python3 scripts/validate_fingering_plan.py fingering-plan.json --require-coordinates
python3 scripts/validate_fingering_plan.py fingered-plan.json --require-verified-anchors
```

Derive `keyboard_x_cm` only from `pitch_midi` with the bundled `keypos_midi`; never estimate it from page position or note-name text. Physical key positions must increase strictly with MIDI pitch, and enharmonic spellings must map to the same key.

## Generate fingering

```bash
python3 scripts/generate_fingering_plan.py fingering-plan.json -o fingered-plan.json
```

For a local correction:

```bash
python3 scripts/generate_fingering_plan.py locked-plan.json -o fingered-plan-v2.json --measure-range 49-52 --context-measures 1
python3 scripts/generate_fingering_plan.py patched-fingered-plan.json -o fingered-plan-v2.json --changed-only --context-measures 1
```

Context measures are read-only; preserve all fingerings and manual corrections outside the target. Use hand size `XXS`, `XS`, `S`, `M`, `L`, `XL`, or `XXL`; default to `M`. With `lookahead=0`, select 3–8 events automatically. Use `--max-auto-depth 9` only for a deliberately slow final search. Use `--ignore-existing` only when the user explicitly requests it, and at most once per task.

The adapted PianoPlayer core scores key distance, duration, finger strength, black-key tendencies, span, chord ordering, lookahead, and existing fingering anchors. It also penalizes skipped adjacent fingers in scalar motion, excessive `2->1` crossings, and premature use of finger 5 while a melody continues in the same direction. The output is an executable draft, not final musical truth.

## Musical review

Apply [references/professional-fingering-rules.md](references/professional-fingering-rules.md) in priority order. Remove hard violations first, then review full phrases and cross-measure transitions:

- favor relaxed movement, continuity, stable positions, and preparation for what follows;
- avoid the same finger on successive different pitches in legato;
- do not trap a scale on finger 5 without preparation;
- require a contextual reason for thumb crossings, substitutions, skips, and shifts;
- give chords non-conflicting fingers ordered by pitch;
- preserve the same mapping for structurally identical double notes or chords when the whole hand can shift;
- review left-hand bass–chord–next-bass as one motion; an outer bass below the following dyad normally uses finger 5;
- keep the same finger across tied identical notes unless an explicit silent substitution is marked and verified;
- keep repeated accompaniment pitches and structural slots consistent unless an explained `repeated_note` or `substitution` exception exists;
- preserve `locked=true` fingerings and review handoffs, simultaneities, and collisions.

For manual corrections set `source=reviewed`, write `transition_type` and `exception_reason`, add the applicable `rule_id`, and set `exception_verified=true` only after note-by-note review. Recognition or structural errors must be fixed; musical preference warnings may remain as review items.

## Write back and render

```bash
python3 scripts/apply_fingerings.py input.musicxml fingered-plan.json -o fingered.musicxml
python3 scripts/render_fingering_pdf.py fingered-plan.json --source input.pdf -o fingered-score.pdf
```

Place right-hand labels above noteheads in dark blue and left-hand labels below their own staff in dark red; never let left-hand labels enter the next system. Keep labels visibly clear of notes and notation. Use `label_x`, `label_offset`, and `font_size` only where ownership remains unambiguous.

For chords use `chord_label_layout="stacked"`, one shared `chord_label_x`, and vertical order matching `chord_row`. Never scatter one chord's finger numbers diagonally, which can imply sequential attacks. Also deliver a PNG preview for image/PDF input.

For anchor inspection, render source pages to images, store them in `pages[].image`, then run:

```bash
python3 scripts/audit_overlay_anchors.py fingered-plan.json -o anchor-audit
```

## Final verification

```bash
python3 scripts/verify_output.py fingered-plan.json fingered-score.pdf
```

Render the final PDF to images and compare every page with the source. Confirm correct note/chord ownership, no missing or duplicate labels, no crop or page-order change, no collision with noteheads/accidentals/stems/beams/ties, natural cross-measure fingering, and a reopenable PDF with the correct page count.

Require evidence for all five states: `recognition_verified`, `pitch_geometry_verified`, `ties_verified`, `fingering_rules_verified`, and `placement_verified`. Fix only dirty measures/pages, run local checks, then perform one final whole-score pass. Limit automatic collision repair to two rounds and never create free alternating vertical offsets within one continuous group.

Create the report:

```bash
python3 scripts/create_delivery_report.py fingered-plan.json -o result-report.md --pdf fingered-score.pdf --preview fingered-score.png
```

Report delivery level, scope, recognized and fingered note counts, coverage, low-confidence notes, collisions, and remaining review measures. A complete result requires 100% scoped coverage and zero collisions. Deliver available files even when the result is review-required or partial, and add short practice guidance for crossings, shifts, and leaps.
