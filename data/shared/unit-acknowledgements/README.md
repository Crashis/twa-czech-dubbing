# Unit acknowledgements (staged research)

Status: canonical source plan of the shared module `unit-voices` ("Univerzální hlášky"). This folder is deliberately not a
commander folder and contains no `manifest.json`; the installer and release builder never read it. Production (2026-10-22):
44/44 performances (`Units Male CZ`, `Units Women CZ`, `eleven_v4`; Falxy → Falksy approved), 5 compact sources and 10
approved byte-budget fallback lines (`byte-budget-fallbacks.csv`, `translation-notes.md`), 465/465 exact-size WEMs, active
installer module `data/shared/unit-voices/manifest.json` with `replacements/unit-voices/wem/`. See the "Univerzální hlášky" section of [DEVELOPMENT](../../../docs/DEVELOPMENT.md).

- `plan.staged.json`: canonical English phrases, approved Czech texts (male/neutral and female-slot forms, optional TTS
  pronunciation input), and one planned performance per unique Czech text and voice group, mapped to its reachable Media IDs.
- `media-map.staged.csv`: production scope only: one row per reachable Media ID with ownership, reach, safety and original budget.
- `pronunciation-overrides.csv`: token rules for the TTS input only (Falxy → Falksy), resolved by `tools.tts.pronunciation`
  exactly like commander overrides; the staged `tts_input_text` values must equal the resolver's pilot output.
- `excluded-media.staged.csv`: shared Media IDs of the same events that no live unit reaches; they get no audio and, like every
  ID here, must stay out of commander-only releases.

What these lines are: the unit-selection callouts ("Elephants!", "Repeating crossbows!") and the generic selection
acknowledgements ("Awaiting orders!") of DialogueEvent 1419778157 (battle) and 2732370230 (frontend unit card). They are keyed
by `vo_culture` x `vo_actor` (`Male_1..3`, `Female_1..3`) x `vo_unit_type`; the unit's own database row supplies culture and
unit type, the unit entity's gender selects the male or female list, and the game picks one of the three slots. No commander
identity is involved, so every Media ID here is shared by all commanders who can field a matching unit.

Counts: 1050 Media IDs in the events, 465 reachable (production scope),
40 English phrases (all Czech texts final), 44 planned Czech performances
(29 male, 15 female),
421 Media IDs reuse another target's performance.

Before any production use: a human-reviewed voice pilot, a separately authorized TTS run (one generation per performance),
exact-size WEM work, and a new shared/joint release type with its own validated whole-PACK hash. Commander-only releases
must keep these IDs untouched.
