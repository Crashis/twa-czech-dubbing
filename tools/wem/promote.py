"""Promote a fully QC-passed offline commander set from work/ to schema 1.

The canonical original is read-only. A complete candidate PACK stays in work/;
no release metadata is published until its full entry diff and RSA pass.
--activate later turns a validated staged set into an installer commander.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil

from tools import mod
from tools.installer.catalog import discover, discover_shared
from tools.pack.reader import ArenaPack, require
from tools.resources import VERSION
from tools.wem.production import context, save


MANIFEST = 'manifest.json'
# A fully validated production set that the installer must not discover yet
# (catalog.discover() reads only */manifest.json). Integration renames it.
STAGED = 'manifest.staged.json'

FIELDS = ('media_id', 'english', 'czech', 'category', 'trigger', 'original_duration',
          'czech_duration', 'original_size_bytes', 'model', 'delivery_tags',
          'source_batch', 'transcript_confidence', 'translation_status', 'wem_sha256',
          'tts_source_media_id', 'tts_performance_group', 'source_audio_sha256')


def load_staged(commander):
    """Load a staged schema-1 manifest with the same installer alias checks as mod.load_manifest."""
    folder = mod.ROOT / 'data/commanders' / commander
    require(not (folder / MANIFEST).exists(), 'Staged and installer manifests both exist for ' + commander)
    value = json.loads((folder / STAGED).read_text(encoding='utf-8'))
    require(value['schema_version'] == 1 and value['commander'] == value['id'] == commander
            and value['runtime_slot'] == value['required_runtime_pack'] == 'audio_cn.pack'
            and value['spoken_count'] == value['expected_spoken_count']
            and value['replacement_count'] == value['expected_replacement_count']
            and value['supported_base_pack_hash'] == value['base']['sha256']
            and value['replacement_directory'] == f'replacements/{commander}/wem', 'Staged manifest metadata mismatch')
    return value


def next_display_order(prior):
    # A newly integrated commander is appended after every existing installer checkbox.
    return max((m['display_order'] for m in prior), default=0) + 1


def activate(commander):
    """Integrate a staged set: manifest.staged.json -> manifest.json, never both afterwards.

    Payloads, inventory and QA stay byte-identical; only the release version and
    display order change. Joint descriptors are created afterwards by tools.installer.joint.
    """
    folder = mod.ROOT / 'data/commanders' / commander
    require((folder / STAGED).is_file(), 'No staged production set for ' + commander)
    staged = load_staged(commander)
    prior = discover()
    require(commander not in {m['commander'] for m in prior}, 'Commander is already an installer commander')
    require(all(m['base'] == staged['base'] and m['wem_format'] == staged['wem_format'] for m in prior),
            'Staged commander base/format differs from production')
    taken = {s['media_id'] for m in prior for s in m['replacements']}
    require(not taken.intersection(s['media_id'] for s in staged['replacements']),
            'Staged commander replacements overlap an existing release')
    require(mod.validate_data(staged)['status'] == 'PASS', 'Staged production set did not validate')
    value = dict(staged, version=VERSION, display_order=next_display_order(prior))
    target = folder / MANIFEST
    with target.open('x', encoding='utf-8') as stream:  # never overwrite an installer manifest
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    try:
        manifest = mod.load_manifest(commander)
        require(manifest == value and mod.validate_data(manifest)['status'] == 'PASS',
                'Activated manifest did not validate')
        require(commander in {m['commander'] for m in discover()}, 'Installer does not discover the activated commander')
    except BaseException:
        target.unlink()
        raise
    (folder / STAGED).unlink()
    return {'status': 'PASS', 'commander': commander, 'activated': True, 'installer_discoverable': True,
            'staged_manifest_removed': not (folder / STAGED).exists(), 'version': VERSION,
            'display_order': value['display_order'], 'replacements': len(value['replacements']),
            'release_sha256': value['release']['sha256'],
            'installer_order': [m['commander'] for m in discover()]}


UNIT = 'unit-voices'
UNIT_DISPLAY = {'display_name': 'Univerzální hlášky', 'description': 'Český dabing obecných hlášek jednotek'}
UNIT_VOICE_FIELDS = ('media_id', 'phrase_id', 'english', 'czech', 'canonical_plan_czech', 'canonical_text', 'tts_input_text',
                     'applied_pronunciation_overrides', 'content_type', 'voice_group', 'voice_name', 'voice_id',
                     'slot_gender', 'vo_cultures', 'vo_actors', 'vo_unit_types', 'reached_via_wildcard',
                     'original_duration', 'czech_duration', 'original_size_bytes', 'model', 'delivery_style',
                     'delivery_tags', 'source_batch', 'transcript_confidence', 'translation_status', 'wem_sha256',
                     'tts_source_media_id', 'tts_performance_group', 'source_audio_sha256')


def state_members(group, performance):
    """Media IDs of one deferred performance, from the unit context's voice-group summary."""
    return group['deferred_members'][performance]


