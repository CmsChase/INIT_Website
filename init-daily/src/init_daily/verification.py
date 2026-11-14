"""Verify selections and eligible alternates against current primary articles."""
from collections import Counter
from dataclasses import replace
from datetime import datetime
from hashlib import sha256
from itertools import chain
import logging
import re
from urllib.parse import urljoin, urlsplit

import httpx

from .config import Settings
from .editorial import companies
from .models import Article, Story, canonical_url, is_research, trusted_url
from .news_index import _Index
from .ranking import RELEVANCE, fallback_story, score

log = logging.getLogger(__name__)
PRIMARY_HOSTS = {
    "openai": ("openai.com",),
    "google": ("blog.google", "deepmind.google", "cloud.google.com", "developers.googleblog.com"),
    "anthropic": ("www.anthropic.com", "anthropic.com", "claude.com"),
    "meta": ("ai.meta.com", "about.fb.com"), "xai": ("x.ai", "www.x.ai"),
    "microsoft": ("blogs.microsoft.com", "www.microsoft.com", "github.blog"),
    "nvidia": ("blogs.nvidia.com", "nvidianews.nvidia.com"),
    "deepseek": ("www.deepseek.com", "deepseek.com", "api-docs.deepseek.com"),
    "amazon": ("www.aboutamazon.com", "aws.amazon.com"), "apple": ("www.apple.com",),
    "alibaba": ("www.alibabacloud.com", "qwenlm.github.io"),
}
PRICE = re.compile(r"[$€£]|\b(?:price|pricing|priced|introductory rate|per million tokens)\b", re.I)
ACCESS = re.compile(r"\b(?:available|availability|access|rolling out|rollout|paid tier|preview|try|general public|everyone)\b", re.I)
RESTRICT = re.compile(r"\b(?:paid|paying|subscribers?|subscription|eligible|eligibility|only|waitlist|apply for access|verification programs?|subject to)\b", re.I)
QUANTITY = re.compile(r"\b(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:(?:million|billion|thousand)\s+)?(?:lines|users|tokens|hours|days|percent)\b|\d+(?:\.\d+)?%", re.I)
STOP = {"a", "an", "the", "to", "in", "of", "for", "and", "is", "with", "new", "now", "our", "introducing", "releases", "release", "available", "google", "openai", "anthropic"}


class VerificationError(ValueError):
    pass


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower())) - STOP


def _same_topic(discovery: str, primary: str) -> bool:
    # A predecessor mentioned in a report is not part of the launched model's name.
    discovery = re.split(r"\b(?:replacing|superseding|compared (?:with|to)|vs\.?)\b", discovery, maxsplit=1, flags=re.I)[0]
    a, b = _words(discovery), _words(primary)
    overlap = len(a & b)
    versions_a = set(re.findall(r"\b\d+(?:\.\d+)*\b", discovery))
    versions_b = set(re.findall(r"\b\d+(?:\.\d+)*\b", primary))
    return (overlap >= 2 and overlap / max(1, min(len(a), len(b))) >= .75
            and not (versions_a and versions_b and not versions_a <= versions_b))


def article_body(raw: bytes) -> tuple[str, list[str], list[str]]:
    parser = _Index()
    parser.feed(raw.decode("utf-8"))
    nodes = list(parser.root.walk())
    explicit = [n for n in nodes if n.attrs.get("data-article-body") == "true"
                or n.attrs.get("data-component") == "uni-article-body"
                or n.attrs.get("itemprop") == "articleBody"]
    mains = [n for n in nodes if n.tag == "main"]
    articles = [n for n in nodes if n.tag == "article"]
    choices = explicit or mains or articles
    if not choices:
        raise VerificationError("article_body_missing")
    root = max(choices, key=lambda n: sum(c.tag == "p" for c in n.walk()))
    headings = [n.text() for n in nodes if n.tag == "h1" and n.text()]
    if not headings:
        raise VerificationError("article_title_missing")
    blocks, links = [], []

    def walk(node):
        classes = node.attrs.get("class", "") or ""
        if node.tag in {"script", "style", "nav", "footer", "header", "aside"} or re.search(r"\b(?:card|related|newsletter|author-bio)\b", classes):
            return
        if node.tag == "a" and node.attrs.get("href"):
            links.append(node.attrs["href"])
        if node.tag in {"p", "li"}:
            text = node.text()
            if 20 <= len(text) <= 6000:
                blocks.append(text)
            # Still collect links, but not duplicate nested paragraph text.
            for child in node.walk():
                if child.tag == "a" and child.attrs.get("href"):
                    links.append(child.attrs["href"])
            return
        for child in node.children:
            if not isinstance(child, str):
                walk(child)
    walk(root)
    if not blocks:
        raise VerificationError("article_body_empty")
    return headings[0], list(dict.fromkeys(blocks)), list(dict.fromkeys(links))


