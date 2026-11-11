from collections import Counter
from datetime import datetime
import re

from .config import Settings
from .models import Article, Story, is_research, same_story

# Small, transparent topic model. Match whole words, not substrings such as 'paid'.
TOPICS = {
    "agents": (3.2, r"\b(agent(?:ic|s)?|tool.use|computer.use|mcp|multi.agent)\b"),
    "models": (3.0, r"\b(model(?:s)?|llm(?:s)?|language.model|weights|multimodal|reasoning)\b"),
    "tools": (3.0, r"\b(api|sdk|developer(?:s)?|inference|coding|compiler|copilot)\b"),
    "open_source": (3.0, r"\b(open.source|open.weight|repository|transformers|pytorch)\b"),
    "robotics": (3.1, r"\b(robot(?:s|ics|ic)?|embodied|manipulation|humanoid|locomotion)\b"),
    "research": (1.8, r"\b(benchmark|training|evaluation|research|preprint|dataset)\b"),
}
RELEVANCE = {
    "agents": "Check the tool interfaces and failure modes before trying it in a small agent workflow.",
    "models": "Compare access, licensing, latency, and evaluation results against your current model before switching.",
    "tools": "Check the API and compatibility requirements, then test it against one task in your development workflow.",
    "open_source": "Inspect the repository, license, and hardware requirements before adapting it for a project.",
    "robotics": "Check hardware assumptions and transfer limits before attempting to reproduce the results.",
    "research": "Treat this as a research lead; inspect the evaluation setup and reproduction materials before relying on it.",
}


def score(article: Article, now: datetime) -> tuple[float, str]:
    text = f"{article.title} {article.excerpt[:1200]}".lower()
    matches = [(weight, category) for category, (weight, pattern) in TOPICS.items()
               if re.search(pattern, text)]
    if article.category:
        matches.append((TOPICS.get(article.category, (0,))[0], article.category))
    if not matches:
        return 0, "research"
    weight, category = max(matches)
    age = max(0, (now - article.published_at).total_seconds() / 3600)
    freshness = max(0, 1 - age / 72)
    release = .7 if re.search(r"\b(releas(?:e|ed|ing)|launch(?:ed)?|introducing|available)\b", text) else 0
    noise = 4 if re.search(r"\b(fundraising|funding round|lawsuit|earnings|webinar|register now)\b", text) else 0
    prerelease = 3 if re.search(r"\b(pre.release|release candidate|\d+\.\d+\.\d+rc\d+)\b", text) else 0
    return article.weight + weight + freshness + release - noise - prerelease, article.category or category


def shortlist(articles: list[Article], previous: list[dict], settings: Settings,
              now: datetime) -> list[Article]:
    ranked = sorted(articles, key=lambda a: (-score(a, now)[0], -a.weight, a.url))
    result, counts = [], Counter()
    # Limit each feed's influence before the paid model sees candidates.
    source_cap = max(settings.max_per_source, 4)
    for article in ranked:
        if score(article, now)[0] < settings.min_score:
            continue
        if any(article.id == p["id"] or same_story(article.title, p["title"]) for p in previous):
            continue
        if any(article.id == a.id or same_story(article.title, a.title) for a in result):
            continue
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
    stories, counts = [], Counter()
    research_count = 0
    for article in candidates:
        if counts[article.source_id] >= settings.max_per_source:
            continue
        if is_research(article) and research_count >= settings.max_research_stories:
            continue
        category = score(article, now)[1]
        stories.append(Story(article, excerpt_summary(article.excerpt), RELEVANCE[category], category, "fallback"))
        counts[article.source_id] += 1
        research_count += int(is_research(article))
        if len(stories) == settings.max_stories:
            break
    return stories
