"""Insert RIFF JUNK without changing codec chunks; never truncate encoded audio."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from tools.pack.reader import require


def chunks(raw):
    require(raw[:4] == b'RIFF' and raw[8:12] == b'WAVE', 'Expected little-endian RIFF/WAVE')
    require(len(raw) >= 12 and struct.unpack_from('<I', raw, 4)[0] + 8 == len(raw), 'RIFF size mismatch')
    result = {}
    pos = 12
    while pos < len(raw):
        require(pos + 8 <= len(raw), 'Truncated chunk header')
        tag = raw[pos:pos + 4]
        size = struct.unpack_from('<I', raw, pos + 4)[0]
        end = pos + 8 + size
        require(end <= len(raw) and tag not in result, 'Truncated/duplicate RIFF chunk')
        result[tag] = (pos, raw[pos + 8:end])
        # Arena/ww2ogg accept an odd terminal data chunk without an alignment byte.
        pos = end + (size % 2 if end < len(raw) else 0)
    require(pos == len(raw) and b'fmt ' in result and b'data' in result, 'Invalid RIFF chunks')
    return result


def pad(raw, target):
    original = chunks(raw)
    require(b'JUNK' not in original, 'Input already has JUNK; encode a fresh candidate')
    at, data = original[b'data']
    if len(data) % 2 and at + 8 + len(data) + 1 == len(raw):
        require(raw[-1:] == b'\0', 'Nonzero terminal alignment byte')
        raw = bytearray(raw[:-1])
        struct.pack_into('<I', raw, 4, len(raw) - 8)
        raw = bytes(raw)
    extra = target - len(raw)
    require(extra == 0 or extra >= 8 and extra % 2 == 0, 'No valid exact-size JUNK fit; choose another encoding')
    if extra:
        at = chunks(raw)[b'data'][0]
        raw = bytearray(raw[:at] + b'JUNK' + struct.pack('<I', extra - 8) + bytes(extra - 8) + raw[at:])
        struct.pack_into('<I', raw, 4, len(raw) - 8)
        raw = bytes(raw)
    after = chunks(raw)
    require(len(raw) == target and all(after[tag][1] == body for tag, (_, body) in original.items()), 'Padding changed codec chunks')
    return raw


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input')
    parser.add_argument('output')
    parser.add_argument('--size', type=int, required=True)
    args = parser.parse_args()
    result = pad(Path(args.input).read_bytes(), args.size)
    with Path(args.output).open('xb') as stream:
        stream.write(result)
    print(json.dumps({'size': len(result), 'sha256': hashlib.sha256(result).hexdigest()}))