class _Reader:
    def __init__(self, client: httpx.Client, settings: Settings):
        self.client, self.settings, self.requests, self.cache = client, settings, 0, {}

    def get(self, url: str, hosts: tuple[str, ...]) -> tuple[str, bytes]:
        if url in self.cache:
            return self.cache[url]
        original = url
        for _ in range(4):
            if not trusted_url(url, hosts):
                raise VerificationError("untrusted_primary_url")
            if self.requests >= self.settings.verification_max_requests:
                raise VerificationError("verification_budget_exhausted")
            self.requests += 1
            try:
                with self.client.stream("GET", url, headers={"Cache-Control": "no-cache"}, timeout=self.settings.verification_timeout,
                                        follow_redirects=False) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get("location", ""))
                        continue
                    if response.status_code != 200:
                        raise VerificationError(f"primary_http_{response.status_code}")
                    chunks, size = [], 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > 2_000_000:
                            raise VerificationError("primary_body_too_large")
                        chunks.append(chunk)
                    result = canonical_url(url), b"".join(chunks)
                    self.cache[original] = result
                    return result
            except httpx.HTTPError:
                raise VerificationError("primary_network_error") from None
        raise VerificationError("too_many_primary_redirects")


def _primary_candidates(story: Story, urls: tuple[str, ...], hosts: tuple[str, ...]) -> list[str]:
    tokens = _words(story.article.title)
    result = []
    for url in urls:
        if not trusted_url(url, hosts) or re.search(r"\.(?:pdf|png|jpg|svg)(?:$|\?)", url, re.I):
            continue
        path_tokens = _words(urlsplit(url).path.replace("-", " "))
        overlap = len(tokens & path_tokens)
        # A company homepage or a generic product link is not corroboration.
        if overlap >= 2:
            result.append((overlap, canonical_url(url)))
    return list(dict.fromkeys(url for _, url in sorted(result, reverse=True)))[:2]


def _sentences(text: str) -> list[str]:
    return re.split(r"(?<=[.!?])\s+(?=[A-Z\"“])", text)


def _short_quote(text: str) -> str | None:
    if len(text.split()) <= 25 and len(text) <= 340:
        return text
    # Stop at a complete clause, never an arbitrary word boundary. Do not drop
    # an exception, access condition, negation, or price qualification afterward.
    for match in re.finditer(r",\s+(?:a |an |which |the )", text):
        lead, tail = text[:match.start()], text[match.start():]
        if 8 <= len(lead.split()) <= 25 and not (RESTRICT.search(tail) or PRICE.search(tail) or re.search(r"\b(?:but|unless|except|not|if)\b", tail, re.I)):
            return lead
    return None


def _access_quotes(blocks: list[str]) -> list[str]:
    for index, block in enumerate(blocks):
        if not (ACCESS.search(block) and RESTRICT.search(block)):
            continue
        # Capture the entire audience clause, cutting only an explicit price
        # clause. Exact rates are deliberately omitted; promotions/expiry dates
        # cannot be safely reduced to a headline price.
        price = re.search(r",?\s+at (?:the |an? )?(?:same )?(?:introductory |promotional )?price\b", block, re.I)
        scope = block[:price.start()] if price else block
        match = re.search(r"\bfor (?:all )?(?:paying|paid|eligible|selected)\b[^.;]*", scope, re.I)
        if not match:
            continue
        quotes = [match.group().strip().rstrip(",")]
        followings = [block[match.end():], *blocks[index + 1:index + 2]]
        for following in followings:
            # The immediately following rollout sentence retains its audience,
            # rather than copying an unqualified 'available to the public' lead.
            rollout = re.search(r"\b(?:It is also )?rolling out to (?:all )?[^.;]*?subscribers\b", following, re.I)
            if rollout:
                sentence = _sentences(following[rollout.start():])[0]
                tail = sentence[len(rollout.group()):]
                quotes.append(sentence if RESTRICT.search(tail) else rollout.group())
                break
        if (not any(PRICE.search(q) for q in quotes) and sum(len(q.split()) for q in quotes) <= 25
                and sum(map(len, quotes)) <= 330):
            return quotes
    return []


def current_excerpt(story: Story, blocks: list[str]) -> tuple[str, list[str], dict]:
    original = story.summary
    access = _access_quotes(blocks)
    if access:
        return "Access: " + " … ".join(access), access, {"access_conditions_retained": True, "pricing_omitted": any(PRICE.search(b) for b in blocks)}
    # Numerical claims must come from the current body, with 'over', 'about',
    # units, and the applicable object intact, not from feed/meta descriptions.
    candidates = []
    topic = _words(original) | _words(story.article.title)
    old_quantity = bool(QUANTITY.search(original))
    for index, block in enumerate(blocks):
        for sentence in _sentences(block):
            if PRICE.search(sentence) or ACCESS.search(sentence) or RESTRICT.search(sentence):
                continue
            quote = _short_quote(sentence)
            if not quote:
                continue
            overlap = len(topic & _words(quote))
            if overlap < 2:
                continue
            priority = overlap + (10 if old_quantity and QUANTITY.search(quote) else 0) - index * .02
            candidates.append((priority, quote))
    if not candidates:
        raise VerificationError("no_safe_current_excerpt")
    quote = max(candidates, key=lambda item: item[0])[1]
    return quote, [quote], {"access_claims_omitted": any(ACCESS.search(b) and RESTRICT.search(b) for b in blocks),
                            "pricing_omitted": any(PRICE.search(b) for b in blocks),
                            "quantitative_body_quote": bool(QUANTITY.search(quote))}


