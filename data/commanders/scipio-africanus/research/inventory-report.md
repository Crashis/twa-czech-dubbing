# Scipio Africanus — inventory report

Structural scope: commander voice, culture/unit voice contexts reachable in the supported corpus, and explicit commander-keyed branches even when their runtime trigger is unknown. Generic advisor/tutorial references are a separate audit table and are not attributed to this commander.

| Metric | Count |
|---|---:|
| Total relevant Media IDs | 1874 |
| Spoken/non-silent decoded voice candidates | 1874 |
| Silent placeholder WEMs | 0 |
| Explicit commander speaker, including shared IDs | 249 |
| Commander-specific | 249 |
| Culture shared | 59 |
| Unit type shared | 123 |
| Global shared | 1443 |
| Unknown shared | 0 |
| Safe to replace, Media ID ownership only | 249 |
| Not safe/shared | 1625 |
| Frontend spoken, commander-specific | 9 |
| Battle spoken, commander-specific | 240 |
| Orders, commander-specific | 131 |
| Abilities, commander-specific | 14 |
| Emotes, commander-specific | 42 |
| Other, commander-specific | 53 |
| Exact recording duplicate groups | 43 |
| Pilot menu | 6 |
| Pilot battle | 25 |

| Transcript confidence | All relevant spoken | Commander-specific spoken |
|---|---:|---:|
| CONFIRMED | 84 | 84 |
| HIGH | 1403 | 165 |
| MEDIUM | 323 | 0 |
| LOW | 64 | 0 |
| UNKNOWN | 0 | 0 |

READY FOR TRANSLATION/TTS: **YES**.

Commander-specific wording review items: **0**. Missing transcripts across the primary inventory: **0**.

Ownership safety does not approve a transcript, translation or voice performance. MEDIUM/LOW/UNKNOWN text must be resolved before generating the affected performance. Czech text remains empty. Delivery/model fields are proposals using the project’s historical routing, with no API availability or generation claim.

Completeness evidence:

- Forward DialogueEvent/Event traversal: 1874 Media IDs.
- Independent Sound-to-root reverse traversal: 1874 Media IDs; difference: [].
- Explicit speaker branches / named ordinary events: 249 forward, 249 reverse, 249 independently enumerated.
- Emote parent-pool candidates: 42; mapped Event media: 42; difference: [].
- Raw BNK verification: 44675 Sound source fields; HIRC IDs and decision keys/targets also match original bytes.
- Entire live installation scan: 545 PACK indexes, RSA validated; 21 unique BNKs in 3 PACKs. All 6 voice banks and the remaining banks participate in the Sound usage audit. Alias bank payload hashes are retained in the source audit.
- Every YES row has matching forward/reverse usage roots and no unrooted or foreign Sound use. Relevant unresolved references: [].

No-audio commander branches: **0**, listed in no-audio-branches.csv. Null leaves and empty random containers have no Media ID and are separate from silent WEM placeholders.

Frontend containers:

| Event ID | Container | Variants | Trigger |
|---|---|---:|---|
| 2732370230 | 979337840 | 3 | open/select/unlock commander card (static game.dll delays 32-34; not newly runtime tested) |
| 1402037848 | 926662753 | 3 | unknown frontend random quote event; no call site found in prior static analysis |
| 1823898040 | 807840061 | 3 | matchmaking / battle search starts with selected commander (static game.dll COMMANDER_FRONTEND_MATCHMAKE_VO_DELAY) |

The quote event’s exact runtime trigger remains unknown. Unknown trigger does not remove a structurally present random variant.

Transcript evidence consists of local unprompted faster-whisper hypotheses, exact localization/Event hashes, exact PCM duplicate transfers and explicitly documented context corrections. Agreement is not human listening. Latin or proper-name spelling is retained when supported by localization/actor evidence. Raw alternatives remain in the CSV.

Exact duplicate groups use decoded PCM plus format/sample count. Original WEM hashes additionally distinguish byte-identical payloads from different encodes/headers. Equal text alone never merges performances. Cross-inventory groups resolve through the shared research duplicate table.

Original English WEMs and direct PCM16 WAVs are held only in the private archive. All original rate/channel/sample counts match direct decode. Original signal peaks and clipping flags are descriptive; no original audio was altered. Float/ww2ogg replacement QC does not apply because this phase creates no replacement audio.

Human listening: **NOT RUN**. Game/launcher/runtime test: **NOT RUN**. Paid API/TTS calls: **0**. Installer release manifest: **not created**.

The [integrity audit](../../shared-research/integrity-audit.json) compares source PACK hashes and all Hannibal files with the initial baseline. It also records externally running game/launcher processes and installation timestamp changes; this task did not start or stop those processes.

Open commander-specific wording review (audio paths are relative to the private archive root):

| Media ID | Candidate text | Confidence / resolution | Archive WAV reference |
|---|---|---|---|
| none | | | |

Corpus voice Sounds without a playback root:

- battle_vo_emotes.bnk: Sound 646687175, source 711536925; sibling owners: commander:Commander_Xerxes. No playable commander event is inferred from this sibling context.

See transcript-review.csv for all shared and commander-specific uncertainty. Full references are preserved in usage-paths.csv. No runtime observation or human review is marked PASS.
