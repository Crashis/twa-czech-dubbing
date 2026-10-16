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
    variants = {stem, stem.replace('-', '_'), re.sub('_+', '_', stem.replace('-', '_'))}
    # Typographic punctuation (e.g. U+2019 in "doesn’t") is absent from event names.
    return variants | {v.encode('ascii', 'ignore').decode('ascii') for v in variants}


CHAT_TAG_PREFIX = 'arena_localised_chat_tags_value_'


def chat_tag_events(rows, event_ids, actor_names, source):
    """Exact Play_<chat tag> names for real Event IDs, with the speaking owner."""
    from tools.inventory.names import fnv1
    found = {}
    for key, text in rows:
        if not key.startswith(CHAT_TAG_PREFIX):
            continue
        stem = key.removeprefix(CHAT_TAG_PREFIX)
        actor_stem = re.split('_emote_|_EMO_', stem)[0]
        short = actor_stem.split('_', 1)[-1]
        actor = next((n for n in actor_names if n.lower() == 'commander_' + short.lower()), None)
        for spelling in sorted(emote_spellings(stem)):
            name = 'Play_' + spelling
            eid = fnv1(name)
            if eid not in event_ids:
                continue
            require(eid not in found or found[eid]['key'] == key, 'Conflicting chat-tag event hash')
            found[eid] = {'name': name, 'text': text.replace('\\n', ' '), 'key': key,
                          'owner': 'commander:' + actor if actor else 'unknown:emote-owner:' + actor_stem,
                          'source': source, 'normalization': 'exact FNV-1 match against an actual bank Event ID'}
    return found