def load_unit(staged):
    """The unit-voice manifest: installer manifest.json, or the staged copy the installer cannot discover."""
    if not staged:
        return mod.load_manifest(UNIT)
    folder = mod.ROOT / 'data' / mod.SHARED / UNIT
    require(not (folder / MANIFEST).exists(), 'Staged and installer manifests both exist for ' + UNIT)
    value = json.loads((folder / STAGED).read_text(encoding='utf-8'))
    require(value['schema_version'] == 1 and mod.is_shared(value) and value['commander'] == value['id'] == UNIT,
            'Staged unit manifest metadata mismatch')
    return value


def activate_unit():
    """Integrate a validated staged unit set as an installer module (an explicit human decision)."""
    folder = mod.ROOT / 'data' / mod.SHARED / UNIT
    staged = load_unit(True)
    prior = discover()
    require(all(m['base'] == staged['base'] and m['wem_format'] == staged['wem_format'] for m in prior),
            'Staged module base/format differs from production')
    require(mod.validate_data(staged)['status'] == 'PASS', 'Staged unit voice set did not validate')
    with (folder / MANIFEST).open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(dict(staged, version=VERSION), ensure_ascii=False, indent=2) + '\n')
    try:
        require(mod.validate_data(mod.load_manifest(UNIT))['status'] == 'PASS'
                and UNIT in {m['commander'] for m in discover_shared()}, 'Activated unit module did not validate')
    except BaseException:
        (folder / MANIFEST).unlink()
        raise
    (folder / STAGED).unlink()
    return {'status': 'PASS', 'module': UNIT, 'activated': True, 'installer_discoverable': True,
            'replacements': len(staged['replacements']), 'deferred_media_ids': len(staged['deferred_media_ids']),
            'next_step': 'tools.installer.joint for every commander combination + unit-voices'}


def commander_specific_ids():
    """Every Media ID any commander owns, in production and in prepared research inventories."""
    owned = set()
    for path in sorted((mod.ROOT / 'data/commanders').glob('*/research/voice-lines.csv')) + \
            sorted((mod.ROOT / 'data/commanders').glob('*/media-inventory.csv')):
        name = path.parts[-3] if path.parent.name == 'research' else path.parts[-2]
        owned |= {r['media_id'] for r in mod.csv_rows(path) if r['scope'] == name.upper() + '_SPECIFIC'}
    return owned


def candidate_pack(base, original, specs, wem_dir, candidate, canonical_sha):
    """Copy the canonical original, overwrite exact-size payloads, prove RSA/structure/changed set."""
    with base.open('rb') as src, candidate.open('xb') as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)
        for spec in specs:
            payload = (wem_dir / (spec['media_id'] + '.wem')).read_bytes()
            dst.seek(spec['offset'])
            require(dst.write(payload) == spec['size'], 'Short WEM write')
        dst.flush()
        os.fsync(dst.fileno())
    require(mod.sha256(base) == canonical_sha, 'Canonical source changed during build')
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
    return changed


