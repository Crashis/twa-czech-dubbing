# Offline voice inventory

Research data lives under `data/commanders/<id>/research/` for Leonidas, Scipio Africanus, Spartacus, Germanicus, Zhuge Liang, Miltiades, Julius Caesar, Hasdrubal, Alexander the Great and Cynane. It is deliberately excluded from installer discovery, which only reads production `*/manifest.json`. `manifest-draft.json` has `status: research_ready`, `release_ready: false`, an explicit inventory status and separate translation/TTS readiness. A metadata validation PASS does not approve uncertain wording, a performance or a release.

The Leonidas and Scipio outputs contain one row per Media ID, plus `usage-paths.csv` with every bank-scoped event/branch/container/Sound path. `scope` retains the commander-specific alias; `sharing_scope` uses the common classification. Both `safe_to_replace_for_commander` and the commander-specific safety column are present. Original WEM hashes are explicitly original hashes, never replacement hashes. Czech text is empty.

Primary counts include commander-keyed speech and reachable culture/unit voice sets. Advisor/tutorial recordings are separately catalogued in `battle-advice-global-reference.csv`; they are not counted as the commander speaking. A nonzero PCM peak is not, by itself, proof of intelligible words: unresolved ASR stays uncertain. Silent WEMs require zero decoded PCM. Null decision leaves and empty random containers have no WEM and appear in `no-audio-branches.csv`.

## Workspace and sources

Use an external private directory, referenced below as `$researchWorkspace`. Never put original PACK, BNK, WEM, WAV, localization dumps or model weights in this repository. The tools reject original-audio output inside the repo or the supplied game directory. Read only the supported canonical original SHA-256; a CN-named installed slot may already contain Czech audio and must not be treated as an original.

The reusable commands consume these private workspace files:

- `corpus/graph.json`: fresh `tools.inventory.banks` parse of wwiser XML.
- `corpus/*.bnk`, `bank-inputs.json`, `all-pack-bank-scan.json`: privately extracted banks and source hashes.
- `names.json`: numeric state ID to family-reviewed name; each candidate needs exact lowercase FNV-1 and actual group membership. The public `shared-research/state-names.json` also retains provenance. Ability/event group labels with numeric suffixes are semantic aliases, not recovered symbol names.
- `event-names.json`: numeric Event ID to name, owner, optional localization key/text and source evidence. Only accept a candidate spelling against a real Event; detect hash/owner conflicts. `localization.emote_spellings()` includes hyphen conversion and repeated-underscore collapse. The latter recovers Scipio’s `Gods, hear me - bring us victory!` event.
- `specs.json`: commander `id`, `display_name`, `actor_name`, `actor_id`, `culture_names`, `culture_ids`. The first `vo_actor` is the speaker; a repeated actor argument is a reaction target.

Current actor/culture identity, exact DB offsets, localized display names and frontend branch values are documented in `shared-research/commander-identification.json`. No filename, culture label or voice accent proves ownership.

## Reproduction

All commands below are offline. Supply local tools/models separately; `requirements-research.txt` pins the optional ASR environment, while installers keep their existing dependencies.

```powershell
python -B -m tools.inventory.research --workspace $researchWorkspace scan --game-data $gameData
python -B $wwiser -d xml -dn "$researchWorkspace/corpus/banks" "$researchWorkspace/corpus/*.bnk"
python -B -m tools.inventory.banks --xml "$researchWorkspace/corpus/banks.xml" --output "$researchWorkspace/corpus/graph.json"

# Prepare/review names.json, event-names.json and specs.json before enumeration.
python -B -m tools.inventory.research --workspace $researchWorkspace enumerate
python -B -m tools.inventory.research --workspace $researchWorkspace audit
python -B -m tools.inventory.research --workspace $researchWorkspace decode --pack $canonicalOriginal --canonical-sha256 $canonicalHash --decoder $vgmstream --game-directory $gameDirectory
python -B -m tools.inventory.research --workspace $researchWorkspace jobs

& $localSttPython -B -m tools.inventory.local_stt --jobs "$researchWorkspace/stt-jobs.json" --model-directory $localModelDirectory --model-label small.en --output "$researchWorkspace/stt-small.en.json"

python -B -m tools.inventory.research_export --workspace $researchWorkspace --output-root data/commanders --profiles data/commanders/shared-research/event-profiles.json --commander leonidas --commander scipio-africanus
python -B -m tools.inventory.crosscheck --workspace $researchWorkspace --commander-root data/commanders --left leonidas --right scipio-africanus --reference hannibal --reference-audio-audit "$researchWorkspace/reference-hannibal/original-audio-audit.json" --output data/commanders/shared-research --stem leonidas-scipio-crosscheck
python -B -m tools.inventory.research_report data/commanders/leonidas/research data/commanders/scipio-africanus/research

python -B -m tools.mod --commander leonidas validate
python -B -m tools.mod --commander scipio-africanus validate
python -B -m unittest discover -s tests -v
python -B -m tools.validation.repository
```

