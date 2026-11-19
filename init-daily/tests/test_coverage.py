"""Regressions for major news lost in the November 18 publication."""
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import unittest

import httpx

from init_daily.collect import parse_feed
from init_daily.config import load_settings
from init_daily.editorial import assess
from init_daily.models import Article, Story
from init_daily.news_index import changelog_entries
from init_daily.verification import OPENAI_CHANGELOG, article_body, current_excerpt, verify_selected

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 18, 1, 15, tzinfo=timezone.utc)
LAUNCH = "https://openai.com/index/introducing-gpt-6-2-astra-sol"
CHANGELOG = b"""# Changelog
## November, 2026
### Nov 17
Feature \xc2\xb7 Model: gpt-6.2-astra \xc2\xb7 Model: gpt-6.2-sol

Use [GPT-6.2 Astra](https://developers.openai.com/api/docs/models/gpt-6.2-astra) for demanding reasoning and coding tasks, or [GPT-6.2 Sol](https://developers.openai.com/api/docs/models/gpt-6.2-sol) for everyday coding and agent workflows. Both models support the Responses API and Chat Completions. Tool calling requires the Responses API.

### Nov 17
Feature

Choose a background completion window in the Responses API public beta.
## October, 2026
### Oct 1
Feature

An unrelated older release supports unlimited free access for everyone.
"""


