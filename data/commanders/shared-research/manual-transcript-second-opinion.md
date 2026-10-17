# Second opinion — five disputed English voice lines

Independent re-transcription of five commander-specific lines that the Leonidas, Scipio Africanus and Spartacus inventories had left for manual wording review. This report is metadata only. It changes no existing transcript, translation, plan or audio, and records **no human listening**. Machine-readable rows are in `manual-transcript-second-opinion.csv`.

## Independence protocol

1. **Audio-only phase.** Only the five decoded WAVs were opened. No Wwise context, localization, sibling variants or previous transcript files were read. The results were frozen in a timestamped private file before step 2.
2. **Context phase.** DialogueEvent, decision-tree path, random-container siblings, the same ability/event for other commanders, and the original English localization.
3. **Comparison phase.** Only after steps 1–2 were the existing `voice-lines.csv`, `manual-transcript-review.md`, `transcript-review-decisions.csv` and `voice-lines-cz.csv` rows for these IDs read.

## Audio-only method

- Local faster-whisper `base.en`, `small.en` and `medium.en` (CPU int8, no prompt or hotwords, offline). Each model ran on six analysis-only signal variants: raw, 0.8× and 0.7× pitch-preserving `atempo`, 200–3800 Hz band-pass, 0.5 s padding, and slowed + band-passed. Each variant used beam 5 and beam 10, plus nine temperature-sampled decodes on raw and 0.7×.
- Segment-isolated ASR: single word regions were cut out and padded, so the language model cannot use neighbouring words.
- Forced-choice scoring: teacher-forced Whisper token probabilities for candidate texts that came from the audio-only phase.
- Phonetics (numpy): LPC formants, voicing, band energies, fricative spectra over the full 0–16 kHz band of the 32 kHz WAVs, and onset transients at 2 ms resolution. Spectrograms were inspected as images.
- The variants and spectrograms are temporary analysis artifacts. They were never used as game assets and are not in this repository.

Model agreement is evidence, not human listening. Agreement across *signal variants* of one model is weaker than agreement between independent models, and both are weaker than a human check.

## Results

| Commander | Media ID | Audio-only result | After-context result | Confidence | vs previous | Manual review |
|---|---|---|---|---|---|---|
| Leonidas | 12766875 | We're being damaged by friendly fire! (MEDIUM) | We're being damaged by friendly fire! | MEDIUM | DISAGREES (prev. "We have been…"); STILL_UNRESOLVED | **YES** |
| Scipio Africanus | 191571653 | The flank's exposed! (MEDIUM) | The flank's exposed! | HIGH | DISAGREES (prev. "Their flank's…"); MORE_CONFIDENT | NO |
| Scipio Africanus | 238862791 | Attack the flank! (MEDIUM) | Attack the flank! | HIGH | DISAGREES (prev. "Attack that flank!"); MORE_CONFIDENT | NO |
| Scipio Africanus | 1022842783 | Onward! (LOW) | Onward! | HIGH | MORE_CONFIDENT (prev. NEEDS_MANUAL_TRANSCRIPTION) | NO |
| Spartacus | 697820721 | Strike through! (MEDIUM) | Strike through! | HIGH | AGREES; MORE_CONFIDENT | NO |

### 12766875 — Leonidas, friendly fire (announcer)

"damaged by friendly fire" is unanimous; only the auxiliary is disputed. small.en is unanimously progressive (6/6 variants, 18/18 samples). base.en is mostly progressive (5/6). medium.en is mostly perfect (4/6 variants, 8/9 raw samples), but it flips to "We're being" on slowed audio. On the isolated first 0.56 s, small and medium hear "We're being" and base hears "We've been". A ~100 ms schwa offglide after "we" (F2 2340 → ~1500–1800, no frication) argues against "We've", but not against "We have". Context gives no tense evidence: all 14 friendly-fire triggers use this single Sound. **Still needs human listening**, for wording only: the existing Czech "Zasáhla nás palba vlastních!" fits both readings.

### 191571653 — Scipio, Exposed Flanks (variant 1 of 2)

