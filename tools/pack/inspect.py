"""Read-only signed PACK inventory or one payload extraction to a new file."""
import argparse
import json
from pathlib import Path
from tools.pack.reader import ArenaPack


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pack')
    parser.add_argument('--media-id', '--entry', dest='media_id')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    pack = ArenaPack(args.pack)
    if args.media_id:
        with Path(args.output).open('xb') as stream:
            stream.write(pack.read(pack.find(args.media_id)))
    else:
        with Path(args.output).open('x', encoding='utf-8') as stream:
            json.dump({'RSA': 'PASS', 'entries': [{'path': e.path, 'offset': e.offset, 'size': e.size}
                       for e in pack.entries]}, stream, indent=2)


if __name__ == '__main__':
    main()
