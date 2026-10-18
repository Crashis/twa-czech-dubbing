"""Decode/QC a WEM with user-supplied vgmstream and ww2ogg executables."""
import argparse
import json
import math
from pathlib import Path
import struct
import subprocess

from tools.mod import sha256
from tools.pack.reader import require
from tools.wem.audio import compare, pcm16
from tools.wem.exact_size import chunks
from tools.wem.fingerprint import fingerprint, ogg_regranule


def run(args):
    result = subprocess.run([str(x) for x in args], capture_output=True, text=True)
    require(result.returncode == 0 and not any(word in (result.stdout + result.stderr).lower()
            for word in ('parse error', 'invalid packet', 'not a vorbis', 'failed decoding', 'decode error')),
            'External audio tool failed; inspect inputs and tool versions')


def float_peak(path):
    bodies = chunks(Path(path).read_bytes())
    fmt = bodies[b'fmt '][1]
    tag, channels, rate = struct.unpack_from('<HHI', fmt)
    if tag == 0xfffe:
        tag = struct.unpack_from('<H', fmt, 24)[0]
    require(tag == 3 and channels == 1 and struct.unpack_from('<H', fmt, 14)[0] == 32, 'Expected mono float32 decode')
    pcm = [x[0] for x in struct.iter_unpack('<f', bodies[b'data'][1])]
    require(pcm and all(math.isfinite(x) for x in pcm) and max(abs(x) for x in pcm) < 1, 'Float decode clips/is invalid')
    return {'rate': rate, 'frames': len(pcm), 'peak_linear': max(abs(x) for x in pcm)}


def validate(wem, reference, vgmstream, ww2ogg, codebooks, work, original=None, raw=None):
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    fp = fingerprint(wem)
    require(fp['fmt']['sample_rate'] == 32000 and fp['fmt']['channels'] == 1, 'Expected 32 kHz mono WEM')
    if original:
        old = fingerprint(original)
        require(fp['size'] == old['size'], 'WEM is not exact size')
        require(all(fp['fmt'][k] == old['fmt'][k] for k in ('sample_rate', 'channels', 'block_sizes', 'subtype_channel_config')), 'Original format mismatch')
    decoded, floats = work / 'decoded.wav', work / 'float.wav'
    run([vgmstream, '-i', '-o', decoded, wem])
    run([vgmstream, '-i', '-W', '4', '-o', floats, wem])
    info, pcm = pcm16(decoded)
    peak = float_peak(floats)
    require(info['rate'] == peak['rate'] == 32000 and info['frames'] == peak['frames'] == fp['fmt']['sample_count'], 'Decode sample count mismatch')
    require(not info['samples_at_or_above_full_scale'], 'PCM16 clipping')
    quality = compare(reference, decoded)
    ogg, fixed, ogg_wav = work / 'reconstructed.ogg', work / 'granules.ogg', work / 'ogg.wav'
    run([ww2ogg, wem, '-o', ogg, '--pcb', codebooks])
    ogg_regranule(ogg, fixed, fp)
    run([vgmstream, '-i', '-o', ogg_wav, fixed])
    ogg_info, other = pcm16(ogg_wav)
    require(ogg_info['rate'] == 32000 and len(other) == len(pcm), 'ww2ogg decode frame mismatch')
    require(max(abs(a - b) for a, b in zip(pcm, other)) <= 1, 'ww2ogg/direct decode mismatch')
    if raw:
        raw_decoded = work / 'raw-decoded.wav'
        run([vgmstream, '-i', '-o', raw_decoded, raw])
        raw_info, raw_pcm = pcm16(raw_decoded)
        require(raw_info['pcm_sha256'] == info['pcm_sha256'] and raw_pcm == pcm,
                'RIFF padding changed decoded PCM')
    result = {'status': 'PASS', 'wem_sha256': sha256(wem), 'size': fp['size'], 'quality': quality,
              'float_decode': peak, 'ww2ogg_decode': 'PASS',
              'raw_vs_padded_pcm': 'PASS' if raw else 'NOT_CHECKED',
              'fresh_human_listening_claimed': False}
    (work / 'validation.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('wem', 'reference', 'vgmstream', 'ww2ogg', 'codebooks', 'work'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--original')
    parser.add_argument('--raw')
    print(json.dumps(validate(**vars(parser.parse_args())), indent=2))
