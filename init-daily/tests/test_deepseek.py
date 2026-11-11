"""Diagnostics must remain useful even when provider text contains a secret."""
from dataclasses import replace
from datetime import datetime, timezone
import io
import json
import logging
from pathlib import Path
import unittest

import httpx

from init_daily.config import load_settings
from init_daily.models import Article
from init_daily.processing import process, summary_options
from init_daily.ranking import RELEVANCE

NOW = datetime(2026, 11, 11, 1, 15, tzinfo=timezone.utc)
SENTINEL = "PRIVATE_TEST_SENTINEL_DO_NOT_PRINT"


class DeepSeekRegressionTests(unittest.TestCase):
    def setUp(self):
        self.settings = load_settings(Path(__file__).resolve().parents[1] / "fixtures/config.toml")
        self.articles = [Article(f"Model {i} release for developers", f"https://example.com/model-{i}",
            "A developer model release includes evaluation tools and downloadable materials. "
            "The source describes a research workflow for inspecting model behavior before deployment.",
            NOW, f"source-{i}", f"Source {i}", 1.0) for i in range(5)]
        self.stream = io.StringIO()
        handler = logging.StreamHandler(self.stream)
        logger = logging.getLogger("init_daily.processing")
        logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)
        self.calls = []

    def body(self):
        return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"stories": [
            {"id": a.id, "summary_id": "s0", "why": "Consider testing the evaluation workflow in a small project."}
            for a in self.articles]})}}], "usage": {"prompt_tokens": 1234, "completion_tokens": 400, "total_tokens": 1634}}

    def run_response(self, response, settings=None):
        def handler(request):
            self.calls.append(request)
            if isinstance(response, Exception):
                raise response
            return response
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = process(client, self.articles, settings or self.settings, NOW, SENTINEL)
        # Check report/log output, never print the sentinel or raw model data.
        self.assertNotIn(SENTINEL, json.dumps(result[1]) + self.stream.getvalue())
        return result

    def mutate(self, change):
        body = self.body()
        content = json.loads(body["choices"][0]["message"]["content"])
        change(content)
        body["choices"][0]["message"]["content"] = json.dumps(content)
        return httpx.Response(200, json=body)

    def test_http_failures_are_distinct_actionable_and_single_attempt(self):
        for status, reason in [(400, "invalid_request"), (401, "authentication_error"),
                (402, "quota_error"), (403, "permission_error"), (404, "invalid_request"),
                (422, "invalid_request"), (429, "rate_limit_error"), (500, "api_error"), (503, "api_error")]:
            with self.subTest(status=status):
                before = len(self.calls)
                _, report = self.run_response(httpx.Response(status, json={"error": {
                    "message": SENTINEL, "code": SENTINEL, "type": SENTINEL, "param": SENTINEL}},
                    headers={"x-request-id": SENTINEL}))
                self.assertEqual(report["mode"], "fallback")
                self.assertEqual(report["reason"], reason)
                self.assertEqual(report["http_status"], status)
                self.assertEqual(report["diagnostics"]["code"], f"http_{status}")
                self.assertTrue(report["diagnostics"]["action"])
                self.assertEqual(len(self.calls) - before, 1)

    def test_non_json_error_body_still_reports_http_failure(self):
        _, report = self.run_response(httpx.Response(502, text=SENTINEL))
        self.assertEqual(report["reason"], "api_error")
        self.assertEqual(report["diagnostics"]["code"], "http_502")

    def test_allowlisted_api_codes_and_parameters_only(self):
        _, report = self.run_response(httpx.Response(422, json={"error": {
            "code": "invalid_request_error", "message": SENTINEL, "param": "temperature"}}))
        self.assertEqual(report["diagnostics"]["api_code"], "invalid_request_error")
        self.assertEqual(report["diagnostics"]["parameter"], "temperature")

    def test_api_error_in_success_envelope_is_not_a_schema_failure(self):
        _, report = self.run_response(httpx.Response(200, json={"error": {
            "code": "insufficient_quota", "message": SENTINEL}}))
        self.assertEqual(report["reason"], "quota_error")
        self.assertEqual(report["diagnostics"]["code"], "api_error_envelope")

    def test_http_status_takes_priority_over_generic_error_type(self):
        _, report = self.run_response(httpx.Response(402, json={"error": {
            "type": "invalid_request_error", "message": SENTINEL}}))
        self.assertEqual(report["reason"], "quota_error")

    def test_timeout_network_and_bad_header_have_separate_diagnostics(self):
        for error, reason in [(httpx.ReadTimeout(SENTINEL), "timeout"),
                              (httpx.ConnectError(SENTINEL), "network_error"),
                              (httpx.LocalProtocolError(SENTINEL), "network_error")]:
            with self.subTest(reason=reason):
                _, report = self.run_response(error)
                self.assertEqual(report["reason"], reason)
                self.assertNotIn("http_status", report)

    def test_non_json_success_and_wrong_completion_shapes_never_crash(self):
        for response in [httpx.Response(200, text=SENTINEL), *[httpx.Response(200, json=body) for body in (
                None, [], {}, {"choices": None}, {"choices": []}, {"choices": [None]},
                {"choices": [{"finish_reason": SENTINEL}]},
                {"choices": [{"finish_reason": "stop", "message": None}]},
                {"choices": [{"finish_reason": "stop", "message": {"content": []}}]})]]:
            with self.subTest():
                _, report = self.run_response(response)
                self.assertEqual(report["reason"], "malformed_response")

    def test_blank_json_mode_output_and_invalid_inner_json_are_distinct(self):
        for content, code in [("   \n", "empty_content"), (SENTINEL, "invalid_model_json")]:
            body = self.body()
            body["choices"][0]["message"]["content"] = content
            _, report = self.run_response(httpx.Response(200, json=body))
            self.assertEqual(report["diagnostics"]["code"], code)
            self.assertEqual(report["usage"]["total_tokens"], 1634)

    def test_truncation_and_filtered_or_aborted_output_are_not_validation_errors(self):
        for finish in ("length", "content_filter", "aborted", "insufficient_system_resource"):
            body = self.body()
            body["choices"][0]["finish_reason"] = finish
            _, report = self.run_response(httpx.Response(200, json=body))
            self.assertEqual(report["reason"], "incomplete_response")
            self.assertEqual(report["finish_reason"], finish)
            self.assertEqual(report["usage"]["total_tokens"], 1634)

    def test_invalid_inner_schemas_have_safe_codes(self):
        for content, code in [("null", "invalid_stories_schema"), ("[]", "invalid_stories_schema"),
                ('{"stories":{}}', "invalid_stories_schema"),
                ('{"stories":[null,null,null]}', "invalid_story_schema"),
                ('{"stories":[{"id":[]},{},{}]}', "invalid_story_schema")]:
            body = self.body()
            body["choices"][0]["message"]["content"] = content
            _, report = self.run_response(httpx.Response(200, json=body))
            self.assertEqual(report["reason"], "malformed_response")
            self.assertEqual(report["diagnostics"]["code"], code)

    def test_unknown_article_and_summary_ids_are_evidence_failures(self):
        for field, code in [("id", "unknown_article_id"), ("summary_id", "unknown_summary_id")]:
            response = self.mutate(lambda content: content["stories"][0].update({field: SENTINEL}))
            _, report = self.run_response(response)
            self.assertEqual(report["reason"], "evidence_validation_error")
            self.assertEqual(report["diagnostics"]["code"], code)
            self.assertEqual(report["diagnostics"]["item_index"], 0)

    def test_duplicate_selection_has_distinct_diagnostic(self):
        response = self.mutate(lambda c: c["stories"].__setitem__(1, c["stories"][0]))
        _, report = self.run_response(response)
        self.assertEqual(report["reason"], "selection_validation_error")
        self.assertEqual(report["diagnostics"]["code"], "duplicate_article")

    def test_server_inserts_option_text_even_if_model_also_sends_fabrication(self):
        response = self.mutate(lambda c: c["stories"][0].update(summary=SENTINEL))
        stories, report = self.run_response(response)
        self.assertEqual(report["mode"], "deepseek")
        self.assertEqual(stories[0].summary, summary_options(self.articles[0])["s0"])
        self.assertNotIn(SENTINEL, stories[0].summary)

    def test_legacy_summary_accepts_whitespace_only_changes_but_not_new_facts(self):
        def good(content):
            item = content["stories"][0]
            item.pop("summary_id")
            item["summary"] = self.articles[0].excerpt.replace(" ", "\n  ")
        stories, report = self.run_response(self.mutate(good))
        self.assertEqual(report["mode"], "deepseek")
        self.assertIn(stories[0].summary, self.articles[0].excerpt)
        def bad(content):
            item = content["stories"][0]
            item.pop("summary_id")
            item["summary"] = "A model release guarantees an invented performance improvement."
        _, report = self.run_response(self.mutate(bad))
        self.assertEqual(report["diagnostics"]["code"], "summary_not_in_source")

    def test_safe_long_quote_is_shortened_locally(self):
        self.articles[0] = replace(self.articles[0], excerpt=self.articles[0].excerpt * 3)
        def change(content):
            content["stories"][0].pop("summary_id")
            content["stories"][0]["summary"] = self.articles[0].excerpt
        stories, report = self.run_response(self.mutate(change))
        self.assertEqual(report["mode"], "deepseek")
        self.assertLessEqual(len(stories[0].summary), 320)

    def test_invalid_editorial_only_replaces_guidance_not_grounded_ai_selection(self):
        for why in (None, 123, "", "Try " + SENTINEL + " https://evil.example @everyone 999", "No action or evidence."):
            response = self.mutate(lambda c: c["stories"][0].update(why=why))
            stories, report = self.run_response(response)
            self.assertEqual(report["mode"], "deepseek")
            self.assertEqual(report["validation"]["editorial_replacements"], 1)
            self.assertIn(stories[0].why, RELEVANCE.values())

    def test_editorial_line_wrapping_is_not_rejected(self):
        response = self.mutate(lambda c: c["stories"][0].update(why="Explore this approach\n in a small prototype before adopting it."))
        _, report = self.run_response(response)
        self.assertEqual(report["mode"], "deepseek")
        self.assertEqual(report["validation"]["editorial_replacements"], 0)

    def test_usage_and_model_metadata_cannot_reflect_arbitrary_provider_text(self):
        body = self.body()
        body["usage"] = {"total_tokens": SENTINEL, "prompt_tokens": True, "completion_tokens": -3, "other": SENTINEL}
        body["model"] = SENTINEL
        _, report = self.run_response(httpx.Response(200, json=body), replace(self.settings, model=SENTINEL))
        self.assertEqual(report["model"], "custom")
        self.assertEqual(report["usage"], {})


if __name__ == "__main__":
    unittest.main()
