"""Build an offline, commander-only Czech script and future TTS request plan.

No network, credentials, generation, audio encoding or game installation.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path

from tools.inventory.research_metadata import FINAL_RESOLUTIONS, read_csv, validate_research, write_csv
from tools.pack.reader import require
from tools.resources import ROOT


VOICE_FIELDS = '''media_id english_text czech_text category trigger transcript_confidence
translation_status delivery_style recommended_model recommended_tags original_duration
original_size_bytes duplicate_group tts_performance_group tts_source_media_id
wem_budget_risk notes bank decision_tree_path sample_rate channels sample_count
original_wem_sha256 pcm_sha256 original_wem_identical_ids
archive_wav_reference transcript_resolution'''.split()
PLAN_FIELDS = '''tts_performance_group tts_source_media_id member_media_ids media_ids_total
english_text czech_text translation_status delivery_style recommended_model
recommended_tags original_duration original_size_bytes wem_budget_risk
original_wem_identical_ids pcm_sha256 notes'''.split()
PILOT_EXTRAS = ['english', 'czech', 'translation_status', 'recommended_tags',
                'tts_performance_group', 'tts_source_media_id', 'wem_budget_risk',
                'original_wem_identical_ids']
REVIEW_FIELDS = '''media_id current_transcript final_transcript evidence transcript_confidence
transcript_resolution source_transcript_resolution category trigger original_duration
original_size_bytes decision_tree_path bank event_id container_id sound_id
archive_wav_reference'''.split()
RISK_ORDER = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2}


def english_key(value):
    return ' '.join(value.casefold().split())


MEMORY_FIELDS = ['english_text', 'czech_text']
DELIVERY_FIELDS = ['delivery_style', 'recommended_model', 'recommended_tags']
V3_STYLES = {'BATTLE_SHOUT', 'CHARGE', 'RAGE', 'FIERCE', 'ANGRY_SHOUT', 'URGENT_SHOUT'}


def check_delivery(style, model, tags):
    """eleven_v3 is reserved for genuinely shouted, expressive performances."""
    properties = [p.strip() for p in tags[1:-1].split(',')] if tags.startswith('[') and tags.endswith(']') else []
    require(1 <= len(properties) <= 2 and all(properties), 'Delivery tags need one or two properties: ' + tags)
    require(model in {'eleven_v3', 'eleven_v4'}, 'Unknown TTS model route: ' + model)
    require((model == 'eleven_v3') == (style in V3_STYLES) == ('shouting' in properties),
            'eleven_v3 only for shouted expressive delivery: ' + style + ' ' + tags)
    return style, model, tags


def read_memory(path):
    """Two-column memory, optionally with reviewed per-phrase delivery decisions."""
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        require(reader.fieldnames in (MEMORY_FIELDS, MEMORY_FIELDS + DELIVERY_FIELDS),
                'Translation memory requires english_text/czech_text and optional delivery columns')
        memory, decisions = {}, {}
        for row in reader:
            key = english_key(row['english_text'])
            require(key and row['czech_text'].strip() and key not in memory, 'Blank or duplicate translation memory entry')
            memory[key] = row['czech_text'].strip()
            values = [(row.get(f) or '').strip() for f in DELIVERY_FIELDS]
            if any(values):
                decisions[key] = check_delivery(*values)
    return memory, decisions


def translation_memory(path):
    return read_memory(path)[0]


def performance_key(row, czech):
    """The original recording and intended spoken wording must both agree."""
    require(row['pcm_sha256'] and int(row['sample_count']) > 0, 'Missing original recording fingerprint')
    return (row['sample_rate'], row['channels'], row['sample_count'], row['pcm_sha256'],
            english_key(row['english_text']) or 'UNRESOLVED:'+row['media_id'], czech)


def delivery(group, commander):
    trigger = ' '.join(r['trigger'].lower() for r in group)
    strong = any('battlecry' in r['trigger'].lower() or 'warcry' in r['trigger'].lower()
                 or r['category'] == 'ABILITY' and 'shield bash' in r['trigger'].lower()
                    and r['english_text'].isupper()
                 or r['category'] == 'ABILITY' and 'wrath of mars' in r['trigger'].lower()
                    and r['english_text'].isupper() for r in group)
    if strong:
        return 'BATTLE_SHOUT', 'eleven_v3', '[fierce, shouting]' if commander == 'leonidas' else '[shouting, commanding]'
    categories = {r['category'] for r in group}
    if 'VICTORY' in categories or ('BATTLE_EVENT' in categories and 'winning' in trigger):
        return 'TRIUMPHANT', 'eleven_v4', '[triumphant]'
    if 'DEFEAT' in categories:
        return 'DEFIANT', 'eleven_v4', '[defiant]'
    if 'BATTLE_EVENT' in categories and any(x in trigger for x in ['under attack', 'damaged', 'firing on', 'damages allies']):
        return 'URGENT_COMMAND', 'eleven_v4', '[urgent, commanding]'
    if 'DEATH_REACTION' in categories:
        return 'SERIOUS', 'eleven_v4', '[serious, commanding]'
    if any('intimidate' in r['trigger'].lower() for r in group):
        return 'THREATENING', 'eleven_v4', '[threatening, restrained]'
    if 'FRONTEND' in categories or any('quote' in r['trigger'].lower() for r in group):
        return ('PROUD', 'eleven_v4', '[proud, authoritative]') if commander == 'leonidas' else (
            'CALM_COMMANDING', 'eleven_v4', '[calm, commanding]')
    if 'EMOTE' in categories and any('affirmative' in r['trigger'].lower() for r in group):
        return ('PROUD', 'eleven_v4', '[proud, authoritative]') if commander == 'leonidas' else (
            'CALM_COMMANDING', 'eleven_v4', '[calm, commanding]')
    return ('AUTHORITATIVE', 'eleven_v4', '[authoritative]') if commander == 'leonidas' else (
        'CALM_COMMANDING', 'eleven_v4', '[serious, commanding]')


# Hannibal's runtime-reviewed routing (42 of 305 lines on eleven_v3): battle
# cries, charge-type/aggressive unit orders and urgent or angry announcer yells.
# Standard commands stay on eleven_v4. Ability names follow the research trigger text.
V3_ORDER_ABILITIES = {'charge', 'unit manual charge', 'cavalry charge', 'infantry charge', 'frenzied charge',
                      'heavy infantry charge', 'unit light chase stance', 'spear piercing blows',
                      'unit spear piercing blows', 'sword heavy strikes', 'unit sword heavy strikes',
                      'strain', 'push', 'pursuit', 'vicious assault', 'execute', 'berserk'}
# Friendly-fire and winning-timer states default to v4: Hannibal used v3 there only for an
# explicit "Stop!/Cease fire!" or "finish them" yell, which a reviewed phrase decision records.
V3_BATTLE_STATES = {'your base is under attack': 'urgent_shout', 'one of your units is attacked': 'urgent_shout',
                    'time running out while your team is losing': 'urgent_shout',
                    'one of your units routes': 'angry_shout'}
VOICE_PROFILES = {
    # Escaped gladiator and rebel leader: direct, hard, defiant, never aristocratic.
    'spartacus': {'shout': ('BATTLE_SHOUT', '[fierce, shouting]'),
                  'urgent_shout': ('URGENT_SHOUT', '[urgent, shouting]'), 'angry_shout': ('ANGRY_SHOUT', '[angry, shouting]'),
                  'shout_abilities': {'blaze of glory', 'uprising'},
                  'frontend': ('DEFIANT', '[defiant, proud]'), 'quote': ('DEFIANT', '[defiant]'),
                  'affirmative': ('ENCOURAGING', '[encouraging]'), 'negative': ('DISAPPOINTED', '[disappointed]'),
                  'getready': ('URGENT_COMMAND', '[urgent, commanding]'), 'intimidate': ('THREATENING', '[threatening, restrained]'),
                  'victory': ('TRIUMPHANT', '[triumphant]'), 'defeat': ('DEFIANT', '[defiant]'),
                  'urgent': ('URGENT_COMMAND', '[urgent, commanding]'), 'reaction': ('TRIUMPHANT', '[triumphant]'),
                  'own_death': ('FIERCE', '[defiant, shouting]'),
                  'tutorial': ('DETERMINED', '[determined, commanding]'), 'default': ('DETERMINED', '[determined, commanding]')},
    # Roman field commander: disciplined, confident and precise; harder than Scipio's strategic calm.
    'germanicus': {'shout': ('BATTLE_SHOUT', '[shouting, commanding]'),
                   'urgent_shout': ('URGENT_SHOUT', '[urgent, shouting]'), 'angry_shout': ('ANGRY_SHOUT', '[angry, shouting]'),
                   'shout_abilities': {'heavy infantry charge'},
                   'frontend': ('PROUD', '[proud, authoritative]'), 'quote': ('PROUD', '[proud, authoritative]'),
                   'affirmative': ('CONFIDENT', '[confident]'), 'negative': ('STERN', '[stern]'),
                   'getready': ('FIELD_COMMAND', '[firm, commanding]'), 'intimidate': ('THREATENING', '[threatening, restrained]'),
                   'victory': ('TRIUMPHANT', '[triumphant]'), 'defeat': ('DEFIANT', '[defiant]'),
                   'urgent': ('URGENT_COMMAND', '[urgent, commanding]'), 'reaction': ('TRIUMPHANT', '[proud, triumphant]'),
                   'own_death': ('SOLEMN', '[solemn]'),
                   'tutorial': ('CALM_COMMANDING', '[calm, commanding]'), 'default': ('FIELD_COMMAND', '[firm, commanding]')},
    # Master strategist: calm, precise, cultivated authority. v3 only where the original is audibly yelled.
    'zhuge-liang': {'shout': ('BATTLE_SHOUT', '[shouting, commanding]'),
                    'urgent_shout': ('URGENT_SHOUT', '[urgent, shouting]'), 'angry_shout': ('ANGRY_SHOUT', '[angry, shouting]'),
                    'shout_abilities': set(), 'shout_needs_audio_evidence': True,
                    'frontend': ('STRATEGIC', '[strategic, composed]'), 'quote': ('STRATEGIC', '[strategic, composed]'),
                    'affirmative': ('CONFIDENT', '[confident, restrained]'), 'negative': ('MEASURED', '[calm, serious]'),
                    'getready': ('CALM_COMMANDING', '[calm, commanding]'), 'intimidate': ('SUPERIOR', '[confident, restrained]'),
                    'insult': ('SUPERIOR', '[confident, restrained]'), 'congratulate': ('ENCOURAGING', '[encouraging]'),
                    'help': ('URGENT_COMMAND', '[urgent, commanding]'),
                    'victory': ('TRIUMPHANT', '[triumphant]'), 'defeat': ('MEASURED', '[calm, serious]'),
                    'urgent': ('URGENT_COMMAND', '[urgent, commanding]'), 'reaction': ('COMPOSED', '[confident, restrained]'),
                    'own_death': ('SOLEMN', '[solemn]'),
                    'tutorial': ('CALM_COMMANDING', '[calm, commanding]'), 'default': ('CALM_COMMANDING', '[calm, commanding]')},
    # Athenian strategos of Marathon: decisive, confident and combative but disciplined; never Leonidas's Spartan hardness.
    'miltiades': {'shout': ('BATTLE_SHOUT', '[shouting, commanding]'),
                  'urgent_shout': ('URGENT_SHOUT', '[urgent, shouting]'), 'angry_shout': ('ANGRY_SHOUT', '[angry, shouting]'),
                  'shout_abilities': set(), 'shout_needs_audio_evidence': True,
                  'frontend': ('STRATEGIC', '[confident, authoritative]'), 'quote': ('STRATEGIC', '[confident, authoritative]'),
                  'affirmative': ('CONFIDENT', '[confident]'), 'negative': ('STERN', '[stern]'),
                  'getready': ('FIELD_COMMAND', '[firm, commanding]'), 'intimidate': ('THREATENING', '[threatening, restrained]'),
                  'insult': ('SUPERIOR', '[confident, restrained]'), 'congratulate': ('ENCOURAGING', '[encouraging]'),
                  'help': ('URGENT_COMMAND', '[urgent, commanding]'),
                  'victory': ('TRIUMPHANT', '[triumphant]'), 'defeat': ('DEFIANT', '[defiant]'),
                  'urgent': ('URGENT_COMMAND', '[urgent, commanding]'), 'reaction': ('TRIUMPHANT', '[proud, triumphant]'),
                  'own_death': ('SOLEMN', '[solemn]'),
                  'tutorial': ('CALM_COMMANDING', '[calm, commanding]'), 'default': ('FIELD_COMMAND', '[confident, commanding]')},
    # Julius Caesar: charismatic, self-assured statesman-general; controlled in routine orders, sharp in combat.
    'julius-caesar': {'shout': ('BATTLE_SHOUT', '[shouting, commanding]'),
                      'urgent_shout': ('URGENT_SHOUT', '[urgent, shouting]'), 'angry_shout': ('ANGRY_SHOUT', '[angry, shouting]'),
                      'shout_abilities': set(), 'shout_needs_audio_evidence': True,
                      'frontend': ('COMPOSED', '[confident, authoritative]'), 'quote': ('COMPOSED', '[confident, authoritative]'),
                      'affirmative': ('CONFIDENT', '[confident, restrained]'), 'negative': ('MEASURED', '[calm, serious]'),
                      'getready': ('CALM_COMMANDING', '[calm, commanding]'), 'intimidate': ('SUPERIOR', '[confident, restrained]'),
                      'insult': ('SUPERIOR', '[confident, restrained]'), 'congratulate': ('ENCOURAGING', '[encouraging]'),
                      'help': ('URGENT_COMMAND', '[urgent, commanding]'),
                      'victory': ('TRIUMPHANT', '[proud, triumphant]'), 'defeat': ('DEFIANT', '[defiant]'),
                      'urgent': ('URGENT_COMMAND', '[urgent, commanding]'), 'reaction': ('COMPOSED', '[confident, restrained]'),
                      'own_death': ('SOLEMN', '[solemn]'),
                      'tutorial': ('CALM_COMMANDING', '[calm, commanding]'), 'default': ('CALM_COMMANDING', '[confident, commanding]')},
    # Hasdrubal: experienced Carthaginian field commander and paymaster; direct, energetic and combative, never a berserker.
    'hasdrubal': {'shout': ('BATTLE_SHOUT', '[fierce, shouting]'),
                  'urgent_shout': ('URGENT_SHOUT', '[urgent, shouting]'), 'angry_shout': ('ANGRY_SHOUT', '[angry, shouting]'),
                  'shout_abilities': set(), 'shout_needs_audio_evidence': True,
                  'frontend': ('CONFIDENT', '[confident, commanding]'), 'quote': ('CONFIDENT', '[confident]'),
                  'affirmative': ('ENCOURAGING', '[encouraging]'), 'negative': ('DISAPPOINTED', '[disappointed]'),
                  'getready': ('URGENT_COMMAND', '[urgent, commanding]'), 'intimidate': ('THREATENING', '[threatening, confident]'),
                  'victory': ('TRIUMPHANT', '[triumphant]'), 'defeat': ('DEFIANT', '[defiant]'),
                  'urgent': ('URGENT_COMMAND', '[urgent, commanding]'), 'reaction': ('TRIUMPHANT', '[proud, triumphant]'),
                  'own_death': ('DEFIANT', '[defiant]'),
                  'tutorial': ('FIELD_COMMAND', '[firm, commanding]'), 'default': ('FIELD_COMMAND', '[determined, commanding]')},
    # Alexander the Great: young, charismatic and absolutely self-assured; inspiring rather than stern.
    'alexander-the-great': {'shout': ('BATTLE_SHOUT', '[confident, shouting]'),
                            'urgent_shout': ('URGENT_SHOUT', '[urgent, shouting]'), 'angry_shout': ('ANGRY_SHOUT', '[angry, shouting]'),
                            'shout_abilities': set(), 'shout_needs_audio_evidence': True,
                            'frontend': ('PROUD', '[proud, confident]'), 'quote': ('PROUD', '[proud, confident]'),
                            'affirmative': ('ENCOURAGING', '[encouraging, confident]'), 'negative': ('SUPERIOR', '[confident, restrained]'),
                            'getready': ('URGENT_COMMAND', '[urgent, confident]'), 'intimidate': ('SUPERIOR', '[confident, threatening]'),
                            'victory': ('TRIUMPHANT', '[proud, triumphant]'), 'defeat': ('DEFIANT', '[defiant]'),
                            'urgent': ('URGENT_COMMAND', '[urgent, commanding]'), 'reaction': ('TRIUMPHANT', '[proud, triumphant]'),
                            'own_death': ('DEFIANT', '[defiant]'),
                            'tutorial': ('CALM_COMMANDING', '[calm, commanding]'), 'default': ('FIELD_COMMAND', '[confident, commanding]')},
    # Cynane: Macedonian warrior princess and army commander; firm, decisive and disciplined, no caricature.
    'cynane': {'shout': ('BATTLE_SHOUT', '[fierce, shouting]'),
               'urgent_shout': ('URGENT_SHOUT', '[urgent, shouting]'), 'angry_shout': ('ANGRY_SHOUT', '[angry, shouting]'),
               'shout_abilities': set(), 'shout_needs_audio_evidence': True,
               'frontend': ('AUTHORITATIVE', '[confident, authoritative]'), 'quote': ('AUTHORITATIVE', '[confident, authoritative]'),
               'affirmative': ('CONFIDENT', '[confident]'), 'negative': ('STERN', '[stern]'),
               'getready': ('FIELD_COMMAND', '[firm, commanding]'), 'intimidate': ('THREATENING', '[threatening, restrained]'),
               'victory': ('TRIUMPHANT', '[triumphant]'), 'defeat': ('DEFIANT', '[defiant]'),
               'urgent': ('URGENT_COMMAND', '[urgent, commanding]'), 'reaction': ('TRIUMPHANT', '[proud, triumphant]'),
               'own_death': ('SOLEMN', '[solemn]'),
               'tutorial': ('CALM_COMMANDING', '[calm, commanding]'), 'default': ('FIELD_COMMAND', '[firm, commanding]')},
}


# Chinese chat tags name the affirmative/negative emotes yes/no.
EMOTE_KIND_ALIASES = {'yes': 'affirmative', 'no': 'negative'}


def shouted(row):
    """Local Whisper renders clearly yelled speech in capitals; localized text keeps normal case."""
    texts = [row.get(k) or '' for k in ('english_text', 'raw_transcript', 'stt_medium_en', 'stt_small_en')]
    return any(sum(c.isalpha() for c in t) >= 2 and t == t.upper() for t in texts)


def profiled_delivery(group, profile):
    """Context routing for commanders with an explicit voice profile."""
    triggers = [r['trigger'].lower() for r in group]
    trigger = ' '.join(triggers)
    categories = {r['category'] for r in group}
    kinds = {t.split('player selects emote: ', 1)[1].split()[0] for t in triggers if 'player selects emote: ' in t}
    kinds = {EMOTE_KIND_ALIASES.get(k, k) for k in kinds}
    abilities = {t.split(': ', 1)[1].split(';')[0].strip() for r, t in zip(group, triggers)
                 if r['category'] in {'ORDER', 'ABILITY'} and ': ' in t}

    def pick(name):
        style, tags = profile[name]
        return style, 'eleven_v3' if style in V3_STYLES else 'eleven_v4', tags
    # A composed profile keeps context-rule v3 routes for originals that are actually shouted.
    loud = not profile.get('shout_needs_audio_evidence') or all(shouted(r) for r in group)
    if 'battlecry' in kinds or 'warcry' in trigger or abilities & (V3_ORDER_ABILITIES | profile['shout_abilities']):
        return pick('shout' if loud else 'urgent')
    if 'BATTLE_EVENT' in categories:
        for state, name in V3_BATTLE_STATES.items():
            if state in trigger:
                return pick(name if loud else 'urgent')
    if 'VICTORY' in categories or ('BATTLE_EVENT' in categories and 'winning' in trigger):
        return pick('victory')
    if 'DEFEAT' in categories:
        return pick('defeat')
    if 'BATTLE_EVENT' in categories and any(x in trigger for x in ['under attack', 'damaged', 'firing on', 'damages allies', 'damage allies']):
        return pick('urgent')
    if 'your commander dies' in trigger:
        return pick('own_death')
    if 'DEATH_REACTION' in categories:
        return pick('reaction')
    if 'intimidate' in kinds or any('intimidate' in a for a in abilities):
        return pick('intimidate')
    for kind in ['quote', 'affirmative', 'negative', 'getready', 'insult', 'congratulate', 'help']:
        if kind in kinds and kind in profile:
            return pick(kind)
    if 'FRONTEND' in categories:
        return pick('frontend')
    if 'TUTORIAL' in categories:
        return pick('tutorial')
    return pick('default')


def plan_delivery(group, commander, decisions):
    reviewed = decisions.get(english_key(group[0]['english_text']))
    if reviewed:
        return reviewed
    if commander in VOICE_PROFILES:
        return check_delivery(*profiled_delivery(group, VOICE_PROFILES[commander]))
    return check_delivery(*delivery(group, commander))


def budget_risk(original_size_bytes, original_duration, english, czech):
    """Planning heuristic only; encoding, fit and intelligibility remain untested."""
    size, duration = int(original_size_bytes), float(original_duration)
    require(size > 0 and duration > 0, 'Missing original WEM budget')
    expansion = len(czech) / max(1, len(english)) if czech else 1
    chars_per_second = len(czech) / duration if czech else 0
    if size < 6500 or chars_per_second > 23 or (expansion > 1.5 and size < 20000):
        return 'HIGH'
    if size < 10000 or duration < 1 or chars_per_second > 17 or expansion > 1.25:
        return 'MEDIUM'
    return 'LOW'


def manual_resolution(row):
    return ('NEEDS_MANUAL_TRANSCRIPTION' if row['transcript_resolution'] == 'NEEDS_MANUAL_TRANSCRIPTION'
            else 'NEEDS_MANUAL_WORDING_VERIFICATION')


def prepare(commander, commander_root, memory, output_root=None, delivery_decisions=None, archive_root=None):
    commander_root = Path(commander_root)
    research = commander_root/commander/'research'
    validate_research(research, commander)
    manifest = json.loads((research/'manifest-draft.json').read_text(encoding='utf-8'))
    source = read_csv(research/'voice-lines.csv')
    source_by_id = {r['media_id']: r for r in source}
    safe = [r for r in source if r['safe_to_replace_for_commander'] == 'YES'
            and r['sharing_scope'] == 'COMMANDER_SPECIFIC' and r['silent_placeholder'] == 'NO']
    # Commander-specific silent placeholders stay in the inventory but are never safe spoken lines.
    silent_specific = sum(r['sharing_scope'] == 'COMMANDER_SPECIFIC' and r['silent_placeholder'] == 'YES' for r in source)
    require(len(safe) == manifest['safe_replacement_media_ids'] == manifest['commander_specific_media_ids'] - silent_specific,
            'Safety allowlist differs from independent inventory')
    require(all(r['reverse_reference_check'] == 'PASS' and r['archive_wav_reference'] for r in safe),
            'Unsafe or untraceable original recording')
    translated = {}
    for row in safe:
        english = row['english_text'].strip()
        if not english:
            require(row['transcript_resolution'] == 'NEEDS_MANUAL_TRANSCRIPTION', 'Missing English without manual deferral')
            czech = ''
        else:
            require(english_key(english) in memory, 'Missing Czech translation: '+row['media_id'])
            czech = memory[english_key(english)]
        translated[row['media_id']] = czech
    groups = defaultdict(list)
    for row in safe:
        groups[performance_key(row, translated[row['media_id']])].append(row)
    by_id, plan = {}, []
    for key, group in groups.items():
        group.sort(key=lambda r: int(r['media_id']))
        source_id = group[0]['media_id']
        identifier = 'PCM-'+key[3][:16]+'-'+hashlib.sha256((key[4]+'\0'+key[5]).encode('utf-8')).hexdigest()[:8]
        style, model, tags = plan_delivery(group, commander, delivery_decisions or {})
        czech = translated[source_id]
        require(all(english_key(r['english_text']) == english_key(group[0]['english_text'])
                    and translated[r['media_id']] == czech for r in group), 'Performance wording conflict')
        hashes = defaultdict(list)
        for row in group:
            hashes[row['original_wem_sha256']].append(row['media_id'])
        risks = []
        for row in group:
            conf = row['transcript_confidence']
            status = ('NEEDS_MANUAL_TRANSCRIPTION' if not row['english_text'] else
                      'PREPARED' if conf in {'CONFIRMED', 'HIGH'} else 'PROVISIONAL_ENGLISH')
            risk = budget_risk(row['original_size_bytes'], row['original_duration'], row['english_text'], czech)
            risks.append(risk)
            notes = ['Offline Czech draft; not a human listening or performance approval',
                     'Budget label is a text/size heuristic, not an encoding result']
            if status != 'PREPARED':
                notes.append('Verify original English from archived WAV before any TTS request')
            identical = ';'.join(sorted(hashes[row['original_wem_sha256']], key=int)) if len(hashes[row['original_wem_sha256']]) > 1 else ''
            by_id[row['media_id']] = {k: row.get(k, '') for k in VOICE_FIELDS} | {
                'czech_text': czech, 'translation_status': status, 'delivery_style': style,
                'recommended_model': model, 'recommended_tags': tags, 'tts_performance_group': identifier,
                'tts_source_media_id': source_id, 'wem_budget_risk': risk,
                'original_wem_identical_ids': identical, 'notes': '; '.join(notes)}
        statuses = {by_id[r['media_id']]['translation_status'] for r in group}
        group_status = ('NEEDS_MANUAL_TRANSCRIPTION' if 'NEEDS_MANUAL_TRANSCRIPTION' in statuses else
                        'PROVISIONAL_ENGLISH' if 'PROVISIONAL_ENGLISH' in statuses else 'PREPARED')
        plan.append({'tts_performance_group': identifier, 'tts_source_media_id': source_id,
                     'member_media_ids': ';'.join(r['media_id'] for r in group), 'media_ids_total': len(group),
                     'english_text': group[0]['english_text'], 'czech_text': czech,
                     'translation_status': group_status, 'delivery_style': style,
                     'recommended_model': model, 'recommended_tags': tags,
                     'original_duration': group[0]['original_duration'],
                     'original_size_bytes': group[0]['original_size_bytes'],
                     'wem_budget_risk': max(risks, key=RISK_ORDER.get),
                     'original_wem_identical_ids': ';'.join(sorted({m for ids in hashes.values() if len(ids)>1 for m in ids}, key=int)),
                     'pcm_sha256': group[0]['pcm_sha256'],
                     'notes': 'One possible future performance; each Media ID still needs its own exact-size WEM and QC'})
    output = Path(output_root) / commander / 'tts-plan' if output_root else commander_root/commander/'tts-plan'
    output.mkdir(parents=True, exist_ok=True)
    voices = sorted(by_id.values(), key=lambda r: int(r['media_id']))
    plan.sort(key=lambda r: int(r['tts_source_media_id']))
    write_csv(output/'voice-lines-cz.csv', voices, VOICE_FIELDS)
    write_csv(output/'tts-plan.csv', plan, PLAN_FIELDS)
    lines = [f'# {manifest["display_name"]} — Czech voice script', '',
             'Commander-specific safe Media IDs only. English MEDIUM/UNKNOWN wording and its Czech draft require manual original-audio review. No TTS was generated.', '',
             '| Media ID | English candidate | Czech draft | Status | Performance source | Model | WEM risk |',
             '|---:|---|---|---|---:|---|---|']
    for row in voices:
        values = [row['media_id'], row['english_text'], row['czech_text'], row['translation_status'],
                  row['tts_source_media_id'], row['recommended_model'], row['wem_budget_risk']]
        lines.append('| '+' | '.join(str(v).replace('|', '\\|').replace('\n',' ') for v in values)+' |')
    (output/'voice-lines-cz.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    review_target_path = commander_root/'shared-research/transcript-review-targets.json'
    targets = set(json.loads(review_target_path.read_text(encoding='utf-8')).get(commander, [])) if review_target_path.exists() else set()
    require(targets <= {r['media_id'] for r in safe}, 'Review target outside safe commander set')
    manual, decisions = [], []
    for row in safe:
        if row['media_id'] in targets or row['transcript_confidence'] not in {'CONFIRMED', 'HIGH'}:
            resolved = row['transcript_confidence'] in {'CONFIRMED', 'HIGH'}
            decision = {k: '' for k in REVIEW_FIELDS} | {
                'media_id': row['media_id'], 'current_transcript': row['english_text'],
                'final_transcript': row['english_text'] if resolved else '',
                'evidence': row['transcript_resolution']+'; alternative local ASR: '+row['stt_alternative_evidence'],
                'transcript_confidence': row['transcript_confidence'],
                'transcript_resolution': (row['transcript_resolution'] if row['transcript_resolution'] in FINAL_RESOLUTIONS
                                          else 'RESOLVED_WITH_LOCAL_EVIDENCE' if resolved else manual_resolution(row)),
                'source_transcript_resolution': row['transcript_resolution'],
                **{k: row[k] for k in ['category','trigger','original_duration','original_size_bytes',
                     'decision_tree_path','bank','event_id','container_id','sound_id','archive_wav_reference']}}
            decisions.append(decision)
            if not resolved:
                manual.append(decision)
    manual.sort(key=lambda r: int(r['media_id']))
    decisions.sort(key=lambda r: int(r['media_id']))
    write_csv(output/'transcript-review-decisions.csv', decisions, REVIEW_FIELDS)
    header = [f'# {manifest["display_name"]} — manual transcript review', '',
              'Audio references below are relative to the private archive root. The candidate is not an approved final transcript. No human listening is recorded.', '']
    package, local = list(header), list(header[:2]) + [
        'PRIVATE local copy: absolute paths to original decoded WAVs. Never copy this file into the repository.', '']
    for row in manual:
        entry = [f'## Media ID {row["media_id"]}', '',
                 f'- Candidate English: {row["current_transcript"] or "UNKNOWN"}',
                 f'- Resolution: {row["transcript_resolution"]}; confidence: {row["transcript_confidence"]}',
                 f'- Category/trigger: {row["category"]}; {row["trigger"]}',
                 f'- Original duration/size: {row["original_duration"]} s / {row["original_size_bytes"]} B',
                 f'- Context: {row["bank"]}; Event {row["event_id"]}; container {row["container_id"]}; Sound {row["sound_id"]}',
                 f'- Decision path: {row["decision_tree_path"]}',
                 f'- Evidence: {row["evidence"]}']
        package += entry + [f'- Archive WAV: `{row["archive_wav_reference"]}`', '']
        if archive_root:
            wav = Path(archive_root)/row['archive_wav_reference']
            require(wav.is_file(), 'Missing private review WAV: '+row['media_id'])
            local += entry + [f'- Local WAV: `{wav}`', '']
    if not manual:
        package += ['No safe commander-specific line requires manual transcription or wording review.', '']
        local += ['No safe commander-specific line requires manual transcription or wording review.', '']
    (research/'manual-transcript-review.md').write_text('\n'.join(package),encoding='utf-8')
    if archive_root:
        private = Path(archive_root)/'commander-research'/commander
        require(private.is_dir() and not private.resolve().is_relative_to(ROOT), 'Private review package must stay outside the repository')
        (private/'manual-transcript-review-local.md').write_text('\n'.join(local), encoding='utf-8')
    for filename in ['pilot-menu.csv','pilot-battle.csv']:
        pilots = []
        for item in read_csv(research/filename):
            value = by_id[item['media_id']]
            original = source_by_id[item['media_id']]
            require(value['translation_status'] == 'PREPARED' and original['trigger_confidence'] in {'CONFIRMED','HIGH'},
                    'Unreliable pilot')
            pilots.append(original | {k: value[k] for k in PILOT_EXTRAS if k not in {'english','czech'}}
                          | {'czech_text': value['czech_text'], 'delivery_style': value['delivery_style'],
                             'recommended_model': value['recommended_model'],
                             'english': value['english_text'], 'czech': value['czech_text']})
        fields = list(source[0]) + PILOT_EXTRAS
        write_csv(output/filename,pilots,fields)
        write_csv(research/filename,pilots,fields)
    counts = Counter(r['translation_status'] for r in voices)
    models = Counter(r['recommended_model'] for r in plan)
    high_risk = [r['media_id'] for r in voices if r['wem_budget_risk']=='HIGH']
    duplicate_groups = [g for g in groups.values() if len(g)>1]
    identical_wem_groups = sum(len({r['original_wem_sha256'] for r in g})==1 for g in duplicate_groups)
    summary = {'commander': commander, 'safe_spoken_media_ids':len(voices),
               'research_voice_lines_sha256': hashlib.sha256((research/'voice-lines.csv').read_bytes()).hexdigest(),
               'translation_memory_content_sha256': hashlib.sha256(json.dumps(sorted(memory.items()),ensure_ascii=False).encode('utf-8')).hexdigest(),
               'english_transcript_complete':counts['PREPARED'],
               'english_candidates_nonempty':sum(bool(r['english_text']) for r in voices),
               'czech_translations_prepared': sum(bool(r['czech_text']) for r in voices),
               'translations_with_reliable_english':counts['PREPARED'],
               'provisional_english':counts['PROVISIONAL_ENGLISH'],
               'manual_transcript_missing':counts['NEEDS_MANUAL_TRANSCRIPTION'],
               'unique_tts_performances':len(plan),'duplicate_ids_saved':len(voices)-len(plan),
               'byte_identical_original_wem_duplicate_groups':identical_wem_groups,
               'pcm_only_duplicate_groups':len(duplicate_groups)-identical_wem_groups,
               'v3_planned':models['eleven_v3'],'v4_planned':models['eleven_v4'],
               'high_wem_budget_risk':len(high_risk),'high_wem_budget_risk_ids':high_risk,
               'manual_transcript_review_remaining':len(manual),
               'manual_review_ids':[r['media_id'] for r in manual],
               'original_review_targets_resolved':len(decisions)-len(manual),
               'ready_for_elevenlabs': len(manual)==0 and counts['PREPARED']==len(voices),
               'tts_api_calls':0,'human_listening':'NOT_RUN','audio_encoding':'NOT_RUN'}
    (output/'plan-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    labelled = Counter(d['transcript_resolution'] for d in decisions if d['transcript_resolution'] in FINAL_RESOLUTIONS)
    review = [f'# {manifest["display_name"]} — translation review', '',
              f'Safe spoken IDs: {len(voices)}. Czech drafts: {summary["czech_translations_prepared"]}. '
              f'English-supported drafts: {counts["PREPARED"]}. Provisional English: {counts["PROVISIONAL_ENGLISH"]}. '
              f'Missing English: {counts["NEEDS_MANUAL_TRANSCRIPTION"]}.', '',
              f'Unique future performances: {len(plan)}; repeated Media IDs covered: {len(voices)-len(plan)}. '
              f'Byte-identical original WEM duplicate groups: {identical_wem_groups}; '
              f'exact decoded PCM duplicates with different WEM bytes: {len(duplicate_groups)-identical_wem_groups}. '
              f'Model routing: eleven_v3 {models["eleven_v3"]}, eleven_v4 {models["eleven_v4"]} per unique performance.', '',
              'The WEM budget labels are planning heuristics based on original size, duration and Czech/English text length. '
              'HIGH means original <6500 B, or planned Czech >23 characters per original second, or >1.5× English length with original <20000 B. '
              'MEDIUM means original <10000 B, duration <1 s, >17 characters/s or >1.25× English length. '
              'They do not establish that a new encoded WEM will fit. Never shorten speech, change timing or truncate to satisfy an estimate.', '',
              'The original PCM fingerprint plus matching English/Czech wording defines a performance group. '
              'An emote and an order can share the same group when both point to the same original recording. '
              'The model/style/tags are shared across that group. Every Media ID still needs separate future size and playback checks.', '',
              f'High WEM budget risk IDs ({len(high_risk)}): '+(', '.join(high_risk) or 'none')+'.', '',
              f'Originally disputed IDs resolved with local context/phonetic evidence: {len(decisions)-len(manual)-sum(labelled.values())}. '
              + (f'Human-confirmed by the project owner: {labelled["HUMAN_CONFIRMED"]}; resolved by the independent second opinion: '
                 f'{labelled["SECOND_OPINION_RESOLVED"]} (labels in `transcript_resolution`, evidence in shared `transcript-corrections.json`). '
                 if labelled else '') +
              'Individual decisions and the unresolved candidate wording are in `transcript-review-decisions.csv`.', '',
              'Manual English review: '+(', '.join(summary['manual_review_ids']) or 'none')+'. '
              'See `manual-transcript-review.md` in the research folder and `transcript-review-decisions.csv` here.', '']
    if (output/'translation-notes.md').is_file():
        review += ['Commander-specific translator decisions and open questions: [translation-notes.md](translation-notes.md).', '']
    review += [
              'READY FOR ELEVENLABS: **'+('YES' if summary['ready_for_elevenlabs'] else 'NO')+'**. '
              'No ElevenLabs request, audio generation, game write or human listening is claimed.', '']
    (output/'translation-review.md').write_text('\n'.join(review),encoding='utf-8')
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commander',action='append',required=True)
    parser.add_argument('--commander-root',default=str(ROOT/'data/commanders'))
    parser.add_argument('--translation-memory',required=True)
    parser.add_argument('--output-root')
    parser.add_argument('--archive-root', help='Private archive root; writes an absolute-path review copy there only')
    args=parser.parse_args()
    memory,decisions=read_memory(args.translation_memory)
    used=set()
    for name in args.commander:
        folder=Path(args.commander_root)/name/'research'
        used.update(english_key(r['english_text']) for r in read_csv(folder/'voice-lines.csv')
                    if r['safe_to_replace_for_commander']=='YES' and r['english_text'])
    require(used==set(memory), 'Translation memory contains unused or missing non-commander phrases')
    for name in args.commander:
        print(json.dumps(prepare(name,args.commander_root,memory,args.output_root,decisions,args.archive_root),ensure_ascii=False))


if __name__=='__main__':
    main()
