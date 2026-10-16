"""Read-only Arena PFH5 parser, retained from the verified payload workflow.
Layout: tw_pack_lib 7a9d2264; XOR: RPFM cbc9626d (MIT; see third_party).
No index writer is exposed. RSA validation is mandatory on every parse.
"""
from dataclasses import dataclass
from pathlib import Path
import struct
from .signature import load_key, verify
STRING_KEY = b'#:AhppdV-!PEfz&}[]Nv?6w4guU%dF5.fq:n*-qGuhBJJBm&?2tPy!geW/+k#pG?'
SIZE_KEY = 0xE10B73F4
class FormatError(ValueError):
    pass
class SignatureError(ValueError):
    pass
def require(condition, message):
    if not condition:
        raise FormatError(message)

@dataclass(frozen=True)
class Entry:
    path: str
    raw_name: bytes
    size: int
    offset: int
    index_start: int
    index_end: int
    timestamp: bytes

class ArenaPack:
    def __init__(self, value):
        self.path = Path(value).resolve(strict=True)
        self.file_size = self.path.stat().st_size
        with self.path.open('rb') as stream:
            self.header = stream.read(48)
            require(len(self.header) == 48 and self.header[:4] == b'PFH5', 'Expected full PFH5 header')
            self.flags, deps_count, deps_size, count, index_size = struct.unpack_from('<5I', self.header, 4)
            require(self.flags & 0x100, 'Non-Arena PFH5 layout unsupported')
            require(self.flags & 15 <= 4, 'Unknown PACK type')
            require(not self.flags & ~0x1CF, 'Unknown PACK flag bits')
            require(not self.flags & 0x10, 'Encrypted payloads unsupported; alignment must not be guessed')
            require(deps_size + index_size <= self.file_size-48-256, 'Indexes exceed container bounds')
            self.dependencies_raw = stream.read(deps_size)
            self.index_raw = stream.read(index_size)
            require(len(self.index_raw) == index_size, 'Truncated file index')
            dependencies = self.dependencies_raw.split(b'\0')
            require((deps_size == 0 and deps_count == 0) or
                    (dependencies[-1] == b'' and len(dependencies)-1 == deps_count), 'Invalid pack index')
            self.payload_start = stream.tell()
        self.entries = []
        pos = 0
        data_pos = self.payload_start
        for ordinal in range(count):
            start = pos
            require(pos+4 <= len(self.index_raw), 'Truncated size field')
            size = struct.unpack_from('<I', self.index_raw, pos)[0]
            pos += 4
            if self.flags & 0x80:
                size ^= SIZE_KEY ^ ((count-1-ordinal) ^ 0xFFFFFFFF)
            timestamp = b''
            if self.flags & 0x40:
                require(pos+4 <= len(self.index_raw), 'Truncated timestamp field')
                timestamp = self.index_raw[pos:pos+4]
                pos += 4
            name = bytearray()
            for char_index in range(4096):
                require(pos < len(self.index_raw), 'Missing path terminator')
                character = self.index_raw[pos]
                pos += 1
                if self.flags & 0x80:
                    character ^= STRING_KEY[char_index % 64] ^ ((size & 255) ^ 255)
                if character == 0:
                    break
                name.append(character)
            else:
                raise FormatError('Path too long')
            path = name.decode('utf-8').replace('\\', '/')
            require(path and not path.startswith('/') and all(ord(c) >= 32 for c in path), 'Invalid internal path')
            require(not any(x in ('..', '') for x in path.split('/')) and ':' not in path, 'Unsafe internal path')
            self.entries.append(Entry(path, bytes(name), size, data_pos, start, pos, timestamp))
            data_pos += size
        require(pos == len(self.index_raw), 'File index not consumed exactly')
        require(len({e.path for e in self.entries}) == count, 'Duplicate internal paths')
        self.payload_end = data_pos
        self.appendix_size, self.appendix_offset = struct.unpack_from('<II', self.header, 0x24)
        require(self.appendix_size == 256, 'Unexpected Appendix length')
        require(self.appendix_offset == data_pos, 'Appendix offset does not match payload end')
        require(self.file_size == data_pos+256, 'Unexpected padding or truncated Appendix')
        with self.path.open('rb') as stream:
            stream.seek(data_pos)
            self.appendix = stream.read(256)
        self.key = load_key()
        if not verify(self.index_raw, self.appendix, *self.key):
            raise SignatureError('Input index RSA signature invalid')

    def find(self, media):
        media = str(media).replace('\\', '/')
        if media.isdecimal():
            media += '.wem'
        matches = [e for e in self.entries if e.path == media or ('/' not in media and Path(e.path).name == media)]
        require(len(matches) == 1, f'Expected one target entry, got {len(matches)}: {media}')
        return matches[0]

    def read(self, entry):
        with self.path.open('rb') as stream:
            stream.seek(entry.offset)
            data = stream.read(entry.size)
        require(len(data) == entry.size, 'Truncated payload')
        return data


