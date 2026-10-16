"""Offline TTS request planning only. No API client or network operations."""
import argparse
import json
from tools.mod import csv_rows
from tools.pack.reader import require


def plan(rows):
    requests = []
    for row in rows:
        model = row['model']
        require(model in ('eleven_v3', 'eleven_v4'), 'Review and set explicit model routing')
        text = row['czech'].strip()
        tags = row.get('delivery_tags', '').strip()
        require(text, 'Empty Czech text')
        payload = (tags + ' ' if tags else '') + text
        requests.append({'media_id': row['media_id'], 'model': model, 'text': payload,
                         'unicode_codepoints': len(payload), 'generation_limit': 1})
    require(len({r['media_id'] for r in requests}) == len(requests), 'Duplicate Media IDs')
    return {'offline_only': True, 'requests': requests, 'unicode_codepoints': sum(r['unicode_codepoints'] for r in requests),
            'pricing': 'Not a current price quote. Historical Batch 04 counted tags, spaces and punctuation.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    with open(args.output, 'x', encoding='utf-8') as stream:
        json.dump(plan(csv_rows(args.csv)), stream, ensure_ascii=False, indent=2)
