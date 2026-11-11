from dataclasses import dataclass
from pathlib import Path
import math
import tomllib
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    url: str
    allowed_hosts: tuple[str, ...]
    weight: float = 1.0
    category: str = ""
    excerpt_adapter: str = ""


@dataclass(frozen=True)
class Settings:
    sources: tuple[Source, ...]
    timezone: str = "Asia/Shanghai"
    lookback_hours: int = 48
    min_stories: int = 3
    max_stories: int = 5
    max_per_source: int = 2
    max_research_stories: int = 2
    candidate_limit: int = 20
    min_score: float = 3.0
    history_path: Path = Path(".state/history.json")
    output_dir: Path = Path("output")
    model: str = "deepseek-flash"
    max_tokens: int = 2200
    ai_timeout: int = 60
    http_timeout: int = 20
    retries: int = 2
    max_feed_bytes: int = 5_000_000
    max_enrichments_per_source: int = 4


def load_settings(path: Path) -> Settings:
    from .models import trusted_url

    with path.open("rb") as stream:
        data = tomllib.load(stream)
    briefing, ai, http = (data.get(k, {}) for k in ("briefing", "deepseek", "http"))
    sources = tuple(Source(**{**{k: v for k, v in s.items() if k != "enabled"},
                              "allowed_hosts": tuple(s["allowed_hosts"])})
                    for s in data.get("sources", []) if s.get("enabled", True))
    # enabled is a config-only switch, not part of Source.
    root = path.resolve().parent
    settings = Settings(
        sources=sources,
        **{k: v for k, v in briefing.items() if k not in {"history_path", "output_dir"}},
        history_path=root / briefing.get("history_path", ".state/history.json"),
        output_dir=root / briefing.get("output_dir", "output"),
        model=ai.get("model", "deepseek-flash"), max_tokens=ai.get("max_tokens", 2200),
        ai_timeout=ai.get("timeout_seconds", 60),
        http_timeout=http.get("timeout_seconds", 20), retries=http.get("retries", 2),
        max_feed_bytes=http.get("max_feed_bytes", 5_000_000),
        max_enrichments_per_source=http.get("max_enrichments_per_source", 4),
    )
    ZoneInfo(settings.timezone)
    if not 3 <= settings.min_stories <= settings.max_stories <= 5:
        raise ValueError("Story count must satisfy 3 <= minimum <= maximum <= 5")
    if not (settings.max_stories <= settings.candidate_limit <= 40):
        raise ValueError("candidate_limit must be between max_stories and 40")
    if not (1 <= settings.lookback_hours <= 168 and 1 <= settings.max_per_source <= 5
            and 0 <= settings.max_research_stories <= 5):
        raise ValueError("Invalid news window or source cap")
    if not (0 <= settings.retries <= 3 and 1 <= settings.http_timeout <= 60
            and 1 <= settings.ai_timeout <= 120 and 500 <= settings.max_tokens <= 4000
            and 1000 <= settings.max_feed_bytes <= 10_000_000
            and 0 <= settings.max_enrichments_per_source <= 8
            and math.isfinite(settings.min_score) and settings.min_score >= 0):
        raise ValueError("Invalid request or ranking limits")
    if not sources or len({s.id for s in sources}) != len(sources):
        raise ValueError("Configure unique enabled sources")
    for source in sources:
        if not trusted_url(source.url, (source.url.split('/')[2],)):
            raise ValueError("Sources must use public HTTPS URLs")
        if not source.allowed_hosts or not math.isfinite(source.weight) or not 0 <= source.weight <= 5:
            raise ValueError("Invalid source trust or weight")
        if source.category not in {"", "models", "agents", "tools", "open_source", "robotics", "research"}:
            raise ValueError("Unknown source category")
        if source.excerpt_adapter not in {"", "huggingface_markdown"}:
            raise ValueError("Unknown excerpt adapter")
    return settings