Adding commanders to an existing workspace must not rewrite earlier results. Append their specs, then limit every step with the global `--commander` option; `audit` merges the selected entries into `completeness.json`. `emote-events` adds only chat-tag spellings whose exact FNV-1 equals a real bank Event ID (typographic apostrophes such as U+2019 are dropped, e.g. Spartacus’s `freedom_doesnt_come_without_a_fight` quote) and refuses owner/key conflicts. `jobs --pending-model` omits recordings already transcribed by that model, so new result files contain only new PCM keys:

```powershell
python -B -m tools.inventory.research --workspace $researchWorkspace emote-events --localization "$gameData/local_en.pack.orig"
python -B -m tools.inventory.research --workspace $researchWorkspace --commander spartacus --commander germanicus enumerate
python -B -m tools.inventory.research --workspace $researchWorkspace --commander spartacus --commander germanicus audit
python -B -m tools.inventory.research --workspace $researchWorkspace --commander spartacus --commander germanicus decode --pack $canonicalOriginal --canonical-sha256 $canonicalHash --decoder $vgmstream --game-directory $gameDirectory
python -B -m tools.inventory.research --workspace $researchWorkspace --commander spartacus --commander germanicus jobs --output stt-jobs-sg-small.en.json --pending-model small.en
python -B -m tools.inventory.research --workspace $researchWorkspace --commander spartacus --commander germanicus jobs --output stt-jobs-sg-medium.en-explicit.json --pending-model medium.en --explicit-only

# One export per commander keeps duplicate references inside that commander's inventory.
python -B -m tools.inventory.research_export --workspace $researchWorkspace --output-root data/commanders --profiles data/commanders/shared-research/event-profiles.json --commander spartacus
python -B -m tools.inventory.research_export --workspace $researchWorkspace --output-root data/commanders --profiles data/commanders/shared-research/event-profiles.json --commander germanicus
python -B -m tools.inventory.crosscheck --workspace $researchWorkspace --commander-root data/commanders --left spartacus --right germanicus --reference hannibal --reference leonidas --reference scipio-africanus --reference-audio-audit "hannibal=$researchWorkspace/reference-hannibal/original-audio-audit.json" --output data/commanders/shared-research --stem spartacus-germanicus-crosscheck --duplicates-output spartacus-germanicus-duplicate-recordings.csv --shared-analysis-output ''
python -B -m tools.inventory.research_report data/commanders/spartacus/research data/commanders/germanicus/research --integrity-audit spartacus-germanicus-integrity-audit.json
```

Zhuge Liang was added the same way, as a single new commander. Chinese commanders name chat-tag events `Play_<ACTOR>_EMO_<kind>_<n>`, not `_emote_`. The exporter accepts both. Three of his emote kinds (`follow`, `help`, `stop`) have no chat-tag localization row, so the emote parent-pool check stopped the audit. `emote-pool-events` recovers such names. A candidate `<stem><kind>_<n>` is accepted only when its exact FNV-1 equals an unnamed Event that plays a Sound in the commander's own emote pool, and the stem comes from that commander's localized emote Events. A hash anywhere else in the bank is ignored. Without `--right`, the crosscheck compares one new inventory with every reference:

```powershell
python -B -m tools.inventory.research --workspace $researchWorkspace --commander zhuge-liang enumerate
python -B -m tools.inventory.research --workspace $researchWorkspace --commander zhuge-liang emote-pool-events --kinds follow,help,stop
python -B -m tools.inventory.research --workspace $researchWorkspace --commander zhuge-liang enumerate
python -B -m tools.inventory.research --workspace $researchWorkspace --commander zhuge-liang audit
python -B -m tools.inventory.research --workspace $researchWorkspace --commander zhuge-liang decode --pack $canonicalOriginal --canonical-sha256 $canonicalHash --decoder $vgmstream --game-directory $gameDirectory
python -B -m tools.inventory.research_export --workspace $researchWorkspace --output-root data/commanders --profiles data/commanders/shared-research/event-profiles.json --commander zhuge-liang
python -B -m tools.inventory.crosscheck --workspace $researchWorkspace --commander-root data/commanders --left zhuge-liang --reference hannibal --reference leonidas --reference scipio-africanus --reference spartacus --reference germanicus --reference-audio-audit "hannibal=$researchWorkspace/reference-hannibal/original-audio-audit.json" --output data/commanders/shared-research --stem zhuge-liang-crosscheck --duplicates-output zhuge-liang-duplicate-recordings.csv --shared-analysis-output ''
python -B -m tools.inventory.research_report data/commanders/zhuge-liang/research --integrity-audit zhuge-liang-integrity-audit.json
```

