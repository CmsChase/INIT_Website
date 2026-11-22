"""Apply an explicitly reviewed, checksum-pinned correction to one existing post.

No collection, AI calls, new messages, or arbitrary replacement content. Plans
expire at the end of their Shanghai date. Uncertain edits retain a reservation.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from .history import GitHistory, HistoryError, publication_lock
from .publishing import PublishError, edit_message, get_message, message_matches


def payload_hash(payload):
    return sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def correct(history, client, plan, preview_dir, now, *, apply=False, webhook=""):
    if now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat() != plan["date"]:
        raise HistoryError("Correction plan has expired or is not for today")
    if history.pending:
        raise HistoryError("Unresolved publication exists; inspect Discord before correcting")
    documents = {}
    for name in ("discord.json", "run.json"):
        raw = (preview_dir / name).read_bytes()
        if len(raw) > 2_000_000 or sha256(raw).hexdigest() != plan["files"][name]:
            raise HistoryError("Preview checksum does not match the reviewed correction")
        documents[name] = json.loads(raw)
    payload, report = documents["discord.json"], documents["run.json"]
    verification = report.get("verification", {})
    if (report.get("date") != plan["date"] or report.get("status") != "preview"
            or report.get("publishing_requested") is not False or report.get("fixture") is not False
            or not 1 <= report.get("stories", 0) <= 5
            or verification.get("checked") != report["stories"] or verification.get("shortfall") != 0
            or len(payload.get("embeds", [])) != report["stories"]
            or payload.get("allowed_mentions") != {"parse": []}):
        raise HistoryError("Correction requires a fully verified, non-fixture preview")
    checks = [r for r in verification["stories"] if r["status"] == "primary_body_checked"]
    if [r["primary_url"] for r in checks] != [e["url"] for e in payload["embeds"]]:
        raise HistoryError("Preview embeds do not match verified primary sources")
    entries = [e for e in history.data["publications"] if e["id"] == plan["publication_id"]
               and e["date"] == plan["date"] and e.get("message_id") == plan["message_id"]
               and e["status"] == "sent"]
    if len(entries) != 1:
        raise HistoryError("The exact stored publication/message was not found")
    entry = entries[0]
    if entry["payload_sha256"] == payload_hash(payload):
        return {"status": "already_corrected", "message_id": plan["message_id"]}
    if (entry["payload_sha256"] != plan["previous_payload_sha256"]
            or payload_hash(entry["payload"]) != plan["previous_payload_sha256"]):
        raise HistoryError("Stored publication changed since correction review")
    result = {"status": "correction_ready", "date": plan["date"], "message_id": plan["message_id"],
              "stories": report["stories"], "source_run_id": plan["source_run_id"]}
    if not apply:
        return result  # No Discord request or state write during a dry run.
    current = get_message(client, webhook, plan["message_id"])
    if not message_matches(current, entry["payload"]) or current.get("attachments"):
        raise HistoryError("Live message changed or has attachments; refusing to overwrite it")
    entry.setdefault("revisions", []).append({
        "payload": deepcopy(entry["payload"]), "payload_sha256": entry["payload_sha256"],
        "stories": deepcopy(entry["stories"]), "replaced_at": now.isoformat()})
    # Keep every previously displayed story in deduplication history, including
    # the removed interview. The current payload itself contains only new stories.
    known = {s["id"] for s in entry["stories"]}
    for check in checks:
        if check["article_id"] not in known:
            entry["stories"].append({"id": check["article_id"], "title": check["primary_headline"],
                                     "url": check["discovery_url"], "primary_url": check["primary_url"]})
            known.add(check["article_id"])
    entry.update(status="pending", payload=payload, payload_sha256=payload_hash(payload),
                 correction={**result, "status": "pending", "source_commit": plan["source_commit"]})
    history.save()  # Durable write-ahead reservation BEFORE PATCH, never POST.
    edit_message(client, webhook, plan["message_id"], payload)
    entry["correction"].update(status="confirmed", edited_at=datetime.now(timezone.utc).isoformat())
    history.resolve(entry["id"], "sent", plan["message_id"])
    return {**result, "status": "corrected"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--preview-dir", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        repository = Path(__file__).resolve().parents[3]
        with publication_lock(Path(".state/correction.lock")):
            history = GitHistory(repository)
            with httpx.Client(trust_env=False) as client:
                result = correct(history, client, plan, args.preview_dir, datetime.now(timezone.utc),
                                 apply=args.apply, webhook=os.environ.get("DISCORD_WEBHOOK_URL", ""))
        text = json.dumps(result, indent=2)
        print(text)
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
                stream.write("## INIT Daily correction\n\n```json\n" + text + "\n```\n")
        return 0
    except Exception as exc:
        detail = str(exc) if isinstance(exc, (HistoryError, PublishError)) else type(exc).__name__
        logging.error("Correction stopped: %s. No new message or automatic retry.", detail)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
