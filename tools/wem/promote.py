"""Promote a fully QC-passed offline commander set from work/ to schema 1.

The canonical original is read-only. A complete candidate PACK stays in work/;
no release metadata is published until its full entry diff and RSA pass.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil

from tools import mod
from tools.installer.catalog import discover
from tools.pack.reader import ArenaPack, require
from tools.resources import VERSION
from tools.wem.production import context, save


FIELDS = ('media_id', 'english', 'czech', 'category', 'trigger', 'original_duration',
          'czech_duration', 'original_size_bytes', 'model', 'delivery_tags',
          'source_batch', 'transcript_confidence', 'translation_status', 'wem_sha256',
          'tts_source_media_id', 'tts_performance_group', 'source_audio_sha256')


def run(args):
    plan, state, audit, safe = context(args)
    work = Path(args.work).resolve(strict=True)
    require(work.is_relative_to(mod.ROOT / 'work'), 'Production work must be ignored work/')
    base = Path(args.base).resolve(strict=True)
    require(not base.is_relative_to(mod.ROOT) and mod.sha256(base) == audit['canonical_pack_sha256'],
            'Unknown canonical original')
    original = ArenaPack(base)
    prior = discover()
    require(prior and all(m['base']['sha256'] == audit['canonical_pack_sha256'] for m in prior),
            'Existing production base mismatch')
    prior_ids = {r['media_id'] for m in prior for r in m['replacements']}
    require(not prior_ids.intersection(safe), 'Commander replacements overlap an existing release')
    by_target = {mid: row['tts_source_media_id'] for row in plan for mid in row['member_media_ids'].split(';')}
    require(set(by_target) == set(safe), 'TTS mapping incomplete')
    voice_plan = {r['media_id']: r for r in mod.csv_rows(
        mod.ROOT / 'data/commanders' / args.commander / 'tts-plan/voice-lines-cz.csv')}
    require(set(voice_plan) == set(safe), 'Czech voice metadata incomplete')
    wem_dir = work / 'wem'
    require({p.name for p in wem_dir.iterdir()} == {mid + '.wem' for mid in safe},
            'Working WEM set is incomplete or has extras')
    qa = {}
    specs = []
    voice_rows = []
    duration_flags = {}
    by_path = {entry.path: entry for entry in original.entries}
    for mid in sorted(safe, key=int):
        source = by_target[mid]
        old = audit['results'][mid]
        entry = by_path[old['pack_path']]
        require(entry.offset == old['pack_offset'] and entry.size == old['original_size_bytes'],
                'Canonical entry mismatch ' + mid)
        wem = wem_dir / (mid + '.wem')
        report = json.loads((work / 'qa' / mid / 'validation.json').read_text(encoding='utf-8'))
        prepared = work / 'canonical-32k' / (source + '.wav')
        preparation = json.loads((work / 'prepare-reports' / (source + '.json')).read_text(encoding='utf-8'))
        require(report['status'] == report['quality']['status'] == 'PASS'
                and report['raw_vs_padded_pcm'] == report['ww2ogg_decode'] == 'PASS'
                and report['wem_sha256'] == mod.sha256(wem)
                and wem.stat().st_size == report['size'] == entry.size
                and report['quality']['correlation'] > .95 and report['quality']['snr_db'] > 15
                and report['quality']['decoded']['samples_at_or_above_full_scale'] == 0
                and report['float_decode']['peak_linear'] < 1,
                'WEM QA/size mismatch ' + mid)
        # Verify the prepared file against its PCM ledger independently of the
        # cached WEM report; the same source may serve several target IDs.
        from tools.wem.audio import pcm16
        info, _ = pcm16(prepared)
        require(info['pcm_sha256'] == preparation['prepared']['pcm_sha256'],
                'Prepared PCM changed since QA ' + source)
        item = state['items'][source]
        row = voice_plan[mid]
        require(row['tts_source_media_id'] == source and row['tts_performance_group'] == item['tts_performance_group'],
                'Voice provenance mismatch ' + mid)
        specs.append({'media_id': mid, 'path': old['pack_path'], 'offset': entry.offset,
                      'size': entry.size, 'original_sha256': old['original_wem_sha256'],
                      'sha256': report['wem_sha256']})
        voice_rows.append({'media_id': mid, 'english': row['english_text'], 'czech': row['czech_text'],
                           'category': row['category'], 'trigger': row['trigger'],
                           'original_duration': row['original_duration'],
                           'czech_duration': report['quality']['decoded']['duration_seconds'],
                           'original_size_bytes': entry.size, 'model': item['model'],
                           'delivery_tags': item['tags'],
                           'source_batch': args.commander.upper().replace('-', '_') + '_APPROVED_TTS',
                           'transcript_confidence': row['transcript_confidence'],
                           'translation_status': 'APPROVED_TTS_OFFLINE',
                           'wem_sha256': report['wem_sha256'], 'tts_source_media_id': source,
                           'tts_performance_group': item['tts_performance_group'],
                           'source_audio_sha256': item['checksum']})
        ratio = report['quality']['decoded']['duration_seconds'] / float(row['original_duration'])
        if ratio > 1.8 or ratio < .45:
            duration_flags[mid] = round(ratio, 3)
        encoding = json.loads((work / 'encode-reports' / (mid + '.json')).read_text(encoding='utf-8'))
        raw = Path(encoding.get('search_work', work / 'encode-search' / mid)) / f"q{encoding['quality']:.4f}.wem"
        qa[mid] = report | {'encoding': {
            'quality': encoding['quality'], 'advanced_options': encoding.get('advanced_options', []),
            'trailing_margin_ms': encoding.get('trailing_margin_ms', preparation['margins_ms'][1]),
            'raw_bytes_before_padding': raw.stat().st_size, 'original_budget_bytes': entry.size,
            'duration_ratio': round(ratio, 3), 'tts_source_media_id': source,
            # Recovered lines: band-limited production reference plus the audit against the unchanged TTS.
            'preprocessing': {'band_limit_hz': encoding.get('band_limit_hz'),
                              'high_shelf_db': encoding.get('high_shelf_db', 0),
                              'approved_exception': encoding.get('approved_exception')},
            'tts_fidelity': encoding.get('tts_fidelity'),
            'tts_source': {'origin': item['origin'], 'tags': item['tags'], 'audio_sha256': item['checksum'],
                           'attempt': item.get('compact_attempt')}}}
    require(len(specs) == len(safe), 'Incomplete release replacement set')
    candidate = work / (args.commander + '-offline-candidate.pack')
    require(not candidate.exists(), 'Candidate already exists; use a fresh work directory')
    with base.open('rb') as src, candidate.open('xb') as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)
        for spec in specs:
            payload = (wem_dir / (spec['media_id'] + '.wem')).read_bytes()
            dst.seek(spec['offset'])
            require(dst.write(payload) == spec['size'], 'Short WEM write')
        dst.flush()
        os.fsync(dst.fileno())
    require(mod.sha256(base) == audit['canonical_pack_sha256'], 'Canonical source changed during build')
    modified = ArenaPack(candidate)  # mandatory RSA verification on output
    require(modified.entries == original.entries and modified.file_size == original.file_size,
            'PACK entry order, offsets or size changed')
    for name in ('header', 'dependencies_raw', 'index_raw', 'appendix'):
        require(getattr(modified, name) == getattr(original, name), 'Protected PACK bytes changed: ' + name)
    changed = set()
    with base.open('rb') as left, candidate.open('rb') as right:
        for entry in original.entries:
            left.seek(entry.offset)
            right.seek(entry.offset)
            if left.read(entry.size) != right.read(entry.size):
                changed.add(entry.path)
    require(changed == {s['path'] for s in specs}, 'Unexpected PACK entry differences')
    release_sha = mod.sha256(candidate)
    silent = sorted(r['media_id'] for r in mod.csv_rows(
        mod.ROOT / 'data/commanders' / args.commander / 'research/voice-lines.csv')
        if r['scope'] == args.commander.upper() + '_SPECIFIC' and r['silent_placeholder'] == 'YES')
    manifest = {'schema_version': 1, 'commander': args.commander, 'display_name': args.display_name,
                'runtime_slot': 'audio_cn.pack', 'expected_spoken_count': len(specs),
                'silent_placeholder_ids': silent, 'expected_replacement_count': len(specs),
                'base': {'sha256': audit['canonical_pack_sha256'], 'size': original.file_size,
                         'entry_count': len(original.entries), 'flags': original.flags,
                         'header_sha256': hashlib.sha256(original.header).hexdigest(),
                         'dependencies_sha256': hashlib.sha256(original.dependencies_raw).hexdigest(),
                         'encrypted_index_sha256': hashlib.sha256(original.index_raw).hexdigest(),
                         'appendix_sha256': hashlib.sha256(original.appendix).hexdigest()},
                'release': {'sha256': release_sha, 'changed_entries': len(changed),
                            'unchanged_entries': len(original.entries) - len(changed),
                            'runtime_test': 'PENDING HUMAN IN-GAME TEST'},
                'wem_format': prior[0]['wem_format'], 'replacements': specs,
                'id': args.commander, 'spoken_count': len(specs), 'replacement_count': len(specs),
                'replacement_directory': f'replacements/{args.commander}/wem',
                'supported_base_pack_hash': audit['canonical_pack_sha256'],
                'required_runtime_pack': 'audio_cn.pack', 'version': VERSION}
    destination = mod.ROOT / 'replacements' / args.commander / 'wem'
    folder = mod.ROOT / 'data/commanders' / args.commander
    require(not destination.exists() and not any((folder / n).exists() for n in
            ('manifest.json', 'voice-lines.csv', 'media-inventory.csv', 'audio-qa.json')),
            'Production output already exists')
    destination.mkdir(parents=True)
    for spec in specs:
        shutil.copyfile(wem_dir / (spec['media_id'] + '.wem'), destination / (spec['media_id'] + '.wem'))
    with (folder / 'voice-lines.csv').open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, FIELDS)
        writer.writeheader()
        writer.writerows(voice_rows)
    shutil.copyfile(folder / 'research/voice-lines.csv', folder / 'media-inventory.csv')
    save(folder / 'manifest.json', manifest)
    save(folder / 'audio-qa.json', {'status': 'PASS', 'replacement_count': len(qa),
         'source_performances': len(plan), 'duration_ratio_review_flags': duration_flags,
         'human_listening_of_final_wems': 'NOT_PERFORMED', 'game_runtime_test': 'NOT_PERFORMED',
         'results': qa})
    checked = mod.validate_data(mod.load_manifest(args.commander))
    require(checked['status'] == 'PASS', 'Promoted production set did not validate')
    return {'status': 'PASS', 'commander': args.commander, 'replacements': len(specs),
            'source_performances': len(plan), 'candidate_sha256': release_sha,
            'changed_entries': len(changed), 'RSA': 'PASS', 'duration_ratio_review_flags': duration_flags}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commander', required=True)
    parser.add_argument('--display-name', required=True)
    parser.add_argument('--routing', required=True)
    parser.add_argument('--state', required=True)
    parser.add_argument('--base', required=True)
    parser.add_argument('--work', required=True)
    print(json.dumps(run(parser.parse_args()), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
