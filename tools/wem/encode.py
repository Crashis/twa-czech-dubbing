"""Bounded offline encoding search against an unchanged 32 kHz PCM reference."""
import argparse
import json
from pathlib import Path

from tools.mod import sha256
from tools.pack.reader import require
from tools.wem.audio import compare, pcm16
from tools.wem.exact_size import pad
from tools.wem.validate import run


def search(source, output, size, media_id, oggenc, wav2wem, vgmstream, work,
           decimal_separator=',', advanced_option=()):
    source, output, work = Path(source).resolve(strict=True), Path(output).resolve(), Path(work).resolve()
    require(not output.exists() and str(media_id).isdecimal(), 'Output exists or invalid Media ID')
    info, _ = pcm16(source)
    require(info['rate'] == 32000, 'Prepare 32 kHz mono PCM16 first')
    work.mkdir(parents=True, exist_ok=False)
    trials, passing, visited = [], [], set()
    original_sha = sha256(source)

    def trial(q):
        q = round(q, 4)
        if q in visited:
            return False
        visited.add(q)
        stem = work / f'q{q:.4f}'
        ogg, raw, decoded = Path(str(stem) + '.ogg'), Path(str(stem) + '.wem'), Path(str(stem) + '.wav')
        args = [oggenc, source, '-q', f'{q:.4f}'.replace('.', decimal_separator), '-o', ogg, '-s', str(media_id)]
        for option in advanced_option:
            args += ['--advanced-encode-option', option]
        run(args)
        run([wav2wem, '-no-hash', '-o', raw, ogg])
        item = {'quality': q, 'raw_bytes': raw.stat().st_size, 'status': 'DOES_NOT_FIT'}
        try:
            final = pad(raw.read_bytes(), size)
        except ValueError:
            final = None
        if final is not None:
            run([vgmstream, '-i', '-o', decoded, raw])
            try:
                item['comparison'] = compare(source, decoded)
                item['status'] = 'PASS'
                passing.append((q, final))
            except ValueError:
                item['status'] = 'QUALITY_FAIL'
        trials.append(item)
        (work / 'trials.json').write_text(json.dumps({'source_sha256': original_sha, 'reference_filtered': False,
              'advanced_options': list(advanced_option), 'trials': trials}, indent=2), encoding='utf-8')
        return item['status'] == 'PASS'

    first = None
    for step in range(45):
        q = 10 - step * .25
        if trial(q):
            first = q
            break
    if first is not None:
        for step in range(1, 10):
            q = round(first + .25 - step * .025, 4)
            if -1 <= q <= 10:
                trial(q)
    require(passing, 'No fitting encoding passed QC; review optional encoder profiles without changing the reference')
    require(sha256(source) == original_sha, 'QC reference changed during search')
    quality, final = max(passing, key=lambda item: item[0])
    with output.open('xb') as stream:
        stream.write(final)
    return {'status': 'ENCODED_REQUIRES_FULL_VALIDATION', 'quality': quality, 'size': len(final), 'sha256': sha256(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'output', 'media-id', 'oggenc', 'wav2wem', 'vgmstream', 'work'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--size', type=int, required=True)
    parser.add_argument('--decimal-separator', choices=[',', '.'], default=',')
    parser.add_argument('--advanced-option', action='append', default=[])
    print(json.dumps(search(**vars(parser.parse_args())), indent=2))
