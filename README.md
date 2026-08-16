# Piano Score Fingering

An AI-agent Skill for recognizing piano scores, generating playable two-hand fingering, and placing finger numbers back onto the original score with coordinate-aware annotation.

It accepts score images, PDFs, MusicXML, MXL, and supported MuseScore files. Depending on the input and the host environment, it can produce fingered MusicXML, an annotated PDF, a PNG preview, and a verification report.

> **Important:** automatic fingering is a practice aid, not a replacement for a pianist or teacher. Image/PDF recognition and musically ambiguous passages still require human review.

## What it does

- Preserves a stable identity and page coordinate for every recognized notehead.
- Separates score recognition from fingering generation so recognition errors are blocked before they propagate.
- Uses a bundled dynamic hand-position search adapted from [PianoPlayer](https://github.com/marcomusy/pianoplayer).
- Reviews both hands with ergonomic, polyphonic, voice-continuity, chord-connection, and repeated-pattern rules.
- Keeps chord fingering labels vertically stacked and tied to the correct noteheads.
- Validates note coverage, duplicate or missing labels, collisions, ties, fingering constraints, and output readability.
- Supports local corrections without recomputing an already verified full score.

## Core workflow

1. **Read the source** — inspect every page and declare the requested measure range.
2. **Recognize score facts** — identify notes, rests, clefs, accidentals, rhythm, voices, ties, chords, staves, and notehead centers.
3. **Review and lock recognition** — run an independent measure-level structure pass and block unresolved score facts.
4. **Generate fingering** — search candidate hand positions with configurable hand size and multi-event lookahead.
5. **Review musical continuity** — check scales, crossings, repeated patterns, chords, sustained notes, hand assignment, and phrase-level preparation.
6. **Place labels** — overlay right-hand numbers above the treble staff and left-hand numbers below their own staff without obscuring notation.
7. **Verify delivery** — compare the rendered result with the source and produce a report describing coverage, warnings, and remaining review measures.

## Supported inputs and outputs

| Input | Typical output |
| --- | --- |
| PDF | Annotated PDF, PNG preview, fingering plan, report |
| Score image | Annotated PDF or image-based preview, fingering plan, report |
| MusicXML / MXL | Fingered MusicXML, fingering plan, optional PDF when verifiable rendering is available |
| MSCX / MSCZ | Semantic conversion when the host can read or unpack the file; MusicXML export may be requested otherwise |

## Requirements

The host agent must be able to:

- read the supplied score files and visually inspect rendered pages;
- run Python 3 scripts;
- read and write local files;
- create or merge PDF output when PDF delivery is requested.

The Skill does not require the user to install PianoPlayer, MuseScore, an online OMR service, or additional Python packages for its bundled offline workflow. The host still needs sufficient multimodal reasoning and file-execution capabilities. A flagship multimodal model with high reasoning effort is recommended for dense image or PDF scores.

## Installation

Clone or download this repository, then place the complete `piano-score-fingering` folder in the Skill directory used by your agent environment. Keep the folder structure and `NOTICE.txt` intact.

```bash
git clone https://github.com/Yannxinn/piano-score-fingering.git
```

In products that support named Skills, invoke it as:

```text
$piano-score-fingering
```

Example requests:

```text
Use $piano-score-fingering to add fingering to this piano-score PDF and return an annotated PDF.
```

```text
Use $piano-score-fingering to review the fingering in measures 17–24 of this MusicXML file. Preserve my locked fingering and return corrected MusicXML.
```

## Accuracy model

The workflow uses a recognition lifecycle of:

```text
draft -> review -> verified -> locked
```

Fingering is blocked when pitch, clef, accidental, rhythm, hand, chord membership, tie, voice, or notehead identity remains unresolved. The Skill limits repeated automatic correction loops and can return one of three honest delivery levels:

- **Complete** — the full requested scope passed recognition, fingering, placement, and output checks.
- **Review required** — the score semantics are verified, but musical-preference or layout warnings remain.
- **Partial** — only a reliable portion can be completed; unresolved measures are explicitly reported.

## Musical basis

The fingering rules synthesize accessible primary research and open-source engineering work:

- Parncutt et al. (1997), *An Ergonomic Model of Keyboard Fingering for Melodic Fragments* — ergonomic spans, crossings, position changes, weak fingers, timing, articulation, and phrase context.
- Al Kasimi, Nichols, and Raphael (2007), *A Simple Algorithm for Automatic Generation of Polyphonic Piano Fingerings* — polyphonic constraints, chord comfort, and chord-to-chord motion.
- Nakamura, Ono, and Sagayama (2014), *Merged-output HMM for Piano Fingering of Both Hands* — two-hand voice continuity and hand assignment.
- Nakamura, Saito, and Yoshii (2020), *Statistical Learning and Estimation of Piano Fingering* — multi-event context, performer variation, sustain constraints, and multiple acceptable solutions.
- Marco Musy's [PianoPlayer](https://github.com/marcomusy/pianoplayer) — hand geometry, keyboard movement cost, dynamic lookahead, and fingering anchors.

See [professional-fingering-rules.md](references/professional-fingering-rules.md) for the full rule hierarchy, scope, and source links.

## Repository structure

```text
piano-score-fingering/
├── SKILL.md                  # Agent workflow and execution rules
├── agents/openai.yaml        # Skill UI metadata
├── references/               # Fingering rules, plan schema, error catalogue
├── scripts/                  # Recognition, fingering, rendering, and validation tools
├── assets/tests/             # Offline MusicXML regression fixtures
└── NOTICE.txt                # Authorship and third-party notices
```

## Limitations

- Dense, low-resolution, handwritten, skewed, or partially cropped scores can still be misrecognized.
- More than one fingering may be musically valid; hand size, tempo, articulation, level, and interpretation matter.
- Phrase detection, pedaling, advanced redistribution between hands, and some ornamentation cases still require model or human review.
- Users should inspect the final score before relying on it for practice or publication.

## Authorship and notices

Original design, workflow, adaptations, and documentation: **Yanxin Liu**.

Copyright © 2026 Yanxin Liu. All rights reserved.

This repository includes or adapts third-party components under their respective licenses. See [NOTICE.txt](NOTICE.txt) for complete authorship, attribution, and license information. No public license is currently granted for the original portions unless the author provides one separately.

