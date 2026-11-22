"""Regressions for November 22: missed announcements and interview filler."""
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

import httpx

from init_daily.collect import enrich_missing
from init_daily.config import load_settings
from init_daily.editorial import assess
from init_daily.history import History
from init_daily.models import Article, Story
from init_daily.pipeline import run_pipeline
from init_daily.ranking import shortlist
from init_daily.verification import VerificationError, current_excerpt, verify_selected

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 22, 7, 33, tzinfo=timezone.utc)


class QuietDayTests(unittest.TestCase):
    def setUp(self):
        self.settings = load_settings(ROOT / "config.toml")

    def article(self, title, company="google", **kwargs):
        return Article(title, "https://blog.google/" + title.lower().replace(" ", "-"),
                       kwargs.pop("excerpt", "The company describes how AI could change work and society in the coming years."),
                       NOW, kwargs.pop("source_id", "google-ai"), "Google AI", 1.3,
                       source_tier=kwargs.pop("tier", "official"), company=company, **kwargs)

    def test_official_brand_alone_does_not_make_interview_or_research_news(self):
        for title in ("Walter Isaacson on curiosity and creativity in the AI age.",
                      "Research acceleration: The jagged frontier",
                      "Can AI help scientists identify promising drug candidates?",
                      "Highlights From the Open Source AI For Science Summit",
                      "Our new AI podcast: conversations with researchers"):
            article = self.article(title)
            self.assertLess(assess(article, NOW).score, self.settings.min_score, title)
            self.assertEqual(shortlist([article], [], self.settings, NOW), [])

    def test_ipo_closing_survives_missing_ai_keyword(self):
        article = self.article("Anthropic announces closing of initial public offering", company="anthropic",
                               excerpt="Today Anthropic announced the closing of its initial public offering of Class A common stock.",
                               ai_focused_source=False)
        result = assess(article, NOW)
        self.assertIn("major_corporate_development", result.signals)
        self.assertGreaterEqual(result.score, 12)
        self.assertEqual(shortlist([article], [], self.settings, NOW), [article])

    def test_ceo_appearance_is_not_a_leadership_transition(self):
        article = self.article("At Nasdaq opening bell, Anthropic CEO recommits to pacing AI development",
                               company="anthropic", tier="reporting")
        result = assess(article, NOW)
        self.assertNotIn("major_corporate_development", result.signals)
        self.assertLess(result.score, self.settings.min_score)
        for title in ("Anthropic appoints new chief executive", "NVIDIA CEO ousted by board"):
            self.assertIn("major_corporate_development", assess(self.article(title, company="anthropic"), NOW).signals)

    def test_ipo_implication_is_about_capital_not_export_controls(self):
        article = replace(self.article("Anthropic announces closing of initial public offering", company="anthropic",
                                       source_id="anthropic"), url="https://www.anthropic.com/news/ipo-close")
        raw = (f'<main><h1>{article.title}</h1><p>Anthropic common stock began trading on the Nasdaq Global Select Market under the symbol ANT.</p></main>').encode()
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=raw))) as client:
            stories, _ = verify_selected([Story(article, article.excerpt, "Consider the implications.", "strategy", "deepseek")],
                                          self.settings, client, NOW)
        self.assertEqual(len(stories), 1)
        self.assertIn("capital", stories[0].why)
        self.assertNotIn("export", stories[0].why)

    def test_concrete_product_change_can_be_in_official_teaser_or_report_headline(self):
        for excerpt in ("We’re introducing computer use in the Gemini app for Mac to automate repetitive tasks.",
                        "Gemini can now navigate Mac apps and websites to finish complex tasks.",
                        "The Gemini app for Mac now has computer use to help you with repetitive tasks."):
            article = self.article("Let Gemini tackle repetitive chores on your Mac", excerpt=excerpt)
            self.assertGreaterEqual(assess(article, NOW).score, self.settings.min_score)
        report = self.article("Google gives Gemini the ability to use your Mac for you", tier="reporting")
        self.assertGreaterEqual(assess(report, NOW).score, self.settings.min_score)
        self.assertGreaterEqual(assess(self.article("Gemini introduces podcast generation for creators"), NOW).score,
                                self.settings.min_score)

    def test_article_linked_footnote_preserves_paid_access_and_region(self):
        from init_daily.verification import article_body
        raw = b'''<h1>Let Gemini tackle repetitive chores on your Mac</h1>
        <main><div data-article-body="true">
          <p>Gemini can navigate apps and websites in a background window while you keep working.</p>
          <p>Computer use is rolling out in English in the U.S. in the Gemini app for Mac. <a href="#footnote-1">1</a></p>
        </div><div id="footnote-1"><p>Requires an Apple Silicon Mac running macOS Sequoia 15.0+. Available for personal Google accounts 18+, available to Google AI Plus, Pro and Ultra users.</p></div>
        <div id="footnote-2"><p>Unrelated product is free for everyone.</p></div></main>'''
        title, blocks, _ = article_body(raw)
        self.assertTrue(any("Requires an Apple Silicon" in b for b in blocks))
        self.assertFalse(any("Unrelated product" in b for b in blocks))
        article = self.article(title, excerpt="The Gemini app for Mac now has computer use to help you with repetitive tasks.")
        story = Story(article, article.excerpt, "Consider the implications.", "tools", "deepseek")
        summary, quotes, details = current_excerpt(story, blocks)
        self.assertIn("English in the U.S.", summary)
        self.assertIn("personal Google accounts 18+", summary)
        self.assertIn("Google AI Plus, Pro and Ultra users", summary)
        self.assertLessEqual(sum(len(q.split()) for q in quotes), 25)
        self.assertTrue(details["access_conditions_retained"])

    def test_missing_product_and_developer_feeds_are_covered(self):
        sources = {s.id: s for s in self.settings.sources}
        self.assertTrue(sources["google-gemini-app"].url.endswith("/products/gemini-app/rss/"))
        self.assertTrue(sources["google-developers"].url.endswith("/technology/developers-tools/rss/"))

    def test_image_prompt_is_enriched_before_product_ranking(self):
        source = next(s for s in self.settings.sources if s.id == "google-gemini-app")
        article = self.article("Let Gemini tackle repetitive chores on your Mac", source_id=source.id,
                               excerpt="Prompting Gemini to take a kid's butterfly sketch, model it, and rig it in Blender")
        description = "We’re introducing computer use in the Gemini app for Mac to automate repetitive tasks."
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=
                f'<meta property="og:description" content="{description}">'))) as client:
            enriched = enrich_missing(client, [article], source, self.settings)
        self.assertEqual(enriched[0].excerpt, description)
        self.assertGreaterEqual(assess(enriched[0], NOW).score, self.settings.min_score)

    def test_unverifiable_selection_cannot_be_replaced_with_official_interview(self):
        initial = self.article("Google rolls out a new AI search homepage", source_id="ars-ai", tier="reporting")
        interview = self.article("Walter Isaacson on curiosity and creativity in the AI age.")
        calls = []
        def handler(request):
            calls.append(str(request.url))
            self.assertEqual(str(request.url), initial.url)
            return httpx.Response(200, text="<main><h1>AI search news</h1><p>No primary link exists here.</p></main>")
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            stories, audit = verify_selected([Story(initial, initial.excerpt, "Consider the implications.", "industry", "deepseek")],
                                              self.settings, client, NOW, alternates=(interview,))
        self.assertEqual(stories, [])
        self.assertEqual(len(calls), 1)
        self.assertEqual(audit["withheld_codes"], {"primary_reference_missing": 1, "editorial_below_threshold": 1})

    def test_rhetorical_question_cannot_be_a_factual_summary(self):
        article = self.article("Introducing a new AI capability")
        story = Story(article, article.excerpt, "Consider the implications.", "tools", "deepseek")
        with self.assertRaisesRegex(VerificationError, "no_safe_current_excerpt"):
            current_excerpt(story, ["What do Leonardo da Vinci and Ada Lovelace have to teach us about creativity in the age of AI?"])

    def test_selection_audit_distinguishes_history_weak_and_duplicate_items(self):
        sent = self.article("Introducing a new Gemini model")
        launch = self.article("Introducing Genie 4 in the Gemini API")
        duplicate = replace(launch, url=launch.url + "-report", source_tier="reporting")
        interview = self.article("Walter Isaacson on curiosity and creativity in the AI age.")
        audit = {}
        result = shortlist([sent, launch, duplicate, interview], [sent.record()], self.settings, NOW, audit=audit)
        self.assertEqual(result, [launch])
        self.assertEqual(audit["counts"], {"already_published": 1, "shortlisted": 1, "duplicate_in_run": 1, "below_threshold": 1})
        self.assertEqual(len(audit["articles"]), 4)

    def test_same_day_preview_keeps_history_deduplication_without_writing_or_posting(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = replace(self.settings, sources=(self.settings.sources[0],),
                               history_path=root / "history.json", output_dir=root / "output", verify_selected=False)
            history = History(settings.history_path)
            sent = self.article("Introducing a new Gemini model")
            ident = history.reserve("2026-11-22", [Story(sent, sent.excerpt, "Consider testing.", "models", "fallback")], {})
            history.resolve(ident, "sent", "123456789")
            before = settings.history_path.read_bytes()
            feed = f'''<rss version="2.0"><channel><title>Test</title><item>
              <title>{sent.title}</title><link>{sent.url.replace('blog.google', 'openai.com')}</link>
              <description>{sent.excerpt}</description><pubDate>Sun, 22 Nov 2026 06:00:00 GMT</pubDate>
              </item></channel></rss>'''
            def handler(request):
                self.assertEqual(request.method, "GET")
                self.assertEqual(str(request.url), settings.sources[0].url)
                return httpx.Response(200, text=feed)
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                report = run_pipeline(settings, history, client, NOW)
            self.assertTrue(report["already_published_today"])
            self.assertFalse(report["publishing_requested"])
            self.assertEqual(report["status"], "insufficient_news")
            self.assertEqual(report["editorial"]["filter_counts"], {"already_published": 1})
            self.assertIsNone(json.loads((settings.output_dir / "discord.json").read_text()))
            self.assertEqual(settings.history_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
