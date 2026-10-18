"""Offline, resumable preparation and WEM encoding from an approved TTS ledger.

All intermediate outputs stay in work/. The caller promotes validated WEMs to
replacements/ only after every target passes its own exact-size and decode QC.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import shutil
import wave

from tools import mod
from tools.pack.reader import ArenaPack, require
from tools.tts.production import load_plan
from tools.wem.audio import pcm16
from tools.wem.encode import search
from tools.wem.prepare import prepare_game_wav
from tools.wem.validate import validate

# Encoder-only profiles that produced approved Hannibal/Spartacus WEMs, mildest
# first. The QC reference never changes; only the encoder spends bits differently.
FALLBACK_PROFILES = (
    ('lowpass12', ('lowpass_frequency=12',)),
    ('lowpass11', ('lowpass_frequency=11',)),
    ('lowpass10', ('lowpass_frequency=10',)),
    ('lowpass10-transients', ('lowpass_frequency=10', 'impulse_noisetune=-10')),
    ('lowpass9', ('lowpass_frequency=9',)),
    ('lowpass8', ('lowpass_frequency=8',)),
    ('lowpass7.75', ('lowpass_frequency=7,75',)),
    ('lowpass7', ('lowpass_frequency=7',)),
)


def fallback_one(mid, source, budget, original, tools, work, wem_format, profiles=FALLBACK_PROFILES, tag=''):
    """Try each validated profile for one Media ID; return the first full-QC pass."""
    oggenc, wav2wem, vgmstream, ww2ogg, codebooks = tools
    attempts = []
    for name, options in profiles:
        name = tag + name
        stem = f'{mid}-{name}'
        result = work / 'fallback' / (stem + '.wem')
        search_dir = work / 'fallback-search' / stem
        if result.is_file() or search_dir.exists():
            attempts.append({'profile': name, 'status': 'SKIPPED_PREVIOUS_ATTEMPT'})
            continue
        try:
            report = search(source, result, budget, mid, oggenc, wav2wem, vgmstream, search_dir,
                            advanced_option=list(options), wem_format=wem_format)
        except (OSError, ValueError) as error:
            attempts.append({'profile': name, 'status': 'NO_FIT', 'reason': str(error)})
            continue
        raw = search_dir / f"q{report['quality']:.4f}.wem"
        try:
            qa = validate(result, source, vgmstream, ww2ogg, codebooks, work / 'fallback-qa' / stem,
                          original=original, raw=raw)
        except (OSError, ValueError) as error:
            attempts.append({'profile': name, 'status': 'FULL_QC_FAIL', 'reason': str(error)})
            continue
        attempts.append({'profile': name, 'status': 'PASS', 'snr_db': qa['quality']['snr_db'],
                         'correlation': qa['quality']['correlation']})
        return mid, attempts, {**report, 'search_work': str(search_dir), 'advanced_options': list(options),
                               'profile': name}, str(result)
    return mid, attempts, None, None


def context(args):
    root = mod.ROOT
    plan, routes, hashes, safe_count = load_plan(args.commander, Path(args.routing))
    state_path = Path(args.state)
    state = json.loads(state_path.read_text(encoding='utf-8'))
    require(state['commander'] == args.commander and state['safe_media_ids'] == safe_count
            and state['unique_performances'] == len(plan) and state['source_hashes'] == hashes,
            'Generation ledger and current plan/routing differ')
    require(len(state['items']) == len(plan), 'Generation item count mismatch')
    audit = json.loads((root / 'data/commanders' / args.commander / 'research/original-audio-audit.json').read_text(encoding='utf-8'))
    research = mod.csv_rows(root / 'data/commanders' / args.commander / 'research/voice-lines.csv')
    safe = {r['media_id']: r for r in research if r['safe_to_replace_for_commander'] == 'YES'
            and r['safe_to_replace_for_' + args.commander] == 'YES'}
    require(len(safe) == safe_count, 'Independent safe inventory count mismatch')
    require(audit['canonical_pack_sha256'] == state.get('canonical_pack_sha256', audit['canonical_pack_sha256'])
            and audit['RSA'] == 'PASS', 'Original audit mismatch')
    members = set()
    items = state['items']
    for row in plan:
        source = row['tts_source_media_id']
        item = items[source]
        ids = row['member_media_ids'].split(';')
        require(item['status'] == 'complete' and item['tts_source_media_id'] == source
                and item['tts_performance_group'] == row['tts_performance_group']
                and item['member_media_ids'] == ids and item['model'] == routes[source]['selected_model']
                and item['czech_text'] == row['czech_text'], 'Unapproved or changed performance ' + source)
        path = root / Path(item['output_path'])
        require(path.is_file() and mod.sha256(path) == item['checksum'] == item['audio']['sha256']
                and path.stat().st_size == item['audio']['bytes'], 'TTS source checksum mismatch ' + source)
        for mid in ids:
            require(mid not in members and mid in safe and mid in audit['results'], 'Unsafe/duplicate target ' + mid)
            original = audit['results'][mid]
            inventory = safe[mid]
            require(original['original_size_bytes'] == int(inventory['original_size_bytes'])
                    and original['pack_offset'] == int(inventory['pack_offset'])
                    and original['original_wem_sha256'] == inventory['original_wem_sha256']
                    and original['silent_placeholder'] == 'NO'
                    and inventory['scope'] == args.commander.upper() + '_SPECIFIC', 'Original inventory mismatch ' + mid)
            members.add(mid)
    require(members == set(safe), 'Source performance mapping incomplete')
    return plan, state, audit, safe


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def run(args):
    plan, state, audit, safe = context(args)
    work = Path(args.work)
    require(work.resolve().is_relative_to(mod.ROOT / 'work'), 'Intermediate outputs must stay under work/')
    work.mkdir(parents=True, exist_ok=True)
    base = Path(args.base).resolve(strict=True)
    require(not base.is_relative_to(mod.ROOT) and mod.sha256(base) == audit['canonical_pack_sha256'],
            'Canonical original unavailable or has an unknown SHA-256')
    pack = ArenaPack(base)
    by_path = {entry.path: entry for entry in pack.entries}
    with base.open('rb') as stream:
        for mid in safe:
            original = audit['results'][mid]
            entry = by_path[original['pack_path']]
            require(entry.offset == original['pack_offset'] and entry.size == original['original_size_bytes'],
                    'Canonical PACK entry metadata mismatch ' + mid)
            stream.seek(entry.offset)
            require(hashlib.sha256(stream.read(entry.size)).hexdigest() == original['original_wem_sha256'],
                    'Canonical original WEM hash mismatch ' + mid)
    if args.phase == 'preflight':
        result = {'status': 'PASS', 'safe_media_ids': len(safe), 'unique_performances': len(plan),
                  'duplicate_media_ids': len(safe) - len(plan), 'source_checksums': 'PASS',
                  'canonical_pack_sha256': audit['canonical_pack_sha256'], 'RSA': 'PASS'}
        save(work / 'preflight.json', result)
        return result
    require((work / 'preflight.json').is_file(), 'Run preflight first')
    if args.phase == 'prepare':
        import miniaudio
        reports = {}
        for index, row in enumerate(plan, 1):
            mid = row['tts_source_media_id']
            item = state['items'][mid]
            source = mod.ROOT / Path(item['output_path'])
            decoded = work / 'decoded-24k' / (mid + '.wav')
            prepared = work / 'canonical-32k' / (mid + '.wav')
            if not prepared.exists():
                decoded.parent.mkdir(exist_ok=True)
                prepared.parent.mkdir(exist_ok=True)
                require(not decoded.exists(), 'Unfinished decoded WAV requires manual review ' + mid)
                sound = miniaudio.decode_file(str(source), output_format=miniaudio.SampleFormat.SIGNED16,
                                              nchannels=1, sample_rate=24000)
                require(sound.sample_rate == 24000 and sound.nchannels == 1 and len(sound.samples) > 1000,
                        'MP3 decode failed ' + mid)
                with wave.open(str(decoded), 'wb') as output:
                    output.setnchannels(1)
                    output.setsampwidth(2)
                    output.setframerate(24000)
                    output.writeframes(sound.samples.tobytes())
                report = prepare_game_wav(decoded, prepared)
                save(work / 'prepare-reports' / (mid + '.json'), report)
            report = json.loads((work / 'prepare-reports' / (mid + '.json')).read_text(encoding='utf-8'))
            info, _ = pcm16(prepared)
            require(info['rate'] == 32000 and info['peak_linear'] < 1
                    and info['samples_at_or_above_full_scale'] == 0
                    and info['pcm_sha256'] == report['prepared']['pcm_sha256'], 'Prepared WAV QC failed ' + mid)
            reports[mid] = {'source_sha256': item['checksum'], 'prepared_sha256': mod.sha256(prepared),
                            'duration_seconds': info['duration_seconds']}
            if index % 20 == 0:
                print(f'Prepared {index}/{len(plan)}', flush=True)
        save(work / 'prepared.json', reports)
        return {'status': 'PASS', 'prepared': len(reports)}
    require((work / 'prepared.json').is_file(), 'Run prepare first')
    if args.phase == 'encode':
        require(all((args.oggenc, args.wav2wem, args.vgmstream)), 'Encoding tools required')
        from tools.installer.catalog import discover
        wem_format = discover()[0]['wem_format']
        by_target = {mid: row['tts_source_media_id'] for row in plan for mid in row['member_media_ids'].split(';')}
        encoded, blocked = [], {}
        for index, mid in enumerate(sorted(safe, key=int), 1):
            result = work / 'wem' / (mid + '.wem')
            if not result.is_file():
                result.parent.mkdir(exist_ok=True)
                source = work / 'canonical-32k' / (by_target[mid] + '.wav')
                try:
                    report = search(source, result, audit['results'][mid]['original_size_bytes'], mid,
                                    args.oggenc, args.wav2wem, args.vgmstream, work / 'encode-search' / mid,
                                    wem_format=wem_format)
                    save(work / 'encode-reports' / (mid + '.json'), report)
                except (OSError, ValueError) as error:
                    blocked[mid] = str(error)
                    save(work / 'blocked.json', blocked)
                    print(f'BLOCKED {mid}: {error}', flush=True)
                    continue
            require(result.stat().st_size == audit['results'][mid]['original_size_bytes'],
                    'Previously encoded WEM size mismatch ' + mid)
            encoded.append(mid)
            if index % 10 == 0:
                print(f'Encoded {index}/{len(safe)}; blocked {len(blocked)}', flush=True)
        save(work / 'blocked.json', blocked)
        return {'encoded': len(encoded), 'blocked': blocked}
    if args.phase == 'fallback':
        # Same unchanged QC reference; only the encoder low-pass profile changes.
        require(all((args.oggenc, args.wav2wem, args.vgmstream, args.ww2ogg, args.codebooks, args.original_dir)),
                'Encoding, validation tools and private original WEMs required')
        original_dir = Path(args.original_dir).resolve(strict=True)
        by_target = {mid: row['tts_source_media_id'] for row in plan for mid in row['member_media_ids'].split(';')}
        from tools.installer.catalog import discover
        from tools.wem.encode import format_matches
        from tools.wem.fingerprint import fingerprint
        wem_format = discover()[0]['wem_format']
        blocked = json.loads((work / 'blocked.json').read_text(encoding='utf-8'))
        summary_path = work / 'fallback-summary.json'
        results = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.is_file() else {}
        (work / 'fallback').mkdir(exist_ok=True)
        # A selected WEM in another Vorbis setup is not the Arena format: reject it and search again.
        retry_standard = set()
        for mid in sorted(safe, key=int):
            wem = work / 'wem' / (mid + '.wem')
            if wem.is_file() and not format_matches(fingerprint(wem)['fmt'], wem_format):
                rejected = work / 'format-rejected'
                rejected.mkdir(exist_ok=True)
                wem.replace(rejected / (mid + '.wem'))
                (work / 'encode-reports' / (mid + '.json')).replace(rejected / (mid + '.json'))
                blocked[mid] = 'Selected encoding used a non-Arena Vorbis setup; searched again'
                retry_standard.add(mid)
        save(work / 'blocked.json', blocked)
        tag = f'tail{args.trailing_margin_ms}-' if args.trailing_margin_ms else ''
        # Attempts interrupted before a full-QC pass leave no result; start them cleanly.
        for mid in blocked:
            if not (work / 'wem' / (mid + '.wem')).is_file():
                if not tag:
                    results.pop(mid, None)
                for folder in ('fallback', 'fallback-search', 'fallback-qa'):
                    for path in (work / folder).glob(mid + '-' + tag + '*'):
                        if tag or not path.name.startswith(mid + '-tail'):
                            shutil.rmtree(path) if path.is_dir() else path.unlink()
        members = {}
        for target, source in by_target.items():
            members.setdefault(source, []).append(target)
        jobs, variants = [], {}
        for mid in sorted(blocked, key=int):
            if (work / 'wem' / (mid + '.wem')).is_file():
                continue
            original = original_dir / (mid + '.wem')
            require(mod.sha256(original) == audit['results'][mid]['original_wem_sha256'],
                    'Private original WEM checksum mismatch ' + mid)
            source_id = by_target[mid]
            reference = work / 'canonical-32k' / (source_id + '.wav')
            profiles = ((('standard', ()),) if mid in retry_standard or tag else ()) + FALLBACK_PROFILES
            if tag:
                # Only real edge silence may go, and only when no sibling already uses the reference.
                if any((work / 'wem' / (m + '.wem')).is_file() for m in members[source_id]):
                    results.setdefault(mid, []).append({'profile': tag + 'reference', 'status': 'SHARED_REFERENCE_IN_USE'})
                    continue
                reference = work / f'canonical-32k-{tag[:-1]}' / (source_id + '.wav')
                report_path = work / f'prepare-reports-{tag[:-1]}' / (source_id + '.json')
                if not reference.is_file():
                    reference.parent.mkdir(exist_ok=True)
                    report_path.parent.mkdir(exist_ok=True)
                    save(report_path, prepare_game_wav(work / 'decoded-24k' / (source_id + '.wav'), reference,
                                                       trailing_margin_ms=args.trailing_margin_ms))
                if mod.sha256(reference) == mod.sha256(work / 'canonical-32k' / (source_id + '.wav')):
                    results.setdefault(mid, []).append({'profile': tag + 'reference', 'status': 'NO_EXTRA_EDGE_SILENCE'})
                    continue
                variants[mid] = (source_id, reference, report_path)
            jobs.append((mid, reference, audit['results'][mid]['original_size_bytes'], original,
                         (args.oggenc, args.wav2wem, args.vgmstream, args.ww2ogg, args.codebooks), work,
                         wem_format, profiles, tag))
        # Each job owns distinct search/QA directories; only this process writes results.
        with ProcessPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            for future in as_completed([pool.submit(fallback_one, *job) for job in jobs]):
                mid, attempts, report, result = future.result()
                if report:
                    if mid in variants:
                        # Promote the shorter-silence reference that this WEM was validated against.
                        source_id, reference, report_path = variants[mid]
                        canonical = work / 'canonical-32k' / (source_id + '.wav')
                        kept = work / 'canonical-32k-replaced'
                        kept.mkdir(exist_ok=True)
                        if not (kept / (source_id + '.wav')).exists():
                            shutil.copyfile(canonical, kept / (source_id + '.wav'))
                            shutil.copyfile(work / 'prepare-reports' / (source_id + '.json'),
                                            kept / (source_id + '.json'))
                        shutil.copyfile(reference, canonical)
                        shutil.copyfile(report_path, work / 'prepare-reports' / (source_id + '.json'))
                        report['trailing_margin_ms'] = args.trailing_margin_ms
                    shutil.copyfile(result, work / 'wem' / (mid + '.wem'))
                    save(work / 'encode-reports' / (mid + '.json'), report)
                results[mid] = results.get(mid, []) + attempts if tag else attempts
                save(summary_path, results)
                print(mid, attempts[-1]['status'], attempts[-1]['profile'], flush=True)
        remaining = {mid: reason for mid, reason in blocked.items() if not (work / 'wem' / (mid + '.wem')).is_file()}
        save(work / 'fallback-blocked.json', remaining)
        return {'fallback_resolved': sorted(set(blocked) - set(remaining), key=int), 'still_blocked': sorted(remaining, key=int)}
    if args.phase == 'validate':
        require(all((args.vgmstream, args.ww2ogg, args.codebooks)), 'Validation tools required')
        original_dir = Path(args.original_dir).resolve(strict=True) if args.original_dir else None
        by_target = {mid: row['tts_source_media_id'] for row in plan for mid in row['member_media_ids'].split(';')}
        results, failed = {}, {}
        for index, mid in enumerate(sorted(safe, key=int), 1):
            wem = work / 'wem' / (mid + '.wem')
            if not wem.is_file():
                failed[mid] = 'MISSING'
                continue
            report_path = work / 'qa' / mid / 'validation.json'
            if not report_path.is_file():
                try:
                    encode_report = json.loads((work / 'encode-reports' / (mid + '.json')).read_text(encoding='utf-8'))
                    search_work = Path(encode_report.get('search_work', work / 'encode-search' / mid))
                    raw = search_work / f"q{encode_report['quality']:.4f}.wem"
                    original = original_dir / (mid + '.wem') if original_dir else None
                    if original:
                        require(mod.sha256(original) == audit['results'][mid]['original_wem_sha256'],
                                'Private original WEM checksum mismatch ' + mid)
                    report = validate(wem, work / 'canonical-32k' / (by_target[mid] + '.wav'), args.vgmstream,
                                      args.ww2ogg, args.codebooks, work / 'qa' / mid, original=original, raw=raw)
                except (OSError, ValueError) as error:
                    failed[mid] = str(error)
                    continue
            else:
                report = json.loads(report_path.read_text(encoding='utf-8'))
            require(report['wem_sha256'] == mod.sha256(wem), 'WEM changed since QA ' + mid)
            results[mid] = report
            if index % 10 == 0:
                print(f'Validated {index}/{len(safe)}; failed {len(failed)}', flush=True)
        summary = {'validated': len(results), 'failed': failed}
        save(work / 'validation-summary.json', summary)
        return summary
    raise ValueError('Unknown phase')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commander', required=True)
    parser.add_argument('--routing', required=True)
    parser.add_argument('--state', required=True)
    parser.add_argument('--base', required=True)
    parser.add_argument('--work', required=True)
    parser.add_argument('--phase', choices=('preflight', 'prepare', 'encode', 'fallback', 'validate'), required=True)
    parser.add_argument('--oggenc')
    parser.add_argument('--wav2wem')
    parser.add_argument('--vgmstream')
    parser.add_argument('--ww2ogg')
    parser.add_argument('--codebooks')
    parser.add_argument('--original-dir')
    parser.add_argument('--jobs', type=int, default=1, help='parallel fallback workers')
    parser.add_argument('--trailing-margin-ms', type=int, choices=(20,),
                        help='fallback only: re-prepare still-blocked sources with the validated 20 ms tail margin')
    args = parser.parse_args()
    print(json.dumps(run(args), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