def run_unit(args):
    """Promote the shared unit voices: one module, male and female payloads together, never a commander."""
    from tools.tts import units
    from tools.wem.audio import pcm16
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
    media = {r['media_id']: r for r in mod.csv_rows(mod.ROOT / units.MEDIA_PATH)}
    excluded = {r['media_id'] for r in mod.csv_rows(mod.ROOT / units.EXCLUDED_PATH)}
    owned = commander_specific_ids() | {s['media_id'] for m in prior for s in m['replacements']} | {
        mid for m in prior for mid in m['silent_placeholder_ids']}
    require(not owned & set(media) and not excluded & set(safe), 'Unit voices overlap a commander or excluded Media ID')
    reasons = {m: 'PRONUNCIATION_REVIEW: ' + s for g in state['voice_groups'].values() for s in g['deferred']
               for m in state_members(g, s)}
    require(set(safe) | set(reasons) == set(media) and not set(safe) & set(reasons), 'Unit scope incomplete')
    by_target = {mid: row['tts_source_media_id'] for row in plan for mid in row['member_media_ids'].split(';')}
    wem_dir = work / 'wem'
    present = {p.name for p in wem_dir.iterdir()}
    require(present <= {mid + '.wem' for mid in safe}, 'Working WEM set has extras')
    # A reachable ID without a valid exact-size WEM keeps its original audio; only a staged set may record it.
    blocked = sorted((m for m in safe if m + '.wem' not in present), key=int)
    require(args.staged or not blocked, f'{len(blocked)} Media IDs have no valid exact-size WEM; use --staged')
    reasons.update({m: 'NO_EXACT_SIZE_WEM: ' + by_target[m] for m in blocked})
    deferred = sorted(reasons, key=int)
    by_path = {entry.path: entry for entry in original.entries}
    specs, voice_rows, qa, duration_flags = [], [], {}, {}
    for mid in sorted(set(safe) - set(blocked), key=int):
        source = by_target[mid]
        old = audit['results'][mid]
        entry = by_path[old['pack_path']]
        require(entry.offset == old['pack_offset'] and entry.size == old['original_size_bytes'],
                'Canonical entry mismatch ' + mid)
        wem = wem_dir / (mid + '.wem')
        report = json.loads((work / 'qa' / mid / 'validation.json').read_text(encoding='utf-8'))
        preparation = json.loads((work / 'prepare-reports' / (source + '.json')).read_text(encoding='utf-8'))
        require(report['status'] == report['quality']['status'] == 'PASS'
                and report['raw_vs_padded_pcm'] == report['ww2ogg_decode'] == 'PASS'
                and report['wem_sha256'] == mod.sha256(wem) and wem.stat().st_size == report['size'] == entry.size
                and report['quality']['correlation'] > .95 and report['quality']['snr_db'] > 15
                and report['quality']['decoded']['samples_at_or_above_full_scale'] == 0
                and report['float_decode']['peak_linear'] < 1, 'WEM QA/size mismatch ' + mid)
        require(pcm16(work / 'canonical-32k' / (source + '.wav'))[0]['pcm_sha256'] == preparation['prepared']['pcm_sha256'],
                'Prepared PCM changed since QA ' + source)
        item, row = state['items'][source], media[mid]
        group = state['voice_groups'][item['voice_group']]
        specs.append({'media_id': mid, 'path': old['pack_path'], 'offset': entry.offset, 'size': entry.size,
                      'original_sha256': old['original_wem_sha256'], 'sha256': report['wem_sha256']})
        ratio = report['quality']['decoded']['duration_seconds'] / float(row['original_duration'])
        if ratio > 1.8 or ratio < .45:
            duration_flags[mid] = round(ratio, 3)
        voice_rows.append({'media_id': mid, 'phrase_id': row['phrase_id'], 'english': row['english_transcript'],
                           'czech': item['czech_text'], 'canonical_plan_czech': row['czech_for_slot'],
                           'canonical_text': item['canonical_text'],
                           'tts_input_text': item['tts_input_text'],
                           'applied_pronunciation_overrides': json.dumps(item['applied_pronunciation_overrides'],
                                                                         ensure_ascii=False),
                           'content_type': row['content_type'], 'voice_group': item['voice_group'],
                           'voice_name': group['voice_name'], 'voice_id': group['voice_id'],
                           'slot_gender': row['voice_gender'], 'vo_cultures': row['vo_cultures'],
                           'vo_actors': row['vo_actors'], 'vo_unit_types': row['vo_unit_types'],
                           'reached_via_wildcard': row['reached_via_wildcard'],
                           'original_duration': row['original_duration'],
                           'czech_duration': report['quality']['decoded']['duration_seconds'],
                           'original_size_bytes': entry.size, 'model': item['model'],
                           'delivery_style': item['delivery_style'], 'delivery_tags': item['tags'],
                           'source_batch': 'UNIT_VOICES_APPROVED_TTS', 'transcript_confidence': row['transcript_confidence'],
                           'translation_status': item.get('translation_status', 'APPROVED_TTS_OFFLINE'),
                           'wem_sha256': report['wem_sha256'],
                           'tts_source_media_id': source, 'tts_performance_group': item['tts_performance_group'],
                           'source_audio_sha256': item['checksum']})
        encoding = json.loads((work / 'encode-reports' / (mid + '.json')).read_text(encoding='utf-8'))
        raw = Path(encoding.get('search_work', work / 'encode-search' / mid)) / f"q{encoding['quality']:.4f}.wem"
        qa[mid] = report | {'encoding': {
            'quality': encoding['quality'], 'advanced_options': encoding.get('advanced_options', []),
            'profile': encoding.get('profile', 'standard'),
            'trailing_margin_ms': encoding.get('trailing_margin_ms', preparation['margins_ms'][1]),
            'raw_bytes_before_padding': raw.stat().st_size if raw.is_file() else None,
            'original_budget_bytes': entry.size, 'duration_ratio': round(ratio, 3), 'tts_source_media_id': source,
            'preprocessing': {'band_limit_hz': encoding.get('band_limit_hz'),
                              'high_shelf_db': encoding.get('high_shelf_db', 0)},
            'tts_fidelity': encoding.get('tts_fidelity'),
            'tts_source': {'origin': item['origin'], 'tags': item['tags'], 'audio_sha256': item['checksum'],
                           'voice_group': item['voice_group'], 'attempt': item.get('compact_attempt')}}}
    candidate = work / (UNIT + '-offline-candidate.pack')
    require(not candidate.exists(), 'Candidate already exists; use a fresh work directory')
    changed = candidate_pack(base, original, specs, wem_dir, candidate, audit['canonical_pack_sha256'])
    release_sha = mod.sha256(candidate)
    groups = {g: {'voice_name': v['voice_name'], 'voice_id': v['voice_id'],
                  'media_ids': sum(r['voice_group'] == g for r in voice_rows),
                  'performances': len({i['tts_performance_group'] for i in state['items'].values() if i['voice_group'] == g}),
                  'compact_sources': sorted(k for k, i in state['items'].items()
                                            if i['voice_group'] == g and i.get('origin') == 'compact_regeneration'),
                  'byte_budget_fallbacks': {mid: i['czech_text'] for i in state['items'].values() if i['voice_group'] == g
                                            and i.get('translation_status') == 'BYTE_BUDGET_COMPACT_FALLBACK'
                                            for mid in i['member_media_ids']},
                  'deferred_performances': v['deferred']} for g, v in sorted(state['voice_groups'].items())}
    manifest = {'schema_version': 1, 'module_type': mod.SHARED, 'commander': UNIT, **UNIT_DISPLAY,
                'runtime_slot': 'audio_cn.pack', 'expected_spoken_count': len(specs), 'silent_placeholder_ids': [],
                'expected_replacement_count': len(specs),
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
                'id': UNIT, 'spoken_count': len(specs), 'replacement_count': len(specs),
                'replacement_directory': f'replacements/{UNIT}/wem',
                'supported_base_pack_hash': audit['canonical_pack_sha256'],
                'required_runtime_pack': 'audio_cn.pack', 'version': VERSION, 'display_order': 1,
                'voice_groups': groups, 'deferred_media_ids': deferred,
                # Reachable IDs that keep their original audio, each with the reason (review or WEM budget).
                'deferred_reason': {m: reasons[m] for m in deferred},
                'source_plan': units.PLAN_PATH.as_posix()}
    destination = mod.ROOT / manifest['replacement_directory']
    folder = mod.ROOT / 'data' / mod.SHARED / UNIT
    require(not destination.exists() and not folder.exists(), 'Production output already exists')
    destination.mkdir(parents=True)
    folder.mkdir(parents=True)
    for spec in specs:
        shutil.copyfile(wem_dir / (spec['media_id'] + '.wem'), destination / (spec['media_id'] + '.wem'))
    with (folder / 'voice-lines.csv').open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, UNIT_VOICE_FIELDS)
        writer.writeheader()
        writer.writerows(voice_rows)
    # Independent inventory: every reachable Media ID of the canonical plan, replaced or deferred.
    group_of = {mid: item['voice_group'] for item in state['items'].values() for mid in item['member_media_ids']}
    group_of.update({mid: g for g, v in state['voice_groups'].items() for mid in v['deferred_media_ids']})
    fields = list(next(iter(media.values()))) + ['scope', 'silent_placeholder', 'safe_to_replace_for_' + UNIT,
                                                 'production_status', 'deferred_reason', 'voice_group', 'wem_sha256',
                                                 'pack_path', 'pack_offset']
    with (folder / 'media-inventory.csv').open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        for mid in sorted(media, key=int):
            writer.writerow(media[mid] | {'scope': 'SHARED', 'silent_placeholder': audit['results'][mid]['silent_placeholder'],
                                          'safe_to_replace_for_' + UNIT: 'YES',
                                          'production_status': 'DEFERRED' if mid in reasons else 'REPLACED',
                                          'deferred_reason': reasons.get(mid, ''),
                                          'voice_group': group_of[mid], 'wem_sha256': audit['results'][mid]['original_wem_sha256'],
                                          'pack_path': audit['results'][mid]['pack_path'],
                                          'pack_offset': audit['results'][mid]['pack_offset']})
    save(folder / (STAGED if args.staged else MANIFEST), manifest)
    save(folder / 'audio-qa.json', {'status': 'PASS', 'replacement_count': len(qa), 'source_performances': len(plan),
         'deferred_media_ids': deferred, 'deferred_reason': manifest['deferred_reason'],
         'duration_ratio_review_flags': duration_flags,
         'human_listening_of_final_wems': 'NOT_PERFORMED', 'game_runtime_test': 'NOT_PERFORMED', 'results': qa})
    checked = mod.validate_data(load_unit(args.staged))
    require(checked['status'] == 'PASS', 'Promoted unit voice set did not validate')
    require((UNIT in {m['commander'] for m in discover_shared()}) != args.staged,
            'Installer discovery does not match the requested promotion mode')
    return {'status': 'PASS', 'module': UNIT, 'staged': args.staged, 'installer_discoverable': not args.staged,
            'replacements': len(specs), 'deferred_media_ids': deferred, 'blocked_no_exact_size_wem': blocked,
            'source_performances': len(plan), 'voice_groups': groups, 'candidate_sha256': release_sha,
            'candidate': str(candidate), 'changed_entries': len(changed),
            'unchanged_entries': len(original.entries) - len(changed), 'RSA': 'PASS',
            'commander_overlap': 0, 'duration_ratio_review_flags': duration_flags}


