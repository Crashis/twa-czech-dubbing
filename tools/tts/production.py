"""Resume-safe ElevenLabs TTS staging from an independently checked routing CSV.

This tool writes only to ignored work/. It does not create WEMs or touch game files.
Run with an explicit --commander, --routing, and --output directory. A submitted
request without a saved response is never automatically retried unless the task
explicitly passes --auto-retry-technical; even then a transport error is first
resolved against ElevenLabs history, and each performance gets at most one retry.
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
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from tools.tts.pronunciation import Resolver, commander_resolver, request_text

BASE = "https://api.elevenlabs.io"
MODELS = {"eleven_v3": "v3", "eleven_v4": "v4"}
FORMAT = "mp3_44100_128"
TECHNICAL_HTTP = {429, 500, 502, 503, 504}
BLOCKING_HTTP = {401, 402, 403, 404}


class HardStop(RuntimeError):
    """Account, credential, quota or voice rejection: no further request may be sent."""


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


def voice_and_models(key, voice_name, expected_voice_id=None, required_models=MODELS):
    page = get_json("/v2/voices?" + urlencode({"search": voice_name, "page_size": 100}), key)
    matches = [voice for voice in page.get("voices", []) if voice.get("name") == voice_name]
    if page.get("has_more") or len(matches) != 1:
        raise RuntimeError("Requested voice lookup was not unique")
    if expected_voice_id and matches[0].get("voice_id") != expected_voice_id:
        raise HardStop("Production voice name and voice ID do not match")
    models = get_json("/v1/models", key)
    available = {m.get("model_id") for m in models if m.get("can_do_text_to_speech")}
    if not set(required_models).issubset(available):
        raise RuntimeError("Required ElevenLabs models are unavailable")
    return matches[0]["voice_id"]


def load_plan(commander, routing_path, require_model=None):
    root = Path("data/commanders") / commander
    plan_path = root / "tts-plan/tts-plan.csv"
    voice_path = root / "tts-plan/voice-lines-cz.csv"
    inventory_path = root / "research/voice-lines.csv"
    plan, voices, inventory, routing = map(read_csv, (plan_path, voice_path, inventory_path, routing_path))
    # Inventory field names keep the commander id verbatim (e.g. zhuge-liang).
    safe_column = "safe_to_replace_for_" + commander
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
    summary_path = root / "tts-plan/plan-summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if (summary["safe_spoken_media_ids"], summary["unique_tts_performances"],
                summary["duplicate_ids_saved"]) != (len(safe), len(plan), len(safe) - len(plan)):
            raise RuntimeError("Canonical plan summary counts changed")
    if require_model and any(route["selected_model"] != require_model for route in routes.values()):
        raise RuntimeError("Routing does not use the required production model everywhere")
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
            "clipped_samples_pcm16": sum(x in (-32768, 32767) for x in samples),
            "sha256": sha_file(path)}


def items_from_plan(plan, routes, output, voice_id, voice_name=None, pronunciation=None):
    pronunciation = pronunciation or Resolver([])
    pronunciation.verify_phrases({row["tts_source_media_id"]: row["czech_text"] for row in plan})
    items = {}
    for row in plan:
        source = row["tts_source_media_id"]
        model = routes[source]["selected_model"]
        # Only approved overrides; an unreviewed one stops the run instead of silently using either spelling.
        spoken = pronunciation.resolve(row["czech_text"], "production", source)
        text = request_text(row["recommended_tags"], spoken["tts_input_text"])
        request = {"voice_id": voice_id, "model_id": model, "text": text, "output_format": FORMAT}
        items[source] = {
            "tts_performance_group": row["tts_performance_group"],
            "tts_source_media_id": source, "member_media_ids": row["member_media_ids"].split(";"),
            "voice_id": voice_id, "voice_name": voice_name,
            "czech_text_sha256": sha_bytes(row["czech_text"].encode("utf-8")),
            "model": model, "czech_text": row["czech_text"], "canonical_text": row["czech_text"],
            "tts_input_text": spoken["tts_input_text"],
            "applied_pronunciation_overrides": spoken["applied_pronunciation_overrides"],
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
    # Single-voice journals name the voice once; comparison journals per request.
    if "voice_name" in journal and journal["voice_name"] != state["voice_name"]:
        raise RuntimeError("Unexpected pilot voice")
    for pilot in journal["requests"]:
        if pilot["status"] != "complete":
            continue
        if "voice_id" in pilot and pilot["voice_id"] != state["voice_id"]:
            continue  # another candidate voice; never production audio
        if "voice_id" in pilot and pilot.get("voice_name") != state["voice_name"]:
            raise RuntimeError(f"Pilot voice name mismatch {pilot['media_id']}")
        if "voice_name" not in journal and "voice_id" not in pilot:
            raise RuntimeError("Pilot voice provenance missing")
        item = state["items"].get(pilot["media_id"])
        if not item or item["model"] != pilot["model"] or item["status"] in ("complete", "stale"):
            continue
        if (pilot.get("tts_input_text", pilot["czech_text"]) != item.get("tts_input_text", item["czech_text"])
                and pilot["czech_text"] == item["czech_text"]):
            continue  # piloted with a pronunciation production did not approve; never production audio
        expected_sha = pilot["audio"]["sha256"] if "audio" in pilot else pilot["sha256"]
        if (item["czech_text"] != pilot["czech_text"]
                or item["request_text"] != pilot.get("request_text", pilot.get("text"))
                or item["tags"] != pilot["tags"]
                or pilot.get("output_format", FORMAT) != FORMAT):
            raise RuntimeError(f"Pilot provenance mismatch {pilot['media_id']}")
        source = Path(pilot["output"])
        if sha_file(source) != expected_sha:
            raise RuntimeError(f"Pilot checksum mismatch {pilot['media_id']}")
        target = Path(item["output_path"])
        if target.exists():
            if sha_file(target) != expected_sha:
                raise RuntimeError(f"Staged pilot checksum mismatch {pilot['media_id']}")
        else:
            shutil.copyfile(source, target)
        metrics = inspect_audio(target, mini)
        item.update(status="complete", origin="pilot_reused", source="reused_pilot",
                    checksum=metrics["sha256"],
                    generation_timestamp=pilot.get("submitted_at_utc") or
                    datetime.fromtimestamp(source.stat().st_mtime, timezone.utc).isoformat(),
                    credits_used=pilot.get("credits"), request_id=pilot.get("request_id"),
                    pilot_output=str(source), audio=metrics)


REQUEST_FIELDS = ("tts_input_text", "applied_pronunciation_overrides", "request_text", "request_sha256")
STALE_FIELDS = ("needs_regeneration", "stale_reason", "status_before_stale", "current_tts_input_text",
                "current_applied_pronunciation_overrides")


def reconcile_pronunciation(item, expected):
    """Audio requested with an older TTS input is never current; it is marked, never resent automatically."""
    sent = item.get("tts_input_text", item["czech_text"])  # older states sent the canonical text
    if sent == expected["tts_input_text"]:
        if item.get("needs_regeneration"):  # the override returned to what was actually sent
            item["status"] = item["status_before_stale"]
            for field in STALE_FIELDS:
                item.pop(field, None)
        return
    if item["status"] == "planned":  # nothing was sent yet
        item.update({field: expected[field] for field in REQUEST_FIELDS})
        return
    # The recorded request stays: it is what ElevenLabs actually received (and what history recovery matches).
    item.setdefault("status_before_stale", item["status"])
    item.update(status="stale", needs_regeneration=True,
                stale_reason="pronunciation override changed after the request; regeneration needs authorization",
                current_tts_input_text=expected["tts_input_text"],
                current_applied_pronunciation_overrides=expected["applied_pronunciation_overrides"])


def prepare_state(args, plan, routes, hashes, safe_count, voice_id, before, mini, pronunciation=None):
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    (output / "audio").mkdir(exist_ok=True)
    state_path = output / "generation-state.json"
    expected = items_from_plan(plan, routes, output, voice_id, args.voice_name, pronunciation)
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if (state["source_hashes"] != hashes or state["voice_id"] != voice_id
                or set(state["items"]) != set(expected)):
            raise RuntimeError("Frozen production inputs changed; refusing resume")
        for source, item in state["items"].items():
            for key in ("model", "output_path", "czech_text"):
                if item[key] != expected[source][key]:
                    raise RuntimeError(f"Frozen request changed {source}")
            reconcile_pronunciation(item, expected[source])
            for key in ("request_sha256", "request_text"):
                if item[key] != expected[source][key] and not item.get("needs_regeneration"):
                    raise RuntimeError(f"Frozen request changed {source}")
    else:
        state = {"schema": 1, "commander": args.commander, "voice_name": args.voice_name,
                 "voice_id": voice_id, "source_hashes": hashes, "safe_media_ids": safe_count,
                 "unique_performances": len(plan), "created_at": utc_now(),
                 "starting_credits": before["remaining"], "starting_usage": before["used"],
                 "credit_limit": before["limit"], "latest_credits": before["remaining"],
                 "items": expected}
    # Informational only: override edits are judged per performance, not as a whole-run freeze.
    state["pronunciation_override_hashes"] = pronunciation.files if pronunciation else {}
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
    body = {"text": item["request_text"], "model_id": item["model"]}
    if item.get("voice_settings"):
        # Request-level override only; the stored voice settings are never modified.
        body["voice_settings"] = item["voice_settings"]
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
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
        try:
            detail = json.load(exc).get("detail") or {}
        except (ValueError, OSError, AttributeError):
            detail = {}
        reason = detail.get("status", "") if isinstance(detail, dict) else ""
        item["status"] = "failed" if 400 <= exc.code < 500 and exc.code != 429 else "uncertain"
        item["error"] = f"HTTP {exc.code} {reason}".strip() + "; no automatic retry"
        item["failure_kind"] = "technical" if exc.code in TECHNICAL_HTTP else "rejected"
        save_json(state_path, state)
        if exc.code in BLOCKING_HTTP or "quota" in reason or "voice" in reason:
            raise HardStop(f"ElevenLabs rejected the request: HTTP {exc.code} {reason}".strip())
        return
    except (URLError, TimeoutError, OSError):
        item["status"] = "uncertain"
        item["error"] = "transport error; charge uncertain; no automatic retry"
        item["failure_kind"] = "transport"
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
        item["failure_kind"] = "empty_or_corrupt"
        item["request_id"] = request_id
        item["failed_credits_header"] = int(cost_header) if cost_header and cost_header.isdecimal() else None
        if partial.exists():
            item["partial_sha256"] = sha_file(partial)
        save_json(state_path, state)
        return
    partial.replace(target)
    item.update(status="complete", origin="new_generation", source="generated", checksum=metrics["sha256"],
                credits_used=int(cost_header) if cost_header and cost_header.isdecimal() else None,
                request_id=request_id, audio=metrics)
    item.pop("error", None)
    item.pop("failure_kind", None)
    save_json(state_path, state)


def history_items(key, voice_id, model, since_unix):
    """All TTS history for one voice/model since a time, with complete pagination."""
    found, after = [], None
    for _ in range(50):
        query = {"voice_id": voice_id, "model_id": model, "source": "TTS",
                 "date_after_unix": int(since_unix), "page_size": 1000}
        if after:
            query["start_after_history_item_id"] = after
        page = get_json("/v1/history?" + urlencode(query), key)
        found.extend(page.get("history", []))
        after = page.get("last_history_item_id")
        if not page.get("has_more"):
            return found
        if not after:
            break
    raise RuntimeError("History pagination did not finish")


def history_fields(history):
    """Text and voice live either on the item or on its single dialogue turn."""
    text, voice_id, voice_name = history.get("text"), history.get("voice_id"), history.get("voice_name")
    turns = history.get("dialogue") or []
    if turns:
        if len(turns) != 1:
            return None, None, None
        text, voice_id = turns[0].get("text"), turns[0].get("voice_id")
        voice_name = turns[0].get("voice_name", voice_name)
    return text, voice_id, voice_name


def recover_from_history(item, key, state, mini):
    """Download an already-billed response instead of paying for a retry."""
    submitted = datetime.fromisoformat(item["generation_timestamp"]).timestamp()
    matches = []
    for history in history_items(key, state["voice_id"], item["model"], submitted - 10):
        text, voice_id, _ = history_fields(history)
        if (text == item["request_text"] and voice_id == state["voice_id"]
                and history.get("model_id") == item["model"]
                and abs(history.get("date_unix", 0) - submitted) <= 180):
            matches.append(history)
    if len(matches) > 1:
        raise RuntimeError(f"Ambiguous history for {item['tts_source_media_id']}; refusing retry")
    if not matches:
        return False
    history = matches[0]
    request = Request(BASE + "/v1/history/" + history["history_item_id"] + "/audio",
                      headers={"xi-api-key": key, "Accept": "audio/mpeg"})
    try:
        with urlopen(request, timeout=60) as response:
            audio = response.read()
    except (HTTPError, URLError, TimeoutError, OSError):
        raise RuntimeError(f"Billed history audio unavailable for {item['tts_source_media_id']}; refusing retry") from None
    target = Path(item["output_path"])
    partial = target.with_name(target.stem + ".partial.mp3")
    if not audio:
        return False
    with partial.open("xb") as stream:
        stream.write(audio)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        metrics = inspect_audio(partial, mini)
    except (ValueError, OSError):
        return False
    partial.replace(target)
    credits = (history.get("character_count_change_to") or 0) - (history.get("character_count_change_from") or 0)
    item.update(status="complete", origin="new_generation", source="generated", checksum=metrics["sha256"],
                credits_used=credits, request_id=history.get("request_id"),
                history_item_id=history["history_item_id"], recovered_from_history=True, audio=metrics)
    item.pop("error", None)
    item.pop("failure_kind", None)
    return True


def retry_technical(item, key, state, state_path, mini):
    """At most one automatic retry for a clear technical failure."""
    if item.get("retry_count") or item.get("failure_kind") not in {"technical", "transport", "empty_or_corrupt"}:
        return
    target = Path(item["output_path"])
    partial = target.with_name(target.stem + ".partial.mp3")
    time.sleep(15 if "429" in item.get("error", "") else 5)
    prior = {"generation_timestamp": item["generation_timestamp"], "error": item["error"],
             "failure_kind": item["failure_kind"], "request_id": item.get("request_id"),
             "credits_header": item.get("failed_credits_header")}
    if item["failure_kind"] == "transport" or item["error"].startswith("HTTP 5"):
        # The server may have completed and billed the request; never pay twice.
        if recover_from_history(item, key, state, mini):
            item["prior_failed_attempt"] = prior | {"resolution": "billed response recovered from history"}
            save_json(state_path, state)
            return
    if partial.exists():
        recovery = state_path.parent / "recovery"
        recovery.mkdir(exist_ok=True)
        partial.replace(recovery / f"{item['tts_source_media_id']}-first-attempt.mp3")
    if target.exists():
        raise RuntimeError(f"Unexpected staged audio before retry {item['tts_source_media_id']}")
    item["prior_failed_attempt"] = prior
    item["retry_count"] = 1
    item["status"] = "planned"
    for field in ("error", "failure_kind", "partial_sha256", "failed_credits_header"):
        item.pop(field, None)
    save_json(state_path, state)
    generate_one(item, key, state["voice_id"], mini, state, state_path)
    if item["status"] != "complete":
        item["error"] = item.get("error", "retry failed") + "; one automatic retry already used"
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


def spent_credits(state):
    """Known cost of this run: final new outputs plus billed failed first attempts."""
    items = state["items"].values()
    return (sum(x.get("credits_used") or 0 for x in items if x.get("origin") == "new_generation")
            + sum((x.get("prior_failed_attempt") or {}).get("credits_header")
                  or (x.get("prior_failed_attempt") or {}).get("credits_used") or 0 for x in items))


def audit_outputs(state, state_path, key, mini, before):
    """Read-only: re-decode every output and match each paid request to ElevenLabs history."""
    output = state_path.parent
    items = list(state["items"].values())
    rows, problems = [], []
    for item in items:
        if item["status"] != "complete":
            problems.append({"tts_source_media_id": item["tts_source_media_id"], "problem": item["status"]})
            continue
        path = Path(item["output_path"])
        metrics = inspect_audio(path, mini)
        valid = (metrics["sha256"] == item["checksum"] == item["audio"]["sha256"]
                 and item.get("voice_id", state["voice_id"]) == state["voice_id"]
                 and item["request_text"] == request_text(item["tags"], item.get("tts_input_text", item["czech_text"]))
                 and sha_bytes(item["czech_text"].encode("utf-8")) == item.get("czech_text_sha256",
                     sha_bytes(item["czech_text"].encode("utf-8"))))
        if not valid:
            problems.append({"tts_source_media_id": item["tts_source_media_id"], "problem": "provenance"})
        rows.append({"tts_source_media_id": item["tts_source_media_id"], "origin": item["origin"],
                     "model": item["model"], "request_id": item.get("request_id"), "audio": metrics,
                     "clipping_pass": metrics["clipped_samples_pcm16"] == 0})
    since = min(datetime.fromisoformat(x["generation_timestamp"]).timestamp() for x in items
                if x.get("generation_timestamp")) - 60
    history = []
    for model in sorted({x["model"] for x in items}):
        history.extend(history_items(key, state["voice_id"], model, since))
    by_request = {h.get("request_id"): h for h in history if h.get("request_id")}
    expected = {x["request_id"]: x for x in items if x["status"] == "complete" and x.get("request_id")}
    failed_first = {(x.get("prior_failed_attempt") or {}).get("request_id") for x in items} - {None}
    mismatches, missing, history_credits = [], [], 0
    for request_id, item in expected.items():
        found = by_request.get(request_id)
        if not found:
            missing.append(item["tts_source_media_id"])
            continue
        text, voice_id, voice_name = history_fields(found)
        if (text != item["request_text"] or voice_id != state["voice_id"]
                or found.get("model_id") != item["model"]
                or (voice_name and voice_name != state["voice_name"])):
            mismatches.append(item["tts_source_media_id"])
        history_credits += ((found.get("character_count_change_to") or 0)
                            - (found.get("character_count_change_from") or 0)) if item["origin"] == "new_generation" else 0
    known = set(expected) | failed_first
    unexpected = [h.get("history_item_id") for h in history if h.get("request_id") not in known]
    history_audit = {"source": "ElevenLabs GET /v1/history", "voice_id": state["voice_id"],
                     "voice_name": state["voice_name"], "history_items_in_window": len(history),
                     "matched_final_requests": len(expected) - len(missing),
                     "matched_new_generation_requests": sum(1 for r, x in expected.items()
                                                            if x["origin"] == "new_generation" and r in by_request),
                     "matched_reused_pilot_requests": sum(1 for r, x in expected.items()
                                                          if x["origin"] == "pilot_reused" and r in by_request),
                     "matched_failed_first_attempts": len(failed_first & set(by_request)),
                     "missing_history_for": missing, "text_model_voice_mismatches": mismatches,
                     "unexpected_history_items_in_window": len(unexpected),
                     "credits_new_generation_history": history_credits}
    origins = {}
    for item in items:
        if item["status"] == "complete":
            origins[item["origin"]] = origins.get(item["origin"], 0) + 1
    durations = [r["audio"]["duration_seconds"] for r in rows]
    audit = {"status": "PASS" if not problems and not missing and not mismatches and not unexpected
             and all(r["clipping_pass"] for r in rows) else "FAIL",
             "voice_name": state["voice_name"], "voice_id": state["voice_id"],
             "models": {m: sum(1 for x in items if x["model"] == m) for m in sorted({x["model"] for x in items})},
             "safe_media_ids": state["safe_media_ids"], "unique_performances": len(items),
             "duplicate_media_ids_reusing_performance": state["safe_media_ids"] - len(items),
             "successful": len(rows), "failed": sum(x["status"] == "failed" for x in items),
             "uncertain": sum(x["status"] == "uncertain" for x in items),
             "missing": sum(x["status"] == "planned" for x in items), "origins": origins,
             "automatic_retries": sum(1 for x in items if x.get("retry_count")),
             "duplicate_media_id_requests": 0, "problems": problems,
             "starting_credits": state["starting_credits"], "remaining_credits_api": before["remaining"],
             "account_usage_delta_since_start": before["used"] - state["starting_usage"],
             "credits_used_known": spent_credits(state),
             "audio_files": len(rows), "audio_bytes_total": sum(r["audio"]["bytes"] for r in rows),
             "duration_min_seconds": min(durations, default=None),
             "duration_max_seconds": max(durations, default=None),
             "clipped_files": {r["tts_source_media_id"]: r["audio"]["clipped_samples_pcm16"]
                               for r in rows if not r["clipping_pass"]},
             "human_listening": "NOT_RUN", "rows": rows}
    save_json(output / "history-audit.json", history_audit)
    save_json(output / "audio-audit.json", audit)
    return {k: v for k, v in audit.items() if k != "rows"} | {"history": history_audit}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commander", required=True)
    parser.add_argument("--voice-name", required=True)
    parser.add_argument("--voice-id", help="expected voice ID; a different lookup result is a hard stop")
    parser.add_argument("--routing", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--pilot-journal", type=Path)
    parser.add_argument("--decoder-path", type=Path)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--require-model", choices=sorted(MODELS))
    parser.add_argument("--max-credits", type=int, default=10000,
                        help="ceiling for the conservative 1 credit/character projection of this run")
    parser.add_argument("--auto-retry-technical", action="store_true",
                        help="explicitly authorized single retry after a clear technical failure")
    parser.add_argument("--preflight-only", action="store_true", help="validate and project cost; no TTS request")
    parser.add_argument("--audit", action="store_true", help="read-only audio/history audit; no TTS request")
    parser.add_argument("--retry-empty-history", nargs=2, metavar=("MEDIA_ID", "HISTORY_ITEM_ID"))
    args = parser.parse_args()
    if args.batch_size < 1 or args.batch_size > 30:
        parser.error("batch-size must be 1..30")
    if not args.output.resolve().is_relative_to(Path("work").resolve()):
        parser.error("output must be under ignored work/")
    plan, routes, hashes, safe_count = load_plan(args.commander, args.routing, args.require_model)
    pronunciation = commander_resolver(args.commander)
    items_from_plan(plan, routes, args.output, None, pronunciation=pronunciation)  # offline stop before any request
    key = api_key()
    voice_id = voice_and_models(key, args.voice_name, args.voice_id,
                                {route["selected_model"] for route in routes.values()})
    before = subscription(key)
    mini = decoder(args.decoder_path)
    if args.audit:
        state_path = args.output / "generation-state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state["source_hashes"] != hashes or state["voice_id"] != voice_id:
            raise RuntimeError("Frozen production inputs changed; refusing audit")
        print(json.dumps(audit_outputs(state, state_path, key, mini, before), ensure_ascii=False, indent=2))
        return
    state, state_path = prepare_state(args, plan, routes, hashes, safe_count, voice_id, before, mini, pronunciation)
    verify_and_recover(state, state_path, mini)
    pending = [state["items"][row["tts_source_media_id"]] for row in plan
               if state["items"][row["tts_source_media_id"]]["status"] == "planned"]
    projected = sum(len(item["request_text"]) for item in pending)
    print(json.dumps({"safe_media_ids": safe_count, "unique_performances": len(plan),
                      "pending_generations": len(pending),
                      "projected_credit_ceiling": projected,
                      "starting_credits": state["starting_credits"],
                      "current_credits": before["remaining"],
                      "needs_regeneration": sum(x["status"] == "stale" for x in state["items"].values()),
                      "reused": sum(x["origin"] == "pilot_reused" for x in state["items"].values() if x["status"] == "complete")}), flush=True)
    if projected + spent_credits(state) > args.max_credits:
        raise RuntimeError(f"Conservative credit projection {projected} exceeds {args.max_credits}")
    if before["remaining"] < projected:
        raise HardStop(f"Insufficient credits for conservative projection {projected}")
    if args.preflight_only:
        return
    if args.retry_empty_history:
        media_id, history_id = args.retry_empty_history
        retry_proven_empty(state, state_path, media_id, history_id, key, mini)
        after = subscription(key)
        state["latest_credits"] = after["remaining"]
        save_json(state_path, state)
        return
    submitted = 0
    stop = None
    try:
        for row in plan:
            item = state["items"][row["tts_source_media_id"]]
            if item["status"] != "planned":
                continue
            if spent_credits(state) + len(item["request_text"]) > args.max_credits:
                stop = f"{args.max_credits} credit safety ceiling"
                break
            generate_one(item, key, voice_id, mini, state, state_path)
            if item["status"] != "complete" and args.auto_retry_technical:
                try:
                    retry_technical(item, key, state, state_path, mini)
                except HardStop:
                    raise
                except RuntimeError as error:
                    item["status"] = "uncertain"
                    item["error"] = str(error)
                    save_json(state_path, state)
            submitted += 1
            counts = {status: sum(x["status"] == status for x in state["items"].values()) for status in ("complete", "failed", "uncertain", "planned", "stale")}
            print(f"{item['tts_source_media_id']} {item['model']} {item['status']} {counts}", flush=True)
            if submitted % args.batch_size == 0:
                current = subscription(key)
                state["latest_credits"] = current["remaining"]
                save_json(state_path, state)
                print(f"BATCH {submitted}: remaining credits {current['remaining']}", flush=True)
                if state["starting_usage"] <= current["used"] and current["used"] - state["starting_usage"] > args.max_credits:
                    stop = f"subscription usage exceeded {args.max_credits}"
                    break
    except HardStop as error:
        stop = str(error)
    if stop:
        print("HARD STOP: " + stop, flush=True)
        state["hard_stop"] = stop
    try:
        after = subscription(key)
    except RuntimeError:
        after = None
    if after:
        state["latest_credits"] = after["remaining"]
    state["finished_at"] = utc_now()
    save_json(state_path, state)
    counts = {status: sum(x["status"] == status for x in state["items"].values()) for status in ("complete", "failed", "uncertain", "planned", "stale")}
    print(json.dumps({"counts": counts, "starting_credits": state["starting_credits"],
                      "remaining_credits": after and after["remaining"],
                      "account_usage_delta": after and after["used"] - state["starting_usage"],
                      "known_credits_used": spent_credits(state), "hard_stop": stop}), flush=True)
    if stop:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
