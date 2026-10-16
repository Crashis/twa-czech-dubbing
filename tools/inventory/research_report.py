"""Readable report from research CSVs; never promotes listening or runtime QA."""
import argparse
from collections import Counter
import json
from pathlib import Path

from tools.inventory.research_metadata import read_csv


def report(folder):
    manifest = json.loads((folder/'manifest-draft.json').read_text(encoding='utf-8'))
    complete = json.loads((folder/'completeness.json').read_text(encoding='utf-8'))
    rows = read_csv(folder/'voice-lines.csv')
    specific = [r for r in rows if r['sharing_scope'] == 'COMMANDER_SPECIFIC' and r['silent_placeholder'] == 'NO']
    review = [r for r in specific if r['transcript_review_required'] == 'YES']
    empty = read_csv(folder/'no-audio-branches.csv')
    shared = manifest['sharing_counts']
    cat = manifest['category_counts']
    all_conf, specific_conf = manifest['transcript_counts_all'], manifest['transcript_counts_commander_specific']
    ready = manifest['ready_for_translation_tts'] and not manifest['missing_transcripts_all']
    lines = [f"# {manifest['display_name']} — inventory report", '',
             'Structural scope: commander voice, culture/unit voice contexts reachable in the supported corpus, and explicit commander-keyed branches even when their runtime trigger is unknown. Generic advisor/tutorial references are a separate audit table and are not attributed to this commander.', '',
             '| Metric | Count |', '|---|---:|',
             f"| Total relevant Media IDs | {len(rows)} |",
             f"| Spoken/non-silent decoded voice candidates | {manifest['spoken_media_ids']} |",
             f"| Silent placeholder WEMs | {manifest['silent_placeholders']} |",
             f"| Explicit commander speaker, including shared IDs | {manifest['explicit_commander_speaker_media_ids']} |",
             f"| Commander-specific | {manifest['commander_specific_media_ids']} |",
             f"| Culture shared | {shared.get('CULTURE_SHARED', 0)} |",
             f"| Unit type shared | {shared.get('UNIT_TYPE_SHARED', 0)} |",
             f"| Global shared | {shared.get('GLOBAL_SHARED', 0)} |",
             f"| Unknown shared | {shared.get('UNKNOWN_SHARED_SCOPE', 0)} |",
             f"| Safe to replace, Media ID ownership only | {manifest['safe_replacement_media_ids']} |",
             f"| Not safe/shared | {len(rows)-manifest['safe_replacement_media_ids']} |",
             f"| Frontend spoken, commander-specific | {manifest['frontend_count']} |",
             f"| Battle spoken, commander-specific | {manifest['battle_count']} |",
             f"| Orders, commander-specific | {cat.get('ORDER', 0)+cat.get('ORDER_ACK', 0)} |",
             f"| Abilities, commander-specific | {cat.get('ABILITY', 0)} |",
             f"| Emotes, commander-specific | {cat.get('EMOTE', 0)} |",
             f"| Other, commander-specific | {len(specific)-manifest['frontend_count']-cat.get('ORDER',0)-cat.get('ORDER_ACK',0)-cat.get('ABILITY',0)-cat.get('EMOTE',0)} |",
             f"| Exact recording duplicate groups | {manifest['duplicate_groups']} |",
             f"| Pilot menu | {manifest['pilot_menu']} |", f"| Pilot battle | {manifest['pilot_battle']} |", '',
             '| Transcript confidence | All relevant spoken | Commander-specific spoken |', '|---|---:|---:|']
    lines.extend(f"| {c} | {all_conf.get(c,0)} | {specific_conf.get(c,0)} |" for c in ['CONFIRMED','HIGH','MEDIUM','LOW','UNKNOWN'])
    lines += ['', f"READY FOR TRANSLATION/TTS: **{'YES' if ready else 'NO'}**.", '',
              f"Commander-specific wording review items: **{len(review)}**. Missing transcripts across the primary inventory: **{manifest['missing_transcripts_all']}**.", '',
              'Ownership safety does not approve a transcript, translation or voice performance. MEDIUM/LOW/UNKNOWN text must be resolved before generating the affected performance. Czech text remains empty. Delivery/model fields are proposals using the project’s historical routing, with no API availability or generation claim.', '',
              'Completeness evidence:', '',
              f"- Forward DialogueEvent/Event traversal: {complete['forward_relevant_media']} Media IDs.",
              f"- Independent Sound-to-root reverse traversal: {complete['reverse_relevant_media']} Media IDs; difference: {complete['forward_reverse_symmetric_difference']}.",
              f"- Explicit speaker branches / named ordinary events: {complete['forward_explicit_speaker_media']} forward, {complete['reverse_explicit_speaker_media']} reverse, {complete['independent_branch_enumeration_media']} independently enumerated.",
              f"- Emote parent-pool candidates: {complete['emote_parent_pool_media']}; mapped Event media: {complete['emote_named_event_media']}; difference: {complete['emote_pool_symmetric_difference']}.",
              f"- Raw BNK verification: {complete['raw_sound_sources_checked']} Sound source fields; HIRC IDs and decision keys/targets also match original bytes.",
              f"- Entire live installation scan: {complete['pack_indexes_checked']} PACK indexes, RSA validated; {complete['parsed_bank_count']} unique BNKs in {complete['pack_bank_sources']} PACKs. All {complete['parsed_voicebank_count']} voice banks and the remaining banks participate in the Sound usage audit. Alias bank payload hashes are retained in the source audit.",
              f"- Every YES row has matching forward/reverse usage roots and no unrooted or foreign Sound use. Relevant unresolved references: {complete['unresolved_relevant_sound_references']}.", '',
              f"No-audio commander branches: **{len(empty)}**, listed in no-audio-branches.csv. Null leaves and empty random containers have no Media ID and are separate from silent WEM placeholders.", '',
              'Frontend containers:', '', '| Event ID | Container | Variants | Trigger |', '|---|---|---:|---|']
    groups = {}
    for row in specific:
        if row['category'] == 'FRONTEND':
            groups[row['event_id'],row['container_id']] = row
    for (eid, cid), row in groups.items():
        lines.append(f"| {eid} | {cid} | {row['random_variant_count']} | {row['trigger']} |")
    lines += ['', 'The quote event’s exact runtime trigger remains unknown. Unknown trigger does not remove a structurally present random variant.', '',
              'Transcript evidence consists of local unprompted faster-whisper hypotheses, exact localization/Event hashes, exact PCM duplicate transfers and explicitly documented context corrections. Agreement is not human listening. Latin or proper-name spelling is retained when supported by localization/actor evidence. Raw alternatives remain in the CSV.', '',
              'Exact duplicate groups use decoded PCM plus format/sample count. Original WEM hashes additionally distinguish byte-identical payloads from different encodes/headers. Equal text alone never merges performances. Cross-inventory groups resolve through the shared research duplicate table.', '',
              'Original English WEMs and direct PCM16 WAVs are held only in the private archive. All original rate/channel/sample counts match direct decode. Original signal peaks and clipping flags are descriptive; no original audio was altered. Float/ww2ogg replacement QC does not apply because this phase creates no replacement audio.', '',
              'Human listening: **NOT RUN**. Game/launcher/runtime test: **NOT RUN**. Paid API/TTS calls: **0**. Installer release manifest: **not created**.', '',
              'The [integrity audit](../../shared-research/integrity-audit.json) compares source PACK hashes and all Hannibal files with the initial baseline. It also records externally running game/launcher processes and installation timestamp changes; this task did not start or stop those processes.', '',
              'Open commander-specific wording review (audio paths are relative to the private archive root):', '',
              '| Media ID | Candidate text | Confidence / resolution | Archive WAV reference |', '|---|---|---|---|']
    for row in review:
        resolution = ' / NEEDS_MANUAL_TRANSCRIPTION' if row['transcript_resolution'] == 'NEEDS_MANUAL_TRANSCRIPTION' else ''
        lines.append(f"| {row['media_id']} | {row['english_text'].replace('|','/')} | {row['transcript_confidence']}{resolution} | `{row['archive_wav_reference']}` |")
    if not review:
        lines.append('| none | | | |')
    lines += ['', 'Corpus voice Sounds without a playback root:', '']
    for orphan in complete.get('all_voice_orphans', []):
        lines.append(f"- {orphan['bank']}: Sound {orphan['sound_id']}, source {orphan['media_id']}; sibling owners: {', '.join(orphan['sibling_owners']) or 'unknown'}. No playable commander event is inferred from this sibling context.")
    lines += ['', 'See transcript-review.csv for all shared and commander-specific uncertainty. Full references are preserved in usage-paths.csv. No runtime observation or human review is marked PASS.', '']
    (folder/'inventory-report.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folders', nargs='+')
    args = parser.parse_args()
    for folder in args.folders:
        report(Path(folder))


if __name__ == '__main__':
    main()
