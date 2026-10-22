"""Shared unit-voice TTS plan: the canonical staged unit plan as production plan rows, one voice group at a time.

Unit acknowledgements are shared by every commander, so they never enter a commander plan. Each voice group
(CZ_UNIT_MALE, CZ_UNIT_FEMALE) is generated with its own ElevenLabs voice and its own generation ledger; the
loader proves that every member Media ID belongs to that gender before any request can be planned.

`python -B -m tools.tts.units routing --output work/tts-production/unit-voices/routing.csv` writes the routing
(model and delivery per performance) offline from the staged plan; tools.tts.production checks it again.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

MODULE = "unit-voices"
ROOT = Path("data/shared/unit-acknowledgements")
PLAN_PATH = ROOT / "plan.staged.json"
MEDIA_PATH = ROOT / "media-map.staged.csv"
EXCLUDED_PATH = ROOT / "excluded-media.staged.csv"
GROUPS = {"CZ_UNIT_MALE": "male", "CZ_UNIT_FEMALE": "female"}
GROUP_OF_SLOT = {gender: group for group, gender in GROUPS.items()}
VOICE_NAMES = {"CZ_UNIT_MALE": "Units Male CZ", "CZ_UNIT_FEMALE": "Units Women CZ"}
MODEL = "eleven_v4"
WILDCARD = "UNSAFE_INCOMPLETE_COVERAGE"
ROUTING_FIELDS = ("tts_source_media_id", "tts_performance_group", "voice_group", "czech_text", "english_text",
                  "kind", "delivery_style", "recommended_tags", "selected_model", "reason")
# Existing project v4 vocabulary only. Plain acknowledgements and unit-type callouts carry no tag: the voice
# itself was designed as a battlefield soldier, and the tight original byte budgets favour a short, neutral read.
# Combative lines use the [defiant] delivery the staged voice pilot proposed.
COMBATIVE = {"dogs_of_war"}


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def delivery(performance):
    phrase = performance["performance_id"].split("-", 1)[1]
    if performance["kind"] == "BATTLE_CRY" or phrase in COMBATIVE:
        return "DEFIANT", "[defiant]"
    return "NEUTRAL_SOLDIER", ""


def staged():
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    if plan["schema"] != "unit-acknowledgements-staged/1" or plan["terminology_status"].split()[0] != "approved":
        raise RuntimeError("Unsupported or unapproved staged unit plan")
    return plan


def routing_rows():
    rows = []
    for performance in staged()["performances"]:
        style, tags = delivery(performance)
        rows.append({"tts_source_media_id": performance["performance_id"],
                     "tts_performance_group": performance["performance_id"],
                     "voice_group": performance["voice_group"], "czech_text": performance["czech_text"],
                     "english_text": performance["english_phrases"], "kind": performance["kind"],
                     "delivery_style": style, "recommended_tags": tags, "selected_model": MODEL,
                     "reason": "canonical staged unit plan; v4 for every unit performance (task decision)"})
    return rows


def load_unit_plan(voice_group, routing_path, require_model=None):
    """Plan rows shaped like a commander tts-plan for one voice group, after independent gender/scope checks."""
    if voice_group not in GROUPS:
        raise RuntimeError("Unknown unit voice group")
    gender = GROUPS[voice_group]
    plan = staged()
    media = read_csv(MEDIA_PATH)
    by_id = {row["media_id"]: row for row in media}
    excluded = {row["media_id"] for row in read_csv(EXCLUDED_PATH)}
    routes = {row["tts_source_media_id"]: row for row in read_csv(routing_path)}
    if len(by_id) != len(media) or excluded & set(by_id) or len(routes) != len(plan["performances"]):
        raise RuntimeError("Unit media map, exclusions or routing cardinality mismatch")
    if plan["counts"]["production_scope_media"] != len(media) or plan["counts"]["performances"] != len(routes):
        raise RuntimeError("Canonical unit plan counts changed")
    rows, members = [], set()
    for performance in plan["performances"]:
        source = performance["performance_id"]
        route = routes.get(source)
        style, tags = delivery(performance)
        if (not route or any(route[field] != value for field, value in (
                ("tts_performance_group", source), ("voice_group", performance["voice_group"]),
                ("czech_text", performance["czech_text"]), ("kind", performance["kind"]),
                ("delivery_style", style), ("recommended_tags", tags))) or not route["reason"].strip()
                or route["selected_model"] != MODEL or (require_model and route["selected_model"] != require_model)):
            raise RuntimeError(f"Unit routing mismatch {source}")
        if performance["voice_group"] != voice_group:
            continue
        ids = performance["required_media"].split("+")
        # Wildcard-reached members (research: UNSAFE_INCOMPLETE_COVERAGE, "not production-ready" for any
        # commander-only release) belong to the canonical 465-ID scope; the shared module records them explicitly.
        wildcard = set(filter(None, performance["not_production_ready_media"].split("+")))
        if (not source.startswith(gender + "-") or len(ids) != int(performance["target_media_count"])
                or performance["transcript_blocked_media"] or not wildcard <= set(ids)
                or any(by_id[m]["safe_replacement_status"] != WILDCARD or by_id[m]["reached_via_wildcard"] != "YES"
                       for m in wildcard)
                or performance["tts_generations_allowed"] != "1"):
            raise RuntimeError(f"Invalid unit performance {source}")
        if any(media_id not in by_id for media_id in ids):
            raise RuntimeError(f"Unit performance outside the production scope {source}")
        # The voice follows the original recording. China's female slots hold byte-identical copies of the
        # male recording, so only such a proven copy may sit in a group of the other slot gender.
        own_recordings = {by_id[m]["original_wem_sha256"] for m in ids if by_id[m]["voice_gender"] == gender}
        for media_id in ids:
            row = by_id[media_id]
            slot = row["voice_gender"]
            actors = row["vo_actors"].split("+")
            if (media_id in members or row["dubbing_priority"] != "REQUIRED"
                    or row["czech_for_slot"] != performance["czech_text"]
                    or not any(a.startswith(slot.title() + "_") for a in actors)
                    or any(a.startswith(("Male_", "Female_")) and not a.startswith(slot.title() + "_") for a in actors)
                    or (slot != gender and (gender != "male" or row["vo_cultures"] != "China"
                                            or row["original_wem_sha256"] not in own_recordings))):
                raise RuntimeError(f"Unit member outside voice group or scope {media_id}")
            members.add(media_id)
        rows.append({"tts_source_media_id": source, "tts_performance_group": source, "member_media_ids": ";".join(ids),
                     "media_ids_total": str(len(ids)), "czech_text": performance["czech_text"],
                     "english_text": performance["english_phrases"], "delivery_style": style,
                     "recommended_tags": tags, "kind": performance["kind"]})
    expected = {mid for mid, row in by_id.items()
                if (GROUP_OF_SLOT["male"] if row["vo_cultures"] == "China" else GROUP_OF_SLOT[row["voice_gender"]])
                == voice_group}
    if members != expected:
        raise RuntimeError("Unit voice group does not cover its reachable Media IDs exactly")
    if plan["counts"]["performances_by_voice"][voice_group] != len(rows):
        raise RuntimeError("Unit performance count changed")
    hashes = {str(path): sha_file(path) for path in (PLAN_PATH, MEDIA_PATH, EXCLUDED_PATH, Path(routing_path))}
    return rows, {row["tts_source_media_id"]: routes[row["tts_source_media_id"]] for row in rows}, hashes, len(members)


FALLBACK_PATH = ROOT / "byte-budget-fallbacks.csv"
FALLBACK_REASON = "BYTE_BUDGET_COMPACT_FALLBACK"


def load_fallback_plan(voice_group, routing_path, require_model=None):
    """User-approved per-Media-ID shorter lines for IDs whose canonical line cannot fit the WEM byte budget.

    One performance '<performance>.fallback' per fallback text and voice group; it serves only the listed IDs,
    every other member keeps the canonical performance. Shaped like load_unit_plan's rows.
    """
    canonical, routes, _, _ = load_unit_plan(voice_group, routing_path, require_model)
    by_source = {row["tts_source_media_id"]: row for row in canonical}
    media = {row["media_id"]: row for row in read_csv(MEDIA_PATH)}
    rows, seen = {}, set()
    for entry in read_csv(FALLBACK_PATH):
        if entry["voice_group"] != voice_group:
            continue
        mid, perf = entry["media_id"], entry["performance"]
        if (mid in seen or perf not in by_source or mid not in by_source[perf]["member_media_ids"].split(";")
                or entry["reason"] != FALLBACK_REASON or entry["status"] != "APPROVED" or not entry["approved"].strip()
                or entry["canonical_plan_czech"] != by_source[perf]["czech_text"] != entry["fallback_czech"]
                or media[mid]["english_transcript"] != entry["english"] or entry["selected_model"] != MODEL
                or (require_model and entry["selected_model"] != require_model)):
            raise RuntimeError(f"Invalid byte-budget fallback {mid}")
        seen.add(mid)
        source = perf + ".fallback"
        row = rows.setdefault(source, {
            "tts_source_media_id": source, "tts_performance_group": perf, "member_media_ids": [],
            "czech_text": entry["fallback_czech"], "english_text": entry["english"],
            "delivery_style": entry["delivery_style"], "recommended_tags": entry["recommended_tags"],
            "kind": by_source[perf]["kind"], "canonical_plan_czech": entry["canonical_plan_czech"]})
        if (row["czech_text"], row["recommended_tags"]) != (entry["fallback_czech"], entry["recommended_tags"]):
            raise RuntimeError(f"One fallback text and delivery per performance {source}")
        row["member_media_ids"].append(mid)
    plan = []
    for row in rows.values():
        plan.append(dict(row, member_media_ids=";".join(row["member_media_ids"]),
                         media_ids_total=str(len(row["member_media_ids"]))))
    hashes = {str(path): sha_file(path) for path in (PLAN_PATH, MEDIA_PATH, FALLBACK_PATH)}
    fallback_routes = {row["tts_source_media_id"]: {"selected_model": MODEL} for row in plan}
    return plan, fallback_routes, hashes, len(seen)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    routing = commands.add_parser("routing", help="write the offline routing CSV for both voice groups")
    routing.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(Path("work").resolve()):
        parser.error("output must be under ignored work/")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, ROUTING_FIELDS)
        writer.writeheader()
        writer.writerows(routing_rows())
    summary = {group: len(load_unit_plan(group, args.output)[0]) for group in GROUPS}
    print(json.dumps({"routing": args.output.as_posix(), "performances": summary}, indent=2))


if __name__ == "__main__":
    main()
