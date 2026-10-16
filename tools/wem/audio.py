"""PCM16 mono QC against an unchanged reference (standard library only)."""
import argparse
from array import array
import hashlib
import json
import math
import sys
import wave

from tools.pack.reader import require


def pcm16(path):
    with wave.open(str(path), 'rb') as audio:
        require(audio.getnchannels() == 1 and audio.getsampwidth() == 2 and audio.getcomptype() == 'NONE', 'Expected mono PCM16')
        rate, frames = audio.getframerate(), audio.getnframes()
        raw = audio.readframes(frames)
    require(len(raw) == frames * 2 and frames > 0, 'Empty/truncated PCM')
    pcm = array('h', raw)
    if sys.byteorder != 'little':
        pcm.byteswap()
    peak = max(abs(x) for x in pcm) / 32768
    rms = math.sqrt(sum(float(x) ** 2 for x in pcm) / frames) / 32768
    info = {'rate': rate, 'frames': frames, 'channels': 1, 'bits': 16, 'duration_seconds': frames / rate,
            'peak_linear': peak, 'rms_dbfs': 20 * math.log10(max(rms, 1e-30)),
            'samples_at_or_above_full_scale': sum(x in (-32768, 32767) for x in pcm),
            'pcm_sha256': hashlib.sha256(raw).hexdigest()}
    return info, pcm


def compare(reference, decoded):
    left, x = pcm16(reference)
    right, y = pcm16(decoded)
    require(left['rate'] == right['rate'] and len(x) == len(y), 'Rate/frame count mismatch; do not realign/truncate to pass QC')
    xx = sum(float(a) * a for a in x)
    yy = sum(float(b) * b for b in y)
    xy = sum(float(a) * b for a, b in zip(x, y))
    error = sum(float(a - b) ** 2 for a, b in zip(x, y))
    require(xx > 0 and yy > 0, 'Silent QC input')
    correlation = xy / math.sqrt(xx * yy)
    snr = 10 * math.log10(xx / max(error, 1e-30))
    require(correlation > .95 and snr > 15 and right['samples_at_or_above_full_scale'] == 0, 'Audio fidelity/clipping QC failed')
    return {'status': 'PASS', 'correlation': correlation, 'snr_db': snr, 'decoded': right}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference')
    parser.add_argument('decoded')
    args = parser.parse_args()
    print(json.dumps(compare(args.reference, args.decoded), indent=2))
