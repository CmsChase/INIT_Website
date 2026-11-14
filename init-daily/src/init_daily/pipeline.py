from datetime import datetime, time, timedelta, timezone
import json
import logging
from collections import Counter
from pathlib import Path
from time import sleep
from zoneinfo import ZoneInfo

import httpx

from .collect import collect, parse_feed
from .config import Settings
from .editorial import candidate_record
from .models import is_research
from .formatting import discord_payload, markdown_preview
from .history import History, HistoryError
from .processing import process
from .publishing import publish, validate_webhook
from .ranking import fallback, shortlist

log = logging.getLogger(__name__)


def write_outputs(directory: Path, report: dict, payload: dict | None = None):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "run.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    # Always replace previews so a skipped run cannot leave yesterday's payload.
    (directory / "discord.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    preview = markdown_preview(payload) if payload else f"INIT Daily — {report['status']}\nNo message prepared.\n"
    if report.get("fixture"):
        preview = "> OFFLINE DEMO — synthetic test data, not real news.\n\n" + preview
    (directory / "briefing.md").write_text(preview, encoding="utf-8")


def run_pipeline(settings: Settings, history: History, client: httpx.Client, now: datetime,
                 *, send: bool = False, api_key: str | None = None, webhook: str = "",
                 fixture: Path | None = None, publish_at: time | None = None) -> dict:
    if send and fixture:
        raise ValueError("Fixture data can never be published")
    local_now = now.astimezone(ZoneInfo(settings.timezone))
    date = local_now.date().isoformat()
    report = {"date": date, "fixture": bool(fixture), "publishing_requested": send,
              "status": "started", "collected": 0, "candidates": 0, "stories": 0}
    target = datetime.combine(local_now.date(), publish_at, local_now.tzinfo) if publish_at else None
    if target:
        report["scheduled_for"] = target.isoformat()
        report["schedule_start_offset_seconds"] = round((local_now - target).total_seconds())
        if target - local_now > timedelta(minutes=20):
            report["status"] = "outside_delivery_window"
            write_outputs(settings.output_dir, report)
            return report
    if send:
        validate_webhook(webhook)  # Reject bad credentials/config before paying for AI.
    if history.pending:
        raise HistoryError("Unresolved publication exists; inspect the Discord channel and resolve history first")
    if history.sent_on(date):
        report["status"] = "already_published"
        write_outputs(settings.output_dir, report)
        return report
    if fixture:
        articles, source_report = [], {}
        for source in settings.sources:
            items = parse_feed((fixture / f"{source.id}.xml").read_bytes(), source, now, settings)
            articles.extend(items)
            source_report[source.id] = {"status": "fixture", "recent_items": len(items)}
        api_key = None  # Even if secrets are set, the demo has NO external calls.
    else:
        articles, source_report = collect(client, settings, now)
    report.update(collected=len(articles), sources=source_report)
    previous = history.previous_stories()
    candidates = shortlist(articles, previous, settings, now)
    report["candidates"] = len(candidates)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    audit = [candidate_record(a, now) for a in candidates]
    (settings.output_dir / "candidates.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report["editorial"] = {"profile": "mainstream_ai_industry", "candidate_standalone_research": sum(is_research(a) for a in candidates)}
    # Avoid a paid call when diversity/minimum requirements cannot be met.
    if len(fallback(candidates, settings, now)) < settings.min_stories:
        report["status"] = "insufficient_news"
        write_outputs(settings.output_dir, report)
        log.info("Fewer than %s eligible stories; skipping today's message", settings.min_stories)
        return report
    stories, ai_report = process(client, candidates, settings, now, api_key)
    if settings.verify_selected and not fixture:
        from .verification import verify_selected
        # Prefer directly verifiable primary candidates among replacements, then
        # preserve the editorial order within each tier.
        alternates = sorted(candidates, key=lambda a: a.source_tier != "official")
        stories, verification = verify_selected(stories, settings, client, now,
                                               alternates=tuple(alternates), previous=tuple(previous))
        report["verification"] = verification
    report.update(stories=len(stories), processing=ai_report)
    report["editorial"].update(
        selected=[candidate_record(s.article, now) for s in stories],
        selected_standalone_research=sum(is_research(s.article) for s in stories),
        company_counts=dict(Counter(c for s in stories for c in candidate_record(s.article, now)["companies"])),
        source_tiers=dict(Counter(s.article.source_tier for s in stories)),
    )
    if len(stories) < settings.min_stories:
        if report.get("verification", {}).get("withheld"):
            report["status"] = "insufficient_verified_news"
            log.warning("Only %s stories passed primary-source checks; no Discord message prepared", len(stories))
        else:
            report["status"] = "insufficient_news"
        write_outputs(settings.output_dir, report)
        return report
    payload = discord_payload(stories, date, now, ai_report["mode"])
    if fixture:
        payload["content"] = "**OFFLINE DEMO · SYNTHETIC DATA**\n" + payload["content"]
    report["status"] = "preview"
    write_outputs(settings.output_dir, report, payload)
    if send:
        if target:
            delay = (target - datetime.now(timezone.utc)).total_seconds()
            if delay > 0:
                log.info("Briefing prepared. Waiting %.1f seconds for scheduled delivery at %s", delay, target.isoformat())
                sleep(delay)
        publication_id = history.reserve(date, stories, payload)
        report.update(status="reserved", publication_id=publication_id)
        write_outputs(settings.output_dir, report, payload)
        message_id = publish(client, webhook, payload)
        published_at = datetime.now(local_now.tzinfo).isoformat()
        history.resolve(publication_id, "sent", message_id)
        report.update(status="published", message_id=message_id, published_at=published_at)
        write_outputs(settings.output_dir, report, payload)
    return report
