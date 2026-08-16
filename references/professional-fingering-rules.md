# Professional Piano Fingering Rules

Use this document as the musical rule hierarchy for draft generation, human review, and exception explanations. `common-fingering-errors.md` contains only counterexamples.

## Evidence scope

Only full primary papers, author manuscripts, and upstream source code were used. The rules below are original summaries; no paper text or tables are redistributed.

### Sources

- **[P97]** Parncutt, Sloboda, Clarke, Raekallio, and Desain. *An Ergonomic Model of Keyboard Fingering for Melodic Fragments*. Music Perception 14(4), 1997, 341–382. [Author manuscript](https://static.uni-graz.at/fileadmin/_Persoenliche_Webseite/parncutt_richard/Pdfs/PaSlClRaDe97_FingeringModel.pdf). Supports playable/comfortable spans, stretch and compression, position changes, weak fingers, black/white keys, crossings, rhythm, tempo, articulation, register, repetition, and phrase boundaries. The model focuses mainly on monophonic legato fragments and its provisional average-hand weights are not universal.
- **[AK07]** Al Kasimi, Nichols, and Raphael. *A Simple Algorithm for Automatic Generation of Polyphonic Piano Fingerings*. ISMIR 2007, 355–356. [Full paper](https://archives.ismir.net/ismir2007/paper/000355.pdf). Supports hard constraints for polyphony/chords and joint vertical chord comfort plus horizontal chord-to-chord motion, adjustable by hand size. It does not model substitutions, black/white-key differences, or automatic hand assignment.
- **[N14]** Nakamura, Ono, and Sagayama. *Merged-output HMM for Piano Fingering of Both Hands*. ISMIR 2014. [Author manuscript](https://eita-nakamura.github.io/articles/Nakamura_etal_MergedOutputHMMForPianoFingering_ISMIR2014.pdf). Supports preserving within-hand voice continuity instead of assigning hands from an instantaneous pitch split. It is a statistical architecture, not a teaching rulebook.
- **[N19]** Nakamura, Saito, and Yoshii. *Statistical Learning and Estimation of Piano Fingering*. Information Sciences 517, 2020; [open preprint](https://arxiv.org/pdf/1904.10237). Supports multi-event context, systematic performer variation, simultaneous/sustained-note constraints, and multiple acceptable answers. Statistical fit alone does not equal musical quality.
- **[PP]** Marco Musy. [PianoPlayer](https://github.com/marcomusy/pianoplayer). Engineering basis for hand geometry, motion/duration cost, lookahead, and anchors. It is not a pedagogical authority and has limitations in ornamentation, hand interaction, and crossing cases.

Exclude paywalled books, abstract-only papers, previews, blogs, and secondary summaries from the formal evidence base.

## Priority hierarchy

Resolve conflicts in this order:

1. user-locked fingering, explicit composer instructions, and established musical intent;
2. playability and safety hard constraints;
3. articulation, voice, sustain, and phrase continuity;
4. relaxed hand shape, motion economy, and preparation;
5. consistency of repeated structures;
6. general preferences about weak fingers, black keys, and conventional shapes.

A lower rule never overrules a higher one. Optimize stable, repeatable realization of the whole phrase, not local ease on one note. [P97][N19]

## A. Hard constraints and explainable connections

### A1. One finger per simultaneous key

One finger cannot depress two different keys at once. Simultaneous notes in one hand require distinct fingers. **Enforced by generator and validator.** [AK07][N19]

### A2. No finger crossing inside a chord

When chord pitches rise, right-hand finger numbers normally rise and left-hand numbers normally fall. Right-hand C–E may be `1-3`; left-hand C–E may be `3-1`. **Enforced by generator and validator.** [AK07][N19]

### A3. Fit every interval inside the selected hand's playable span

Discard candidates outside `MinPrac/MaxPrac`, then compare comfort. Adjust thresholds for hand size and skill; never impose an average adult hand as universal. **Enforced with XXS–XXL hand presets.** [P97][AK07]

### A4. Preserve finger occupancy during sustain

A finger holding a note cannot play another key simultaneously. Keep the same finger by default. Allow same-note substitution only when notation, legato, or explicit review requires it; mark `transition_type=substitution`. Recognized `tie_group` membership is enforced; other cross-event sustain still requires review. [AK07][N19]

### A5. Do not repeat one finger on adjacent different legato pitches without reason

Use an adjacent finger, crossing, or planned shift. Staccato, pedal connection, phrase breaks, or a deliberate color may justify an exception. **Validator warning plus musical review.** [P97]

## B. High-priority scoring rules

### B1. Match finger distance to musical interval

Compare interval distance with finger distance in melody and simultaneity. Begin with adjacent fingers for seconds, right-hand `1-3` / left-hand low-to-high `3-1` for thirds, `1-4` for fourths, and `1-5` / `5-1` for fifths or wider. Override only for black/white-key shape, voice, or continuation and record why. [P97][AK07]

### B2. Penalize both excessive stretch and compression

Reachable is not automatically comfortable in repetition. Add cost outside the comfort zone, especially for pairs without the thumb. The algorithm partly scores this; pair-specific comfort and compression still need review. [P97][AK07]

### B3. Minimize the number and size of position changes

Prefer stable positions. When movement is necessary, compare frequency, distance, landing comfort, and preparation for later notes. Never create a large next-beat leap for one locally convenient note. [P97][PP]

### B4. Use at least three events of context

Do not decide from one pair alone. Runs, arpeggios, and shifts must see beyond the next turning point. Use 3–9 events of lookahead. [N19][PP]

### B5. Prefer adjacent fingers in ordinary scalar motion

Avoid unexplained skipped fingers, unless adjacent fingering would create a dead end, trap the hand on finger 5, or damage crossing preparation. [P97]

### B6. Evaluate crossings with direction and key height

Thumb crossings are not categorically wrong. White-to-white, black-to-black, thumb-on-black, and directional compression have different costs. Relax only for articulation, pedal, or tempo with an explanation. [P97][AK07]

### B7. Make weak-finger preference subordinate to music and tempo

Penalize unnecessary 4/5 dependence or awkward `3-4-5` coordination, but never ban weak fingers mechanically. Accent, voice projection, stable position, and tempo may require them. [P97]

### B8. Keep the mapping of repeated, sequential, and isomorphic patterns

When interval structure, key shape, and continuation match, repeat the same finger sequence to build a stable motor program. Change as a whole group only when tonal shape, phrase target, or landing changes. Current section-level pattern detection requires model review. [P97]

### B9. Place shifts at phrase, rest, articulation, or pedal opportunities

Prefer phrase boundaries, rests, staccato, pedal cover, or structural accents. A legato-optimal fingering need not be staccato-optimal. [P97][N19]

### B10. Evaluate chords vertically and horizontally

Check internal interval/finger comfort and the complete connection from the previous chord to the next. Do not choose isolated beautiful shapes that connect poorly. The algorithm enforces stable outer-note-to-dyad behavior; larger chords and complex sustains need review. [AK07][N19]

### B11. Review hand assignment through voice continuity

Do not split hands mechanically at middle C or an instantaneous pitch boundary. Preserve each hand's voice, rhythm, and motion and inspect handoff conflicts. [N14][N19]

### B12. Preserve multiple valid answers and individual variation

Professional performers may choose different acceptable fingerings. Respect anchors, hand size, level, tempo, and user preference. Present alternatives or review flags instead of claiming one universal answer. [P97][AK07][N19][PP]

## Generation and review procedure

1. Lock user/source fingering, voices, articulation, sustains, and coordinate identity.
2. Remove impossible candidates with A1–A4; make A5 create an explainable warning.
3. Accumulate local and lookahead costs for B1–B7 and B10.
4. Review B8, B9, and B11 over a phrase or at least one complete pattern.
5. For tied or near-tied solutions, apply B12: preserve anchors and choose the most stable; report meaningful alternatives.
6. Record `exception_reason` whenever retaining a general-rule violation, identifying articulation, voice, tempo, hand size, or preparation.

## Exit checklist

- [ ] Simultaneous notes use distinct, non-crossing fingers.
- [ ] Every span fits the selected hand; small intervals do not mechanically use `1-5/5-1`.
- [ ] Sustains, substitutions, and same-finger different notes match articulation.
- [ ] Every crossing, skip, and shift is explained by at least three surrounding events.
- [ ] Repeated or sequential patterns do not change fingering meaninglessly.
- [ ] Shifts occur at musically or physically suitable opportunities.
- [ ] Chords are comfortable alone and connect naturally.
- [ ] Hand assignment preserves voices rather than using a crude pitch split.
- [ ] Fast passages penalize unnecessary motion and awkward shape more heavily.
- [ ] Locked fingering is preserved and individual variation is treated as a parameter.

## Capability boundary

The Skill generates and validates an ergonomic draft, but phrase detection, metric accent, pedal, articulation, section-level similarity, and cross-hand redistribution are not all encoded in one optimizer. The host model must review them from the full score, and the report must distinguish algorithmic enforcement from musical review.
