"""Regression coverage for silent no-delivery runs and trusted reporting."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from init_daily.cli import main
from init_daily.config import load_settings
from init_daily.editorial import assess
from init_daily.formatting import discord_payload
from init_daily.history import History
from init_daily.models import Article, Story
from init_daily.pipeline import run_pipeline
from init_daily.ranking import shortlist
from init_daily.verification import article_body, verify_selected

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 28, 1, 5, tzinfo=timezone.utc)
REPORT = "https://techcrunch.com/2026/11/27/nvidia-pauses-ai-chip-shipments"
PRIMARY = "https://blog.google/products-and-platforms/products/search/google-search-personal-intelligence-apps"


def page(title, body, *, published=NOW.isoformat(), outside=""):
    metadata = f'<meta property="article:published_time" content="{published}">' if published else ""
    return (f'<html><head>{metadata}</head><body><main><h1>{title}</h1>'
            f'<div class="entry-content">{body}</div>{outside}</main></body></html>').encode()


class ReportingDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.settings = load_settings(ROOT / "config.toml")

    def story(self, title="Nvidia pauses AI chip shipments", *, url=REPORT, company="nvidia", refs=()):
        article = Article(title, url, "Nvidia has paused AI chip shipments while it checks whether partners meet export requirements.",
                          NOW, "techcrunch-ai", "TechCrunch AI", 1, source_tier="reporting", company=company,
                          reference_urls=refs)
        return Story(article, "An old unsupported feed claim.", "Invented market effects.", "industry", "deepseek")

    def verify(self, story, handler, **kwargs):
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return verify_selected([story], self.settings, client, NOW, **kwargs)

    def test_fresh_opted_in_reporting_is_attributed_and_uses_current_body(self):
        story = self.story()
        quote = "Nvidia has paused AI chip shipments while it checks whether partners meet export requirements."
        raw = page(story.article.title, f"<p>{quote}</p>", outside="<p>Nvidia introduces a different AI chip with invented capabilities.</p>")
        stories, audit = self.verify(story, lambda r: httpx.Response(200, content=raw))
        self.assertEqual(len(stories), 1)
        self.assertEqual(stories[0].summary, "TechCrunch AI reports: " + quote)
        self.assertNotIn("Invented", stories[0].why)
        self.assertEqual(audit["http_requests"], 1)
        self.assertEqual((audit["primary_checked"], audit["reporting_checked"]), (0, 1))
        record = audit["stories"][0]
        self.assertNotIn("primary_url", record)
        self.assertEqual(record["evidence_method"], "reporting_article_body")
        self.assertEqual(record["evidence_quotes"], [quote])
        self.assertTrue(record["body_sha256"])
        embed = discord_payload(stories, "2026-11-28", NOW, "deepseek")["embeds"][0]
        self.assertIn("Report:", embed["title"])
        self.assertIn("reporting", embed["footer"]["text"])
        self.assertEqual(embed["url"], REPORT)

    def test_reporting_requires_explicit_source_opt_in(self):
        self.settings = replace(self.settings, sources=tuple(replace(s, verify_reporting_body=False) for s in self.settings.sources))
        story = self.story()
        raw = page(story.article.title, f"<p>{story.article.excerpt}</p>")
        stories, audit = self.verify(story, lambda r: httpx.Response(200, content=raw))
        self.assertEqual(stories, [])
        self.assertEqual(audit["withheld_codes"], {"primary_reference_missing": 1})

    def test_reporting_rejects_missing_stale_future_or_feed_conflicting_dates(self):
        story = self.story()
        for date in ("", (NOW - timedelta(days=4)).isoformat(), (NOW + timedelta(hours=1)).isoformat(),
                     (NOW - timedelta(days=2)).isoformat(), "2026-11-28T01:05:00", "bad-date"):
            with self.subTest(date=date):
                raw = page(story.article.title, f"<p>{story.article.excerpt}</p>", published=date)
                stories, audit = self.verify(story, lambda r: httpx.Response(200, content=raw))
                self.assertEqual(stories, [])
                self.assertEqual(audit["withheld_codes"], {"reporting_publication_date_invalid": 1})

    def test_mismatched_title_or_untrusted_reporting_host_never_passes(self):
        raw = page("A different AI event", "<p>Nvidia is mentioned incidentally in an unrelated discussion about AI chips.</p>")
        stories, audit = self.verify(self.story(), lambda r: httpx.Response(200, content=raw))
        self.assertFalse(stories)
        self.assertEqual(audit["withheld_codes"], {"primary_topic_mismatch": 1})
        stories, audit = self.verify(self.story(url="https://evil.example/nvidia-ai-chip-shipments"),
                                     lambda r: self.fail("An untrusted reporting host was fetched"))
        self.assertFalse(stories)
        self.assertEqual(audit["withheld_codes"], {"untrusted_reporting_url": 1})

    def test_reporting_does_not_mask_blocked_or_conflicting_primary_evidence(self):
        primary = "https://blogs.nvidia.com/blog/nvidia-pauses-ai-chip-shipments"
        story = self.story(refs=(primary,))
        for response, code in ((httpx.Response(403), "primary_http_403"),
                               (httpx.Response(200, content=page("A different AI event", "<p>An unrelated product is discussed here.</p>")), "primary_topic_mismatch")):
            def handler(request):
                self.assertEqual(str(request.url), primary)
                return response
            stories, audit = self.verify(story, handler)
            self.assertFalse(stories)
            self.assertEqual(audit["withheld_codes"], {code: 1})

    def test_different_official_slug_is_checked_against_body_and_history(self):
        story = self.story("Google Search’s AI Mode can now tap into Drive and Wallet for more personalized responses",
                           company="google", refs=(PRIMARY,))
        quote = "Google Search AI Mode can connect Wallet and Drive to offer more personalized responses for account holders."
        raw = page("A more tailored Google Search that’s uniquely yours", f"<p>{quote}</p>")
        stories, audit = self.verify(story, lambda r: httpx.Response(200, content=raw))
        self.assertEqual([s.verified_url for s in stories], [PRIMARY])
        self.assertEqual(audit["stories"][0]["topic_match"], "explicit_link_and_body")
        stories, audit = self.verify(story, lambda r: httpx.Response(200, content=raw),
                                     previous=({"url": PRIMARY, "primary_url": PRIMARY},))
        self.assertFalse(stories)
        self.assertEqual(audit["withheld_codes"], {"duplicate_primary_story": 1})

    def test_one_shared_url_word_cannot_corroborate_unrelated_body(self):
        story = self.story("Google Search adds AI shopping tools", company="google", refs=(PRIMARY,))
        raw = page("Google Search education resources", "<p>Search helps students find school library information for their reading assignments.</p>")
        stories, audit = self.verify(story, lambda r: httpx.Response(200, content=raw))
        self.assertFalse(stories)
        self.assertEqual(audit["withheld_codes"], {"primary_topic_mismatch": 1})

    def test_entry_content_excludes_related_stories_and_promotions(self):
        raw = page("Nvidia pauses AI chip shipments", "<p>Nvidia paused AI chip shipments while it checks export requirements with its partners.</p>",
                   outside="<section><p>Unrelated AI release with far more exciting new capabilities.</p></section>")
        _, blocks, _ = article_body(raw)
        self.assertEqual(len(blocks), 1)
        self.assertNotIn("exciting", blocks[0])

    def test_usage_limits_and_credit_reviews_outrank_routine_papers(self):
        paper = replace(self.story().article, title="An incremental AI benchmark paper", source_tier="research", category="research")
        for title, company in (("OpenAI says heavy ChatGPT users may hit limits sooner as it merges Chat and Work", "openai"),
                               ("S&P considers Nvidia credit downgrade over governance and key man risks", "nvidia")):
            article = self.story(title, company=company).article
            self.assertGreaterEqual(assess(article, NOW).score, self.settings.min_score)
            self.assertGreater(assess(article, NOW).score, assess(paper, NOW).score)
        for title in ("Anthropic CEO appears at opening bell", "Nvidia CEO discusses personal hobbies"):
            self.assertLess(assess(self.story(title).article, NOW).score, self.settings.min_score)

    def test_reporting_preserves_small_paid_rollout_and_removes_old_summary(self):
        story = self.story("OpenAI changes ChatGPT usage limits", company="openai")
        raw = page(story.article.title, "<p>The ChatGPT update is rolling out to a small group of Pro subscribers, according to the company.</p>")
        stories, audit = self.verify(story, lambda r: httpx.Response(200, content=raw))
        self.assertEqual(len(stories), 1)
        self.assertIn("small group of Pro subscribers", stories[0].summary)
        self.assertNotIn("old unsupported", stories[0].summary)
        self.assertTrue(audit["stories"][0]["access_conditions_retained"])

    def test_usage_policy_summary_includes_the_change_and_paid_scope(self):
        story = self.story("OpenAI changes ChatGPT usage limits", company="openai")
        raw = page(story.article.title, "<p>The ChatGPT update is rolling out to a small group of Pro subscribers, according to the company.</p>"
                   "<p>Under the new system, Chat and Work will share a single usage meter across ChatGPT, the OpenAI spokesperson told TechCrunch.</p>")
        stories, audit = self.verify(story, lambda r: httpx.Response(200, content=raw))
        self.assertIn("share a single usage meter", stories[0].summary)
        self.assertIn("small group of Pro subscribers", stories[0].summary)
        quotes = audit["stories"][0]["evidence_quotes"]
        self.assertLessEqual(sum(len(q.split()) for q in quotes), 25)

    def test_shipping_pause_summary_retains_unspecified_duration_and_conditions(self):
        story = self.story()
        scope = "for an unspecified period while it checks regional partners against export requirements."
        raw = page(story.article.title, "<p>Nvidia is under pressure to do things differently, and a new report shows how far that goes.</p>"
                   f"<p>Nvidia has asked manufacturing partners, including several server suppliers and distributors, to pause AI chip shipments {scope}</p>")
        stories, audit = self.verify(story, lambda r: httpx.Response(200, content=raw))
        self.assertIn(scope, stories[0].summary)
        self.assertNotIn("under pressure", stories[0].summary)
        self.assertEqual(audit["stories"][0]["evidence_quotes"], [scope])

    def test_complete_reporting_preview_uses_one_ai_call_and_never_contacts_discord(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = next(s for s in self.settings.sources if s.id == "techcrunch-ai")
            settings = replace(self.settings, sources=(source,), history_path=root/"history.json", output_dir=root/"output")
            story = self.story()
            feed = f'<rss><channel><item><title>{story.article.title}</title><link>{REPORT}</link><pubDate>Sat, 28 Nov 2026 01:05:00 GMT</pubDate><description>{story.article.excerpt}</description></item></channel></rss>'
            calls = []
            def handler(request):
                calls.append(request)
                if request.url.host == "api.deepseek.com":
                    return httpx.Response(200, json={"choices":[{"finish_reason":"stop", "message":{"content":json.dumps({"stories":[{"id":story.article.id}]})}}]})
                self.assertEqual(request.method, "GET")
                self.assertEqual(request.url.host, "techcrunch.com")
                return httpx.Response(200, text=feed) if str(request.url) == source.url else httpx.Response(200, content=page(story.article.title, f"<p>{story.article.excerpt}</p>"))
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                report = run_pipeline(settings, History(settings.history_path), client, NOW, api_key="fake-key")
            self.assertEqual(report["status"], "preview")
            self.assertEqual(report["verification"]["reporting_checked"], 1)
            self.assertEqual(sum(r.method == "POST" for r in calls), 1)
            self.assertFalse(settings.history_path.exists())

    def test_blocked_production_returns_failure_but_dry_run_stays_reviewable(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = replace(self.settings, history_path=Path(directory)/"history.json", output_dir=Path(directory)/"output")
            report = {"date":"2026-11-28", "status":"insufficient_verified_news", "stories":0}
            with patch("init_daily.cli.load_settings", return_value=settings), patch("init_daily.cli.run_pipeline", return_value=report), \
                 patch.dict(os.environ, {"INIT_DAILY_PUBLISH_ENABLED":"true", "GITHUB_STEP_SUMMARY":""}):
                self.assertEqual(main(["--publish"]), 2)
                self.assertEqual(main(["--dry-run"]), 0)


if __name__ == "__main__":
    unittest.main()
