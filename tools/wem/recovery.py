"""Evidence-based WEM recovery for Media IDs that no encoder profile could fit.

Original Arena voice assets were measured band-limited (no energy above about 8 kHz). For a
blocked line the prepared TTS reference is low-passed to the mildest cutoff from a ladder,
re-encoded with the unchanged Arena search, and accepted only if it passes:

* the standard full QC against that band-limited production reference, and
* a fidelity audit against the unchanged TTS reference (full-band correlation, in-band SNR,
  no speech dropouts or added energy, no bandwidth collapse, no clipping).

Speech is never shortened, sped up or pitch-shifted. Outputs stay under an ignored work/ folder.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import json
import math
from pathlib import Path

from tools import mod
from tools.pack.reader import require
from tools.wem.audio import pcm16
from tools.wem.encode import search
from tools.wem.prepare import band_limit_wav
from tools.wem.validate import validate

# Mildest first. Originals measured at most 7.8 kHz wide (-40 dB), so 7.5 kHz still matches them;
# 7.0 and 6.5 kHz are allowed only where that line's own original is narrower still.
LADDER_HZ = (10000, 9000, 8500, 8000, 7500)
NARROW_HZ = (7000, 6500)
# Second stage, only after every plain cutoff failed: a mild static -3 dB shelf above 6.5 kHz
# (the TTS measured +8 to +13 dB brighter than the originals between 5 and 7.6 kHz).
SHELF_DB = -3
# Validated encoder-only low-pass values (kHz); the combination uses the nearest one at or above the cutoff.
ENCODER_LOWPASS_KHZ = (7, 7.75, 8, 9, 10, 11, 12)
# Added-energy frames: none in steady speech; at most one at an onset/offset transition, the
# maximum measured in the approved Spartacus WEMs (MDCT block smearing, not a tonal artifact).
GUARD = {'full_band_correlation': .95, 'in_band_snr_db': 15, 'in_band_correlation': .95,
         'speech_dropout_frames': 0, 'steady_added_energy_frames': 0, 'transition_added_energy_frames': 1,
         'bandwidth_ratio': .9, 'clipped_samples': 0}
TRANSITION_DB = 6


def ladder(original_bandwidth_hz, unfiltered=False, below_original=False):
    """(cutoff Hz or None, shelf dB, trailing margin ms) variants, mildest first.

    unfiltered adds the untouched reference first (for a new performance). below_original re-enables
    the first recovery's 7 kHz rung for lines whose original is wider; by default no cutoff is
    narrower than the line's own original asset.
    """
    cutoffs = LADDER_HZ + tuple(fc for fc in NARROW_HZ if original_bandwidth_hz <= fc)
    stages = [(None, 0, 40)] if unfiltered else []
    stages += [(fc, 0, 40) for fc in cutoffs] + [(fc, SHELF_DB, 40) for fc in cutoffs if fc <= 8000]
    # Third stage: the validated 20 ms trailing-silence margin with the matching band limits.
    stages += [(fc, 0, 20) for fc in cutoffs if fc <= 8000]
    if below_original and 7000 not in cutoffs:
        stages += [(7000, 0, 40), (7000, 0, 20)]
    return stages


def variant(cutoff, shelf_db, tail_ms=40):
    return (f'lp{cutoff}' if cutoff else 'full') + (f'-shelf{-shelf_db:g}' if shelf_db else '') + \
        (f'-tail{tail_ms}' if tail_ms != 40 else '')


def profiles(cutoff_hz):
    if cutoff_hz is None:
        # Untouched reference: the standard search, then the validated encoder-only low-pass profiles.
        return [('standard', ())] + [(f'lowpass{k}', (f'lowpass_frequency={k}',)) for k in (12, 11, 10, 9, 8)]
    khz = min(k for k in ENCODER_LOWPASS_KHZ if k * 1000 >= cutoff_hz) if cutoff_hz <= 12000 else None
    result = [('standard', ())]
    if khz:
        result.append((f'lowpass{khz:g}', (f'lowpass_frequency={khz:g}'.replace('.', ','),)))
    return result


def bandwidth_40db(values):
    import numpy as np
    n = 1024
    window = np.hanning(n)
    segments = [values[i:i + n] * window for i in range(0, max(1, len(values) - n), n // 2)]
    ltas = (np.abs(np.fft.rfft(np.array(segments), axis=1)) ** 2).mean(axis=0)
    smooth = np.convolve(ltas, np.ones(8) / 8, mode='same')
    freqs = np.fft.rfftfreq(n, 1 / 32000)
    return float(freqs[np.flatnonzero(smooth >= smooth.max() * 1e-4)].max())


def fidelity(decoded, tts, cutoff_hz, reference=None):
    """Compare a decoded WEM with the unchanged TTS reference (and the band-limited one)."""
    import numpy as np
    cutoff_hz = cutoff_hz or 16000  # untouched reference: the whole 32 kHz band
    info, y = pcm16(decoded)
    _, x = pcm16(tts)
    require(len(x) == len(y), 'Decoded length differs from the TTS reference')
    x, y = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    corr = lambda a, b: float(a @ b / math.sqrt((a @ a) * (b @ b)))
    snr = lambda a, b: 10 * math.log10(float(a @ a) / max(float((a - b) @ (a - b)), 1e-30))
    freqs = np.fft.rfftfreq(len(x), 1 / 32000)
    band = (freqs >= 80) & (freqs <= cutoff_hz - 400)
    xb = np.fft.irfft(np.fft.rfft(x) * band, len(x))
    yb = np.fft.irfft(np.fft.rfft(y) * band, len(y))
    frame = 320
    count = len(x) // frame
    fx = xb[:count * frame].reshape(count, frame)
    fy = yb[:count * frame].reshape(count, frame)
    ex = 10 * np.log10(np.maximum((fx ** 2).mean(axis=1) / 32768 ** 2, 1e-12))
    ey = 10 * np.log10(np.maximum((fy ** 2).mean(axis=1) / 32768 ** 2, 1e-12))
    speech = ex > -40
    added = speech & (ey > ex + 3)
    step = np.abs(np.diff(ex))
    transition = np.zeros(count, dtype=bool)
    transition[1:] |= step >= TRANSITION_DB
    transition[:-1] |= step >= TRANSITION_DB
    seg = 10 * np.log10(np.maximum((fx ** 2).sum(axis=1), 1e-9) / np.maximum(((fx - fy) ** 2).sum(axis=1), 1e-9))
    target_bw = bandwidth_40db(np.asarray(pcm16(reference)[1], dtype=np.float64)) if reference else bandwidth_40db(x)
    result = {'full_band_correlation': corr(x, y), 'full_band_snr_db': snr(x, y),
              'in_band_hz': [80, cutoff_hz - 400], 'in_band_correlation': corr(xb, yb), 'in_band_snr_db': snr(xb, yb),
              'speech_frames': int(speech.sum()),
              'speech_dropout_frames': int((speech & (ey < ex - 6)).sum()),
              'speech_added_energy_frames': int(added.sum()),
              'steady_added_energy_frames': int((added & ~transition).sum()),
              'transition_added_energy_frames': int((added & transition).sum()),
              'segmental_in_band_snr_db_median': float(np.median(seg[speech])) if speech.any() else None,
              'segmental_in_band_snr_db_p05': float(np.percentile(seg[speech], 5)) if speech.any() else None,
              'decoded_bandwidth_40db_hz': bandwidth_40db(y), 'reference_bandwidth_40db_hz': target_bw,
              'clipped_samples': info['samples_at_or_above_full_scale']}
    result['bandwidth_ratio'] = result['decoded_bandwidth_40db_hz'] / target_bw
    failed = [key for key, limit in GUARD.items() if
              (result[key] > limit if key.endswith(('frames', 'samples')) else result[key] <= limit)]
    result.update(status='PASS' if not failed else 'FAIL', failed_guards=failed, thresholds=GUARD,
                  stt_intelligibility='NOT_AVAILABLE (only English Whisper models are installed locally)')
    return result


def recover_one(mid, tts, references, budget, original, tools, work, wem_format):
    """Mildest band limit first; within a cutoff the standard search, then the encoder combination."""
    oggenc, wav2wem, vgmstream, ww2ogg, codebooks = tools
    attempts = []
    for cutoff, shelf_db, tail_ms, reference, tts in references:
        for name, options in profiles(cutoff):
            stem = f'{mid}-{variant(cutoff, shelf_db, tail_ms)}-{name}'
            result = work / 'candidates' / (stem + '.wem')
            result.parent.mkdir(parents=True, exist_ok=True)
            search_dir = work / 'search' / stem
            if search_dir.exists():
                attempts.append({'cutoff_hz': cutoff, 'shelf_db': shelf_db, 'tail_ms': tail_ms, 'profile': name, 'status': 'SKIPPED_PREVIOUS_ATTEMPT'})
                continue
            try:
                report = search(reference, result, budget, mid, oggenc, wav2wem, vgmstream, search_dir,
                                advanced_option=list(options), wem_format=wem_format)
            except (OSError, ValueError) as error:
                attempts.append({'cutoff_hz': cutoff, 'shelf_db': shelf_db, 'tail_ms': tail_ms, 'profile': name, 'status': 'NO_FIT', 'reason': str(error)})
                continue
            raw = search_dir / f"q{report['quality']:.4f}.wem"
            qa_dir = work / 'qa' / stem
            try:
                qa = validate(result, reference, vgmstream, ww2ogg, codebooks, qa_dir, original=original, raw=raw)
            except (OSError, ValueError) as error:
                attempts.append({'cutoff_hz': cutoff, 'shelf_db': shelf_db, 'tail_ms': tail_ms, 'profile': name, 'status': 'FULL_QC_FAIL', 'reason': str(error)})
                continue
            audit = fidelity(qa_dir / 'decoded.wav', tts, cutoff, reference)
            attempt = {'cutoff_hz': cutoff, 'shelf_db': shelf_db, 'tail_ms': tail_ms, 'profile': name, 'quality': report['quality'],
                       'raw_bytes': raw.stat().st_size, 'production_qc': qa['quality'], 'tts_reference': str(tts),
                       'tts_fidelity': audit}
            if audit['status'] != 'PASS':
                attempts.append({**attempt, 'status': 'FIDELITY_FAIL'})
                continue
            attempts.append({**attempt, 'status': 'PASS'})
            return mid, attempts, {**report, 'search_work': str(search_dir), 'advanced_options': list(options),
                                   'profile': name, 'band_limit_hz': cutoff, 'high_shelf_db': shelf_db,
                                   'trailing_margin_ms': tail_ms, 'reference': str(reference), 'tts_reference': str(tts),
                                   'tts_fidelity': audit}, str(result)
    return mid, attempts, None, None


def reselect(work, production, by_target):
    """Re-audit every production-QC pass with the current guard; keep the mildest passing variant."""
    summary_path = work / 'recovery-summary.json'
    results = json.loads(summary_path.read_text(encoding='utf-8'))
    selected = {}
    for mid, attempts in results.items():
        source = by_target[mid]
        tts = production / 'canonical-32k' / (source + '.wav')
        for attempt in attempts:
            if 'production_qc' not in attempt:
                continue
            name = variant(attempt['cutoff_hz'], attempt.get('shelf_db', 0), attempt.get('tail_ms', 40))
            stem = f"{mid}-{name}-{attempt['profile']}"
            base = Path(attempt.get('tts_reference', tts))
            reference = work / 'references' / f'{source}-{name}.wav' if attempt['cutoff_hz'] else base
            audit = fidelity(work / 'qa' / stem / 'decoded.wav', base, attempt['cutoff_hz'], reference)
            attempt.update(tts_fidelity=audit, status='PASS' if audit['status'] == 'PASS' else 'FIDELITY_FAIL')
            if audit['status'] == 'PASS' and mid not in selected:
                selected[mid] = (attempt, stem, reference, base)
    (work / 'candidates').mkdir(exist_ok=True)
    for mid in results:
        current = work / 'wem' / (mid + '.wem')
        report_path = work / 'reports' / (mid + '.json')
        if current.is_file():
            # Return the previous choice to the candidate pool before choosing again.
            previous = json.loads(report_path.read_text(encoding='utf-8'))
            stem = (f"{mid}-{variant(previous['band_limit_hz'], previous.get('high_shelf_db', 0), previous.get('trailing_margin_ms', 40))}"
                    f"-{previous['profile']}")
            current.replace(work / 'candidates' / (stem + '.wem'))
            report_path.unlink()
        if mid not in selected:
            continue
        attempt, stem, reference, base = selected[mid]
        candidate = work / 'candidates' / (stem + '.wem')
        qa = json.loads((work / 'qa' / stem / 'validation.json').read_text(encoding='utf-8'))
        require(qa['status'] == 'PASS' and qa['wem_sha256'] == mod.sha256(candidate), 'Candidate differs from its QA ' + mid)
        (work / 'wem').mkdir(exist_ok=True)
        candidate.replace(current)
        report_path.parent.mkdir(exist_ok=True)
        report_path.write_text(json.dumps({
            'status': 'ENCODED_REQUIRES_FULL_VALIDATION', 'quality': attempt['quality'], 'size': qa['size'],
            'sha256': qa['wem_sha256'], 'search_work': str(work / 'search' / stem),
            'advanced_options': [o for _, opts in profiles(attempt['cutoff_hz']) if _ == attempt['profile'] for o in opts],
            'profile': attempt['profile'], 'band_limit_hz': attempt['cutoff_hz'], 'high_shelf_db': attempt.get('shelf_db', 0),
            'trailing_margin_ms': attempt.get('tail_ms', 40), 'reference': str(reference), 'tts_reference': str(base),
            'tts_fidelity': attempt['tts_fidelity']}, indent=2) + '\n', encoding='utf-8')
    summary_path.write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    return {'selected': len(selected), 'still_blocked': sorted(set(results) - set(selected), key=int)}


def prepare_sources(state_path, attempt, media_ids, target):
    """Decode regenerated MP3s and prepare them exactly like production (40 ms and 20 ms tail margins)."""
    import miniaudio
    import wave
    from tools.wem.prepare import prepare_game_wav
    state = json.loads(state_path.read_text(encoding='utf-8'))
    for mid in media_ids:
        item = state['items'][f'{mid}#{attempt}']
        source = Path(item['new_audio_path'])
        require(item['status'] == 'complete' and mod.sha256(source) == item['checksum'], 'Regenerated audio changed ' + mid)
        decoded = target / 'decoded-24k' / (mid + '.wav')
        if not decoded.is_file():
            decoded.parent.mkdir(parents=True, exist_ok=True)
            sound = miniaudio.decode_file(str(source), output_format=miniaudio.SampleFormat.SIGNED16,
                                          nchannels=1, sample_rate=24000)
            require(sound.sample_rate == 24000 and len(sound.samples) > 1000, 'MP3 decode failed ' + mid)
            with wave.open(str(decoded), 'wb') as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(24000)
                output.writeframes(sound.samples.tobytes())
        for margin, folder in ((40, 'canonical-32k'), (20, 'canonical-32k-tail20')):
            prepared = target / folder / (mid + '.wav')
            if not prepared.is_file():
                prepared.parent.mkdir(parents=True, exist_ok=True)
                report = prepare_game_wav(decoded, prepared, trailing_margin_ms=margin)
                report['tts_source'] = {'path': str(source), 'sha256': item['checksum'], 'attempt': attempt,
                                        'tags': item['tags']}
                reports = target / ('prepare-reports' if margin == 40 else 'prepare-reports-tail20')
                reports.mkdir(exist_ok=True)
                (reports / (mid + '.json')).write_text(json.dumps(report, indent=2) + chr(10), encoding='utf-8')


def run(args):
    from tools.installer.catalog import discover
    from tools.wem.production import context
    plan, state, audit, safe = context(args)
    if args.reselect:
        by_target = {mid: row['tts_source_media_id'] for row in plan for mid in row['member_media_ids'].split(';')}
        return reselect(Path(args.work).resolve(strict=True), Path(args.production_work).resolve(strict=True), by_target)
    production = Path(args.production_work).resolve(strict=True)
    work = Path(args.work).resolve()
    sources = Path(args.source_dir).resolve() if args.source_dir else production
    require(all(p.is_relative_to(mod.ROOT / 'work') for p in (work, production, sources)),
            'Recovery outputs must stay under ignored work/')
    work.mkdir(parents=True, exist_ok=True)
    if args.prepare_from_state:
        prepare_sources(Path(args.prepare_from_state), args.attempt, args.media_ids.split(','), sources)
    original_dir = Path(args.original_dir).resolve(strict=True)
    analysis = {r['media_id']: r for r in csv.DictReader(Path(args.analysis).open(encoding='utf-8'))}
    by_target = {mid: row['tts_source_media_id'] for row in plan for mid in row['member_media_ids'].split(';')}
    wem_format = discover()[0]['wem_format']
    blocked = (sorted(args.media_ids.split(','), key=int) if args.media_ids else
               sorted((m for m in safe if not (production / 'wem' / (m + '.wem')).is_file()), key=int))
    require(set(blocked) <= set(safe), 'Only safe Media IDs can be recovered')
    require(set(blocked) <= set(analysis), 'Every blocked Media ID needs an original-asset analysis row')
    summary_path = work / 'recovery-summary.json'
    results = json.loads(summary_path.read_text(encoding='utf-8')) if summary_path.is_file() else {}
    jobs = []
    for mid in blocked:
        if (work / 'wem' / (mid + '.wem')).is_file():
            continue
        original = original_dir / (mid + '.wem')
        require(mod.sha256(original) == audit['results'][mid]['original_wem_sha256'], 'Original checksum mismatch ' + mid)
        source = by_target[mid]
        tts = sources / 'canonical-32k' / (source + '.wav')
        references = []
        for cutoff, shelf_db, tail_ms in ladder(float(analysis[mid]['orig_bandwidth_40db_hz']),
                                                args.unfiltered, args.below_original):
            base = tts
            if tail_ms != 40:
                # Same established preparation with the shorter edge-silence margin (prepare phase variant).
                base = sources / f'canonical-32k-tail{tail_ms}' / (source + '.wav')
                if not base.is_file() or mod.sha256(base) == mod.sha256(tts):
                    continue
            if cutoff is None:
                references.append((cutoff, shelf_db, tail_ms, base, base))
                continue
            # Built here, never in workers: one shared reference per source and preprocessing variant.
            reference = work / 'references' / f'{source}-{variant(cutoff, shelf_db, tail_ms)}.wav'
            report_path = reference.with_suffix('.json')
            if not reference.is_file():
                reference.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(json.dumps(band_limit_wav(base, reference, cutoff, shelf_db), indent=2) + '\n',
                                       encoding='utf-8')
            references.append((cutoff, shelf_db, tail_ms, reference, base))
        jobs.append((mid, tts, references, audit['results'][mid]['original_size_bytes'], original,
                     (args.oggenc, args.wav2wem, args.vgmstream, args.ww2ogg, args.codebooks), work, wem_format))
    with ProcessPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        for future in as_completed([pool.submit(recover_one, *job) for job in jobs]):
            mid, attempts, report, result = future.result()
            if report:
                (work / 'wem').mkdir(exist_ok=True)
                Path(result).replace(work / 'wem' / (mid + '.wem'))
                (work / 'reports').mkdir(exist_ok=True)
                (work / 'reports' / (mid + '.json')).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
            results[mid] = results.get(mid, []) + [a for a in attempts if a['status'] != 'SKIPPED_PREVIOUS_ATTEMPT']
            summary_path.write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
            last = attempts[-1] if attempts else {'status': 'NO_ATTEMPT'}
            print(mid, last['status'], last.get('cutoff_hz'), last.get('shelf_db'), last.get('tail_ms'), last.get('profile'),
                  flush=True)
    remaining = [m for m in blocked if not (work / 'wem' / (m + '.wem')).is_file()]
    return {'blocked_at_start': len(blocked), 'recovered': len(blocked) - len(remaining), 'still_blocked': remaining}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    owner = parser.add_mutually_exclusive_group(required=True)
    owner.add_argument('--commander')
    owner.add_argument('--module', choices=('unit-voices',), help='shared unit voices: pass both ledgers to --state')
    parser.add_argument('--original-audit', help='unit voices: private original-audio-audit.json')
    parser.add_argument('--fallback-state', nargs='+', help='unit voices: byte-budget fallback ledgers (approved per-ID lines)')
    parser.add_argument('--compact', help='unit voices: accepted compact sources JSON (performance, attempt, regeneration_state, media_ids)')
    parser.add_argument('--state', required=True, nargs='+')
    for name in ('routing', 'production-work', 'work', 'analysis', 'original-dir',
                 'oggenc', 'wav2wem', 'vgmstream', 'ww2ogg', 'codebooks'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--jobs', type=int, default=1)
    parser.add_argument('--reselect', action='store_true', help='re-audit existing QC passes; no new encoding')
    parser.add_argument('--media-ids', help='comma-separated targets instead of every production-blocked ID')
    parser.add_argument('--source-dir', help='work folder with canonical-32k[-tail20]/ for the target sources')
    parser.add_argument('--prepare-from-state', help='tools.tts.regenerate state; prepare its accepted attempt first')
    parser.add_argument('--attempt', type=int, default=1)
    parser.add_argument('--unfiltered', action='store_true', help='try the untouched reference before any band limit')
    parser.add_argument('--below-original', action='store_true',
                        help='also allow the 7 kHz rung where the original is wider (first recovery only)')
    args = parser.parse_args()
    print(json.dumps(run(args), indent=2))


if __name__ == '__main__':
    main()
