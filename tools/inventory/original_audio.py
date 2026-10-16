"""Extract/decode canonical originals to a private directory, never the repo.

This module has no network, TTS, installer or game-launch functionality.
"""
from array import array
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import wave

from tools.pack.reader import ArenaPack, require
from tools.wem.exact_size import chunks


def sha256(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def private_directory(path, forbidden):
    path = Path(path).resolve()
    for root in forbidden:
        root = Path(root).resolve()
        require(not path.is_relative_to(root), 'Original audio output must be outside protected directories')
    path.mkdir(parents=True, exist_ok=True)
    return path


def original_format(raw):
    fmt = chunks(raw)[b'fmt '][1]
    codec, channels, rate = struct.unpack_from('<HHI', fmt)
    require(codec == 0xffff and len(fmt) == 66, 'Unsupported original voice codec')
    frames = struct.unpack_from('<I', fmt, 24)[0]
    require(rate > 0 and channels > 0 and frames > 0, 'Invalid original voice format')
    return {'sample_rate': rate, 'channels': channels, 'sample_count': frames,
            'original_duration': frames / rate}


def decode_one(pack, entry, folder, decoder, cached=None):
    raw = pack.read(entry)
    info = original_format(raw)
    mid = Path(entry.path).stem
    wem = folder / 'original-wem' / (mid + '.wem')
    wav = folder / 'decoded-wav' / (mid + '.wav')
    if wem.exists():
        require(wem.read_bytes() == raw, 'Existing original WEM differs from canonical PACK')
    else:
        with wem.open('xb') as f:
            f.write(raw)
    if wav.exists():
        require(cached and cached['original_wem_sha256'] == hashlib.sha256(raw).hexdigest(),
                'Existing decoded WAV lacks matching original provenance; verify it separately before resuming')
    if not wav.exists():
        run = subprocess.run([str(decoder), '-i', '-o', str(wav), str(wem)],
                             capture_output=True, timeout=120)
        require(run.returncode == 0 and wav.exists(), 'Original decode failed: ' + mid)
    with wave.open(str(wav), 'rb') as w:
        require(w.getsampwidth() == 2 and w.getcomptype() == 'NONE', 'Expected direct PCM16 decode')
        require(w.getnchannels() == info['channels'] and w.getframerate() == info['sample_rate']
                and w.getnframes() == info['sample_count'], 'Decoded original format/sample count mismatch')
        pcm = w.readframes(w.getnframes())
    require(len(pcm) == info['sample_count'] * info['channels'] * 2, 'Truncated decoded original')
    if cached:
        require(hashlib.sha256(pcm).hexdigest() == cached['pcm_sha256'], 'Cached decoded original PCM changed')
    values = array('h', pcm)
    if sys.byteorder != 'little':
        values.byteswap()
    peak = max(abs(v) for v in values)
    return info | {'media_id': int(mid), 'wem_filename': mid + '.wem', 'pack_path': entry.path,
                   'pack_offset': entry.offset, 'original_size_bytes': entry.size,
                   'original_wem_sha256': hashlib.sha256(raw).hexdigest(),
                   'pcm_sha256': hashlib.sha256(pcm).hexdigest(), 'decode_status': 'PASS_PCM16',
                   'silent_placeholder': 'YES' if peak == 0 else 'NO', 'audio_peak_pcm16': peak,
                   'clipped_sample_count': sum(v in (-32768, 32767) for v in values)}


def extract_decode(pack_path, expected_sha256, ids, folder, decoder, forbidden, workers=4):
    require(sha256(pack_path) == expected_sha256, 'Unknown original PACK SHA-256: STOP')
    pack = ArenaPack(pack_path)  # validates RSA before extraction
    folder = private_directory(folder, forbidden)
    for name in ['original-wem', 'decoded-wav']:
        (folder / name).mkdir(exist_ok=True)
    by_path = {e.path: e for e in pack.entries}
    paths = ['audio/wwise/' + str(mid) + '.wem' for mid in sorted(set(ids), key=int)]
    require(all(p in by_path for p in paths), 'Missing original external WEM in canonical PACK')
    entries = [by_path[p] for p in paths]
    audit_path = folder / 'original-audio-audit.json'
    cached = json.loads(audit_path.read_text(encoding='utf-8')) if audit_path.exists() else {}
    if cached:
        require(cached['canonical_pack_sha256'] == expected_sha256 and cached['decoder_sha256'] == sha256(decoder),
                'Cached original provenance or decoder changed')
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda e: decode_one(pack, e, folder, decoder, cached.get('results', {}).get(Path(e.path).stem)), entries))
    result = {'canonical_pack_sha256': expected_sha256, 'RSA': 'PASS',
              'decoder_sha256': sha256(decoder), 'results': {str(r['media_id']): r for r in results}}
    (folder / 'original-audio-audit.json').write_text(json.dumps(result, indent=1), encoding='utf-8')
    return result


def verify_existing(folder):
    """Read-only verification of every privately retained original WEM and WAV."""
    folder = Path(folder)
    audit = json.loads((folder/'original-audio-audit.json').read_text(encoding='utf-8'))
    for mid, fact in audit['results'].items():
        require(mid.isdecimal(), 'Invalid original audio cache ID')
        wem = folder/'original-wem'/(mid+'.wem')
        require(wem.stat().st_size == fact['original_size_bytes'] and sha256(wem) == fact['original_wem_sha256'], 'Original WEM cache changed')
        with wave.open(str(folder/'decoded-wav'/(mid+'.wav')), 'rb') as w:
            require(w.getsampwidth() == 2 and w.getframerate() == fact['sample_rate']
                    and w.getnchannels() == fact['channels'] and w.getnframes() == fact['sample_count'], 'Original WAV format changed')
            raw = w.readframes(w.getnframes())
        require(hashlib.sha256(raw).hexdigest() == fact['pcm_sha256'], 'Original WAV PCM changed')
    return {'status': 'PASS', 'original_wem_files': len(audit['results']), 'original_wav_files': len(audit['results'])}
