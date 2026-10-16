"""Rank original WAVs by whole-signal, gain/polarity/offset-tolerant correlation.

Requires local NumPy. Results are evidence for review, never automatic ownership
or transcript labels. Different performances with the same text are not merged.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import wave


def read_pcm(path):
    import numpy as np
    with wave.open(str(path), 'rb') as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise ValueError('Expected mono PCM16')
        rate = w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype(np.float64)
    return rate, pcm


def correlation(left, right, max_shift):
    import numpy as np
    length = len(left)+len(right)-1
    size = 1 << (length-1).bit_length()
    dot = np.fft.irfft(np.fft.rfft(left, size)*np.fft.rfft(right[::-1], size), size)[:length]
    first, last = max(0, len(right)-1-max_shift), min(length, len(right)+max_shift)
    index = first + int(np.argmax(np.abs(dot[first:last])))
    norm = float(np.linalg.norm(left)*np.linalg.norm(right))
    return {'correlation': float(dot[index]/norm) if norm else 0.0, 'shift_samples': index-len(right)+1}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', required=True)
    parser.add_argument('--candidates', action='append', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    reference = Path(args.reference).resolve(strict=True)
    rate, pcm = read_pcm(reference)
    def inspect(path):
        other_rate, other = read_pcm(path)
        if other_rate != rate or abs(len(other)-len(pcm)) > rate//2:
            return None
        return {'candidate': path.name, 'candidate_directory': path.parent.name,
                'sample_count': len(other), **correlation(pcm, other, rate//2)}
    files = [p for d in args.candidates for p in Path(d).glob('*.wav') if p.resolve() != reference]
    with ThreadPoolExecutor(max_workers=4) as pool:
        matches = sorted((r for r in pool.map(inspect, files) if r), key=lambda r: -abs(r['correlation']))[:20]
    result = {'reference_media_id': reference.stem, 'reference_sample_count': len(pcm), 'sample_rate': rate,
              'method': 'whole-signal normalized PCM cross-correlation; no time stretching', 'matches': matches}
    Path(args.output).write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
