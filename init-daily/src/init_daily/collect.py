from dataclasses import replace
from datetime import datetime, timedelta, timezone
import calendar
import logging
import re
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import feedparser
import httpx

from .config import Settings, Source
from .models import Article, canonical_url, plain_text, trusted_url

log = logging.getLogger(__name__)


class CollectionError(RuntimeError):
    pass


def fetch_feed(client: httpx.Client, source: Source, settings: Settings) -> bytes:
    allowed = tuple({urlsplit(source.url).hostname, *source.allowed_hosts})
    for attempt in range(settings.retries + 1):
        try:
            url = source.url
            for _ in range(5):
                if not trusted_url(url, allowed):
                    raise CollectionError("Untrusted feed redirect")
                with client.stream("GET", url, timeout=settings.http_timeout,
                                   follow_redirects=False) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get("location", ""))
                        continue
                    response.raise_for_status()
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > settings.max_feed_bytes:
                            raise CollectionError("Feed exceeded size limit")
                        chunks.append(chunk)
                    return b"".join(chunks)
            raise CollectionError("Too many feed redirects")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in {429, 500, 502, 503, 504}:
                raise CollectionError(f"HTTP {exc.response.status_code}") from None
        except httpx.RequestError:
            pass
        if attempt < settings.retries:
            time.sleep(.5 * 2 ** attempt)
    raise CollectionError("Feed unavailable after bounded retries")


def parse_feed(body: bytes, source: Source, now: datetime, settings: Settings) -> list[Article]:
    # Do not accept DTDs/entities; feedparser is tolerant of ordinary feed defects.
    markup = re.sub(rb"<!\[CDATA\[.*?\]\]>|<!--.*?-->", b"", body, flags=re.S).upper()
    if b"<!DOCTYPE" in markup or b"<!ENTITY" in markup:
        raise CollectionError("DTD/entity declarations are not accepted")
    parsed = feedparser.parse(body)
    if not parsed.get("version") or not parsed.entries:
        raise CollectionError("Not a recognized, nonempty RSS/Atom feed")
    cutoff = now - timedelta(hours=settings.lookback_hours)
    result = []
    for entry in parsed.entries[:500]:
        date = entry.get("published_parsed") or (entry["updated_parsed"] if "updated_parsed" in entry else None)
        if not date:
            continue  # Never label undated material as today's news.
        try:
            published = datetime.fromtimestamp(calendar.timegm(date), timezone.utc)
        except (ValueError, OverflowError):
            continue
        if not cutoff <= published <= now + timedelta(minutes=5):
            continue
        link = entry.get("link", "")
        if not link and entry.get("guidislink", False):
            link = entry.get("id", "")
        if not trusted_url(link, source.allowed_hosts):
            continue
        title = plain_text(entry.get("title", ""))[:240]
        # Abstracts, release notes, and feed descriptions only; no page scraping.
        excerpt = plain_text(entry.get("summary", "") or
                             next(iter(entry.get("content", [])), {}).get("value", ""))[:1800]
        if source.id.startswith("arxiv-"):
            # Revisions to old papers must not masquerade as fresh breakthroughs.
            if re.search(r"Announce Type:\s*replace", excerpt, re.I):
                continue
            if "Abstract:" in excerpt:
                excerpt = excerpt.split("Abstract:", 1)[1].strip()
        if len(title) < 8 or (len(excerpt) < 50 and not source.excerpt_adapter):
            continue
        result.append(Article(title, canonical_url(link), excerpt, published,
                              source.id, source.name, source.weight, source.category,
                              source.tier, source.company, source.ai_focused))
    return result


class _Description(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = {}

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        key = values.get("property") or values.get("name")
        if tag == "meta" and key in {"description", "og:description"}:
            self.values[key] = values.get("content", "")


def enrich_missing(client: httpx.Client, items: list[Article], source: Source,
                   settings: Settings) -> list[Article]:
    """Repair title-only HF entries or image-caption Google feed descriptions.

    Never follow arbitrary article links or use a third-party article extractor.
    """
    result, attempts = [], 0
    for article in items:
        caption = source.excerpt_adapter == "google_description" and bool(re.search(
            r"^(?:a|an|the) (?:man|woman|person|phone|illustration|image|photo|graphic|screenshot|collage|logo)\b",
            article.excerpt, re.I))
        if len(article.excerpt) >= 50 and not caption:
            result.append(article)
            continue
        if attempts >= settings.max_enrichments_per_source:
            continue
        url = urlsplit(article.url)
        if source.excerpt_adapter == "google_description" and url.hostname == "blog.google":
            attempts += 1
            try:
                page_source = replace(source, url=article.url)
                parser = _Description()
                parser.feed(fetch_feed(client, page_source, settings).decode("utf-8"))
                excerpt = plain_text(parser.values.get("og:description") or parser.values.get("description", ""))[:1800]
                if len(excerpt) >= 50:
                    result.append(replace(article, excerpt=excerpt))
            except (CollectionError, UnicodeError):
                log.warning("Source %s: unavailable official description; skipping one item", source.id)
            continue
        if source.excerpt_adapter != "huggingface_markdown":
            continue
        if url.hostname != "huggingface.co" or not re.fullmatch(r"/blog/[A-Za-z0-9_-]+", url.path):
            continue
        attempts += 1
        slug = url.path.rsplit("/", 1)[-1]
        endpoint = f"https://raw.githubusercontent.com/huggingface/blog/main/{slug}.md"
        markdown_source = Source(source.id, source.name, endpoint, ("raw.githubusercontent.com",))
        try:
            text = fetch_feed(client, markdown_source, settings).decode("utf-8").replace("\r\n", "\n")
            text = re.sub(r"\A---\n.*?\n---\s*", "", text, count=1, flags=re.S)
            text = re.sub(r"^```.*?^```[^\n]*", "", text, flags=re.M | re.S)
            text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
            text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
            text = re.sub(r"(?m)^#{1,6}\s+.*$", "", text)
            excerpt = plain_text(text)[:1800]
            if len(excerpt) >= 50:
                result.append(replace(article, excerpt=excerpt))
        except (CollectionError, UnicodeError):
            log.warning("Source %s: unavailable official excerpt; skipping one item", source.id)
    return result


def collect(client: httpx.Client, settings: Settings, now: datetime) -> tuple[list[Article], dict]:
    articles, report = [], {}
    for source in settings.sources:
        try:
            body = fetch_feed(client, source, settings)
            if source.format == "anthropic_news":
                from .news_index import parse_announcements
                items = parse_announcements(body, source, now, settings)
            else:
                items = parse_feed(body, source, now, settings)
            items = enrich_missing(client, items, source, settings)
            articles.extend(items)
            report[source.id] = {"status": "ok", "recent_items": len(items)}
            log.info("Source %s: %s recent validated items", source.id, len(items))
        except (CollectionError, ValueError, TypeError, KeyError) as exc:
            # Do not log response bodies, credential-bearing URLs, or raw exceptions.
            reason = str(exc) if isinstance(exc, CollectionError) else type(exc).__name__
            report[source.id] = {"status": "failed", "reason": reason}
            log.warning("Source %s failed (%s); continuing", source.id, reason)
    if not any(s["status"] == "ok" for s in report.values()):
        raise CollectionError("All sources failed; no briefing will be sent")
    return articles, report
