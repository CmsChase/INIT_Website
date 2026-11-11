"""Read dated announcement cards when a publisher has no usable public RSS.

This adapter reads one public index, executes no scripts, follows no article
links, and never substitutes page-update dates for publication dates.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin

from .config import Settings, Source
from .models import Article, canonical_url, trusted_url


@dataclass
class _Node:
    tag: str
    attrs: dict
    children: list = field(default_factory=list)

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, _Node):
                yield from child.walk()

    def text(self):
        if self.tag in {"script", "style"}:
            return ""
        return " ".join(" ".join(child.text() if isinstance(child, _Node) else child
                                 for child in self.children).split())


class _Index(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _published(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        result = None
        for pattern in ("%b %d, %Y", "%B %d, %Y"):
            try:
                result = datetime.strptime(value, pattern)
                break
            except ValueError:
                continue
        if result is None:
            raise ValueError("Unrecognized publication date")
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result


def parse_announcements(body: bytes, source: Source, now: datetime, settings: Settings) -> list[Article]:
    parser = _Index()
    parser.feed(body.decode("utf-8"))
    articles, recognized = [], 0
    for node in parser.root.walk():
        if node.tag not in {"article", "li"}:
            continue
        nodes = list(node.walk())
        dates = {n.attrs.get("datetime") or n.text() for n in nodes if n.tag == "time"}
        if len(dates) != 1:
            continue  # Do not mix dates from a container holding multiple stories.
        try:
            published = _published(next(iter(dates)))
        except ValueError:
            continue
        headings = [n.text() for n in nodes if n.tag in {"h1", "h2", "h3"} and len(n.text()) >= 8]
        if not headings:
            continue
        title = headings[0][:240]
        links = []
        for anchor in nodes:
            if anchor.tag != "a":
                continue
            url = urljoin(source.url, anchor.attrs.get("href") or "")
            if not trusted_url(url, source.allowed_hosts):
                continue
            if anchor.text().startswith(title):
                links.append(url)
        if len(set(links)) != 1:
            continue
        paragraphs = [n.text() for n in nodes if n.tag == "p" and len(n.text()) >= 50]
        if not paragraphs:
            continue
        recognized += 1
        if not now - timedelta(hours=settings.lookback_hours) <= published <= now + timedelta(minutes=5):
            continue
        articles.append(Article(title, canonical_url(links[0]), paragraphs[0][:1800], published,
                                source.id, source.name, source.weight, source.category,
                                source.tier, source.company, source.ai_focused))
    if not recognized:
        raise ValueError("No dated announcement cards recognized")
    return list({article.id: article for article in articles}.values())
