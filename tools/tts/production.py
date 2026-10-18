"""Resume-safe ElevenLabs TTS staging from an independently checked routing CSV.

This tool writes only to ignored work/. It does not create WEMs or touch game files.
Run with an explicit --commander, --routing, and --output directory. A submitted
request without a saved response is never automatically retried.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://api.elevenlabs.io"
MODELS = {"eleven_v3": "v3", "eleven_v4": "v4"}
FORMAT = "mp3_44100_128"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    return sha_bytes(path.read_bytes())


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def save_json(path, value):
    tmp = path.with_name(path.name + ".partial")
    with tmp.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(path)


def api_key():
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        dot_env = Path(".env")
        if dot_env.exists():
            for line in dot_env.read_text(encoding="utf-8-sig").splitlines():
                name, separator, value = line.strip().partition("=")
                if separator and name.strip() == "ELEVENLABS_API_KEY":
                    key = value.strip().strip("\"'")
                    break
    if not key or key == "your_api_key_here":
        raise RuntimeError("ElevenLabs API key unavailable")
    return key


def get_json(path, key):
    request = Request(BASE + path, headers={"xi-api-key": key, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"ElevenLabs read-only request HTTP {exc.code}") from None
    except URLError:
        raise RuntimeError("ElevenLabs read-only request network error") from None


def subscription(key):
    data = get_json("/v1/user/subscription", key)
    used, limit = data.get("character_count"), data.get("character_limit")
    if not isinstance(used, int) or not isinstance(limit, int):
        raise RuntimeError("Subscription credit counts unavailable")
    return {"used": used, "limit": limit, "remaining": limit - used}


def voice_and_models(key, voice_name):
    page = get_json("/v2/voices?" + urlencode({"search": voice_name, "page_size": 100}), key)
    matches = [voice for voice in page.get("voices", []) if voice.get("name") == voice_name]
    if page.get("has_more") or len(matches) != 1:
        raise RuntimeError("Requested voice lookup was not unique")
    models = get_json("/v1/models", key)
    available = {m.get("model_id") for m in models if m.get("can_do_text_to_speech")}
    if not set(MODELS).issubset(available):
        raise RuntimeError("Required ElevenLabs models are unavailable")
    return matches[0]["voice_id"]


def load_plan(commander, routing_path):
    root = Path("data/commanders") / commander
    plan_path = root / "tts-plan/tts-plan.csv"
    voice_path = root / "tts-plan/voice-lines-cz.csv"
    inventory_path = root / "research/voice-lines.csv"
    plan, voices, inventory, routing = map(read_csv, (plan_path, voice_path, inventory_path, routing_path))
    safe_column = "safe_to_replace_for_" + commander.replace("-", "_")
    safe = {
        row["media_id"]: row for row in inventory
        if row["safe_to_replace_for_commander"] == "YES" and row[safe_column] == "YES"
    }
    voice_by_id = {row["media_id"]: row for row in voices}
    routes = {row["tts_source_media_id"]: row for row in routing}
    if (len(safe) != len(voices) or set(safe) != set(voice_by_id)
            or len(voice_by_id) != len(voices)
            or len(routes) != len(routing)
            or len(plan) != len(routes)):
        raise RuntimeError("Inventory, voice lines, or routing cardinality mismatch")
    members = set()
    sources = set()
    for row in plan:
        source = row["tts_source_media_id"]
        ids = row["member_media_ids"].split(";")
        if (source in sources or source not in routes or source not in ids
                or len(ids) != int(row["media_ids_total"])
                or row["translation_status"] not in {"PREPARED", "FINAL"}
                or not row["czech_text"].strip() or not row["recommended_tags"].strip()):
            raise RuntimeError(f"Invalid performance group {source}")
        sources.add(source)
        route = routes[source]
        voice = voice_by_id[source]
        if (route["selected_model"] not in MODELS
                or any(route[field] != value for field, value in (
                    ("tts_performance_group", row["tts_performance_group"]),
                    ("czech_text", row["czech_text"]),
                    ("delivery_style", row["delivery_style"]),
                    ("category", voice["category"]),
                    ("trigger", voice["trigger"]),
                )) or not route["reason"].strip()):
            raise RuntimeError(f"Routing mismatch {source}")
        for media_id in ids:
            if media_id in members or media_id not in safe:
                raise RuntimeError(f"Unsafe or duplicate member {media_id}")
            members.add(media_id)
            member = voice_by_id[media_id]
            if (member["tts_source_media_id"] != source
                    or member["tts_performance_group"] != row["tts_performance_group"]
                    or member["czech_text"] != row["czech_text"]
                    or member["english_text"] != row["english_text"]
                    or safe[media_id]["pcm_sha256"] != row["pcm_sha256"]):
                raise RuntimeError(f"Member content mismatch {media_id}")
    if members != set(safe) or sources != set(routes):
        raise RuntimeError("Uncovered safe Media IDs or routing rows")
    if commander == "spartacus" and (len(safe), len(plan), len(safe)-len(plan)) != (304, 259, 45):
        raise RuntimeError("Spartacus expected counts changed")
    force = [row for row in plan if row["czech_text"] == "Tasit čepele!"]
    if commander == "spartacus" and (len(force) != 1 or routes[force[0]["tts_source_media_id"]]["selected_model"] != "eleven_v3"):
        raise RuntimeError("Forced v3 line missing")
    paths = (plan_path, voice_path, inventory_path, routing_path)
    hashes = {str(path): sha_file(path) for path in paths}
    return plan, routes, hashes, len(safe)


def decoder(path):
    if path:
        sys.path.insert(0, str(path.resolve()))
    import miniaudio
    return miniaudio


def inspect_audio(path, mini):
    if not path.is_file() or path.stat().st_size < 1000:
        raise ValueError("missing or tiny audio")
    info = mini.get_file_info(str(path))
    if info.file_format != mini.FileFormat.MP3:
        raise ValueError("output is not MP3")
    decoded = mini.decode_file(str(path), output_format=mini.SampleFormat.SIGNED16, nchannels=1)
    samples = decoded.samples
    if decoded.sample_rate <= 0 or len(samples) < 1000:
        raise ValueError("empty decode")
    duration = len(samples) / decoded.sample_rate
    rms = math.sqrt(sum(int(x) * int(x) for x in samples) / len(samples))
    peak = max(abs(x) for x in samples)
    if duration <= 0 or rms < 100 or peak < 1000:
        raise ValueError("silent or nearly silent audio")
    return {"duration_seconds": round(duration, 4), "sample_rate": decoded.sample_rate,
            "rms_pcm16": round(rms, 1), "peak_pcm16": peak, "bytes": path.stat().st_size,
            "sha256": sha_file(path)}


def items_from_plan(plan, routes, output, voice_id):
    items = {}
    for row in plan:
        source = row["tts_source_media_id"]
        model = routes[source]["selected_model"]
        text = row["recommended_tags"] + " " + row["czech_text"]
        request = {"voice_id": voice_id, "model_id": model, "text": text, "output_format": FORMAT}
        items[source] = {
            "tts_performance_group": row["tts_performance_group"],
            "tts_source_media_id": source, "member_media_ids": row["member_media_ids"].split(";"),
            "model": model, "czech_text": row["czech_text"],
            "delivery_style": row["delivery_style"], "tags": row["recommended_tags"],
            "request_text": text,
            "request_sha256": sha_bytes(json.dumps(request, ensure_ascii=False, sort_keys=True).encode("utf-8")),
            "status": "planned", "output_path": str(output / "audio" / f"{source}_{MODELS[model]}.mp3"),
            "generation_timestamp": None, "credits_used": None, "checksum": None,
        }
    return items


def import_pilot(state, pilot_journal, mini):
    if not pilot_journal:
        return
    journal = json.loads(pilot_journal.read_text(encoding="utf-8"))
    if journal.get("voice_name") != state["voice_name"]:
        raise RuntimeError("Unexpected pilot voice")
    for pilot in journal["requests"]:
        if pilot["status"] != "complete":
            continue
        item = state["items"].get(pilot["media_id"])
        if not item or item["model"] != pilot["model"] or item["status"] == "complete":
            continue
        if (item["czech_text"] != pilot["czech_text"] or item["request_text"] != pilot["text"]
                or item["tags"] != pilot["tags"]):
            raise RuntimeError(f"Pilot provenance mismatch {pilot['media_id']}")
        source = Path(pilot["output"])
        if sha_file(source) != pilot["sha256"]:
            raise RuntimeError(f"Pilot checksum mismatch {pilot['media_id']}")
        target = Path(item["output_path"])
        if target.exists():
            if sha_file(target) != pilot["sha256"]:
                raise RuntimeError(f"Staged pilot checksum mismatch {pilot['media_id']}")
        else:
            shutil.copyfile(source, target)
        metrics = inspect_audio(target, mini)
        item.update(status="complete", origin="pilot_reused", checksum=metrics["sha256"],
                    generation_timestamp=datetime.fromtimestamp(source.stat().st_mtime, timezone.utc).isoformat(),
                    credits_used=pilot.get("credits"), audio=metrics)


def prepare_state(args, plan, routes, hashes, safe_count, voice_id, before, mini):
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    (output / "audio").mkdir(exist_ok=True)
    state_path = output / "generation-state.json"
    expected = items_from_plan(plan, routes, output, voice_id)
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if (state["source_hashes"] != hashes or state["voice_id"] != voice_id
                or set(state["items"]) != set(expected)):
            raise RuntimeError("Frozen production inputs changed; refusing resume")
        for source, item in state["items"].items():
            for key in ("request_sha256", "model", "request_text", "output_path", "czech_text"):
                if item[key] != expected[source][key]:
                    raise RuntimeError(f"Frozen request changed {source}")
    else:
        state = {"schema": 1, "commander": args.commander, "voice_name": args.voice_name,
                 "voice_id": voice_id, "source_hashes": hashes, "safe_media_ids": safe_count,
                 "unique_performances": len(plan), "created_at": utc_now(),
                 "starting_credits": before["remaining"], "starting_usage": before["used"],
                 "credit_limit": before["limit"], "latest_credits": before["remaining"],
                 "items": expected}
        save_json(state_path, state)
    import_pilot(state, args.pilot_journal, mini)
    save_json(state_path, state)
    return state, state_path


def generate_one(item, key, voice_id, mini, state, state_path):
    target = Path(item["output_path"])
    partial = target.with_name(target.stem + ".partial.mp3")
    if target.exists() or partial.exists():
        raise RuntimeError(f"Unrecorded audio already exists for {item['tts_source_media_id']}")
    item["status"] = "submitted"
    item["generation_timestamp"] = utc_now()
    save_json(state_path, state)
    payload = json.dumps({"text": item["request_text"], "model_id": item["model"]}, ensure_ascii=False).encode("utf-8")
    request = Request(BASE + "/v1/text-to-speech/" + voice_id + "?output_format=" + FORMAT,
                      data=payload,
                      headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
                      method="POST")
    try:
        with urlopen(request, timeout=120) as response:
            audio = response.read()
            cost_header = response.headers.get("character-cost")
            request_id = response.headers.get("request-id")
    except HTTPError as exc:
        item["status"] = "failed" if 400 <= exc.code < 500 and exc.code != 429 else "uncertain"
        item["error"] = f"HTTP {exc.code}; no automatic retry"
        save_json(state_path, state)
        return
    except (URLError, TimeoutError, OSError):
        item["status"] = "uncertain"
        item["error"] = "transport error; charge uncertain; no automatic retry"
        save_json(state_path, state)
        return
    try:
        with partial.open("xb") as stream:
            stream.write(audio)
            stream.flush()
            os.fsync(stream.fileno())
        metrics = inspect_audio(partial, mini)
    except Exception:
        item["status"] = "failed"
        item["error"] = "audio storage or decode validation failed; no automatic retry"
        if partial.exists():
            item["partial_sha256"] = sha_file(partial)
        save_json(state_path, state)
        return
    partial.replace(target)
    item.update(status="complete", origin="new_generation", checksum=metrics["sha256"],
                credits_used=int(cost_header) if cost_header and cost_header.isdecimal() else None,
                request_id=request_id, audio=metrics)
    save_json(state_path, state)


def verify_and_recover(state, state_path, mini):
    for item in state["items"].values():
        target = Path(item["output_path"])
        partial = target.with_name(target.stem + ".partial.mp3")
        if item["status"] == "complete":
            metrics = inspect_audio(target, mini)
            if metrics["sha256"] != item["checksum"]:
                raise RuntimeError(f"Completed audio changed {item['tts_source_media_id']}")
        elif item["status"] == "submitted":
            candidate = target if target.exists() else partial if partial.exists() else None
            if candidate:
                try:
                    metrics = inspect_audio(candidate, mini)
                except (ValueError, OSError):
                    item["status"] = "failed"
                    item["error"] = "orphaned response failed audio validation"
                else:
                    if candidate == partial:
                        partial.replace(target)
                    item.update(status="complete", origin="recovered_response", checksum=metrics["sha256"],
                                credits_used=None, audio=metrics)
            else:
                item["status"] = "uncertain"
                item["error"] = "submitted before interruption; no audio recovered; no automatic retry"
    save_json(state_path, state)


def retry_proven_empty(state, state_path, media_id, history_id, key, mini):
    """One retry only after a billed history item proves the API returned no audio."""
    item = state["items"].get(media_id)
    if (not item or item["status"] != "failed" or item.get("retry_count")
            or item.get("error") != "audio storage or decode validation failed; no automatic retry"):
        raise RuntimeError("Retry is unavailable for this performance")
    target = Path(item["output_path"])
    partial = target.with_name(target.stem + ".partial.mp3")
    if target.exists() or not partial.is_file() or partial.stat().st_size != 0:
        raise RuntimeError("Original failed response was not an empty audio file")
    history = get_json("/v1/history/" + history_id, key)
    dialogue = history.get("dialogue") or []
    when = datetime.fromtimestamp(history.get("date_unix", 0), timezone.utc)
    submitted = datetime.fromisoformat(item["generation_timestamp"])
    if (history.get("history_item_id") != history_id
            or history.get("model_id") != item["model"]
            or history.get("output_format") != FORMAT
            or len(dialogue) != 1
            or dialogue[0].get("voice_id") != state["voice_id"]
            or dialogue[0].get("text") != item["request_text"]
            or abs((when - submitted).total_seconds()) > 20):
        raise RuntimeError("History item does not prove the failed request")
    request = Request(BASE + "/v1/history/" + history_id + "/audio",
                      headers={"xi-api-key": key, "Accept": "audio/mpeg"})
    try:
        with urlopen(request, timeout=30) as response:
            history_audio = response.read()
    except (HTTPError, URLError, TimeoutError):
        raise RuntimeError("Could not confirm history audio is empty") from None
    if history_audio:
        raise RuntimeError("History audio is no longer empty; recover it instead of retrying")
    recovery = state_path.parent / "recovery"
    recovery.mkdir(exist_ok=True)
    partial.replace(recovery / f"{media_id}-first-empty.mp3")
    item["prior_failed_attempt"] = {
        "history_item_id": history_id, "request_id": history.get("request_id"),
        "credits_used": ((history.get("character_count_change_to") or 0)
                         - (history.get("character_count_change_from") or 0)),
        "audio_bytes": 0, "generation_timestamp": item["generation_timestamp"],
    }
    item["retry_count"] = 1
    item["status"] = "planned"
    item.pop("error", None)
    item.pop("partial_sha256", None)
    save_json(state_path, state)
    generate_one(item, key, state["voice_id"], mini, state, state_path)
    print(json.dumps({"retry_media_id": media_id, "status": item["status"],
                      "original_credits": item["prior_failed_attempt"]["credits_used"],
                      "retry_credits": item.get("credits_used")}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commander", required=True)
    parser.add_argument("--voice-name", required=True)
    parser.add_argument("--routing", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--pilot-journal", type=Path)
    parser.add_argument("--decoder-path", type=Path)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--retry-empty-history", nargs=2, metavar=("MEDIA_ID", "HISTORY_ITEM_ID"))
    args = parser.parse_args()
    if args.batch_size < 1 or args.batch_size > 30:
        parser.error("batch-size must be 1..30")
    if not args.output.resolve().is_relative_to(Path("work").resolve()):
        parser.error("output must be under ignored work/")
    plan, routes, hashes, safe_count = load_plan(args.commander, args.routing)
    projected_ceiling = sum(len(row["recommended_tags"] + " " + row["czech_text"]) for row in plan)
    if projected_ceiling > 10000:
        raise RuntimeError(f"Conservative credit projection {projected_ceiling} exceeds 10000")
    key = api_key()
    voice_id = voice_and_models(key, args.voice_name)
    before = subscription(key)
    if before["remaining"] < projected_ceiling:
        raise RuntimeError(f"Insufficient credits for conservative projection {projected_ceiling}")
    mini = decoder(args.decoder_path)
    state, state_path = prepare_state(args, plan, routes, hashes, safe_count, voice_id, before, mini)
    verify_and_recover(state, state_path, mini)
    print(json.dumps({"safe_media_ids": safe_count, "unique_performances": len(plan),
                      "projected_credit_ceiling": projected_ceiling,
                      "starting_credits": state["starting_credits"],
                      "current_credits": before["remaining"],
                      "reused": sum(x["origin"] == "pilot_reused" for x in state["items"].values() if x["status"] == "complete")}), flush=True)
    if args.retry_empty_history:
        media_id, history_id = args.retry_empty_history
        retry_proven_empty(state, state_path, media_id, history_id, key, mini)
        after = subscription(key)
        state["latest_credits"] = after["remaining"]
        save_json(state_path, state)
        return
    submitted = 0
    for row in plan:
        item = state["items"][row["tts_source_media_id"]]
        if item["status"] != "planned":
            continue
        known_cost = sum(x.get("credits_used") or 0 for x in state["items"].values() if x.get("origin") == "new_generation")
        if known_cost + len(item["request_text"]) > 10000:
            print("HARD STOP: 10000 credit safety ceiling", flush=True)
            break
        generate_one(item, key, voice_id, mini, state, state_path)
        submitted += 1
        counts = {status: sum(x["status"] == status for x in state["items"].values()) for status in ("complete", "failed", "uncertain", "planned")}
        print(f"{item['tts_source_media_id']} {item['model']} {item['status']} {counts}", flush=True)
        if submitted % args.batch_size == 0:
            current = subscription(key)
            state["latest_credits"] = current["remaining"]
            save_json(state_path, state)
            print(f"BATCH {submitted}: remaining credits {current['remaining']}", flush=True)
            if state["starting_usage"] <= current["used"] and current["used"] - state["starting_usage"] > 10000:
                print("HARD STOP: subscription usage exceeded 10000", flush=True)
                break
    after = subscription(key)
    state["latest_credits"] = after["remaining"]
    state["finished_at"] = utc_now()
    save_json(state_path, state)
    counts = {status: sum(x["status"] == status for x in state["items"].values()) for status in ("complete", "failed", "uncertain", "planned")}
    print(json.dumps({"counts": counts, "starting_credits": state["starting_credits"],
                      "remaining_credits": after["remaining"],
                      "account_usage_delta": after["used"] - state["starting_usage"],
                      "new_request_cost_headers": sum(x.get("credits_used") or 0 for x in state["items"].values() if x.get("origin") == "new_generation")}), flush=True)


if __name__ == "__main__":
    main()
