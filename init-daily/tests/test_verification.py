from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

import httpx

from init_daily.collect import parse_feed
from init_daily.config import load_settings
from init_daily.formatting import discord_payload
from init_daily.history import History
from init_daily.models import Article, Story
from init_daily.pipeline import run_pipeline
from init_daily.ranking import shortlist
from init_daily.verification import article_body, current_excerpt, verify_selected

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 11, 1, 15, tzinfo=timezone.utc)
GOOGLE = "https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-4-carbon-now-available"
DEEP = "https://deepmind.google/blog/introducing-alphaproof-code"


def page(title, *paragraphs, meta=""):
    return (f'<html><head><meta name="description" content="{meta}"></head>'
            f'<body><nav><p>Old teaser: three million lines of Lean.</p></nav><main><h1>{title}</h1>'
            + "".join(f"<p>{p}</p>" for p in paragraphs) + '</main></body></html>').encode()


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.settings = load_settings(ROOT / "config.toml")

    def story(self, title="Introducing AlphaProof Code for Signal", url=DEEP, summary=None,
              source="deepmind", tier="official", refs=()):
        summary = summary or "Agents wrote three million lines of Lean proofs for Signal encryption."
        article = Article(title, url, summary, NOW, source, source, 1.5, source_tier=tier,
                          company="google", reference_urls=refs)
        return Story(article, summary, "A widely available model could change how everyone builds.", "models", "deepseek")

    def test_current_body_replaces_stale_feed_and_metadata_quantity(self):
        raw = page("Introducing AlphaProof Code for Signal",
                   "Researchers describe AlphaProof Code for verification of Signal software.",
                   "The agents generated over six million lines of Lean proofs for the Signal protocol.",
                   meta="Agents wrote three million lines of Lean proofs for Signal.")
        _, blocks, _ = article_body(raw)
        summary, quotes, details = current_excerpt(self.story(), blocks)
        self.assertIn("over six million", summary)
        self.assertNotIn("three million", summary)
        self.assertTrue(details["quantitative_body_quote"])
        self.assertTrue(all(any(q in p for p in blocks) for q in quotes))

    def test_approximate_quantity_and_units_are_not_normalized_away(self):
        body = ["AlphaProof Code agents produced approximately 6.5 million lines of Lean proof code for Signal."]
        summary, _, _ = current_excerpt(self.story(), body)
        self.assertIn("approximately 6.5 million lines", summary)

    def access_body(self, together=False):
        paragraphs = ["Gemini 4 Carbon is now available to developers and consumers.",
            "Gemini 4 Carbon is available via the API for all paying developers and enterprises, at the same introductory price of $2 per million tokens.",
            "It is also rolling out to all Google AI Ultra subscribers in the Gemini app and AI Mode in Search.",
            "After the introductory period expires on November 30, 2026, the price is $4 per million input tokens."]
        if together:
            paragraphs[1:3] = [" ".join(paragraphs[1:3])]
        return paragraphs

    def test_paid_and_ultra_access_retained_across_adjacent_paragraphs(self):
        story = self.story("Google releases Gemini 4 Carbon", GOOGLE, "Gemini 4 Carbon is rolling out to the general public.")
        for together in (False, True):
            summary, quotes, details = current_excerpt(story, self.access_body(together))
            self.assertIn("paying developers and enterprises", summary)
            self.assertIn("rolling out to all Google AI Ultra subscribers", summary)
            self.assertNotIn("general public", summary)
            self.assertNotIn("$", summary)
            self.assertTrue(details["access_conditions_retained"])
            self.assertTrue(details["pricing_omitted"])
            self.assertTrue(all(any(q in p for p in self.access_body(together)) for q in quotes))

    def test_regional_exception_after_subscriber_label_is_not_cut_off(self):
        body = self.access_body()
        body[2] = "It is also rolling out to all Google AI Ultra subscribers in eligible regions only."
        summary, _, _ = current_excerpt(self.story("Gemini 4 Carbon launch", GOOGLE), body)
        self.assertIn("eligible regions only", summary)

    def test_price_without_complete_terms_is_omitted_not_promoted_to_permanent_price(self):
        story = self.story("Gemini 4 Carbon launch", GOOGLE, "Carbon costs $2 per million tokens.")
        summary, _, details = current_excerpt(story, self.access_body())
        self.assertNotIn("$2", summary)
        self.assertNotIn("$4", summary)
        self.assertTrue(details["pricing_omitted"])

    def test_cannot_shorten_a_sentence_by_dropping_eligibility(self):
        body = ["Gemini 4 Carbon is available to a broad range of developers building advanced AI applications, but only to eligible paid accounts."]
        with self.assertRaises(ValueError):
            current_excerpt(self.story("Gemini 4 Carbon launch", GOOGLE), body)

    def test_secondary_feed_primary_reference_is_used_and_displayed(self):
        story = self.story("Google releases Gemini 4 Carbon", "https://www.theverge.com/news/carbon",
                           "Rolling out to the general public.", "verge-ai", "reporting", (GOOGLE,))
        calls = []
        def handler(request):
            calls.append(request)
            self.assertEqual(request.url.host, "blog.google")
            self.assertNotIn("authorization", request.headers)
            return httpx.Response(200, content=page("Gemini 4 Carbon is now available", *self.access_body()))
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            stories, audit = verify_selected([story], self.settings, client, NOW)
        self.assertEqual(len(calls), 1)
        self.assertEqual(stories[0].article.id, story.article.id)
        self.assertEqual(audit["checked"], 1)
        self.assertEqual(audit["stories"][0]["primary_url"], GOOGLE)
        self.assertTrue(audit["stories"][0]["body_sha256"])
        payload = discord_payload(stories, "2026-11-11", NOW, "deepseek")
        self.assertEqual(payload["embeds"][0]["url"], GOOGLE)
        self.assertTrue(payload["embeds"][0]["footer"]["text"].startswith("Google AI"))
        self.assertEqual(audit["stories"][0]["primary_source"], "Google AI")
        self.assertNotIn("widely available", stories[0].why)

    def test_unavailable_primary_is_withheld_without_feed_fallback(self):
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403))) as client:
            stories, audit = verify_selected([self.story()], self.settings, client, NOW)
        self.assertEqual(stories, [])
        self.assertEqual(audit["stories"][0]["code"], "primary_http_403")
        self.assertEqual(audit["http_requests"], 1)

    def test_two_reports_of_one_primary_story_are_not_repeated(self):
        first = self.story("Google releases Gemini 4 Carbon", "https://www.theverge.com/report", "Now available to the general public.", "verge-ai", "reporting", (GOOGLE,))
        second = replace(first, article=replace(first.article, url="https://techcrunch.com/another-report"))
        raw = page("Gemini 4 Carbon is now available", *self.access_body())
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=raw))) as client:
            stories, audit = verify_selected([first, second], self.settings, client, NOW)
        self.assertEqual(len(stories), 1)
        self.assertEqual(audit["http_requests"], 1)
        self.assertEqual(audit["stories"][1]["code"], "duplicate_primary_story")

    def test_verification_budget_is_global_and_does_not_retry(self):
        settings = replace(self.settings, verification_max_requests=1)
        second = replace(self.story(), article=replace(self.story().article, url=DEEP + "-second"))
        raw = page("Introducing AlphaProof Code for Signal", "AlphaProof Code agents generated over six million lines of Lean proofs for Signal.")
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=raw))) as client:
            stories, audit = verify_selected([self.story(), second], settings, client, NOW)
        self.assertEqual(len(stories), 1)
        self.assertEqual(audit["http_requests"], 1)
        self.assertEqual(audit["stories"][1]["code"], "verification_budget_exhausted")

    def test_mismatched_primary_and_untrusted_redirect_are_withheld(self):
        for response, code in [(httpx.Response(200, content=page("A different robotics event", "Robotics teams are preparing a new demonstration for students.")), "primary_topic_mismatch"),
                               (httpx.Response(302, headers={"location":"https://evil.example/article"}), "untrusted_primary_url")]:
            with httpx.Client(transport=httpx.MockTransport(lambda r: response)) as client:
                stories, audit = verify_selected([self.story()], self.settings, client, NOW)
            self.assertFalse(stories)
            self.assertEqual(audit["stories"][0]["code"], code)

    def test_common_company_and_version_tokens_do_not_corroborate_a_different_model(self):
        story = self.story("Google releases Gemini 4 Carbon", GOOGLE, "Available to the general public.")
        for title in ("Gemini 4 Argon is now available", "Gemini 5 Carbon is now available"):
            raw = page(title, *self.access_body())
            with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=raw))) as client:
                stories, audit = verify_selected([story], self.settings, client, NOW)
            self.assertFalse(stories)
            self.assertEqual(audit["stories"][0]["code"], "primary_topic_mismatch")

    def test_history_deduplicates_discovery_and_verified_primary_urls(self):
        with tempfile.TemporaryDirectory() as temporary:
            story = replace(self.story(url="https://www.theverge.com/story", source="verge-ai", tier="reporting"), verified_url=DEEP)
            history = History(Path(temporary) / "history.json")
            ident = history.reserve("2026-11-11", [story], {})
            history.resolve(ident, "sent", "123456789")
            changed_title = replace(self.story().article, title="Signal implementation verification milestone by Google", url=DEEP)
            self.assertEqual(shortlist([changed_title], history.previous_stories(), self.settings, NOW), [])

    def test_full_pipeline_uses_one_ai_call_then_checks_body_before_preview(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = next(s for s in self.settings.sources if s.id == "deepmind")
            settings = replace(self.settings, sources=(source,), output_dir=root / "output", history_path=root / "history.json")
            feed = ('<rss version="2.0"><channel><title>Test</title><item>'
                    '<title>Introducing AlphaProof Code for Signal</title>'
                    f'<link>{DEEP}</link><pubDate>Tue, 10 Nov 2026 12:00:00 GMT</pubDate>'
                    '<description>AlphaProof Code agents wrote three million lines of Lean proofs for the Signal protocol.</description>'
                    '</item></channel></rss>').encode()
            article = parse_feed(feed, source, NOW, settings)[0]
            calls = []
            def handler(request):
                calls.append(request)
                if str(request.url) == source.url:
                    return httpx.Response(200, content=feed)
                if request.method == "POST":
                    self.assertEqual(request.url.host, "api.deepseek.com")
                    return httpx.Response(200, json={"choices":[{"finish_reason":"stop","message":{"content":json.dumps({"stories":[{"id":article.id}]})}}]})
                return httpx.Response(200, content=page(article.title, "AlphaProof Code agents generated over six million lines of Lean proofs for the Signal protocol."))
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                result = run_pipeline(settings, History(settings.history_path), client, NOW, api_key="fake-key")
            self.assertEqual(result["processing"]["mode"], "deepseek")
            self.assertEqual(result["verification"]["checked"], 1)
            self.assertEqual(sum(r.method == "POST" for r in calls), 1)
            self.assertNotIn("three million", (settings.output_dir / "briefing.md").read_text())
            self.assertFalse(settings.history_path.exists())


if __name__ == "__main__":
    unittest.main()
