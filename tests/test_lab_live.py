"""Live-collection safety tests using a MOCK client at the transport boundary.

No real credentials, no real network, no model inference. These tests
assert the guard rails: network switch, positive call limit, bounded
timeout, redirect refusal, no implicit retry/fallback, failure recorded
as a non-choice error with no invented cost, and that offline commands
make no network calls at all.
"""

from __future__ import annotations

import http.client
import unittest
from pathlib import Path

from decision_lab.cases import load_suite
from decision_lab.live import (
    HttpClient,
    LiveError,
    LivePlan,
    collect,
    plan_live,
)
from decision_lab.routes import OUTCOME_ERROR, OUTCOME_OK

REPO = Path(__file__).resolve().parent.parent
SUITE_PATH = REPO / "experiments" / "next-action" / "cases.json"


class _MockClient:
    """Records calls; returns scripted transport results."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def post_json(self, url, headers, body):
        self.calls.append({"url": url, "headers": dict(headers), "body": body})
        if not self.script:
            raise AssertionError("mock client called more times than scripted (retry?)")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _Resp:
    def __init__(self, status, body=b"{}", latency_ms=5.0):
        self.status = status
        self.body = body
        self.latency_ms = latency_ms


def _full_dist(selected, mass=0.6):
    from decision_lab.routes import OFFERED_OPTIONS
    others = [o for o in OFFERED_OPTIONS if o != selected]
    rest = (1.0 - mass) / len(others)
    d = {o: rest for o in others}
    d[selected] = mass
    return d


def _jev_body(choice, conf=0.5, usage=None):
    """Documented TypeSafe /v1/systemone response shape."""
    body = {
        "model": "jev-1.13.0",
        "answers": {
            "next_action": {
                "type": "choice",
                "choice": choice,
                "probabilities": _full_dist(choice),
                "confidence": conf,
            }
        },
    }
    if usage is not None:
        body["usage"] = usage
    return body


def _plan(**over) -> LivePlan:
    base = dict(
        route_key="jev",
        run_dir=Path("/tmp/does-not-matter"),
        max_calls=100,
        timeout_s=10.0,
        allow_network=True,
    )
    base.update(over)
    return plan_live(SUITE_PATH, **base)


class TestPreconditions(unittest.TestCase):
    def test_requires_network_switch(self):
        plan = _plan(allow_network=False, max_calls=5)
        with self.assertRaises(LiveError) as ctx:
            plan.validate()
        self.assertIn("allow-network", str(ctx.exception))

    def test_requires_positive_call_limit(self):
        with self.assertRaises(LiveError):
            _plan(max_calls=0).validate()
        with self.assertRaises(LiveError):
            _plan(max_calls=-3).validate()

    def test_requires_positive_timeout(self):
        with self.assertRaises(LiveError):
            _plan(max_calls=5, timeout_s=0).validate()

    def test_case_count_must_not_exceed_limit(self):
        suite = load_suite(SUITE_PATH)
        with self.assertRaises(LiveError):
            _plan(max_calls=1).validate()

    def test_unknown_case_id_rejected(self):
        with self.assertRaises(LiveError):
            _plan(max_calls=5, case_ids=["nope-123"])

    def test_refuse_non_https_endpoint(self):
        client = HttpClient(timeout_s=1)
        with self.assertRaises(LiveError):
            client.post_json("http://api.example.com/x", {}, {})


    def test_refuses_source_tree_run_dir(self):
        for banned in ("catalog", "research", "experiments", "tests"):
            with self.assertRaises(LiveError):
                _plan(run_dir=REPO / banned / "live", max_calls=5).validate()


class TestCollectWithMock(unittest.TestCase):
    def _run_one(self, script, route="jev"):
        import os

        suite = load_suite(SUITE_PATH)
        plan = _plan(route_key=route, max_calls=1, case_ids=[suite.cases[0].id])
        client = _MockClient(script)
        # A fake, non-secret key; only exercised against the mock client.
        os.environ["TYPESAFE_API_KEY"] = "test-fake-key"
        try:
            return collect(plan, client=client), client
        finally:
            os.environ.pop("TYPESAFE_API_KEY", None)

    def test_successful_choice_recorded(self):
        import json

        body = json.dumps(_jev_body("inspect_source", conf=0.6,
                                    usage={"input_tokens": 10, "output_tokens": 0})).encode()
        rec, client = self._run_one([_Resp(200, body)])
        self.assertEqual(len(rec.results), 1)
        self.assertEqual(rec.results[0].outcome, OUTCOME_OK)
        self.assertEqual(rec.results[0].usage, {"input_tokens": 10, "output_tokens": 0})
        self.assertIsNone(rec.results[0].cost)
        self.assertFalse(rec.synthetic)
        self.assertEqual(rec.results[0].confidence, 0.6)
        self.assertEqual(len(client.calls), 1)

    def test_retained_request_matches_sent_body(self):
        import json

        rec, client = self._run_one([_Resp(200, json.dumps(_jev_body("inspect_source")).encode())])
        r = rec.results[0]
        self.assertEqual(r.endpoint, "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(r.request, client.calls[0]["body"])
        self.assertNotIn("request_id", r.request)

    def test_retained_request_kept_on_transport_failure(self):
        rec, client = self._run_one([OSError("connection refused")])
        r = rec.results[0]
        self.assertEqual(r.outcome, OUTCOME_ERROR)
        self.assertIsNotNone(r.request)
        self.assertEqual(r.request, client.calls[0]["body"])
        self.assertEqual(r.endpoint, "https://api.typesafe.ai/v1/systemone")


    def test_no_credentials_in_request(self):
        import json

        body = json.dumps(_jev_body("inspect_source")).encode()
        rec, client = self._run_one([_Resp(200, body)])
        blob = json.dumps(client.calls[0]["body"], ensure_ascii=False)
        self.assertNotIn("test-fake-key", blob)
        # the key travels only in the Authorization header
        self.assertEqual(client.calls[0]["headers"]["Authorization"], "Bearer test-fake-key")
        # and it is never persisted into the retained request or the record
        record_blob = json.dumps([r.as_dict() for r in rec.results], ensure_ascii=False)
        self.assertNotIn("test-fake-key", record_blob)

    def test_missing_credentials_blocks(self):
        import os

        os.environ.pop("TYPESAFE_API_KEY", None)
        suite = load_suite(SUITE_PATH)
        plan = _plan(route_key="jev", max_calls=1, case_ids=[suite.cases[0].id])
        with self.assertRaises(LiveError) as ctx:
            collect(plan, client=_MockClient([_Resp(200, b"{}")]))
        self.assertIn("credentials", str(ctx.exception))

    def test_transport_error_recorded_as_nonchoice(self):
        rec, client = self._run_one([OSError("connection refused")])
        r = rec.results[0]
        self.assertEqual(r.outcome, OUTCOME_ERROR)
        self.assertEqual(r.error_kind, "transport")
        self.assertIsNone(r.cost)
        self.assertIsNone(r.raw)
        self.assertEqual(len(client.calls), 1)  # no retry

    def test_redirect_refused(self):
        rec, client = self._run_one([_Resp(302, b"")])
        self.assertEqual(rec.results[0].outcome, OUTCOME_ERROR)
        self.assertEqual(rec.results[0].error_kind, "redirect_refused")
        self.assertEqual(len(client.calls), 1)

    def test_http_error_recorded(self):
        rec, _ = self._run_one([_Resp(500, b'{"error":"boom"}')])
        self.assertEqual(rec.results[0].outcome, OUTCOME_ERROR)
        self.assertEqual(rec.results[0].error_kind, "http_500")

    def test_parse_error_recorded(self):
        rec, _ = self._run_one([_Resp(200, b"not json")])
        self.assertEqual(rec.results[0].outcome, OUTCOME_ERROR)
        self.assertEqual(rec.results[0].error_kind, "parse")

    def test_no_fallback_between_routes(self):
        """A Jev transport failure must NOT be retried against another route."""
        rec, client = self._run_one([OSError("boom")])
        self.assertEqual(len(client.calls), 1)
        for call in client.calls:
            self.assertIn("api.typesafe.ai", call["url"])

    def test_checkpoint_writes_inspectable_partial_record(self):
        import json
        import os
        import tempfile

        suite = load_suite(SUITE_PATH)
        with tempfile.TemporaryDirectory() as d:
            run_dir = Path(d) / "live"
            plan = plan_live(
                SUITE_PATH, route_key="jev", run_dir=run_dir,
                max_calls=2, timeout_s=5.0, allow_network=True,
                case_ids=[suite.cases[0].id, suite.cases[1].id],
            )
            # first call succeeds, second fails -> record holds both outcomes
            body = json.dumps(_jev_body("inspect_source")).encode()
            client = _MockClient([_Resp(200, body), OSError("boom")])
            os.environ["TYPESAFE_API_KEY"] = "test-fake-key"
            try:
                rec = collect(plan, client=client, checkpoint=True)
            finally:
                os.environ.pop("TYPESAFE_API_KEY", None)
            written = json.loads((run_dir / "record.json").read_text())
            self.assertEqual(len(written["results"]), 2)
            self.assertEqual({r["outcome"] for r in written["results"]}, {"ok", "error"})

    def test_plan_refuses_nonempty_run_dir(self):
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            run_dir = Path(d) / "live"
            run_dir.mkdir()
            (run_dir / "stale.txt").write_text("x")
            plan = plan_live(
                SUITE_PATH, route_key="jev", run_dir=run_dir,
                max_calls=1, timeout_s=5.0, allow_network=True,
            )
            with self.assertRaises(LiveError):
                plan.validate()


class TestCheckpointIsAtomic(unittest.TestCase):
    def _run(self, tmp, script):
        import os

        suite = load_suite(SUITE_PATH)
        run_dir = Path(tmp) / "live"
        plan = plan_live(
            SUITE_PATH, route_key="jev", run_dir=run_dir,
            max_calls=2, timeout_s=5.0, allow_network=True,
            case_ids=[suite.cases[0].id, suite.cases[1].id],
        )
        client = _MockClient(script)
        os.environ["TYPESAFE_API_KEY"] = "test-fake-key"
        try:
            rec = collect(plan, client=client, checkpoint=True)
        finally:
            os.environ.pop("TYPESAFE_API_KEY", None)
        return run_dir, rec

    def test_no_temp_file_left_behind(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            body = json.dumps(_jev_body("inspect_source")).encode()
            run_dir, _ = self._run(d, [_Resp(200, body), _Resp(200, body)])
            files = sorted(p.name for p in run_dir.iterdir())
            self.assertEqual(files, ["record.json"])

    def test_partial_record_valid_after_second_case_failure(self):
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            body = json.dumps(_jev_body("inspect_source")).encode()
            run_dir, _ = self._run(d, [_Resp(200, body), OSError("boom")])
            written = json.loads((run_dir / "record.json").read_text())
            first = written["results"][0]
            self.assertEqual(first["outcome"], "ok")
            self.assertIsNotNone(first["request"])
            from decision_lab.record import load_record
            loaded = load_record(run_dir)
            self.assertEqual([r.outcome for r in loaded.results], ["ok", "error"])


class TestResponseBounding(unittest.TestCase):
    def test_oversized_attempt_is_recorded_and_not_retried(self):
        import os
        import tempfile
        from unittest.mock import patch
        suite = load_suite(SUITE_PATH)
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"TYPESAFE_API_KEY": "synthetic-key"}):
            plan = plan_live(SUITE_PATH, route_key="jev", run_dir=Path(d)/"run",
                             max_calls=1, timeout_s=1, allow_network=True,
                             case_ids=[suite.cases[0].id])
            client = _MockClient([LiveError("response exceeded limit")])
            record = collect(plan, client=client)
            self.assertEqual(len(client.calls), 1)
            self.assertEqual(record.results[0].outcome, "error")
            self.assertIsNotNone(record.results[0].request)

    def test_duplicate_selection_rejected_before_call(self):
        suite = load_suite(SUITE_PATH)
        with self.assertRaises(LiveError):
            plan_live(SUITE_PATH, route_key="jev", run_dir=Path("runs/unused"),
                      max_calls=2, timeout_s=1, allow_network=True,
                      case_ids=[suite.cases[0].id, suite.cases[0].id])

    def test_oversized_response_refused(self):
        client = HttpClient(timeout_s=1.0, max_response_bytes=8)

        class _FakeResp:
            status = 200

            def read(self, n):
                return b"x" * n

        class _FakeConn:
            def request(self, *a, **k):
                pass

            def getresponse(self):
                return _FakeResp()

            def close(self):
                pass

        import decision_lab.live as live
        orig = live.http.client.HTTPSConnection
        live.http.client.HTTPSConnection = lambda *a, **k: _FakeConn()
        try:
            with self.assertRaises(LiveError):
                client.post_json("https://api.example.com/x", {}, {})
        finally:
            live.http.client.HTTPSConnection = orig


class TestOfflineCommandsMakeNoNetwork(unittest.TestCase):
    def test_http_client_constructor_does_not_connect(self):
        # constructing the client must not open a socket
        HttpClient(timeout_s=1.0)

    def test_cli_import_does_not_load_transport(self):
        # Importing the CLI (used by every offline command) must not even
        # import the network transport module.
        import subprocess
        import sys

        code = (
            "import sys; import decision_lab.cli; "
            "print('decision_lab.live' in sys.modules)"
        )
        out = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, check=True, cwd=str(REPO),
        ).stdout.strip()
        self.assertEqual(out, "False")

    def test_baseline_and_demo_use_no_client(self):
        # baseline/demo paths never import or call the transport client
        from decision_lab.record import run_baseline, run_demo

        suite = load_suite(SUITE_PATH)
        run_baseline(suite, suite_path=str(SUITE_PATH))
        run_demo(suite, suite_path=str(SUITE_PATH))


if __name__ == "__main__":
    unittest.main()