def verify_selected(stories: list[Story], settings: Settings, client: httpx.Client,
                    now: datetime, *, alternates: tuple[Article, ...] = (),
                    previous: tuple[dict, ...] = ()) -> tuple[list[Story], dict]:
    reader = _Reader(client, settings)
    accepted, records, primary_seen = [], [], {p.get("primary_url") or p["url"] for p in previous}
    counts = Counter()
    research_count = 0
    selected_ids = {s.article.id for s in stories}
    # Original selections are checked first. Only replace withheld selections.
    # Explicitly empty AI selections and short briefings keep their intended size.
    reserves = (fallback_story(a, now) for a in alternates if a.id not in selected_ids)
    for story in chain(stories, reserves):
        if len(accepted) == len(stories):
            break
        article = story.article
        alternate = article.id not in selected_ids
        research = is_research(article)
        if alternate and (reader.requests >= settings.verification_max_requests
                          or counts[article.source_id] >= settings.max_per_source
                          or (research and research_count >= settings.max_research_stories)):
            continue
        record = {"article_id": article.id, "discovery_url": article.url,
                  "discovery_headline": article.title, "checked_at": now.isoformat(),
                  "selection": "alternate" if alternate else "initial"}
        names = companies(article)
        hosts = tuple(dict.fromkeys(host for name in names for host in PRIMARY_HOSTS.get(name, ())))
        # Explicitly configured official publishers are also trusted originals.
        source = next((s for s in settings.sources if s.id == article.source_id), None)
        primary_publisher = article.source_tier == "official" or (source is not None and source.id in {"github", "huggingface"})
        if primary_publisher and source:
            hosts = tuple(dict.fromkeys((*hosts, *source.allowed_hosts)))
        try:
            if primary_publisher:
                primary_urls = [article.url]
            else:
                primary_urls = _primary_candidates(story, article.reference_urls, hosts)
                if not primary_urls:
                    _, raw_report = reader.get(article.url, (urlsplit(article.url).hostname,))
                    _, _, links = article_body(raw_report)
                    primary_urls = _primary_candidates(story, tuple(urljoin(article.url, u) for u in links), hosts)
            if not primary_urls:
                raise VerificationError("primary_reference_missing")
            # At most two explicit relevant original links; no search API or crawl.
            for primary in primary_urls:
                try:
                    url, raw = reader.get(primary, hosts)
                    title, blocks, _ = article_body(raw)
                    if not _same_topic(article.title, title):
                        raise VerificationError("primary_topic_mismatch")
                    if url in primary_seen:
                        raise VerificationError("duplicate_primary_story")
                    summary, quotes, details = current_excerpt(story, blocks)
                    if any(not any(q in block for block in blocks) for q in quotes):
                        raise VerificationError("body_quote_not_found")
                    break
                except VerificationError:
                    if primary == primary_urls[-1]:
                        raise
            publisher_sources = [s for s in settings.sources if s.tier == "official" or s.id in {"github", "huggingface"}]
            primary_host = urlsplit(url).hostname
            # Redirect allowlists can span related publishers. Prefer the exact
            # configured publishing host, rather than calling blog.google DeepMind.
            issuer = next((s.name for s in publisher_sources if urlsplit(s.url).hostname == primary_host),
                          next((s.name for s in publisher_sources if primary_host in s.allowed_hosts), primary_host))
            why = ("Consider how the stated access and pricing conditions could affect adoption by individuals and small teams."
                   if details.get("access_conditions_retained") else RELEVANCE[score(article, now)[1]])
            accepted.append(replace(story, article=replace(article, title=title),
                                    summary=summary, why=why, verified_url=url, verified_source=issuer))
            primary_seen.add(url)
            counts[article.source_id] += 1
            research_count += int(research)
            record.update(status="primary_body_checked", primary_url=url, primary_source=issuer, body_sha256=sha256(raw).hexdigest(),
                          primary_headline=title,
                          evidence_quotes=quotes, summary_replaced=summary != story.summary,
                          editorial_rechecked=True, **details)
        except (VerificationError, UnicodeError) as exc:
            code = str(exc) if isinstance(exc, VerificationError) else "primary_encoding_error"
            record.update(status="withheld", code=code)
            log.warning("Selected story %s withheld: %s", article.id, code)
        records.append(record)
    return accepted, {"enabled": True, "method": "current_primary_article_body", "http_requests": reader.requests,
                      "checked": len(accepted), "withheld": len(records) - len(accepted),
                      "alternates_checked": sum(r["selection"] == "alternate" for r in records),
                      "alternates_used": sum(r["selection"] == "alternate" and r["status"] == "primary_body_checked" for r in records),
                      "stories": records}
