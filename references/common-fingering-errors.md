# Common Fingering Errors

Use this as a counterexample checklist after the first fingering pass and again before rendering. For evidence, priorities, exceptions, and implementation limits, see [professional-fingering-rules.md](professional-fingering-rules.md).

## 0. Correct-looking fingering on the wrong pitch

- **Error:** notehead geometry shows a second, but the plan records a third and assigns the left-hand dyad `3-1`.
- **Fix:** run `validate_recognition.py` and derive pitch from staff geometry and clef. Block every pitch/geometry contradiction before fingering.
- Never bypass recognition gates with confidence scores, coverage, or a successfully generated PDF.

## 1. Missing a tightly spaced chord member

- **Error:** two adjacent noteheads around one stem become one event, so a three-note chord receives only `1-5`.
- **Fix:** inspect seconds at high zoom, bind every visible notehead, and assign the complete chord, such as `1-2-5`.
- Finger-label count must equal visible notehead count.

## 2. Meaningless changes in an isomorphic transposed pattern

- **Error:** structurally identical dyads use `1-5, 1-5, 1-4`.
- **Fix:** keep `1-5, 1-5, 1-5` and move the hand as a unit. Change only for a documented continuation, articulation, key-shape, or span reason.

## 3. Reassigning an unchanged moving dyad

- **Error:** a comfortable dyad that can shift laterally uses `1-3, 1-4, 1-5`.
- **Fix:** preserve one shape, for example `1-5, 1-5, 1-5`, and review the whole sequence rather than isolated chords.

## 4. Skipping an available adjacent finger in scalar motion

- **Error:** a descending step uses `5-3` even though finger 4 is free and natural.
- **Fix:** prefer `5-4`. Skip only to prepare what follows or avoid an ergonomic problem, and record the reason.

## 5. Reusing one finger on successive different pitches

- **Error:** a connected melody repeatedly uses the same finger without a planned crossing or shift.
- **Fix:** use adjacent fingers, a prepared crossing, or an explicit lateral shift. Staccato, repeated notes, or intentionally detached leaps may be exceptions.

## 6. Finger distance does not match the dyad interval

- **Error:** every dyad receives `1-5` or left-hand `5-1`, unnecessarily stretching a third.
- **Fix:** begin with adjacent fingers for seconds, `1-3` (left hand low-to-high `3-1`) for thirds, `1-4` for fourths, and `1-5` for fifths or wider. Context may justify `2-4` or `3-5`, but the hand must stay relaxed and the reason must be recorded.

## 7. A single note competes with the next chord for the same finger

- **Error:** left-hand bass 3 leads directly to a third with `3-1`, producing `3 -> 3-1`.
- **Fix:** inspect the full transition. A bass below the chord normally uses 5, producing `5 -> 3-1`. Check single-to-chord and chord-to-single transitions finger by finger.

## 8. Copying a bad template through a repeated pattern

- **Error:** `5-4-1` is copied across every wide descending three-note group without validating the first group.
- **Fix:** verify interval geometry and hand shape first; a wide descending group often favors outer–middle–thumb, such as right-hand `5-3-1`. Consistency may amplify only a valid template.

## 9. Unexplained finger changes on repeated accompaniment pitches

- **Error:** the same pitch in the same structural slot changes finger without a repetition technique or preparation need.
- **Fix:** preserve the finger by default, such as left-hand repeated bass on 5. Exceptions require `repeated_note` or `substitution` plus a reason.

## 10. Changing finger across a tied identical pitch

- **Error:** one tie group uses `2-3` without a silent-substitution reason.
- **Fix:** place both notes in the same `tie_group` and force the same finger. A real substitution requires `transition_type=substitution`, `rule_id=A4`, `exception_reason`, and `exception_verified=true` after note-level review.

## 11. Treating left-hand bass and dyads in isolation

- **Error:** individually legal dyads create an unstable `4 -> 3-1 -> 3-1` accompaniment motion.
- **Fix:** review outer bass–dyad–dyad as one unit. Start with bass 5, second `2-1`, or third `3-1`, then adapt to what follows. Any deviation from a stable outer finger or chord shape needs a verified exception.

## 12. Fingering a notehead that does not exist

- **Error:** a stem, beam, or barline creates a sixth event where the score has five noteheads, leaving a floating label.
- **Fix:** record `event_count_checks` for dense or previously faulty measures and count each page/measure/hand independently. A matching global total does not prove local correctness.

## 13. Mistaking a rest for a note

- **Error:** a whole or half rest is read as a filled notehead and affects the next hand-position search.
- **Fix:** require an open or filled oval contour for noteheads. Classify rectangular rests, zig-zag rests, stems, beams, barlines, and dots as non-note symbols. In sparse measures, zoom every candidate and record `sparse_symbol_verified=true`. After deleting a false event, recompute at least that measure and the next.

## 14. Inventing a touching chord member from an accompaniment pattern

- **Error:** only one notehead is visible, but a second coordinate is generated from repeated structure or fixed spacing, turning a third into a second and producing `2-1` instead of `3-1` across the page.
- **Fix:** locate both real oval centers and set `origin=direct_visual_notehead` plus `chord_member_verified=true` for each. Never create members with `page_y +/- 5`, `page_y +/- 10`, or a transposed prior chord. Keep the item unresolved if the image cannot separate it.

## 15. Physical key coordinates run opposite to pitch

- **Error:** equally spacing all semitones makes a higher D receive a smaller `keyboard_x_cm` than a lower B-flat, reversing the search direction.
- **Fix:** map `pitch_midi` to real white/black key centers and require strict increase across MIDI pitch, including octave boundaries. Block every mismatch before dynamic search.