Miltiades (`gre_miltiades`, `Commander_Miltiades`, Greek) and Julius Caesar (`rom_caesar`, `Commander_Caesar`, Roman) were added together the same way, without `emote-pool-events` (their emote pools matched the chat-tag events), and compared with the crosscheck `--left miltiades --right julius-caesar` against all six earlier inventories (`miltiades-julius-caesar-crosscheck`). Three explicit Miltiades charge lines are the same Media IDs as Leonidas's and stay `CULTURE_SHARED`. Caesar's third ability voice state `599090551` has no recoverable name and stays numeric. Disputed wording was resolved by `asr-alternative-*-mc*.json` (medium.en/small.en, 0.5 s analysis-only leading silence, beam 10) and sibling lines of the same state; these are recorded as context corrections, never as listening.

Hasdrubal (`car_hasdrubal`, `Commander_Hasdrubal`, Carthaginian), Alexander the Great (`gre_alexander`, `Commander_Alexander`, Greek; folder from the display name) and Cynane (`gre_cynane`, `Commander_Cynane`, Greek) were added together. `--right` is repeatable, so one crosscheck compares all three with each other and with the eight earlier inventories (`hasdrubal-alexander-cynane-crosscheck`): no shared ID is safe on either side, and the only Hannibal/Hasdrubal recording duplicate is digital silence. Hasdrubal's emote pool held two Events without a chat-tag row, second recordings of lines whose localization key contains punctuation (`listen_…_and_run`, `save_time:_surrender_now`). `emote-pool-events` only tries `<stem><kind>_<n>`, so the names `Play_car_hasdrubal_emote_intimidate_listen___and_run` (U+2026 → `_`) and `…_save_time_surrender_now` (`:` dropped) were verified by exact FNV-1 against the two unnamed Events inside his own pool, with local ASR agreeing with the paired chat text, and recorded in the private `event-names.json` with that provenance. Hasdrubal also has 13 commander-specific silent placeholders. Wording was resolved with the alternative ASR (`asr-alternative-*-hac*.json`), analysis-only forced-choice scoring of meaningful candidates (`forced-choice-hac*.json`), the exact second `vo_actor` and the shared order templates (Hannibal's runtime-approved Carthaginian lines for Hasdrubal, Leonidas/Miltiades/Cynane for the Greek pair). Three recordings stay `NEEDS_MANUAL_TRANSCRIPTION`.

`event-profiles.json` lists each commander’s own ability states (from `arena_commanders_to_com_abilities`) and may set `pilot_mix`, which selects the battle pilot round-robin across battle events, aggressive and standard orders, abilities, emotes and results instead of the legacy priority order. Spartacus, Germanicus and Zhuge Liang use it; Leonidas and Scipio keep the published selection.

Regenerating the published Leonidas/Scipio research from the current workspace reproduces every commander row, safety flag and TTS plan byte for byte. Only their generic `battle-advice-global-reference.csv` would gain medium.en hypotheses for five Germanicus tutorial recordings (catalogued in every inventory as advisor references); those published files were intentionally left unchanged.

The crosscheck CSV has one column per inventory plus `safe` (each inventory’s own flag). Every pair is reported as `NO_OVERLAP`, `SHARED_NOT_SAFE` or `CONFLICT`; any shared ID that either side marks safe is a conflict. Commander-owned tutorial Events (Germanicus’s `Play_Germanicus_Tutorial_VO_Request_0X`, literal in the tutorial scripts) are category `TUTORIAL`, not generic advice.

For the current analysis, base.en and small.en process the full distinct-PCM corpus; medium.en covers commander-specific performances and selected uncertainty. Each run has no prompt/hotwords and records its settings. Shards use separate output files (`--shard 0/2` etc.); the exporter merges their evidence. Alternative onset/beam analyses are kept separately and never counted as independent models. `--leading-silence` only prepends zeros to the in-memory ASR input; original WAVs remain immutable.

Exact original hash matches can reuse prior local evidence, with provenance in `previous-transcripts.json`. Context corrections belong in private `transcript-corrections.json`, with text, confidence and evidence; the corresponding public metadata is in `shared-research/transcript-corrections.json`. Raw model output remains visible. Exact PCM duplicates can inherit verified wording, but equal transcripts alone cannot establish equal performance.

The original decoder cache checks canonical WEM identity, decoder hash, PCM hash, rate, channels and sample count. A partial unproven decode cache stops for separate verification rather than silently trusting a WAV with the right length.

## Completeness and safety

The audit compares forward event traversal, independently built Sound-to-root reverse links, a separate iterative commander-branch descent, and the complete parent emote pools. The pool check catches playable ordinary events whose localization spelling was missed. Every Sound source, HIRC ID and decision key/target is checked against raw BNK offsets. FX/state objects can share IDs in separate namespaces; playback objects cannot.

All bank Sound references participate, including non-voice banks and unreachable Sounds. Missing roots, foreign owners or unknown scope prevent `YES`. Two commanders sharing one Media ID remain unsafe even when both belong to the same culture. Identical recordings under different Media IDs are reported separately; changing one ID does not automatically change the other.

The public source audit records whole-original and bank/tool/model hashes, parser status and the installation-wide bank scan. Human listening and game runtime remain `NOT_RUN`. No paid API, TTS, game/launcher run, installation, build or publication is part of this workflow.
