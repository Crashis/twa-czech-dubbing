"""Pronunciation overrides: the TTS input spelling, kept separate from the canonical Czech text.

The canonical Czech text (voice lines, translation memory, plans, manifests) is never changed. An
override only changes the text ElevenLabs receives. Pilot and production resolve through this one module.

Rule files share the columns of data/commanders/<id>/tts-plan/pronunciation-overrides.csv:
- a row with tts_source_media_id is phrase-specific: czech_text must equal that performance's whole
  canonical text and tts_text_override is the whole TTS input;
- a row without it is a token rule: czech_text is an exact, case-sensitive word or phrase matched on
  whole-word boundaries only, tts_text_override its TTS spelling. Its scope is the file (commander,
  unit-acknowledgements or the optional data/shared/pronunciation-overrides.csv global file).
Precedence is phrase > commander/unit > global. Token rules apply in one pass, so a replacement is never
rewritten again. Statuses: APPROVED (pilot and production), REJECTED (never), review statuses (the pilot
applies tts_text_override if present; production stops until a human approves or rejects the row).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

FILE = "tts-plan/pronunciation-overrides.csv"
GLOBAL_PATH = Path("data/shared/pronunciation-overrides.csv")
UNIT_PATH = Path("data/shared/unit-acknowledgements/pronunciation-overrides.csv")
MODES = ("pilot", "production")
APPROVED, REJECTED = "APPROVED", "REJECTED"
REVIEW = {"REVIEW_REQUIRED", "PROPOSED_VERIFY_IN_PILOT", "FALLBACK_ONLY_IF_PILOT_PALATALIZES"}
RANK = {"phrase": 0, "global": 2}  # any other file scope (commander, unit set) ranks 1


class ReviewRequired(RuntimeError):
    """A matching pronunciation override is neither approved nor rejected; production must not guess."""


def read_rules(path, scope):
    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    rules = []
    for row in rows:
        key = (row.get("tts_source_media_id") or "").strip() or None
        source, tts = row["czech_text"], (row.get("tts_text_override") or "").strip() or None
        status, reason = row["status"].strip(), (row.get("override_reason") or "").strip()
        if (status not in REVIEW | {APPROVED, REJECTED} or not source.strip() or source != source.strip()
                or tts == source or not reason or (status == APPROVED and not tts)):
            raise RuntimeError(f"Invalid pronunciation override {source!r} in {path.as_posix()}")
        rules.append({"scope": "phrase" if key else scope, "key": key, "source": source, "tts": tts,
                      "fallback": (row.get("palatalization_fallback_text") or "").strip() or None,
                      "status": status, "reason": reason, "file": path.as_posix()})
    return rules


def words(text):
    return re.findall(r"\w+", text)


def request_text(tags, tts_input_text):
    """The exact ElevenLabs text: delivery tags, then the resolved TTS input (never the canonical text)."""
    return (tags + " " if tags else "") + tts_input_text


class Resolver:
    def __init__(self, rules, files=()):
        self.rules, self.phrases, self.tokens = rules, {}, {}
        self.files = {Path(path).as_posix(): hashlib.sha256(Path(path).read_bytes()).hexdigest()
                      for path in files if Path(path).exists()}
        for rule in rules:
            if rule["scope"] == "phrase":
                if rule["key"] in self.phrases:
                    raise RuntimeError(f"Duplicate phrase override {rule['key']}")
                self.phrases[rule["key"]] = rule
                continue
            other = self.tokens.get(rule["source"])
            if other and RANK.get(other["scope"], 1) == RANK.get(rule["scope"], 1):
                raise RuntimeError(f"Conflicting pronunciation overrides for {rule['source']!r}")
            if not other or RANK.get(rule["scope"], 1) < RANK.get(other["scope"], 1):
                self.tokens[rule["source"]] = rule
        # Longest source first, so "Publius Cornelius" wins over "Cornelius" at the same position.
        sources = sorted(self.tokens, key=lambda source: (-len(source), source))
        self.pattern = (re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, sources)) + r")(?!\w)")
                        if sources else None)

    def verify_phrases(self, texts_by_key):
        """Every phrase row must name a planned performance and still match its canonical text."""
        for key, rule in self.phrases.items():
            if texts_by_key.get(key) != rule["source"]:
                raise RuntimeError(f"Stale phrase pronunciation override {key}: canonical text differs or is unplanned")

    def resolve(self, canonical, mode, key=None):
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        phrase = self.phrases.get(key) if key else None
        if phrase and phrase["source"] != canonical:
            raise RuntimeError(f"Stale phrase pronunciation override {key}: canonical text changed")
        matched = [phrase] if phrase else [self.tokens[m[0]] for m in self.pattern.finditer(canonical)] if self.pattern else []
        active = []
        for rule in matched:
            if rule["status"] == REJECTED or rule in active:
                continue
            if rule["status"] != APPROVED and mode == "production":
                raise ReviewRequired(f"Pronunciation override {rule['source']!r} ({rule['file']}) is {rule['status']}; "
                                     "approve or reject it before production")
            if rule["tts"]:
                active.append(rule)
        if phrase:
            text = phrase["tts"] if active else canonical
            # Record the changed words, so the audit shows e.g. Caesarovi -> Cézarovi, not two whole lines.
            pairs = list(zip(words(canonical), words(text))) if len(words(canonical)) == len(words(text)) else [(canonical, text)]
            changes = [(phrase, source, tts) for source, tts in pairs if source != tts]
        else:
            chosen = {rule["source"]: rule["tts"] for rule in active}
            text = self.pattern.sub(lambda m: chosen.get(m[0], m[0]), canonical) if chosen else canonical
            changes = [(rule, rule["source"], rule["tts"]) for rule in active]
        applied = [{"scope": rule["scope"], "rule": rule["key"] or rule["source"], "source": source, "tts": tts,
                    "status": rule["status"], "reason": rule["reason"]} for rule, source, tts in changes]
        return {"canonical_text": canonical, "tts_input_text": text, "applied_pronunciation_overrides": applied}


def commander_resolver(commander):
    files = (GLOBAL_PATH, Path("data/commanders") / commander / FILE)
    return Resolver(read_rules(files[0], "global") + read_rules(files[1], "commander"), files)


def unit_resolver():
    return Resolver(read_rules(GLOBAL_PATH, "global") + read_rules(UNIT_PATH, "unit-acknowledgements"),
                    (GLOBAL_PATH, UNIT_PATH))


def check_pilot_plan(path):
    """Offline: a pilot plan's TTS input and request text must equal this resolver's pilot output."""
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    problems = []
    if plan["schema"].startswith("unit-ack-voice-pilot/"):
        resolver = unit_resolver()
        staged = json.loads(Path(plan["source_plan"]).read_text(encoding="utf-8"))
        for performance in staged["performances"]:
            if resolver.resolve(performance["czech_text"], "pilot")["tts_input_text"] != performance["tts_input_text"]:
                problems.append({"performance": performance["performance_id"], "problem": "staged tts_input_text"})
        targets = [(item["performance_id"], None, item["proposed_tags"], item) for item in plan["items"]]
    else:
        resolver = commander_resolver(plan["commander"])
        with (Path("data/commanders") / plan["commander"] / "tts-plan/tts-plan.csv").open(encoding="utf-8-sig") as stream:
            canonical = {row["tts_source_media_id"]: row["czech_text"] for row in csv.DictReader(stream)}
        resolver.verify_phrases(canonical)
        targets = []
        for item in plan["items"]:
            if canonical.get(item["tts_source_media_id"]) != item["czech"]:
                problems.append({"performance": item["tts_source_media_id"], "problem": "canonical text"})
            targets.append((item["tts_source_media_id"], item["tts_source_media_id"], item["recommended_tags"], item))
    for name, key, tags, item in targets:
        spoken = resolver.resolve(item["czech"], "pilot", key)
        if (item["tts_input_text"] != spoken["tts_input_text"]
                or item["request_text"] != request_text(tags, spoken["tts_input_text"])
                or item.get("pronunciation_override", bool(spoken["applied_pronunciation_overrides"]))
                != bool(spoken["applied_pronunciation_overrides"])):
            problems.append({"performance": name, "problem": "tts input", "expected": spoken["tts_input_text"]})
    return {"pilot_plan": Path(path).as_posix(), "items": len(plan["items"]), "problems": problems}


def report():
    """Every rule of every commander and unit file, with what the pilot would send for it."""
    rows = []
    for path in sorted(Path("data/commanders").glob("*/" + FILE)) + [UNIT_PATH, GLOBAL_PATH]:
        owner = path.parts[2] if path.parts[1] == "commanders" else path.parent.name
        for rule in read_rules(path, "global" if path == GLOBAL_PATH else owner):
            rows.append({"owner": owner, "scope": rule["scope"], "key": rule["key"], "canonical": rule["source"],
                         "tts": rule["tts"], "fallback": rule["fallback"], "status": rule["status"],
                         "review_required": rule["status"] in REVIEW, "reason": rule["reason"]})
    statuses = {}
    for row in rows:
        statuses[row["status"]] = statuses.get(row["status"], 0) + 1
    return {"rules": len(rows), "review_required": sum(row["review_required"] for row in rows),
            "statuses": statuses, "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("report", help="list every override and its status (offline)")
    check = commands.add_parser("check-pilot", help="verify pilot-plan.json TTS inputs (offline)")
    check.add_argument("pilot_plans", nargs="+", type=Path)
    args = parser.parse_args()
    if args.command == "report":
        print(json.dumps(report(), ensure_ascii=False, indent=2))
        return
    results = [check_pilot_plan(path) for path in args.pilot_plans]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if any(result["problems"] for result in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
