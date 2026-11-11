from datetime import datetime
import re

from .models import Story, is_research


def safe_text(value: str, limit: int) -> str:
    # Source text must not inject links, mentions, or Discord markdown.
    value = re.sub(r"https?://\S+|www\.\S+", "[link omitted]", value)
    value = value.replace("@", "＠").replace("<", "‹").replace(">", "›")
    value = re.sub(r"([\\`*_~|\[\]])", r"\\\1", value)
    value = " ".join(value.split())
    return value if len(value) <= limit else value[:limit - 1] + "…"


def discord_payload(stories: list[Story], date: str, now: datetime, mode: str) -> dict:
    embeds = []
    for index, story in enumerate(stories, 1):
        article = story.article
        research = " · preliminary research" if is_research(article) else ""
        embeds.append({
            "title": f"{index:02d} / {safe_text(article.title, 230)}",
            "url": article.url,
            "description": safe_text(story.summary, 400),
            "color": 0xB8F36B,
            "fields": [{"name": "Why it matters for builders · editorial",
                        "value": safe_text(story.why, 260), "inline": False}],
            "footer": {"text": f"{safe_text(article.source_name, 80)}{research} · {article.published_at:%Y-%m-%d}"},
        })
    label = "Source excerpts · rule-based selection" if mode == "fallback" else "Source excerpts · AI selection"
    payload = {
        "username": "INIT Daily",
        "content": f"**INIT:// DAILY**  /  {date}\n{len(stories)} signals for people who build.\n-# {label}",
        "embeds": embeds, "allowed_mentions": {"parse": []}, "flags": 4096,
    }
    # Count all embed text, including field/footer strings, against Discord's 6000 total.
    total = sum(len(e["title"]) + len(e["description"]) + len(e["footer"]["text"])
                + sum(len(f["name"]) + len(f["value"]) for f in e["fields"]) for e in embeds)
    if not 3 <= len(embeds) <= 5 or total > 6000 or len(payload["content"]) > 2000:
        raise ValueError("Briefing violates Discord message limits")
    return payload


def markdown_preview(payload: dict) -> str:
    lines = [payload["content"], ""]
    for embed in payload["embeds"]:
        lines.extend([f"### {embed['title']}", embed["description"], "",
                      f"**{embed['fields'][0]['name']}**  {embed['fields'][0]['value']}",
                      f"[{embed['footer']['text']}]({embed['url']})", ""])
    return "\n".join(lines)
