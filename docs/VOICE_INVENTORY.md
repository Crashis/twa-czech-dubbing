# Offline voice inventory

Research data lives under `data/commanders/<id>/research/`. It is deliberately excluded from installer discovery, which only reads production `*/manifest.json`. `manifest-draft.json` has `status: research_ready`, `release_ready: false`, an explicit inventory status and separate translation/TTS readiness. A metadata validation PASS does not approve uncertain wording, a performance or a release.

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

For the current analysis, base.en and small.en process the full distinct-PCM corpus; medium.en covers commander-specific performances and selected uncertainty. Each run has no prompt/hotwords and records its settings. Shards use separate output files (`--shard 0/2` etc.); the exporter merges their evidence. Alternative onset/beam analyses are kept separately and never counted as independent models. `--leading-silence` only prepends zeros to the in-memory ASR input; original WAVs remain immutable.

Exact original hash matches can reuse prior local evidence, with provenance in `previous-transcripts.json`. Context corrections belong in private `transcript-corrections.json`, with text, confidence and evidence; the corresponding public metadata is in `shared-research/transcript-corrections.json`. Raw model output remains visible. Exact PCM duplicates can inherit verified wording, but equal transcripts alone cannot establish equal performance.

The original decoder cache checks canonical WEM identity, decoder hash, PCM hash, rate, channels and sample count. A partial unproven decode cache stops for separate verification rather than silently trusting a WAV with the right length.

## Completeness and safety

The audit compares forward event traversal, independently built Sound-to-root reverse links, a separate iterative commander-branch descent, and the complete parent emote pools. The pool check catches playable ordinary events whose localization spelling was missed. Every Sound source, HIRC ID and decision key/target is checked against raw BNK offsets. FX/state objects can share IDs in separate namespaces; playback objects cannot.

All bank Sound references participate, including non-voice banks and unreachable Sounds. Missing roots, foreign owners or unknown scope prevent `YES`. Two commanders sharing one Media ID remain unsafe even when both belong to the same culture. Identical recordings under different Media IDs are reported separately; changing one ID does not automatically change the other.

The public source audit records whole-original and bank/tool/model hashes, parser status and the installation-wide bank scan. Human listening and game runtime remain `NOT_RUN`. No paid API, TTS, game/launcher run, installation, build or publication is part of this workflow.
