"""Transport contract tests use only a loopback fake service, never providers."""
import base64
import copy
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from unittest.mock import patch
import tempfile
import threading
import unittest

from decision_lab import api_lab as al, collection as c, ledger, typed_values as tv
from decision_lab.live import TransportResponse


class FakeClient:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def post_json(self, endpoint, headers, body):
        self.calls.append((endpoint, headers, body))
        value = next(self.replies)
        if isinstance(value, BaseException):
            raise value
        return TransportResponse(value[0], value[1], 0)


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "run"
        self.manifest = al.prepare_payload(al.load_suite(), al.load_suite().rows[:1], route="decisions")
        self.plan = c.api_plan(self.manifest)
        self.options = dict(allow_network=True, max_calls=3, max_questions=10,
                            max_estimated_tokens=100000, credential="synthetic-test-key", retry_delay_s=0)

    def collect(self, replies, **options):
        return c.collect(self.plan, self.directory, client=FakeClient(replies), **(self.options | options))

    def test_offline_gate_before_credentials_or_transport(self):
        client = FakeClient([])
        with self.assertRaisesRegex(al.ApiLabError, "allow-network"):
            c.collect(self.plan, self.directory, client=client, **(self.options | {"allow_network": False}))
        self.assertEqual(client.calls, [])
        self.assertFalse(self.directory.exists())

    def test_budget_preflight_and_manifest_tamper(self):
        with self.assertRaisesRegex(al.ApiLabError, "exceeds budget"):
            self.collect([], max_estimated_tokens=1)
        self.plan["requests"][0]["body"]["model"] = "changed"
        with self.assertRaises(al.ApiLabError):
            self.collect([])

    def test_typed_duplicate_logical_slots_rejected_before_send(self):
        suite = tv.load_suite()
        self.plan = c.typed_plan(suite, suite.cases[:1], replicates=2)
        self.plan["requests"][1]["trial"]["replicate"] = 0
        with self.assertRaisesRegex(al.ApiLabError, "duplicate planned logical"):
            self.collect([], account_id="a"*32)

    def test_malformed_raw_bytes_and_failed_elapsed_retained(self):
        data = self.collect([(200, b"not json\xff")])
        a = data["attempts"][0]
        self.assertEqual(base64.b64decode(a["raw_body_base64"]), b"not json\xff")
        self.assertEqual(a["parse_status"], "malformed")
        self.assertGreaterEqual(a["elapsed_ms"], 0)
        view = ledger.from_collection(data)
        self.assertEqual(view["trials"][0]["outcome"], "error")
        self.assertIsNone(view["requests"][0]["cost"])

    def test_timeout_uncertain_and_resume_skip(self):
        data = self.collect([TimeoutError("test")], max_attempts=2)
        self.assertEqual(data["attempts"][0]["delivery"], "uncertain")
        self.assertIsNotNone(data["attempts"][0]["elapsed_ms"])
        resumed = self.collect([], resume=True, max_attempts=2)
        self.assertEqual(len(resumed["attempts"]), 1)
        resumed = self.collect([(200, b'{}')], resume=True, retry_uncertain=True, max_attempts=2)
        self.assertEqual(len(resumed["attempts"]), 2)
        self.assertEqual(resumed["attempts"][1]["retry_reason"], "uncertain_explicit")

    def test_429_retry_counted_once_each_and_budget_exhaustion(self):
        data = self.collect([(429, b'{"error":"busy"}'), (200, b'{}')], max_attempts=2)
        self.assertEqual(len(data["attempts"]), 2)
        self.assertEqual(data["attempts"][1]["retry_reason"], "http_429")
        self.assertEqual(len(ledger.from_collection(data)["requests"]), 1)

    def test_attempt_budget_stops_retry(self):
        data = self.collect([(429, b'{}')], max_attempts=2, max_calls=1)
        self.assertEqual(data["state"], "budget_exhausted")
        self.assertEqual(len(data["attempts"]), 1)

    def test_cancel_checkpoint_no_sends(self):
        data = self.collect([], cancel=lambda: True)
        self.assertEqual(data["state"], "cancelled")
        self.assertEqual(ledger.from_collection(data)["trials"][0]["outcome"], "missing")

    def test_keyboard_cancel_is_uncertain(self):
        data = self.collect([KeyboardInterrupt()])
        self.assertEqual(data["state"], "cancelled")
        self.assertEqual(data["attempts"][0]["delivery"], "uncertain")

    def test_success_resume_does_not_resend_and_tamper_rejected(self):
        data = self.collect([(200, b'{}')])
        self.assertEqual(len(self.collect([], resume=True)["attempts"]), 1)
        data["attempts"][0]["parsed"] = {"changed": True}
        al._write(self.directory / "collection.json", data)
        with self.assertRaisesRegex(al.ApiLabError, "evidence changed"):
            c.load_collection(self.directory)

    def test_lock_prevents_parallel_writer(self):
        self.collect([(200, b'{}')])
        (self.directory / ".collector.lock").write_text("test")
        with self.assertRaisesRegex(al.ApiLabError, "lock exists"):
            self.collect([], resume=True)

    def test_resume_reads_checkpoint_under_lock(self):
        self.collect([(200, b'{}')])
        original = c.load_collection
        def checked(path):
            self.assertTrue((self.directory / ".collector.lock").exists())
            return original(path)
        with patch.object(c, "load_collection", side_effect=checked):
            self.collect([], resume=True)

    def test_duplicate_json_is_parse_failure_with_raw_preserved(self):
        data = self.collect([(200, b'{"answers":[],"answers":[]}')])
        self.assertEqual(data["attempts"][0]["state"], "parse_error")

    def test_request_cost_counts_all_known_attempts(self):
        data = self.collect([(429, b'{"cost":{"amount":1,"currency":"USD"}}'),
                             (200, b'{"cost":{"amount":2,"currency":"USD"}}')], max_attempts=2)
        self.assertEqual(ledger.from_collection(data)["requests"][0]["cost"], {"amount": 3, "currency": "USD"})

    def test_partial_answers_preserve_question_failure(self):
        suite = al.load_suite()
        row = next(r for r in suite.rows if len(r["questions"]) > 1)
        self.manifest = al.prepare_payload(suite, [row], route="decisions")
        self.plan = c.api_plan(self.manifest)
        qid = row["questions"][0]["id"]
        response = {"model": "fake", "answers": [{"name": qid, "type": "predicate",
                    "probability": float(row["rubric"]["questions"][qid]["expected"])}]}
        data = self.collect([(200, json.dumps(response).encode())])
        outcomes = [t["outcome"] for t in ledger.from_collection(data)["trials"]]
        self.assertIn("ok", outcomes)
        self.assertIn("error", outcomes)

    def test_clairic_plan_and_null_are_not_guessed(self):
        suite = tv.load_suite()
        case = suite.cases[0]
        self.plan = c.typed_plan(suite, [case])
        native = {"model": "clairic", "truncated": False, "usage": {"input_tokens": 5, "output_tokens": 5},
                  "answers": {name: {"type": field["type"], "value": None,
                  "guess": "not adopted", "confidence": .99} for name, field in case.fields.items()}}
        data = self.collect([(200, json.dumps({"result": native, "success": True}).encode())], account_id="a"*32)
        view = ledger.from_collection(data)
        self.assertEqual(len(view["trials"]), len(case.fields))
        self.assertTrue(all(t["outcome"] == "ok" for t in view["trials"]))
        self.assertTrue(all(t.get("value") is None for t in view["trials"]))

    def test_clairic_estimate_retains_native_value_without_binary_label(self):
        suite = tv.load_suite()
        case = next(c for c in suite.cases if c.experiment_id == "estimate-intervals")
        self.plan = c.typed_plan(suite, [case])
        native = {"model": "clairic", "truncated": False, "usage": {"input_tokens": 5, "output_tokens": 1},
                  "answers": {"completion_days": {"type": "estimate", "value": 5,
                              "median": 5, "p10": 2, "p90": 8}}}
        data = self.collect([(200, json.dumps({"result": native, "success": True}).encode())], account_id="a"*32)
        trial = ledger.from_collection(data)["trials"][0]
        self.assertEqual(trial["outcome"], "ok")
        self.assertEqual(trial["value"], 5)
        self.assertIsNone(trial["correct"])
        self.assertIsNone(trial["loss"])
        self.assertEqual(trial["interval_evaluation"]["estimate"]["p90"], 8)

    def test_loopback_fake_service_receives_only_native_body(self):
        captured = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                captured.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"model":"fake","answers":[]}')
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        class LoopbackClient:
            def post_json(self, endpoint, headers, body):
                conn = http.client.HTTPConnection("127.0.0.1", server.server_port)
                try:
                    conn.request("POST", "/", json.dumps(body), {"Content-Type": "application/json"})
                    response = conn.getresponse()
                    return TransportResponse(response.status, response.read(), 0)
                finally:
                    conn.close()
        try:
            c.collect(self.plan, self.directory, client=LoopbackClient(), **self.options)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
        self.assertEqual(captured, [self.plan["requests"][0]["body"]])
        self.assertNotIn("rubric", captured[0])


if __name__ == "__main__":
    unittest.main()
