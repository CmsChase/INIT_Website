"""Impact-first editorial signals, independent of the paid ranking model.

Company mentions in a paper's abstract are not evidence of industry impact.
Publisher metadata is explicit; reporting never pretends to be an official source.
"""
from dataclasses import dataclass
from datetime import datetime
import re

from .models import Article, is_research

COMPANIES = {
    "openai": r"\b(openai|chatgpt|codex|gpt[- .]?\d)\b",
    "google": r"\b(google|deepmind|gemini|alphafold|alphaproof|veo)\b",
    "anthropic": r"\b(anthropic|claude)\b",
    "meta": r"\b(meta ai|meta|llama)\b",
    "xai": r"\b(xai|x\.ai|grok|spacexsi)\b",
    "microsoft": r"\b(microsoft|copilot|github|azure ai|microsoft foundry)\b",
    "nvidia": r"\b(nvidia|blackwell|rubin|cuda)\b",
    "deepseek": r"\bdeepseek\b",
    "amazon": r"\b(amazon|aws|bedrock)\b",
    "apple": r"\b(apple|siri)\b",
    "alibaba": r"\b(alibaba|qwen)\b",
}
AI = r"\b(ai|artificial intelligence|model(?:s)?|llm(?:s)?|chatgpt|claude|gemini|grok|deepseek|copilot|agent(?:s|ic)?|robot(?:s|ics|ic)?|inference|generative|gpu|llama|qwen)\b"
LAUNCH = r"\b(introduc(?:ing|es)|launch(?:es|ed)?|unveil(?:s|ed)?|releas(?:e|es|ed)|roll(?:s|ing)? out|new features?|new capabilities|new (?:flagship |frontier )?model|now available|upgrade(?:s)?|expand(?:s|ed)?|adds?|bring(?:s|ing)?|debuts?)\b"
STRATEGY = r"\b(partnership|partner(?:s|ing|ed)? (?:with|to)|acquir(?:e[sd]?|ing)|acquisition|merger|strategic|agreement|integration|integrat(?:e[sd]?|ing)|investment|ipo|public offering)\b"
SECURITY = r"\b(security|breach|leaks?|leaked|regulation|oversight|safety law|ai act|ban(?:ned)?)\b"
LOW_VALUE = r"\b(tutorial|beginners?|step.by.step|how to|a guide to|developer.s guide|webinar|register now|weekly roundup|roadshow|case study|customer stor(?:y|ies)|ships? \d+x more|scales? .*development)\b"
SPECULATION = r"\b(rumou?rs?|reportedly|might launch|could launch|may launch|expected to launch|is winning the .*race|could have)\b"
RELEASE_PATCH = r"\bv?\d+\.\d+\.[1-9]\d*(?:\b|rc)|\b(pre.release|release candidate|changelog|bug.fix|maintenance release)\b"


def companies(article: Article) -> tuple[str, ...]:
    # Prefer the headline; a publisher company is reliable for first-party news.
    names = {name for name, pattern in COMPANIES.items() if re.search(pattern, article.title, re.I)}
    if article.company:
        names.add(article.company)
    return tuple(sorted(names))


@dataclass(frozen=True)
class Assessment:
    score: float
    category: str
    companies: tuple[str, ...]
    signals: tuple[str, ...]


def assess(article: Article, now: datetime) -> Assessment:
    title, text = article.title.lower(), f"{article.title} {article.excerpt[:1200]}".lower()
    names = companies(article)
    signals = []
    category = article.category or "industry"
    # Standalone preprints need independent editorial confirmation: significant
    # research can still enter via a company's announcement or reputable reporting.
    if is_research(article) or article.source_tier == "research":
        return Assessment(0, "research", names, ("standalone_research",))
    if not re.search(AI, text) and not article.category:
        return Assessment(0, category, names, ("not_ai_news",))
    strategy = bool(re.search(STRATEGY, title))
    if not article.ai_focused_source and not (re.search(AI, title) or strategy):
        return Assessment(0, category, names, ("not_ai_headline",))
    launch = bool(re.search(LAUNCH, title))
    security = bool(re.search(SECURITY, title))
    amount = 2.0 + article.weight
    amount += {"official": 1.7, "reporting": .6, "ecosystem": .2, "releases": -2.0}.get(article.source_tier, 0)
    age = max(0, (now - article.published_at).total_seconds() / 3600)
    amount += max(0, 1 - age / 96)
    if names:
        amount += 2.5
        signals.append("major_company")
    if launch:
        amount += 2.5
        signals.append("launch_or_product_change")
    if strategy:
        amount += 2.5
        category = "strategy"
        signals.append("strategic_development")
    if security:
        amount += 2.0
        category = "industry"
        signals.append("security_or_regulation")
    if re.search(r"\b(new (?:flagship |frontier |foundation |ai )?models?|gpt[- .]?\d|claude (?:opus|sonnet|haiku|fable|mythos)|gemini \d|grok \d|llama \d|qwen[- .]?\d|deepseek[- .]?[vr]\d)", title) and launch:
        amount += 3
        category = "models"
        signals.append("model_launch")
    elif launch and re.search(r"\b(chatgpt|gemini|claude|copilot|grok)\b", title):
        amount += 1.5
        signals.append("major_ai_product_change")
    elif re.search(r"\b(agent(?:s|ic)?|mcp|tool.use)\b", title):
        category = "agents"
    elif re.search(r"\b(robot(?:s|ics|ic)?|embodied)\b", title):
        category = "robotics"
    elif re.search(r"\b(api|sdk|coding|developer|open.source)\b", title):
        category = "tools"
    if names and re.search(r"\b(breakthrough|frontier|open.source|open.weight|infrastructure|accelerator|chip)\b", title):
        amount += 1.5
        signals.append("broad_capability_or_infrastructure")
    if re.search(LOW_VALUE, title) or re.search(r"\b(uses? .* to|customer story|case study)\b", title):
        amount -= 7
        signals.append("tutorial_or_promotion")
    if re.search(SPECULATION, title):
        amount -= 7
        signals.append("speculation_or_opinion")
    if re.search(RELEASE_PATCH, title):
        amount -= 6
        signals.append("routine_release")
    if re.search(r"\b(deployment recipes|dynamo recipes|optimized recipes|minor update)\b", text):
        amount -= 7
        signals.append("incremental_technical_update")
    if re.search(r"\b(our research infrastructure|internal research|internal workflow|at corl|at iclr|at neurips)\b", text):
        amount -= 4
        signals.append("niche_internal_or_conference_update")
    if re.search(r"\b(paper|preprint|survey|benchmark study|ablation)\b", title) and not (names and launch):
        amount -= 7
        signals.append("niche_research")
    return Assessment(round(amount, 3), category, names, tuple(signals))


def candidate_record(article: Article, now: datetime) -> dict:
    result = assess(article, now)
    return {"id": article.id, "headline": article.title, "url": article.url,
            "source": article.source_name, "source_tier": article.source_tier,
            "companies": list(result.companies), "score": result.score,
            "category": result.category, "signals": list(result.signals)}
