from dataclasses import replace
from datetime import datetime, timedelta, timezone
import io
import json
import logging
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import httpx

from init_daily.cli import main
from init_daily.collect import CollectionError, collect, enrich_missing, fetch_feed, parse_feed
from init_daily.config import Source, load_settings
from init_daily.formatting import discord_payload
from init_daily.history import GitHistory, History, HistoryError, publication_lock
from init_daily.models import Article, Story, canonical_url, is_research, same_story, trusted_url
from init_daily.pipeline import run_pipeline
from init_daily.processing import process, validate_response
from init_daily.publishing import PublishError, publish, validate_webhook
from init_daily.ranking import fallback, shortlist

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures"
NOW = datetime(2026, 11, 11, 1, 15, tzinfo=timezone.utc)
WEBHOOK = "https://discord.com/api/webhooks/123456789/fake-test-token"


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = replace(load_settings(FIXTURE / "config.toml"),
                                output_dir=self.root / "output", history_path=self.root / "history.json",
                                retries=0)
        self.articles = []
        for source in self.settings.sources:
            self.articles += parse_feed((FIXTURE / f"{source.id}.xml").read_bytes(), source, NOW, self.settings)

    def client(self, handler):
        client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
        self.addCleanup(client.close)
        return client

    def network(self, request):
        if request.method == "GET":
            for source in self.settings.sources:
                if str(request.url) == source.url:
                    return httpx.Response(200, content=(FIXTURE / f"{source.id}.xml").read_bytes())
        self.fail(f"Unexpected mocked request to {request.url.host}")

    def stories(self):
        return fallback(shortlist(self.articles, [], self.settings, NOW), self.settings, NOW)

    def ai_response(self):
        return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
            "stories": [{"id": s.article.id, "summary_id": "s0",
                         "why": "Consider testing the approach in a small project before using it in a larger workflow."}
                        for s in self.stories()]})}}], "usage": {"total_tokens": 123}}

    def test_offline_entire_pipeline_never_calls_network_or_modifies_history(self):
        def denied(request):
            self.fail("Offline demo made a network request")
        history = History(self.settings.history_path)
        report = run_pipeline(self.settings, history, self.client(denied), NOW,
                              fixture=FIXTURE, api_key="MUST-NOT-BE-USED", webhook=WEBHOOK)
        self.assertEqual(report["status"], "preview")
        self.assertEqual(report["stories"], 5)
        self.assertFalse(self.settings.history_path.exists())
        payload = json.loads((self.settings.output_dir / "discord.json").read_text())
        self.assertIn("SYNTHETIC", payload["content"])
        self.assertEqual(payload["allowed_mentions"], {"parse": []})

    def test_live_dry_run_collects_and_does_not_post(self):
        report = run_pipeline(self.settings, History(self.settings.history_path),
                              self.client(self.network), NOW)
        self.assertEqual(report["status"], "preview")
        self.assertFalse(self.settings.history_path.exists())

    def test_publish_reserves_before_http_and_marks_sent(self):
        history = History(self.settings.history_path)
        posts = []
        def handler(request):
            if request.method == "GET":
                return self.network(request)
            posts.append(request)
            disk = History(self.settings.history_path)
            self.assertEqual(len(disk.pending), 1)
            self.assertEqual(request.url.params["wait"], "true")
            return httpx.Response(200, json={"id": "987654321"})
        client = self.client(handler)
        report = run_pipeline(self.settings, history, client, NOW, send=True, webhook=WEBHOOK)
        self.assertEqual(report["status"], "published")
        loaded = History(self.settings.history_path)
        self.assertTrue(loaded.sent_on("2026-11-11"))
        again = run_pipeline(self.settings, loaded, client, NOW, send=True, webhook=WEBHOOK)
        self.assertEqual(again["status"], "already_published")
        self.assertEqual(len(posts), 1)

    def test_timeout_keeps_pending_and_blocks_next_day(self):
        def handler(request):
            if request.method == "GET":
                return self.network(request)
            raise httpx.ReadTimeout("secret-token must never be logged", request=request)
        client = self.client(handler)
        with self.assertRaises(PublishError):
            run_pipeline(self.settings, History(self.settings.history_path), client, NOW,
                         send=True, webhook=WEBHOOK)
        loaded = History(self.settings.history_path)
        self.assertEqual(len(loaded.pending), 1)
        with self.assertRaises(HistoryError):
            run_pipeline(self.settings, loaded, client, NOW + timedelta(days=1), send=True, webhook=WEBHOOK)

    def test_failed_reservation_never_posts(self):
        history = History(self.settings.history_path)
        with patch.object(history, "save", side_effect=HistoryError("Disk unavailable")):
            with self.assertRaises(HistoryError):
                run_pipeline(self.settings, history, self.client(self.network), NOW, send=True, webhook=WEBHOOK)

    def test_sparse_news_skips_without_paying_or_publishing(self):
        settings = replace(self.settings, sources=self.settings.sources[:1])
        report = run_pipeline(settings, History(settings.history_path), self.client(self.network), NOW,
                              api_key="not-used", send=True, webhook=WEBHOOK)
        self.assertEqual(report["status"], "insufficient_news")
        self.assertFalse(settings.history_path.exists())
        self.assertIsNone(json.loads((settings.output_dir / "discord.json").read_text()))

    def test_successful_ai_uses_official_interface_and_one_request(self):
        calls = []
        def handler(request):
            calls.append(request)
            self.assertEqual(str(request.url), "https://api.deepseek.com/chat/completions")
            body = json.loads(request.content)
            self.assertEqual(body["thinking"], {"type": "disabled"})
            self.assertEqual(body["response_format"], {"type": "json_object"})
            records = json.loads(body["messages"][1]["content"])["records"]
            self.assertLessEqual(len(records), 20)
            self.assertIn("s0", records[0]["summary_options"])
            return httpx.Response(200, json=self.ai_response())
        stories, report = process(self.client(handler), self.articles, self.settings, NOW, "fake-test-key")
        self.assertEqual(report["mode"], "deepseek")
        self.assertEqual(report["usage"]["total_tokens"], 123)
        self.assertTrue(all(s.summary in s.article.excerpt for s in stories))
        self.assertEqual(len(calls), 1)

    def test_ai_unknown_ids_fabricated_summaries_duplicates_and_truncation_fall_back(self):
        for problem in ("id", "summary", "summary_id", "duplicate", "truncated", "json"):
            with self.subTest(problem=problem):
                body = self.ai_response()
                content = json.loads(body["choices"][0]["message"]["content"])
                if problem == "id":
                    content["stories"][0]["id"] = "invented"
                elif problem == "summary":
                    content["stories"][0].pop("summary_id")
                    content["stories"][0]["summary"] = "This model definitely outperforms every existing model at an invented task."
                elif problem == "summary_id":
                    content["stories"][0]["summary_id"] = "invented"
                elif problem == "duplicate":
                    content["stories"][1] = content["stories"][0]
                elif problem == "truncated":
                    body["choices"][0]["finish_reason"] = "length"
                body["choices"][0]["message"]["content"] = "bad-json" if problem == "json" else json.dumps(content)
                stories, report = process(self.client(lambda r: httpx.Response(200, json=body)),
                                          self.articles, self.settings, NOW, "fake")
                self.assertEqual(report["mode"], "fallback")
                self.assertEqual(len(stories), 5)

    def test_api_failure_falls_back_without_leaking_key(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logging.getLogger().addHandler(handler)
        self.addCleanup(logging.getLogger().removeHandler, handler)
        stories, report = process(self.client(lambda r: httpx.Response(401, text="fake-secret-key")),
                                  self.articles, self.settings, NOW, "fake-secret-key")
        self.assertEqual(report["mode"], "fallback")
        self.assertEqual(len(stories), 5)
        self.assertNotIn("fake-secret-key", stream.getvalue())

    def test_no_api_key_never_calls_model(self):
        stories, report = process(self.client(lambda r: self.fail("Unexpected API call")),
                                  self.articles, self.settings, NOW, None)
        self.assertEqual(report["reason"], "no_api_key")
        self.assertEqual(len(stories), 5)

    def test_rss_atom_and_permalink_guid_are_supported(self):
        self.assertEqual(len(self.articles), 5)
        self.assertTrue(any(a.url.endswith("training-dataset") for a in self.articles))

    def test_undated_stale_future_and_untrusted_entries_are_rejected(self):
        body = (FIXTURE / "demo-robotics.xml").read_text(encoding="utf-8")
        source = self.settings.sources[2]
        for modified in (body.replace("Tue, 10 Nov 2026 16:00:00 GMT", ""),
                         body.replace("10 Nov", "01 Nov"), body.replace("10 Nov", "20 Nov"),
                         body.replace("https://example.com/demo", "https://evil.example/demo")):
            self.assertEqual(parse_feed(modified.encode(), source, NOW, self.settings), [])

    def test_invalid_feed_and_entities_fail(self):
        for body in (b"<html>not a feed</html>", b"<!DOCTYPE rss><rss/>"):
            with self.assertRaises(CollectionError):
                parse_feed(body, self.settings.sources[0], NOW, self.settings)

    def test_harmless_doctype_in_cdata_does_not_break_feed(self):
        body = (FIXTURE / "demo-robotics.xml").read_text(encoding="utf-8")
        body = body.replace("<description>", "<description><![CDATA[<!DOCTYPE html>").replace("</description>", "]]></description>")
        items = parse_feed(body.encode(), self.settings.sources[2], NOW, self.settings)
        self.assertEqual(len(items), 1)

    def test_title_only_huggingface_adapter_uses_bounded_official_endpoints(self):
        source = Source("huggingface", "Hugging Face", "https://huggingface.co/blog/feed.xml",
                        ("huggingface.co",), excerpt_adapter="huggingface_markdown")
        articles = [replace(self.articles[0], url=f"https://huggingface.co/blog/demo-{i}", excerpt="") for i in range(6)]
        calls = []
        def handler(request):
            calls.append(request)
            self.assertEqual(request.url.host, "raw.githubusercontent.com")
            self.assertTrue(request.url.path.startswith("/huggingface/blog/main/demo-"))
            return httpx.Response(200, text="---\ntitle: DEMO\nauthors: []\n---\n# Demo\n\n"
                                  "This source describes an open developer tool for testing models and inspecting evaluation results.\n"
                                  "```python\nsecret_code()\n```\n")
        enriched = enrich_missing(self.client(handler), articles, source, self.settings)
        self.assertEqual(len(calls), 4)
        self.assertEqual(len(enriched), 4)
        self.assertTrue(all("secret_code" not in a.excerpt and "authors" not in a.excerpt for a in enriched))

    def test_arxiv_replacements_excluded_and_abstract_metadata_removed(self):
        body = (FIXTURE / "demo-robotics.xml").read_text(encoding="utf-8")
        source = replace(self.settings.sources[2], id="arxiv-robotics")
        for kind, count in (("replace", 0), ("replace-cross", 0), ("new", 1)):
            marked = body.replace("<description>", f"<description>arXiv:2611.12345 Announce Type: {kind} Abstract: ")
            items = parse_feed(marked.encode(), source, NOW, self.settings)
            self.assertEqual(len(items), count)
            if items:
                self.assertTrue(items[0].excerpt.startswith("This synthetic"))

    def test_research_cap_applies_across_feeds_and_ai_output(self):
        research = [replace(self.articles[0], source_id=f"arxiv-{i}", category="research",
                            url=f"https://arxiv.org/abs/2611.1234{i}", title=f"Research example {i}") for i in range(3)]
        selected = fallback(research + self.articles, self.settings, NOW)
        self.assertLessEqual(sum(is_research(s.article) for s in selected), 2)
        self.assertEqual(sum(is_research(s.article) for s in fallback(research, self.settings, NOW)), 2)
        content = json.dumps({"stories": [{"id": a.id, "summary": a.excerpt[:150],
            "why": "Consider testing the approach in a small project before using it in a larger workflow."}
            for a in research]})
        with self.assertRaises(ValueError):
            validate_response(content, research, self.settings, NOW)

    def test_feed_failure_isolated_and_total_failure_reported(self):
        def partial(request):
            if str(request.url) == self.settings.sources[0].url:
                return httpx.Response(503)
            return self.network(request)
        articles, report = collect(self.client(partial), self.settings, NOW)
        self.assertEqual(len(articles), 3)
        self.assertEqual(report["demo-models"]["status"], "failed")
        with self.assertRaises(CollectionError):
            collect(self.client(lambda r: httpx.Response(503)), self.settings, NOW)

    def test_feed_size_limit_and_untrusted_redirect(self):
        small = replace(self.settings, max_feed_bytes=10)
        with self.assertRaises(CollectionError):
            fetch_feed(self.client(self.network), self.settings.sources[0], small)
        client = self.client(lambda r: httpx.Response(302, headers={"location": "https://evil.example/feed"}))
        with self.assertRaises(CollectionError):
            fetch_feed(client, self.settings.sources[0], self.settings)

    def test_url_title_and_published_history_dedup(self):
        first = self.articles[0]
        duplicate = replace(first, url=first.url + "?utm_source=another#fragment")
        near = replace(first, title=first.title + "!", url=first.url + "/other")
        candidates = shortlist([first, duplicate, near], [], self.settings, NOW)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(shortlist(self.articles, [a.record() for a in self.articles], self.settings, NOW), [])
        self.assertFalse(same_story("Introducing Model 1.0 for developers", "Introducing Model 2.0 for developers"))

    def test_history_corruption_fails_closed(self):
        for value in ("{broken", '{"version":99,"publications":[]}', '{"version":1,"publications":[{}]}'):
            self.settings.history_path.write_text(value)
            with self.assertRaises(HistoryError):
                History(self.settings.history_path)

    def test_explicit_resolution_preserves_or_releases_story_dedup(self):
        history = History(self.settings.history_path)
        publication_id = history.reserve("2026-11-11", self.stories(), {})
        history.resolve(publication_id, "released")
        self.assertEqual(history.previous_stories(), [])
        publication_id = history.reserve("2026-11-11", self.stories(), {})
        history.resolve(publication_id, "sent", "123456789")
        self.assertEqual(len(history.previous_stories()), 5)

    def test_lock_excludes_concurrent_publishers(self):
        path = self.root / "publication.lock"
        with publication_lock(path):
            with self.assertRaises(HistoryError):
                with publication_lock(path):
                    self.fail("Two publishers acquired the lock")
        self.assertFalse(path.exists())

    def test_discord_safety_limits_and_markdown_escape(self):
        stories = [replace(s, summary="@everyone **hello** <@123> https://evil.example") for s in self.stories()]
        payload = discord_payload(stories, "2026-11-11", NOW, "fallback")
        self.assertEqual(len(payload["embeds"]), 5)
        self.assertEqual(payload["flags"], 4096)
        self.assertNotIn("@", payload["embeds"][0]["description"])
        self.assertNotIn("https://evil", json.dumps(payload))
        self.assertIn("\\*", payload["embeds"][0]["description"])

    def test_discord_retries_only_explicit_rate_limit(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(429, json={"retry_after": 0}) if len(calls) == 1 else httpx.Response(200, json={"id": "123"})
        self.assertEqual(publish(self.client(handler), WEBHOOK, {}), "123")
        self.assertEqual(len(calls), 2)
        calls.clear()
        def ambiguous(request):
            calls.append(request)
            return httpx.Response(502)
        with self.assertRaises(PublishError):
            publish(self.client(ambiguous), WEBHOOK, {})
        self.assertEqual(len(calls), 1)

    def test_webhook_redirects_or_missing_confirmation_fail(self):
        for response in (httpx.Response(302, headers={"location": "https://evil.example"}),
                         httpx.Response(204), httpx.Response(200, json={})):
            with self.assertRaises(PublishError):
                publish(self.client(lambda r: response), WEBHOOK, {})
        for url in ("http://discord.com/api/webhooks/1/token", WEBHOOK + "?wait=false", "https://evil.example/api/webhooks/1/token"):
            with self.assertRaises(PublishError):
                validate_webhook(url)

    def test_publish_needs_both_gates_and_fixture_always_rejected(self):
        with patch.dict(os.environ, {"INIT_DAILY_PUBLISH_ENABLED": "false"}):
            self.assertEqual(main(["--publish"]), 1)
        with patch.dict(os.environ, {"INIT_DAILY_PUBLISH_ENABLED": "true"}):
            self.assertEqual(main(["--fixture", str(FIXTURE), "--publish"]), 1)

    def test_config_source_can_be_disabled(self):
        path = self.root / "config.toml"
        text = (FIXTURE / "config.toml").read_text()
        path.write_text(text.replace('id = "demo-models"', 'enabled = false\nid = "demo-models"'))
        self.assertEqual(len(load_settings(path).sources), 2)


class URLTests(unittest.TestCase):
    def test_public_https_and_host_validation(self):
        for url in ("http://openai.com/x", "https://openai.com.evil.example/x", "https://user:pass@openai.com/x",
                    "https://127.0.0.1/x", "https://openai.com:444/x", "javascript:alert(1)", "https://openai.com/x\n"):
            self.assertFalse(trusted_url(url, ("openai.com", "127.0.0.1")), url)
        self.assertTrue(trusted_url("https://openai.com/x", ("openai.com",)))

    def test_arxiv_versions_and_tracking_urls_canonicalized(self):
        self.assertEqual(canonical_url("https://export.arxiv.org/pdf/2601.12345v2.pdf"),
                         "https://arxiv.org/abs/2601.12345")
        self.assertEqual(canonical_url("https://openai.com/x/?utm_source=test&b=2&a=1#frag"),
                         "https://openai.com/x?a=1&b=2")


class GitHistoryTests(unittest.TestCase):
    def test_remote_ledger_survives_runs_and_non_force_push_excludes_race(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            remote, repo = root / "remote.git", root / "checkout"
            def git(*args, cwd=None):
                result = subprocess.run(["git", *map(str, args)], cwd=cwd, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout.strip()
            git("init", "--bare", remote)
            git("init", "-b", "main", repo)
            git("config", "user.name", "Test", cwd=repo)
            git("config", "user.email", "test@example.com", cwd=repo)
            (repo / "website.txt").write_text("DO NOT CHANGE\n")
            git("add", "website.txt", cwd=repo)
            git("commit", "-m", "website", cwd=repo)
            git("remote", "add", "origin", remote, cwd=repo)
            git("push", "origin", "main", cwd=repo)
            original_head = git("rev-parse", "HEAD", cwd=repo)
            first, racing = GitHistory(repo), GitHistory(repo)
            article = Article("A test model release for builders", "https://example.com/test-model",
                              "A source excerpt used only in the local history persistence test.",
                              NOW, "test-source", "Test source", 1.0)
            story = Story(article, article.excerpt, "Inspect the model before trying it.", "models", "fallback")
            publication_id = first.reserve("2026-11-11", [story], {"content": "test"})
            with self.assertRaises(HistoryError):
                racing.reserve("2026-11-11", [], {"content": "racing publisher"})
            # GitHub-hosted runners start from fresh checkouts, without local state.
            next_runner = root / "next-runner"
            git("clone", "--branch", "main", remote, next_runner)
            fresh = GitHistory(next_runner)
            self.assertEqual(fresh.pending[0]["id"], publication_id)
            self.assertEqual(fresh.previous_stories()[0]["id"], article.id)
            fresh.resolve(publication_id, "sent", "123456789")
            third_runner = root / "third-runner"
            git("clone", "--branch", "main", remote, third_runner)
            confirmed = GitHistory(third_runner)
            self.assertTrue(confirmed.sent_on("2026-11-11"))
            settings = load_settings(FIXTURE / "config.toml")
            self.assertEqual(shortlist([article], confirmed.previous_stories(), settings, NOW), [])
            with self.assertRaises(HistoryError):
                confirmed.reserve("2026-11-11", [story], {"content": "duplicate"})
            self.assertEqual(git("rev-parse", "HEAD", cwd=repo), original_head)
            self.assertEqual(git("status", "--porcelain", cwd=repo), "")
            self.assertEqual(git("status", "--porcelain", cwd=next_runner), "")
            self.assertEqual(git("status", "--porcelain", cwd=third_runner), "")
            GitHistory(repo) # Refresh the local history ref after another runner's update.
            self.assertEqual(git("ls-tree", "--name-only", "refs/init-daily/state", cwd=repo), "history.json")


if __name__ == "__main__":
    unittest.main()
