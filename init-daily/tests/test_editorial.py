from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

import httpx

from init_daily.collect import enrich_missing, parse_feed
from init_daily.config import Source, load_settings
from init_daily.editorial import assess, companies
from init_daily.formatting import discord_payload
from init_daily.history import History
from init_daily.models import Article
from init_daily.news_index import parse_announcements
from init_daily.pipeline import run_pipeline
from init_daily.processing import process
from init_daily.ranking import fallback, shortlist

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 11, 1, 15, tzinfo=timezone.utc)
EXCERPT = "The announcement describes a new AI capability with wider availability for individuals and teams building with AI."


class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.settings = load_settings(ROOT / "config.toml")

    def article(self, title, company="openai", tier="official", **kwargs):
        return Article(title, f"https://example.com/{title.replace(' ', '-')}", EXCERPT,
                       NOW, company or "ecosystem", company or "Ecosystem", 1.5,
                       source_tier=tier, company=company, **kwargs)

    def test_production_sources_do_not_collect_raw_arxiv_or_routine_releases(self):
        ids = {s.id for s in self.settings.sources}
        self.assertTrue({"openai", "google-ai", "deepmind", "anthropic", "microsoft", "nvidia", "meta"} <= ids)
        self.assertTrue({"techcrunch-ai", "verge-ai", "ars-ai"} <= ids)
        self.assertFalse({"arxiv-ai", "arxiv-robotics", "transformers"} & ids)

    def test_major_launch_beats_routine_paper_even_with_large_publication_volume(self):
        launch = self.article("OpenAI introduces a new flagship GPT-6 model")
        papers = [self.article(f"Paper {i}: Incremental benchmark of OpenAI and Claude models", company="", tier="research",
                               category="research") for i in range(600)]
        result = shortlist(papers + [launch], [], self.settings, NOW)
        self.assertEqual([a.id for a in result], [launch.id])
        self.assertEqual(len(fallback(result, self.settings, NOW)), 1)

    def test_brand_mentions_and_breakthrough_hype_do_not_promote_arxiv(self):
        paper = self.article("Breakthrough OpenAI Claude Gemini comparison on a new benchmark", tier="research", category="research")
        self.assertLess(assess(paper, NOW).score, self.settings.min_score)

    def test_routine_patch_and_tutorial_do_not_qualify(self):
        for title in ("OpenAI developer guide: how to build a chatbot", "Transformers v5.22.3 bug-fix release",
                      "Anthropic launches roadshow for proposed initial public offering"):
            article = self.article(title)
            self.assertLess(assess(article, NOW).score, self.settings.min_score, title)

    def test_model_launch_beats_minor_official_internal_update(self):
        launch = self.article("Introducing Claude Sonnet 6, a new model", company="anthropic")
        internal = replace(self.article("Control Room for our research infrastructure"),
                           excerpt="An internal research workflow for tracking AI model workloads.")
        self.assertGreater(assess(launch, NOW).score, assess(internal, NOW).score + 3)
        self.assertLess(assess(internal, NOW).score, self.settings.min_score)

    def test_major_company_brand_does_not_promote_routine_deployment_recipes(self):
        article = replace(self.article("NVIDIA Dynamo Recipes Bring Open Models to Production", company="nvidia"),
                          excerpt="NVIDIA is releasing deployment recipes for existing open AI models.")
        self.assertLess(assess(article, NOW).score, self.settings.min_score)
        self.assertNotIn("model_launch", assess(article, NOW).signals)

    def test_major_breakthrough_remains_eligible_when_announced_officially(self):
        article = self.article("Introducing AlphaProof: a breakthrough in software verification", company="google")
        self.assertGreaterEqual(assess(article, NOW).score, self.settings.min_score)

    def test_important_partnership_and_reputable_reporting_are_eligible(self):
        partnership = self.article("OpenAI and Microsoft announce a strategic AI partnership")
        report = self.article("DeepSeek launches V5, a new AI model", company="", tier="reporting")
        self.assertGreaterEqual(assess(partnership, NOW).score, self.settings.min_score)
        self.assertGreaterEqual(assess(report, NOW).score, self.settings.min_score)
        self.assertIn("deepseek", companies(report))

    def test_all_requested_company_families_are_recognized_in_reporting(self):
        for name, token in {"openai": "ChatGPT", "google": "Gemini", "anthropic": "Claude", "meta": "Llama",
                            "xai": "Grok", "microsoft": "Copilot", "nvidia": "NVIDIA", "deepseek": "DeepSeek"}.items():
            self.assertIn(name, companies(self.article(f"{token} launches new AI capabilities", company="", tier="reporting")))

    def test_general_company_feed_does_not_make_non_ai_news_eligible(self):
        article = replace(self.article("Meta expands teen account protections", company="meta"),
                          excerpt="New account protections for families and teenagers around the world.", ai_focused_source=False)
        self.assertEqual(assess(article, NOW).score, 0)

    def test_original_announcement_wins_duplicate_reporting(self):
        title = "OpenAI launches a new flagship model"
        official = self.article(title)
        reporting = replace(self.article(title, company="", tier="reporting"), url="https://example.com/report")
        result = shortlist([reporting, official], [], self.settings, NOW)
        self.assertEqual([a.id for a in result], [official.id])

    def test_company_variety_is_soft_and_does_not_exclude_bigger_same_company_news(self):
        big = [self.article(f"OpenAI introduces GPT-{i + 6}, a new model") for i in range(5)]
        smaller = self.article("Apple adds AI features", company="apple")
        result = fallback(shortlist(big + [smaller], [], self.settings, NOW), self.settings, NOW)
        self.assertEqual(len(result), 5)
        self.assertTrue(all(s.article.company == "openai" for s in result))

    def test_equal_impact_fallback_prefers_variety(self):
        first = self.article("OpenAI launches a new model")
        second = self.article("OpenAI launches another model")
        other = self.article("Anthropic launches a new model", company="anthropic")
        result = fallback([first, second, other], self.settings, NOW)
        self.assertEqual(len({s.article.company for s in result[:2]}), 2)

    def test_quiet_day_can_have_one_story_without_padding(self):
        story = fallback([self.article("OpenAI launches a new model")], self.settings, NOW)
        payload = discord_payload(story, "2026-11-11", NOW, "fallback")
        self.assertEqual(len(payload["embeds"]), 1)
        self.assertIn("1 signal for", payload["content"])

    def test_ai_can_choose_two_or_decline_all_instead_of_triggering_filler(self):
        candidates = [self.article(f"OpenAI introduces GPT-{i + 6}, a new model") for i in range(5)]
        for count in (0, 2):
            body = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"stories": [
                {"id": a.id} for a in candidates[:count]]})}}]}
            with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body))) as client:
                stories, report = process(client, candidates, self.settings, NOW, "fake-key")
            self.assertEqual(report["mode"], "deepseek")
            self.assertEqual(len(stories), count)

    def test_ai_declining_all_produces_no_discord_payload_or_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = replace(load_settings(ROOT / "fixtures/config.toml"), min_stories=1,
                               output_dir=root / "output", history_path=root / "history.json")
            def handler(request):
                if request.method == "GET":
                    source = next(s for s in settings.sources if s.url == str(request.url))
                    return httpx.Response(200, content=(ROOT / "fixtures" / f"{source.id}.xml").read_bytes())
                return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": '{"stories":[]}'}}]})
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                report = run_pipeline(settings, History(settings.history_path), client, NOW, api_key="fake")
            self.assertEqual(report["status"], "insufficient_news")
            self.assertIsNone(json.loads((settings.output_dir / "discord.json").read_text()))
            self.assertFalse(settings.history_path.exists())


