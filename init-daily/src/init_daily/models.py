from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
import ipaddress
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        elif tag in {"p", "br", "li", "div", "h1", "h2"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(value: str) -> str:
    parser = _Text()
    parser.feed(value)
    return re.sub(r"\s+", " ", unescape("".join(parser.parts))).strip()


def trusted_url(value: str, hosts: tuple[str, ...]) -> bool:
    try:
        url = urlsplit(value)
        host = (url.hostname or "").lower()
        if url.scheme != "https" or url.username or url.password or url.port not in (None, 443):
            return False
        if host not in hosts or "." not in host or host.endswith((".local", ".internal")):
            return False
        try:
            ipaddress.ip_address(host)
            return False  # No literal addresses, even public ones.
        except ValueError:
            pass
        return len(value) <= 1500 and not re.search(r"[\s<>\\]", value)
    except ValueError:
        return False


def canonical_url(value: str) -> str:
    url = urlsplit(value)
    query = [(k, v) for k, v in parse_qsl(url.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"ref", "fbclid", "gclid"}]
    host = (url.hostname or "").lower()
    path = url.path.rstrip("/") or "/"
    if host in {"arxiv.org", "export.arxiv.org"}:
        host = "arxiv.org"
        path = re.sub(r"v\d+$", "", path.replace("/pdf/", "/abs/").removesuffix(".pdf"))
    return urlunsplit(("https", host, path, urlencode(sorted(query)), ""))


def title_key(title: str) -> str:
    return re.sub(r"[^\w]+", " ", title.lower()).strip()


def same_story(title_a: str, title_b: str) -> bool:
    a, b = title_key(title_a), title_key(title_b)
    if a == b:
        return True
    # Preserve versions/numbers: a new model version should not disappear.
    if re.findall(r"\d+(?:\.\d+)*", a) != re.findall(r"\d+(?:\.\d+)*", b):
        return False
    tokens_a, tokens_b = set(a.split()), set(b.split())
    overlap = len(tokens_a & tokens_b) / max(1, len(tokens_a | tokens_b))
    return min(len(a), len(b)) >= 25 and (overlap >= .78 or SequenceMatcher(None, a, b).ratio() >= .91)


@dataclass(frozen=True)
class Article:
    title: str
    url: str
    excerpt: str
    published_at: datetime
    source_id: str
    source_name: str
    weight: float
    category: str = ""
    source_tier: str = "ecosystem"
    company: str = ""
    ai_focused_source: bool = True

    @property
    def id(self) -> str:
        return sha256(canonical_url(self.url).encode()).hexdigest()[:24]

    def record(self) -> dict:
        return {"id": self.id, "url": canonical_url(self.url), "title": self.title}


@dataclass(frozen=True)
class Story:
    article: Article
    summary: str
    why: str
    category: str
    mode: str


def is_research(article: Article) -> bool:
    return urlsplit(article.url).hostname == "arxiv.org" or article.category == "research"