def run(args):
    if getattr(args, 'module', None) == UNIT:
        return run_unit(args)
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
                'required_runtime_pack': 'audio_cn.pack', 'version': VERSION,
                'display_order': next_display_order(prior)}
    destination = mod.ROOT / 'replacements' / args.commander / 'wem'
    folder = mod.ROOT / 'data/commanders' / args.commander
    require(not destination.exists() and not any((folder / n).exists() for n in
            (MANIFEST, STAGED, 'voice-lines.csv', 'media-inventory.csv', 'audio-qa.json')),
            'Production output already exists')
    destination.mkdir(parents=True)
    for spec in specs:
        shutil.copyfile(wem_dir / (spec['media_id'] + '.wem'), destination / (spec['media_id'] + '.wem'))
    with (folder / 'voice-lines.csv').open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, FIELDS)
        writer.writeheader()
        writer.writerows(voice_rows)
    shutil.copyfile(folder / 'research/voice-lines.csv', folder / 'media-inventory.csv')
    save(folder / (STAGED if args.staged else MANIFEST), manifest)
    save(folder / 'audio-qa.json', {'status': 'PASS', 'replacement_count': len(qa),
         'source_performances': len(plan), 'duration_ratio_review_flags': duration_flags,
         'human_listening_of_final_wems': 'NOT_PERFORMED', 'game_runtime_test': 'NOT_PERFORMED',
         'results': qa})
    checked = mod.validate_data(load_staged(args.commander) if args.staged else mod.load_manifest(args.commander))
    require(checked['status'] == 'PASS', 'Promoted production set did not validate')
    require((args.commander in {m['commander'] for m in discover()}) != args.staged,
            'Installer discovery does not match the requested promotion mode')
    return {'status': 'PASS', 'commander': args.commander, 'staged': args.staged,
            'installer_discoverable': not args.staged, 'replacements': len(specs),
            'source_performances': len(plan), 'candidate_sha256': release_sha,
            'changed_entries': len(changed), 'RSA': 'PASS', 'duration_ratio_review_flags': duration_flags}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    owner = parser.add_mutually_exclusive_group(required=True)
    owner.add_argument('--commander')
    owner.add_argument('--module', choices=(UNIT,),
                       help='shared unit voices: --routing, --state (both ledgers), --original-audit, --base, --work')
    parser.add_argument('--original-audit', help='unit voices: private original-audio-audit.json')
    parser.add_argument('--fallback-state', nargs='+', help='unit voices: byte-budget fallback ledgers (approved per-ID lines)')
    parser.add_argument('--compact', help='unit voices: accepted compact sources JSON (performance, attempt, regeneration_state, media_ids)')
    production = ('display_name', 'routing', 'state', 'base', 'work')
    for name in production:
        parser.add_argument('--' + name.replace('_', '-'), help='required unless --activate',
                            **({'nargs': '+'} if name == 'state' else {}))
    parser.add_argument('--staged', action='store_true',
                        help=f'write {STAGED} so the installer does not discover the commander yet')
    parser.add_argument('--activate', action='store_true',
                        help=f'integrate an existing validated {STAGED} as {MANIFEST} (version {VERSION})')
    args = parser.parse_args()
    if args.module:
        if args.activate:
            if args.staged or args.original_audit or any(getattr(args, name) for name in production):
                parser.error('--activate takes only --module')
            print(json.dumps(activate_unit(), ensure_ascii=False, indent=2))
            return
        missing = [n for n in ('routing', 'state', 'base', 'work', 'original_audit') if not getattr(args, n)]
        if missing or args.display_name:
            parser.error('--module takes --routing, --state, --original-audit, --base, --work and optionally --staged')
        print(json.dumps(run(args), ensure_ascii=False, indent=2))
        return
    if args.activate:
        if args.staged or any(getattr(args, name) for name in production):
            parser.error('--activate takes only --commander')
        print(json.dumps(activate(args.commander), ensure_ascii=False, indent=2))
        return
    missing = ['--' + name.replace('_', '-') for name in production if not getattr(args, name)]
    if missing:
        parser.error('the following arguments are required: ' + ', '.join(missing))
    print(json.dumps(run(args), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