"flank", not "flag", is settled acoustically:
- After /æ/ there is an 80–90 ms voiced nasal murmur (−28 to −30 dB, 100% of energy below 1 kHz). That level is /ŋ/; a /g/ voice bar would be 25–30 dB below the vowel.
- Then a ~3 kHz velar burst and a **voiceless** /s/. "flag's" would end in voiced /z/.
- "'s" is contracted: there is no /ɪz/ syllable.

The determiner vowel is central ([ðə]). A reduced "their" can sound the same, so the article is decided by the cross-commander template: Leonidas and Spartacus both say "The flank is exposed!". medium.en forced choice and the earlier medium.en +0.5 s run agree. The existing Czech "Křídlo je odkryté!" is article-neutral.

### 238862791 — Scipio, Exposed Flanks (variant 2 of 2)

medium.en's "I tagged that flank!" is a language-model artifact: the isolated first word is "attack" and the isolated tail is "flank" in all three models. The middle vowel (F1 ≈ 740, F2 ≈ 1480) is clearly not this speaker's /æ/ in "atTACK" (F1 1000–1150, F2 ≈ 1600). So it is "the", not "that". Spartacus and Germanicus have the identical line "Attack the flank!". If adopted, the Czech "Útočte na to křídlo!" should lose the demonstrative "to".

### 1022842783 — Scipio, medium-speed stance / Tactical Advance

Free ASR fails on this delivery ("I WERE IT", "Awad", "I WOULD"). The measured phonetic sequence still reads /ɒnwəd/:
- open back vowel with no /aɪ/ glide;
- nasal dip;
- /w/ (the isolated second half is heard as "What?" by all models);
- central vowel;
- voiced closure and release.

"Onward!" was the frozen audio-only first listen. Context then showed that this 5-variant container already holds "Moving out!", "Forward!", "March!" and "Advance!". Leonidas and Germanicus use the same five-line set, including "Onward!". Their confirmed "Onward!" recordings have the same phonetic skeleton, and all three models read them correctly; Scipio's take is longer and more drawn out.

### 697820721 — Spartacus, Execute

The tooltip ("a lethal Strike … low chance to hit") and the sibling "Show your skill!" make "Strike true!" semantically tempting, but the acoustics reject it:
- A ~4 kHz /k/-release transient is followed by an 80 ms build-up of a flat-high fricative (peak 7 kHz, flat to 14 kHz). That fricative has ~10 dB more energy above 9 kHz than the speaker's own /s/: a dental /θ/.
- There is no postalveolar /tr/ frication, and no burst-then-decay pattern for "two".
- medium.en says "through" on all variants and samples, and small.en on all beam runs; only base.en says "two".
- "true" never appeared in 162 free or sampled decodes.

## Summary

RESOLVED BY SECOND OPINION (HIGH):

- 191571653 — The flank's exposed!
- 238862791 — Attack the flank!
- 1022842783 — Onward!
- 697820721 — Strike through!

STILL NEEDS HUMAN LISTENING:

- 12766875 — "We're being damaged by friendly fire!" vs "We have been damaged by friendly fire!" (wording only; meaning and Czech unaffected)

HIGH is an evidence-based recommendation, not CONFIRMED and not human listening. Applying any of these to `voice-lines.csv`, the translation memory or the TTS plans is a separate human decision. 191571653 and 238862791 would also change their `english_text`; 238862791 would also change its Czech draft.

**Applied 2026-10-17 on request:** the four HIGH results were applied through `transcript-corrections.json` and regenerated research/TTS plans. Czech drafts: 191571653 „Křídlo je odkryté!“, 238862791 „Útočte na křídlo!“, 1022842783 „Kupředu!“, 697820721 „Prorazte je!“. 12766875 was intentionally left unchanged as a manual-review item.

**Final human decisions 2026-10-17:** the project owner confirmed 12766875 as "We're being damaged by friendly fire!" (CONFIRMED, `HUMAN_CONFIRMED`; this matches the second-opinion recommendation, Czech unchanged „Zasáhla nás palba vlastních!“). The four HIGH results above are labelled `SECOND_OPINION_RESOLVED`. No manual transcript review remains for Leonidas, Scipio Africanus or Spartacus.
