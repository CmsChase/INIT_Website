"""Corrections edit one existing message with write-ahead history protection."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from init_daily.correction import correct, payload_hash
from init_daily.history import History, HistoryError
from init_daily.models import Article, Story
from init_daily.publishing import PublishError

NOW = datetime(2026, 11, 22, 8, 40, tzinfo=timezone.utc)
WEBHOOK = "https://discord.com/api/webhooks/123456789/test-only-token"
MESSAGE = "987654321"


class CorrectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.history = History(self.root / "history.json")
        self.old = {"content": "INIT Daily 2026-11-22 old", "embeds": [{"title": "Old story"}],
                    "allowed_mentions": {"parse": []}, "flags": 4096}
        article = Article("Old story", "https://example.com/old", "An original source excerpt for an old story.",
                          NOW, "test", "Test", 1)
        ident = self.history.reserve("2026-11-22", [Story(article, article.excerpt, "Consider testing.", "tools", "fallback")], self.old)
        self.history.resolve(ident, "sent", MESSAGE)
        self.payload = {"content": "INIT Daily 2026-11-22 corrected", "embeds": [
            {"title": "First release", "url": "https://example.com/first"},
            {"title": "Second release", "url": "https://example.com/second"}],
            "allowed_mentions": {"parse": []}, "flags": 4096}
        self.report = {"date": "2026-11-22", "status": "preview", "fixture": False,
                       "publishing_requested": False, "stories": 2,
                       "verification": {"checked": 2, "shortfall": 0, "stories": [
                           {"status": "primary_body_checked", "article_id": "first", "discovery_url": "https://example.com/first",
                            "primary_url": "https://example.com/first", "primary_headline": "First release"},
                           {"status": "primary_body_checked", "article_id": "second", "discovery_url": "https://example.com/second",
                            "primary_url": "https://example.com/second", "primary_headline": "Second release"}]}}
        self.plan = {"date": "2026-11-22", "publication_id": ident, "message_id": MESSAGE,
                     "previous_payload_sha256": payload_hash(self.old), "source_run_id": "123", "source_commit": "abc"}
        self.write_preview()

    def write_preview(self):
        self.plan["files"] = {}
        for name, document in (("discord.json", self.payload), ("run.json", self.report)):
            raw = json.dumps(document).encode()
            (self.root / name).write_bytes(raw)
            self.plan["files"][name] = sha256(raw).hexdigest()

    def response(self, payload):
        return {**deepcopy(payload), "id": MESSAGE, "webhook_id": "123456789", "attachments": [],
                "mentions": [], "mention_roles": [], "mention_everyone": False}

    def run_correction(self, handler, **kwargs):
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            return correct(self.history, client, self.plan, self.root, NOW, webhook=WEBHOOK, **kwargs)

    def test_dry_run_has_no_network_or_history_writes(self):
        before = self.history.path.read_bytes()
        result = self.run_correction(lambda r: self.fail("Dry run made a request"))
        self.assertEqual(result["status"], "correction_ready")
        self.assertEqual(self.history.path.read_bytes(), before)

    def test_success_edits_same_message_and_keeps_old_and_new_deduplication(self):
        calls = []
        def handler(request):
            calls.append(request.method)
            self.assertEqual(str(request.url), WEBHOOK + "/messages/" + MESSAGE)
            if request.method == "GET":
                return httpx.Response(200, json=self.response(self.old))
            self.assertEqual(request.method, "PATCH")
            body = json.loads(request.content)
            self.assertEqual(body["allowed_mentions"], {"parse": []})
            self.assertNotIn("flags", body)
            self.assertNotIn("username", body)
            stored = History(self.history.path)
            self.assertEqual(len(stored.pending), 1)
            return httpx.Response(200, json=self.response(self.payload))
        result = self.run_correction(handler, apply=True)
        self.assertEqual(calls, ["GET", "PATCH"])
        self.assertEqual(result["status"], "corrected")
        stored = History(self.history.path)
        self.assertEqual(len(stored.data["publications"]), 1)
        self.assertEqual(stored.data["publications"][0]["message_id"], MESSAGE)
        self.assertTrue(stored.sent_on("2026-11-22"))
        self.assertEqual(len(stored.previous_stories()), 3)
        self.assertEqual(stored.data["publications"][0]["revisions"][0]["payload"], self.old)
        again = self.run_correction(lambda r: self.fail("Already applied correction made a request"), apply=True)
        self.assertEqual(again["status"], "already_corrected")

    def test_failed_reservation_never_edits(self):
        calls = []
        def handler(request):
            calls.append(request.method)
            return httpx.Response(200, json=self.response(self.old))
        with patch.object(self.history, "save", side_effect=HistoryError("State push failed")):
            with self.assertRaises(HistoryError):
                self.run_correction(handler, apply=True)
        self.assertEqual(calls, ["GET"])

    def test_uncertain_patch_stays_pending_and_is_not_retried(self):
        calls = []
        def handler(request):
            calls.append(request.method)
            if request.method == "GET":
                return httpx.Response(200, json=self.response(self.old))
            raise httpx.ReadTimeout("sensitive webhook request", request=request)
        with self.assertRaises(PublishError) as error:
            self.run_correction(handler, apply=True)
        self.assertNotIn("test-only-token", str(error.exception))
        self.assertEqual(calls, ["GET", "PATCH"])
        stored = History(self.history.path)
        self.assertEqual(len(stored.pending), 1)
        with self.assertRaises(HistoryError):
            stored.reserve("2026-11-22", [], {})

    def test_changed_live_message_is_not_overwritten(self):
        before = self.history.path.read_bytes()
        def handler(request):
            self.assertEqual(request.method, "GET")
            return httpx.Response(200, json=self.response({**self.old, "content": "Someone changed this"}))
        with self.assertRaisesRegex(HistoryError, "Live message changed"):
            self.run_correction(handler, apply=True)
        self.assertEqual(self.history.path.read_bytes(), before)

    def test_tampered_preview_and_expired_plan_are_rejected(self):
        (self.root / "discord.json").write_text("{}")
        with self.assertRaisesRegex(HistoryError, "checksum"):
            self.run_correction(lambda r: self.fail("Untrusted preview made a request"), apply=True)
        self.write_preview()
        with httpx.Client(transport=httpx.MockTransport(lambda r: self.fail("Expired plan made a request"))) as client:
            with self.assertRaisesRegex(HistoryError, "expired"):
                correct(self.history, client, self.plan, self.root, NOW + timedelta(days=1), apply=True, webhook=WEBHOOK)

    def test_unverified_preview_and_wrong_message_are_rejected(self):
        self.report["verification"]["shortfall"] = 1
        self.write_preview()
        with self.assertRaisesRegex(HistoryError, "fully verified"):
            self.run_correction(lambda r: self.fail("Unverified preview made a request"), apply=True)
        self.report["verification"]["shortfall"] = 0
        self.write_preview()
        self.plan["message_id"] = "111222333"
        with self.assertRaisesRegex(HistoryError, "exact stored"):
            self.run_correction(lambda r: self.fail("Wrong target made a request"), apply=True)


if __name__ == "__main__":
    unittest.main()
