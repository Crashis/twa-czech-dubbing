"""Read-only modern Wwise Vorbis structural inspector (Python standard library).

Layout references: pinned ww2ogg 0.24 wwriff.cpp and vgmstream wwise.c.
Stripped setup follows the Vorbis I floor1/residue/mapping/mode grammar,
with Wwise's omitted constant fields and external 10-bit codebook indices.
No writes to the input. Existing outputs are never overwritten.
"""
from tools.pack.reader import require
from pathlib import Path
import argparse, struct, hashlib, json
ROOT = Path(__file__).resolve().parents[2]

class Bits:

    def __init__(self, data):
        self.data, self.pos = (data, 0)

    def read(self, n):
        if self.pos + n > len(self.data) * 8:
            raise ValueError('truncated setup')
        v = 0
        for i in range(n):
            v |= (self.data[self.pos // 8] >> self.pos % 8 & 1) << i
            self.pos += 1
        return v

def stripped_setup(data, channels):
    b = Bits(data)
    books = b.read(8) + 1
    ids = [b.read(10) for _ in range(books)]
    floors = b.read(6) + 1
    for _ in range(floors):
        partitions = b.read(5)
        classes = [b.read(4) for _ in range(partitions)]
        dims = []
        for _ in range(max(classes, default=0) + 1):
            dims.append(b.read(3) + 1)
            sub = b.read(2)
            if sub:
                require(b.read(8) < books, 'Invalid Wwise structure')
            for _ in range(1 << sub):
                require(b.read(8) <= books, 'Invalid Wwise structure')
        b.read(2)
        rb = b.read(4)
        for c in classes:
            for _ in range(dims[c]):
                b.read(rb)
    residues = b.read(6) + 1
    residue_types = []
    for _ in range(residues):
        typ = b.read(2)
        require(typ <= 2, 'Invalid Wwise structure')
        residue_types.append(typ)
        b.read(24)
        b.read(24)
        b.read(24)
        count = b.read(6) + 1
        require(b.read(8) < books, 'Invalid Wwise structure')
        cascades = []
        for _ in range(count):
            lo = b.read(3)
            hi = b.read(5) if b.read(1) else 0
            cascades.append(lo + 8 * hi)
        for c in cascades:
            for bit in range(8):
                if c & 1 << bit:
                    require(b.read(8) < books, 'Invalid Wwise structure')
    mappings = b.read(6) + 1
    for _ in range(mappings):
        subs = b.read(4) + 1 if b.read(1) else 1
        if b.read(1):
            steps = b.read(8) + 1
            for _ in range(steps):
                mag = b.read((channels - 1).bit_length())
                ang = b.read((channels - 1).bit_length())
                require(mag != ang and mag < channels and (ang < channels), 'Invalid Wwise structure')
        require(b.read(2) == 0, 'Invalid Wwise structure')
        if subs > 1:
            for _ in range(channels):
                require(b.read(4) < subs, 'Invalid Wwise structure')
        for _ in range(subs):
            require(b.read(8) == 0, 'Invalid Wwise structure')
            require(b.read(8) < floors, 'Invalid Wwise structure')
            require(b.read(8) < residues, 'Invalid Wwise structure')
    modes = b.read(6) + 1
    flags = []
    mode_mapping = []
    for _ in range(modes):
        flags.append(b.read(1))
        m = b.read(8)
        require(m < mappings, 'Invalid Wwise structure')
        mode_mapping.append(m)
    used = b.pos
    remaining = len(data) * 8 - used
    require(0 <= remaining < 8 and b.read(remaining) == 0, 'nonzero trailing setup bits')
    return {'codebook_count': books, 'external_codebook_ids': ids, 'floor_count': floors, 'floor_types': [1] * floors, 'residue_count': residues, 'residue_types': residue_types, 'mapping_count': mappings, 'mode_count': modes, 'mode_blockflags': flags, 'mode_mapping': mode_mapping, 'mode_bits': (modes - 1).bit_length(), 'parsed_bits': used, 'zero_padding_bits': remaining, 'full_setup': False, 'inline_codebooks': False, 'stripped_setup': True, 'codebook_reference_bits': 10}

def fingerprint(path):
    path = Path(path)
    data = path.read_bytes()
    magic = data[:4]
    require(magic in (b'RIFF', b'RIFX') and data[8:12] == b'WAVE', 'Invalid Wwise structure')
    endian = '<' if magic == b'RIFF' else '>'
    u16 = lambda b, o: struct.unpack_from(endian + 'H', b, o)[0]
    u32 = lambda b, o: struct.unpack_from(endian + 'I', b, o)[0]
    require(u32(data, 4) + 8 == len(data), 'Invalid Wwise structure')
    chunks = []
    bodies = {}
    pos = 12
    while pos < len(data):
        tag = data[pos:pos + 4].decode('ascii')
        n = u32(data, pos + 4)
        require(pos + 8 + n <= len(data), 'Invalid Wwise structure')
        chunks.append({'id': tag, 'header_offset': pos, 'payload_offset': pos + 8, 'size': n})
        require(tag not in bodies, 'Invalid Wwise structure')
        bodies[tag] = data[pos + 8:pos + 8 + n]
        pos += 8 + n + (n % 2 if pos + 8 + n < len(data) else 0)
    require(pos == len(data), 'Invalid Wwise structure')
    f = bodies['fmt ']
    require(len(f) == 66 and 'vorb' not in bodies and (u16(f, 0) == 65535), 'Invalid Wwise structure')
    fields = {'format_tag': '0xffff', 'channels': u16(f, 2), 'sample_rate': u32(f, 4), 'average_bytes_per_second': u32(f, 8), 'block_align': u16(f, 12), 'bits_per_sample': u16(f, 14), 'cbSize': u16(f, 16), 'extension_unknown': u16(f, 18), 'subtype_channel_config': hex(u32(f, 20)), 'sample_count': u32(f, 24), 'loop_start_packet_offset': u32(f, 28), 'loop_end_packet_offset': u32(f, 32), 'loop_begin_extra': u16(f, 36), 'loop_end_extra': u16(f, 38), 'seek_table_size': u32(f, 40), 'audio_offset_in_data': u32(f, 44), 'max_packet_size': u16(f, 48), 'last_granule_extra': u16(f, 50), 'decode_alloc_size': u32(f, 52), 'decode_x64_alloc_size': u32(f, 56), 'codebook_hash_field': hex(u32(f, 60)), 'blocksize_exponents': [f[64], f[65]], 'block_sizes': [1 << f[64], 1 << f[65]]}
    d = bodies['data']
    seek = fields['seek_table_size']
    audio = fields['audio_offset_in_data']
    require(seek % 4 == 0 and 0 <= seek < audio <= len(d), 'Invalid Wwise structure')
    setup_size = u16(d, seek)
    require(seek + 2 + setup_size == audio, 'Invalid Wwise structure')
    setup = stripped_setup(d[seek + 2:audio], fields['channels'])
    packets = []
    off = audio
    previous = None
    cum = 0
    while off < len(d):
        size = u16(d, off)
        require(size > 0 and off + 2 + size <= len(d), 'Invalid Wwise structure')
        mode = d[off + 2] & (1 << setup['mode_bits']) - 1
        require(mode < setup['mode_count'], 'Invalid Wwise structure')
        bs = fields['block_sizes'][setup['mode_blockflags'][mode]]
        if previous is not None:
            cum += (previous + bs) // 4
        previous = bs
        packets.append({'offset_in_data': off, 'offset_from_setup': off - seek, 'size': size, 'mode': mode, 'block_size': bs, 'cumulative_samples': cum})
        off += 2 + size
    require(off == len(d) and max((p['size'] for p in packets)) == fields['max_packet_size'], 'Invalid Wwise structure')
    require(cum - fields['last_granule_extra'] == fields['sample_count'], (cum, fields))
    by_offset = {p['offset_from_setup']: p for p in packets}
    s = 0
    o = 0
    seeks = []
    for off in range(0, seek, 4):
        ds = u16(d, off)
        do = u16(d, off + 2)
        s += ds
        o += do
        target = by_offset.get(o)
        seeks.append({'sample_delta': ds, 'byte_delta': do, 'sample': s, 'offset_from_setup': o, 'points_to_packet_boundary': target is not None, 'matches_packet_sample': target is not None and target['cumulative_samples'] == s})
    require(all((x['points_to_packet_boundary'] and x['matches_packet_sample'] for x in seeks)), 'Invalid Wwise structure')
    result = {'path': str(path.resolve()), 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'container': magic.decode(), 'form': 'WAVE', 'endian': 'little' if endian == '<' else 'big', 'riff_declared_size': u32(data, 4), 'terminal_data_unpadded': bool(len(data) % 2), 'chunks': chunks, 'fmt_chunk_size': len(f), 'fmt_raw_hex': f.hex(), 'fmt': fields, 'vorb': {'standalone_present': False, 'embedded_in_fmt': True, 'embedded_offset': 24, 'embedded_length': 42}, 'seek': {'standalone_chunk_present': 'seek' in bodies, 'in_data': True, 'size': seek, 'entry_size': 4, 'entry_format': 'uint16 sample delta + uint16 byte delta, relative to setup packet', 'entries': seeks}, 'setup': {'packet_header_offset_in_data': seek, 'payload_size': setup_size, 'sha256': hashlib.sha256(d[seek + 2:audio]).hexdigest(), **setup}, 'packets': {'header_bytes': 2, 'header_format': 'uint16 payload length, little endian', 'granule_field_present': False, 'mod_packets': True, 'no_mod_packets': False, 'count': len(packets), 'ends_exactly_at_data_end': True, 'calculated_full_samples': cum, 'mode_counts': {str(m): sum((p['mode'] == m for p in packets)) for m in range(setup['mode_count'])}, 'entries': packets}, 'duration_seconds': fields['sample_count'] / fields['sample_rate'], 'smpl_present': 'smpl' in bodies, 'akd_raw_hex': bodies.get('akd ', b'').hex(), 'hash_raw_hex': bodies.get('hash', b'').hex(), 'exact_wwise_sdk_build': 'UNKNOWN', 'original_quality': 'UNKNOWN', 'scope': 'modern fmt=0x42 Wwise Vorbis only; codebook library requires separate probes'}
    return result

def write_json(path, obj):
    p = Path(path).resolve()
    require(not p.exists(), 'Output already exists')
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')

def ogg_regranule(input_path, output_path, fp):
    """ww2ogg no-granule output uses zero granules. Rebuild page granules/CRC.

    Each ww2ogg page ends exactly one packet. Codec packets are untouched.
    Final granule uses WEM sample_count to discard codec end padding.
    """
    source = Path(input_path).read_bytes()
    pos = 0
    out = bytearray()
    packet_idx = 0
    prev = None
    cum = 0
    while pos < len(source):
        require(source[pos:pos + 4] == b'OggS', 'Invalid Wwise structure')
        segments = source[pos + 26]
        n = sum(source[pos + 27:pos + 27 + segments])
        end = pos + 27 + segments + n
        page = bytearray(source[pos:end])
        payload = page[27 + segments:]
        require(page[27 + segments - 1] < 255 and (not page[5] & 1), 'Invalid Wwise structure')
        if packet_idx >= 3:
            mode = payload[0] >> 1 & (1 << fp['setup']['mode_bits']) - 1
            bs = fp['fmt']['block_sizes'][fp['setup']['mode_blockflags'][mode]]
            if prev is not None:
                cum += (prev + bs) // 4
            prev = bs
            granule = fp['fmt']['sample_count'] if page[5] & 4 else cum
        else:
            granule = 0
        struct.pack_into('<q', page, 6, granule)
        struct.pack_into('<I', page, 22, 0)
        crc = 0
        for byte in page:
            crc ^= byte << 24
            for _ in range(8):
                crc = (crc << 1 ^ 79764919) & 4294967295 if crc & 2147483648 else crc << 1 & 4294967295
        struct.pack_into('<I', page, 22, crc)
        out.extend(page)
        packet_idx += 1
        pos = end
    p = Path(output_path).resolve()
    require(not p.exists(), 'Output already exists')
    p.write_bytes(out)
    return {'packet_count': packet_idx, 'final_calculated_samples': cum, 'final_granule': fp['fmt']['sample_count']}
if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('input')
    ap.add_argument('output')
    a = ap.parse_args()
    result = fingerprint(a.input)
    write_json(a.output, result)
    print(json.dumps({k: result[k] for k in ['size', 'sha256', 'fmt', 'setup', 'duration_seconds']}))
