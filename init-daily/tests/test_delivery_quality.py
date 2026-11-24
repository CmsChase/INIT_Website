"""Substantive source excerpts and coverage found during the Nov 24 audit."""
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import unittest

import httpx

from init_daily.collect import enrich_missing
from init_daily.config import load_settings
from init_daily.editorial import assess
from init_daily.models import Article, Story
from init_daily.verification import article_body, current_excerpt

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 24, 9, 30, tzinfo=timezone.utc)


class DeliveryQualityTests(unittest.TestCase):
    def setUp(self):
        self.settings = load_settings(ROOT / "config.toml")

    def story(self, title, excerpt="New AI capabilities improve workflows for developers and teams."):
        a = Article(title, "https://blog.google/story", excerpt, NOW, "google-ai", "Google AI", 1.3,
                    source_tier="official", company="google")
        return Story(a, excerpt, "Consider testing.", "tools", "deepseek")

    def test_search_integration_is_collected_without_ai_in_editorial_headline(self):
        source = next(s for s in self.settings.sources if s.id == "google-search")
        a = replace(self.story("A more tailored Google Search that's uniquely yours").article,
                    excerpt="Google Search bar with the text Personal Intelligence surrounded by the Google Wallet and Drive logo icons",
                    source_id=source.id)
        description = "Get more helpful Search responses by opting in to connect Google Wallet, Drive, and the Gemini app in AI Mode."
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=
                f'<meta property="og:description" content="{description}">'))) as client:
            items = enrich_missing(client, [a], source, self.settings)
        self.assertEqual(items[0].excerpt, description)
        self.assertIn("strategic_development", assess(items[0], NOW).signals)
        self.assertGreaterEqual(assess(items[0], NOW).score, self.settings.min_score)

    def test_claude_article_excludes_related_cards_and_retains_paid_plans_and_beta(self):
        raw = b'''<main><h1>Introducing Claude Ship</h1><article>
          <div class="text-rich-text--article w-richtext">
            <p>Anyone who has opened a pull request knows how this goes. They start on the next thing, and then the review comes back.</p>
            <p>Claude Ship is available on Claude Team and Enterprise plans for repositories on GitHub. Code Review is generally available, and PR Steward and Claude Approvals are in beta.</p>
          </div><div class="text-rich-text--article w-richtext"><p>Claude Ship is not available to organizations with Zero Data Retention or customer-managed encryption keys.</p></div>
          </article><section><p>A related model is now free for everyone.</p></section></main>'''
        title, blocks, _ = article_body(raw)
        self.assertFalse(any("related model" in b for b in blocks))
        self.assertTrue(any("Zero Data Retention" in b for b in blocks))
        summary, quotes, details = current_excerpt(self.story(title), blocks)
        self.assertIn("Team and Enterprise plans", summary)
        self.assertIn("PR Steward and Claude Approvals are in beta", summary)
        self.assertNotIn("knows how this goes", summary)
        self.assertTrue(details["access_conditions_retained"])
        self.assertLessEqual(sum(len(q.split()) for q in quotes), 25)

    def test_summary_rejects_empty_list_intro_and_prefers_complete_useful_fact(self):
        story = self.story("Introducing file slicing controls in the Gemini API")
        fact = "This keeps context focused on the relevant parts of a file while billing tokens only for the parts Gemini inspects."
        summary, _, _ = current_excerpt(story, ["You can customize processing across these media categories:", fact])
        self.assertEqual(summary, fact)

    def test_complete_read_only_privacy_scope_is_retained(self):
        fact = "If you choose to connect your Wallet, AI Mode can only read information from your accounts; it can't move, manage, or invest your money."
        summary, quotes, _ = current_excerpt(self.story("Google Search connects Wallet"), [fact])
        self.assertEqual(summary, fact)
        self.assertEqual(quotes, [fact])

    def test_profiles_and_minor_regional_rollouts_do_not_fill_a_digest(self):
        for title in ("Researchers Are Using Meta's Open-Weight AI Models to Transform Medicine",
                      "Introducing Muse in the UK: A Personal AI Agent You Control",
                      "How Notable Capital bet big on Anthropic before its IPO"):
            self.assertLess(assess(self.story(title).article, NOW).score, self.settings.min_score, title)
        release = self.story("Introducing Gemini 5, a new model in the UK")
        self.assertGreaterEqual(assess(release.article, NOW).score, self.settings.min_score)


if __name__ == "__main__":
    unittest.main()
