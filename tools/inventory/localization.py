"""Strict local .loc reading and candidate emote event spellings.

Candidates are accepted only after their exact FNV-1 matches a real bank event;
normalizing a UI key alone is never evidence of a playable recording.
"""
import re
import struct
from tools.pack.reader import require


def loc_rows(data):
    require(len(data) >= 14 and data[:6] == b'\xff\xfeLOC\x00', 'Invalid localization header')
    version, count = struct.unpack_from('<II', data, 6)
    require(version == 1 and count <= (len(data)-14)//5, 'Unsupported/truncated localization table')
    pos, rows = 14, []
    for _ in range(count):
        row = []
        for _ in range(2):
            require(pos+2 <= len(data), 'Truncated localization string length')
            size = struct.unpack_from('<H', data, pos)[0]
            pos += 2
            require(pos+size*2 <= len(data), 'Truncated localization string')
            row.append(data[pos:pos+size*2].decode('utf-16-le'))
            pos += size*2
        require(pos < len(data) and data[pos] in (0, 1), 'Invalid localization flag')
        pos += 1
        rows.append(row)
    require(pos == len(data), 'Unconsumed localization bytes')
    return rows


def emote_spellings(stem):
    return {stem, stem.replace('-', '_'), re.sub('_+', '_', stem.replace('-', '_'))}
