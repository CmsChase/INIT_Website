from collections import Counter
from datetime import datetime
import re

from .config import Settings
from .editorial import assess, companies
from .models import Article, Story, canonical_url, is_research, same_story

RELEVANCE = {
    "industry": "Consider how this could change access, competition, or trust in the AI tools people use and build with.",
    "strategy": "Watch how this development could affect competition, distribution, and access to AI for individuals and small teams.",
    "agents": "Consider which tasks this could automate and where human oversight would still be needed.",
    "models": "Compare how access, pricing, and capabilities could change what individuals and small teams can build.",
    "tools": "Consider whether this could reduce the time or cost of turning an idea into a working product.",
    "open_source": "Inspect the repository, license, and hardware requirements before adapting it for a project.",
    "robotics": "Check hardware assumptions and transfer limits before attempting to reproduce the results.",
    "research": "Treat this as a research lead; inspect the evaluation setup and reproduction materials before relying on it.",
}


def score(article: Article, now: datetime) -> tuple[float, str]:
    result = assess(article, now)
    return result.score, result.category


def shortlist(articles: list[Article], previous: list[dict], settings: Settings,
              now: datetime) -> list[Article]:
    # Compare equally important duplicates with the original announcement first.
    ranked = sorted(articles, key=lambda a: (a.source_tier != "official", -score(a, now)[0], a.url))
    unique = []
    for article in ranked:
        if score(article, now)[0] < settings.min_score:
            continue
        if any(article.id == p["id"] or canonical_url(article.url) == p.get("primary_url")
               or same_story(article.title, p["title"]) for p in previous):
            continue
        if any(article.id == a.id or same_story(article.title, a.title) for a in unique):
            continue
        unique.append(article)
    ranked = sorted(unique, key=lambda a: (-score(a, now)[0], a.source_tier != "official", a.url))
    result, counts = [], Counter()
    # Limit each feed's influence before the paid model sees candidates.
    source_cap = max(settings.max_per_source, 4)
    for article in ranked:
        if counts[article.source_id] >= source_cap:
            continue
        result.append(article)
        counts[article.source_id] += 1
        if len(result) >= settings.candidate_limit:
            break
    return result


def excerpt_summary(text: str, limit: int = 320) -> str:
    if len(text) <= limit:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    result = ""
    for sentence in sentences:
        if len(result) + len(sentence) + 1 > limit:
            break
        result = f"{result} {sentence}".strip()
    return result or text[:limit - 1].rsplit(" ", 1)[0] + "…"


def fallback(candidates: list[Article], settings: Settings, now: datetime) -> list[Story]:
    stories, counts, company_counts = [], Counter(), Counter()
    research_count = 0
    remaining = list(candidates)
    while remaining:
        # A small tie preference, never a company quota: a clearly bigger second
        # announcement still outranks a less significant competitor's story.
        article = max(remaining, key=lambda a: score(a, now)[0] -
                      min(.6, .3 * max((company_counts[c] for c in companies(a)), default=0)))
        remaining.remove(article)
        if counts[article.source_id] >= settings.max_per_source:
            continue
        if is_research(article) and research_count >= settings.max_research_stories:
            continue
        category = score(article, now)[1]
        stories.append(Story(article, excerpt_summary(article.excerpt), RELEVANCE[category], category, "fallback"))
        counts[article.source_id] += 1
        research_count += int(is_research(article))
        company_counts.update(companies(article))
        if len(stories) == settings.max_stories:
            break
    return stories
