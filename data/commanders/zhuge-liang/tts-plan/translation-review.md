# Zhuge Liang — translation review

Safe spoken IDs: 293. Czech drafts: 293. English-supported drafts: 293. Provisional English: 0. Missing English: 0.

Unique future performances: 292; repeated Media IDs covered: 1. Byte-identical original WEM duplicate groups: 1; exact decoded PCM duplicates with different WEM bytes: 0. Model routing: eleven_v3 0, eleven_v4 292 per unique performance.

The WEM budget labels are planning heuristics based on original size, duration and Czech/English text length. HIGH means original <6500 B, or planned Czech >23 characters per original second, or >1.5× English length with original <20000 B. MEDIUM means original <10000 B, duration <1 s, >17 characters/s or >1.25× English length. They do not establish that a new encoded WEM will fit. Never shorten speech, change timing or truncate to satisfy an estimate.

The original PCM fingerprint plus matching English/Czech wording defines a performance group. An emote and an order can share the same group when both point to the same original recording. The model/style/tags are shared across that group. Every Media ID still needs separate future size and playback checks.

High WEM budget risk IDs (19): 30883094, 109190324, 189996222, 197890216, 238258471, 262213703, 311027298, 432516745, 500434611, 513270410, 717563187, 755199681, 825999162, 873377335, 887795317, 917893418, 992985044, 996690592, 1070375151.

Originally disputed IDs resolved with local context/phonetic evidence: 30. Human-confirmed by the project owner: 2; resolved by the independent second opinion: 0 (labels in `transcript_resolution`, evidence in shared `transcript-corrections.json`). Individual decisions and the unresolved candidate wording are in `transcript-review-decisions.csv`.

Manual English review: none. See `manual-transcript-review.md` in the research folder and `transcript-review-decisions.csv` here.

Commander-specific translator decisions and open questions: [translation-notes.md](translation-notes.md).

READY FOR ELEVENLABS: **YES**. No ElevenLabs request, audio generation, game write or human listening is claimed.