def page(title, *blocks):
    return (f"<main><h1>{title}</h1>" + "".join(f"<p>{b}</p>" for b in blocks) + "</main>").encode()


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.settings = load_settings(ROOT / "config.toml")

    def story(self, title="Introducing GPT-6.2 Astra and Sol", url=LAUNCH, **kwargs):
        article = Article(title, url, "New AI models improve coding and professional workflows.", NOW,
                          kwargs.pop("source_id", "openai"), "OpenAI", 1.5,
                          source_tier=kwargs.pop("tier", "official"),
                          company=kwargs.pop("company", "openai"), **kwargs)
        return Story(article, article.excerpt, "Consider comparing these models in a small project.", "models", "deepseek")

    def test_newsroom_and_product_feeds_are_configured(self):
        sources = {s.id: s for s in self.settings.sources}
        self.assertEqual(sources["nvidia-newsroom"].url, "https://nvidianews.nvidia.com/releases.xml")
        self.assertIn("www.microsoft.com", sources["microsoft365"].allowed_hosts)

    def test_ceo_transition_without_ai_keyword_enters_shortlist(self):
        source = next(s for s in self.settings.sources if s.id == "nvidia-newsroom")
        raw = b'''<rss version="2.0"><channel><title>Newsroom</title><item>
          <title>NVIDIA Announces CEO Transition</title>
          <link>https://nvidianews.nvidia.com/news/nvidia-announces-ceo-transition</link>
          <pubDate>Tue, 17 Nov 2026 12:00:00 GMT</pubDate>
          <description>Jensen Huang has resigned as Chief Executive Officer, effective immediately.</description>
          </item></channel></rss>'''
        articles = parse_feed(raw, source, NOW, self.settings)
        self.assertEqual(len(articles), 1)
        result = assess(articles[0], NOW)
        self.assertIn("major_corporate_development", result.signals)
        self.assertGreaterEqual(result.score, 12)

    def test_earnings_and_leadership_followups_outweigh_survey_and_event_recaps(self):
        for title in ("NVIDIA Announces Financial Results for Third Quarter Fiscal 2027",
                      "Nvidia says its open source AI strategy remains intact after Jensen Huang's exit"):
            article = replace(self.story(title, company="nvidia").article, ai_focused_source=False)
            self.assertGreaterEqual(assess(article, NOW).score, 12)
        for title in ("AI Day Seoul Brings Together Industry Leaders",
                      "94% of Small Business Owners Surveyed Say More AI Guidance Is Needed",
                      "How the World's Most Advanced AI Infrastructure Supply Chain Invents the Future",
                      "How AI Is Helping Care Teams Get Patients the Right Care, Sooner"):
            self.assertLess(assess(self.story(title).article, NOW).score, self.settings.min_score)

    def test_corporate_exception_does_not_promote_unrelated_meta_news(self):
        article = replace(self.story("Meta announces its financial results", company="meta").article,
                          excerpt="Revenue and earnings for the quarter, without an AI announcement.", ai_focused_source=False)
        self.assertEqual(assess(article, NOW).score, 0)

    def test_changelog_scopes_dates_and_discards_metadata(self):
        entries = changelog_entries(CHANGELOG)
        self.assertEqual([d.date().isoformat() for d, _ in entries], ["2026-11-17", "2026-11-17", "2026-10-01"])
        self.assertNotIn("Feature", " ".join(entries[0][1]))
        self.assertNotIn("unlimited free", " ".join(entries[0][1]))

    def test_blocked_model_launch_uses_current_official_documentation(self):
        calls = []
        def handler(request):
            calls.append(str(request.url))
            return httpx.Response(200, content=CHANGELOG) if str(request.url) == OPENAI_CHANGELOG else httpx.Response(403)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            stories, audit = verify_selected([self.story()], self.settings, client, NOW)
        self.assertEqual(len(stories), 1)
        self.assertEqual(calls, [LAUNCH, OPENAI_CHANGELOG])
        self.assertEqual(stories[0].verified_url, LAUNCH)
        self.assertIn("GPT-6.2 Astra", stories[0].summary)
        self.assertIn("GPT-6.2 Sol", stories[0].summary)
        self.assertNotIn("unlimited", stories[0].summary)
        record = audit["stories"][0]
        self.assertEqual(record["evidence_method"], "dated_official_api_changelog")
        self.assertEqual(record["evidence_url"], OPENAI_CHANGELOG)
        for quote in record["evidence_quotes"]:
            self.assertIn(quote, " ".join(changelog_entries(CHANGELOG)[0][1]))

    def test_documentation_must_match_the_model_and_publication_date(self):
        for story in (self.story("Introducing GPT-6.3 Astra and Sol"),
                      replace(self.story(), article=replace(self.story().article, published_at=datetime(2026, 10, 1, tzinfo=timezone.utc)))):
            def handler(request):
                return httpx.Response(200, content=CHANGELOG) if str(request.url) == OPENAI_CHANGELOG else httpx.Response(403)
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                stories, audit = verify_selected([story], self.settings, client, NOW)
            self.assertFalse(stories)
            self.assertEqual(audit["stories"][0]["code"], "matching_official_documentation_missing")

    def test_documentation_for_one_variant_cannot_confirm_a_two_model_release(self):
        raw = CHANGELOG.replace(b", or [GPT-6.2 Sol](https://developers.openai.com/api/docs/models/gpt-6.2-sol) for everyday coding and agent workflows", b"")
        def handler(request):
            return httpx.Response(200, content=raw) if str(request.url) == OPENAI_CHANGELOG else httpx.Response(403)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            stories, _ = verify_selected([self.story()], self.settings, client, NOW)
        self.assertFalse(stories)

    def test_explicit_primary_link_with_different_editorial_headline_is_accepted(self):
        url = "https://blog.google/innovation-and-ai/products/gemini-app/tasks-in-gemini-free-new-features"
        story = self.story("Google expands access to Gemini Tasks, which can help with calls, purchases",
                           "https://techcrunch.com/google-tasks", source_id="techcrunch-ai", tier="reporting",
                           company="google", reference_urls=(url,))
        raw = page("Put Gemini to work for you",
                   "Gemini Tasks can help with calls and purchases while you focus on other work.")
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=raw))) as client:
            stories, audit = verify_selected([story], self.settings, client, NOW)
        self.assertEqual(len(stories), 1)
        self.assertEqual(audit["stories"][0]["topic_match"], "explicit_link_and_body")

    def test_body_mentions_cannot_override_conflicting_model_identity(self):
        url = "https://blog.google/gemini-4-carbon-launch"
        story = self.story("Google releases Gemini 4 Carbon", url, source_id="google-ai", company="google")
        for title in ("Gemini 4 Argon is now available", "Gemini 5 Carbon is now available"):
            raw = page(title, "Gemini 4 Carbon was the previous model before this important new launch.")
            with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=raw))) as client:
                stories, _ = verify_selected([story], self.settings, client, NOW)
            self.assertFalse(stories)

    def test_new_model_variant_names_cannot_bypass_linked_body_checks(self):
        url = "https://blog.google/gemini-4-oxygen-launch"
        story = self.story("Google releases Gemini 4 Oxygen", "https://techcrunch.com/google-model",
                           source_id="techcrunch-ai", tier="reporting", company="google", reference_urls=(url,))
        raw = page("Gemini 4 Chlorine is now available",
                   "Gemini 4 Oxygen was the previous model before this new launch.")
        with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=raw))) as client:
            stories, audit = verify_selected([story], self.settings, client, NOW)
        self.assertFalse(stories)
        self.assertEqual(audit["stories"][0]["code"], "primary_topic_mismatch")

    def test_one_redirect_loop_cannot_use_every_other_storys_budget(self):
        first = self.story("Google introduces a new Gemini model", "https://blog.google/loop", source_id="google-ai", company="google")
        second = self.story("NVIDIA Announces CEO Transition", "https://nvidianews.nvidia.com/news/ceo-transition", source_id="nvidia-newsroom", company="nvidia")
        def handler(request):
            if request.url.host == "blog.google":
                return httpx.Response(302, headers={"location": str(request.url) + "x"})
            return httpx.Response(200, content=page(second.article.title,
                "NVIDIA appointed its chief financial officer as interim chief executive while the board searches for a permanent successor."))
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            stories, audit = verify_selected([first, second], replace(self.settings, verification_max_requests=4), client, NOW)
        self.assertEqual([s.article.id for s in stories], [second.article.id])
        self.assertEqual(audit["http_requests"], 4)
        self.assertEqual(audit["withheld_codes"], {"story_verification_budget_exhausted": 1})

    def test_summary_chooses_substance_instead_of_a_trivial_definition(self):
        story = self.story("Muse launches a personal AI agent", company="meta")
        summary, _, _ = current_excerpt(story, ["Muse is a personal AI agent.",
            "Muse can coordinate appointments and complete household errands with user approval before each purchase."])
        self.assertIn("user approval", summary)
        self.assertNotEqual(summary, "Muse is a personal AI agent.")

    def test_newsroom_article_body_is_not_confused_with_related_story_cards(self):
        raw = b'''<h1>NVIDIA Announces CEO Transition</h1>
          <div class="article-body"><p>NVIDIA appointed its chief financial officer as interim chief executive while it searches for a permanent successor.</p></div>
          <article class="index-item"><h3>Unrelated GPU announcement</h3></article>'''
        title, blocks, _ = article_body(raw)
        self.assertEqual(title, "NVIDIA Announces CEO Transition")
        self.assertEqual(len(blocks), 1)
        self.assertIn("interim chief executive", blocks[0])

    def test_generic_eligible_subscriber_rollout_keeps_its_complete_scope(self):
        story = self.story("Genie 4 is now available", company="google")
        blocks = ["So today, we are rolling out a new Project Genie experience to eligible Google AI Ultra subscribers, making these worlds far more responsive, creative, and social."]
        summary, quotes, details = current_excerpt(story, blocks)
        self.assertIn("eligible Google AI Ultra subscribers", summary)
        self.assertTrue(details["access_conditions_retained"])
        self.assertIn(quotes[0], blocks[0])

    def test_earnings_revenue_is_not_mistaken_for_promotional_api_pricing(self):
        story = self.story("NVIDIA Announces Financial Results for Third Quarter Fiscal 2027", company="nvidia")
        summary, quotes, _ = current_excerpt(story, ["Revenue of $115.8 billion, up 103% from a year ago",
            "NVIDIA is a company that builds important AI infrastructure and computing platforms."])
        self.assertEqual(summary, "Revenue of $115.8 billion, up 103% from a year ago")
        self.assertEqual(quotes, [summary])

    def test_summary_selects_a_product_capability_over_an_empty_press_intro(self):
        story = self.story("Copilot at Microsoft Ignite: Expanding what is possible", company="microsoft")
        intro = "This morning, at Microsoft Ignite 2026, we shared how our vision for Copilot is becoming real for customers."
        fact = "Under the hood, Auto dynamically selects the right models and effort for the task, balancing quality, speed, and cost."
        summary, quotes, _ = current_excerpt(story, [intro, fact])
        self.assertEqual(summary, fact)
        self.assertEqual(quotes, [fact])

    def test_copilot_frontier_rollout_is_not_presented_as_general_availability(self):
        story = self.story("Copilot at Microsoft Ignite", company="microsoft")
        scope = "And Autopilot is beginning to roll out to Frontier customers today."
        summary, quotes, details = current_excerpt(story, [
            "Home and Office in Copilot are now generally available. " + scope,
            "Autopilot can manage recurring work and coordinate business tasks without waiting for a prompt."])
        self.assertIn("Frontier customers", summary)
        self.assertNotIn("generally available", summary)
        self.assertEqual(quotes, [scope])
        self.assertTrue(details["access_conditions_retained"])


if __name__ == "__main__":
    unittest.main()
