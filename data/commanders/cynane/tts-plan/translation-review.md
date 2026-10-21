# Cynane — translation review

Safe spoken IDs: 241. Czech drafts: 240. English-supported drafts: 240. Provisional English: 0. Missing English: 1.

Unique future performances: 239; repeated Media IDs covered: 2. Byte-identical original WEM duplicate groups: 0; exact decoded PCM duplicates with different WEM bytes: 2. Model routing: eleven_v3 5, eleven_v4 234 per unique performance.

The WEM budget labels are planning heuristics based on original size, duration and Czech/English text length. HIGH means original <6500 B, or planned Czech >23 characters per original second, or >1.5× English length with original <20000 B. MEDIUM means original <10000 B, duration <1 s, >17 characters/s or >1.25× English length. They do not establish that a new encoded WEM will fit. Never shorten speech, change timing or truncate to satisfy an estimate.

The original PCM fingerprint plus matching English/Czech wording defines a performance group. An emote and an order can share the same group when both point to the same original recording. The model/style/tags are shared across that group. Every Media ID still needs separate future size and playback checks.

High WEM budget risk IDs (4): 173078305, 470502895, 755477568, 782714451.

Originally disputed IDs resolved with local context/phonetic evidence: 54. Individual decisions and the unresolved candidate wording are in `transcript-review-decisions.csv`.

Manual English review: 667922401. See `manual-transcript-review.md` in the research folder and `transcript-review-decisions.csv` here.

Commander-specific translator decisions and open questions: [translation-notes.md](translation-notes.md).

READY FOR ELEVENLABS: **NO**. No ElevenLabs request, audio generation, game write or human listening is claimed.