class CollectionEditorialTests(unittest.TestCase):
    def setUp(self):
        self.settings = load_settings(ROOT / "config.toml")
        self.source = next(s for s in self.settings.sources if s.id == "anthropic")

    def card(self, date="2026-11-10", href="/news/new-model"):
        return (f'<li><h3><a href="{href}">Introducing Claude, a new AI model</a></h3>'
                f'<p>{EXCERPT}</p><time datetime="{date}">November 10, 2026</time></li>').encode()

    def test_dated_official_announcement_cards_preserve_source_metadata(self):
        items = parse_announcements(self.card(), self.source, NOW, self.settings)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_tier, "official")
        self.assertEqual(items[0].company, "anthropic")
        self.assertEqual(items[0].url, "https://www.anthropic.com/news/new-model")

    def test_announcement_adapters_skip_undated_and_external_links(self):
        for body in (self.card().replace(b'<time datetime="2026-11-10">November 10, 2026</time>', b''),
                     self.card(href="https://evil.example/story")):
            with self.assertRaises(ValueError):
                parse_announcements(body, self.source, NOW, self.settings)

    def test_stale_future_and_duplicate_index_cards(self):
        for date in ("2026-10-01", "2026-11-20"):
            self.assertEqual(parse_announcements(self.card(date), self.source, NOW, self.settings), [])
        self.assertEqual(len(parse_announcements(self.card() + self.card(), self.source, NOW, self.settings)), 1)

    def test_google_image_caption_is_replaced_by_official_description(self):
        source = next(s for s in self.settings.sources if s.id == "google-ai")
        article = Article("Gemini adds new capabilities", "https://blog.google/example", "A man speaks into a phone. " * 3,
                          NOW, source.id, source.name, 1, source_tier=source.tier, company=source.company)
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, text=f'<meta property="og:description" content="{EXCERPT}">')
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            items = enrich_missing(client, [article], source, self.settings)
        self.assertEqual(len(calls), 1)
        self.assertEqual(items[0].excerpt, EXCERPT)

    def test_failed_google_description_does_not_leave_an_image_caption_as_news(self):
        source = next(s for s in self.settings.sources if s.id == "google-ai")
        article = Article("Gemini adds new capabilities", "https://blog.google/example", "A photo of a phone. " * 4,
                          NOW, source.id, source.name, 1)
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404))) as client:
            self.assertEqual(enrich_missing(client, [article], source, self.settings), [])


if __name__ == "__main__":
    unittest.main()
