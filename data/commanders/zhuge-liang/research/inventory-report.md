# Zhuge Liang — inventory report

Structural scope: commander voice, culture/unit voice contexts reachable in the supported corpus, and explicit commander-keyed branches even when their runtime trigger is unknown. Generic advisor/tutorial references are a separate audit table and are not attributed to this commander.

| Metric | Count |
|---|---:|
| Total relevant Media IDs | 1919 |
| Spoken/non-silent decoded voice candidates | 1919 |
| Silent placeholder WEMs | 0 |
| Explicit commander speaker, including shared IDs | 293 |
| Commander-specific | 293 |
| Culture shared | 1473 |
| Unit type shared | 153 |
| Global shared | 0 |
| Unknown shared | 0 |
| Safe to replace, Media ID ownership only | 293 |
| Not safe/shared | 1626 |
| Frontend spoken, commander-specific | 15 |
| Battle spoken, commander-specific | 278 |
| Orders, commander-specific | 130 |
| Abilities, commander-specific | 12 |
| Emotes, commander-specific | 41 |
| Other, commander-specific | 95 |
| Exact recording duplicate groups | 295 |
| Pilot menu | 10 |
| Pilot battle | 23 |

| Transcript confidence | All relevant spoken | Commander-specific spoken |
|---|---:|---:|
| CONFIRMED | 31 | 31 |
| HIGH | 1807 | 262 |
| MEDIUM | 81 | 0 |
| LOW | 0 | 0 |
| UNKNOWN | 0 | 0 |

READY FOR TRANSLATION/TTS: **YES**.

Commander-specific wording review items: **0**. Missing transcripts across the primary inventory: **0**.

Ownership safety does not approve a transcript, translation or voice performance. MEDIUM/LOW/UNKNOWN text must be resolved before generating the affected performance. Czech text remains empty. Delivery/model fields are proposals using the project’s historical routing, with no API availability or generation claim.

Completeness evidence:

- Forward DialogueEvent/Event traversal: 1919 Media IDs.
- Independent Sound-to-root reverse traversal: 1919 Media IDs; difference: [].
- Explicit speaker branches / named ordinary events: 293 forward, 293 reverse, 293 independently enumerated.
- Emote parent-pool candidates: 41; mapped Event media: 41; difference: [].
- Raw BNK verification: 44675 Sound source fields; HIRC IDs and decision keys/targets also match original bytes.
- Entire live installation scan: 545 PACK indexes, RSA validated; 21 unique BNKs in 3 PACKs. All 6 voice banks and the remaining banks participate in the Sound usage audit. Alias bank payload hashes are retained in the source audit.
- Every YES row has matching forward/reverse usage roots and no unrooted or foreign Sound use. Relevant unresolved references: [].

No-audio commander branches: **11**, listed in no-audio-branches.csv. Null leaves and empty random containers have no Media ID and are separate from silent WEM placeholders.

Frontend containers:

| Event ID | Container | Variants | Trigger |
|---|---|---:|---|
| 1823898040 | 801131745 | 5 | matchmaking / battle search starts with selected commander (static game.dll COMMANDER_FRONTEND_MATCHMAKE_VO_DELAY) |
| 2732370230 | 683874514 | 5 | open/select/unlock commander card (static game.dll delays 32-34; not newly runtime tested) |
| 1402037848 | 607873144 | 5 | unknown frontend random quote event; no call site found in prior static analysis |

The quote event’s exact runtime trigger remains unknown. Unknown trigger does not remove a structurally present random variant.

Transcript evidence consists of local unprompted faster-whisper hypotheses, exact localization/Event hashes, exact PCM duplicate transfers and explicitly documented context corrections. Agreement is not human listening. Latin or proper-name spelling is retained when supported by localization/actor evidence. Raw alternatives remain in the CSV.

Exact duplicate groups use decoded PCM plus format/sample count. Original WEM hashes additionally distinguish byte-identical payloads from different encodes/headers. Equal text alone never merges performances. Cross-inventory groups resolve through the shared research duplicate table.

Original English WEMs and direct PCM16 WAVs are held only in the private archive. All original rate/channel/sample counts match direct decode. Original signal peaks and clipping flags are descriptive; no original audio was altered. Float/ww2ogg replacement QC does not apply because this phase creates no replacement audio.

Human listening: **NOT RUN**. Game/launcher/runtime test: **NOT RUN**. Paid API/TTS calls: **0**. Installer release manifest: **not created**.

The [integrity audit](../../shared-research/zhuge-liang-integrity-audit.json) compares source PACK hashes and all Hannibal files with the initial baseline. It also records externally running game/launcher processes and installation timestamp changes; this task did not start or stop those processes.

Open commander-specific wording review (audio paths are relative to the private archive root):

| Media ID | Candidate text | Confidence / resolution | Archive WAV reference |
|---|---|---|---|
| none | | | |

Corpus voice Sounds without a playback root:

- battle_vo_emotes.bnk: Sound 646687175, source 711536925; sibling owners: commander:Commander_Xerxes. No playable commander event is inferred from this sibling context.

See transcript-review.csv for all shared and commander-specific uncertainty. Full references are preserved in usage-paths.csv. No runtime observation or human review is marked PASS.
