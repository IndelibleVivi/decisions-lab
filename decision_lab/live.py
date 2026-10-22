"""Opt-in live collection against the two provider routes.

This module implements the mechanics for a FUTURE authorized operator
run. It is NOT executed in this build. Safety properties, enforced in
code and asserted by tests:

* Fixed official HTTPS endpoints (from the route profiles).
* Credentials come only from env vars (``TYPESAFE_API_KEY`` /
  ``OPENAI_API_KEY``); they are never written into records.
* Requires an explicit network switch AND a positive call limit.
* Bounded timeout; NO implicit retries; NO provider fallback.
* Redirects are refused so an auth header cannot leak to another host.
* Any transport/HTTP/parse failure still produces an inspectable
  partial record and is recorded as a non-choice error - never as a
  successful answer, and never with invented cost.
* Output goes to a NEW local run directory; clobber is refused; fixtures/
  catalog/research source trees are refused.
"""

from __future__ import annotations

import http.client
import json
import os
import socket
import ssl
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cases import Case, load_suite
from .record import (
    CaseResult,
    Record,
    RecordError,
    _forbid_source_path,
    case_digest,
    suite_digest,
    write_record,
)
from .routes import (
    OUTCOME_ERROR,
    build_request,
    get_route,
    protocol_profiles,
)


class LiveError(RuntimeError):
    """Raised for preconditions that must block a live run."""


#: Upper bound on a provider response body we will read into memory.
#: A decision answer is tiny; this only guards against a hostile or broken
#: endpoint streaming an unbounded body.
MAX_RESPONSE_BYTES = 1_000_000


@dataclass
class LivePlan:
    route_key: str
    run_dir: Path
    max_calls: int
    timeout_s: float
    allow_network: bool
    cases: list[Case]
    api_key_env: str
    suite_path: str = ""
    suite_digest: str = ""

    def validate(self) -> None:
        if not self.allow_network:
            raise LiveError(
                "live collection requires the explicit --allow-network switch; "
                "default commands are offline"
            )
        if self.max_calls <= 0:
            raise LiveError("live collection requires a positive --max-calls limit")
        if self.timeout_s <= 0:
            raise LiveError("live collection requires a positive --timeout")
        get_route(self.route_key)  # validates route key
        try:
            _forbid_source_path(self.run_dir)
        except RecordError as exc:
            raise LiveError(str(exc)) from exc
        if self.run_dir.exists() and any(self.run_dir.iterdir()):
            raise LiveError(f"run directory {self.run_dir} is non-empty; refuse to clobber")
        if len(self.cases) > self.max_calls:
            raise LiveError(
                f"{len(self.cases)} cases exceed --max-calls {self.max_calls}; "
                "raise the limit deliberately or select fewer cases"
            )


def _api_key_env_for(route_key: str) -> str:
    prof = get_route(route_key)
    return "TYPESAFE_API_KEY" if prof.provider == "typesafe" else "OPENAI_API_KEY"


@dataclass
class TransportResponse:
    status: int
    body: bytes
    latency_ms: float


class HttpClient:
    """Minimal HTTPS client that never follows redirects.

    Redirects (3xx with a Location) are treated as hard errors so an
    Authorization header cannot be replayed to another host.
    """

    def __init__(self, *, timeout_s: float, max_response_bytes: int = MAX_RESPONSE_BYTES):
        self.timeout_s = timeout_s
        self.max_response_bytes = max_response_bytes

    def post_json(self, url: str, headers: dict[str, str], body: dict[str, Any]) -> TransportResponse:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https":
            raise LiveError(f"refusing non-HTTPS endpoint: {url}")
        host = parsed.hostname or ""
        port = parsed.port or 443
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        ctx = ssl.create_default_context()
        start = time.monotonic()
        conn = http.client.HTTPSConnection(host, port, timeout=self.timeout_s, context=ctx)
        try:
            conn.request("POST", path, body=payload, headers=headers)
            resp = conn.getresponse()
            # Bound the read so a hostile/huge response cannot exhaust memory.
            raw = resp.read(self.max_response_bytes + 1)
            if len(raw) > self.max_response_bytes:
                raise LiveError(
                    f"response exceeded {self.max_response_bytes} bytes; refused"
                )
            latency = (time.monotonic() - start) * 1000.0
            return TransportResponse(status=resp.status, body=raw, latency_ms=latency)
        finally:
            # Always close, including on any exception during request/read.
            conn.close()


def _build_headers(route_key: str, api_key: str) -> dict[str, str]:
    prof = get_route(route_key)
    if prof.provider == "typesafe":
        auth = {"Authorization": f"Bearer {api_key}"}
    else:
        auth = {"Authorization": f"Bearer {api_key}"}
    return {
        **auth,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "decisions-lab/0.1.0",
    }


def plan_live(
    suite_path: str | Path,
    *,
    route_key: str,
    run_dir: str | Path,
    max_calls: int,
    timeout_s: float,
    allow_network: bool,
    case_ids: list[str] | None = None,
) -> LivePlan:
    suite = load_suite(suite_path)
    cases = suite.cases
    if case_ids:
        if len(case_ids) != len(set(case_ids)):
            raise LiveError("duplicate case ids; each case may be called only once per run")
        by_id = suite.by_id()
        missing = [c for c in case_ids if c not in by_id]
        if missing:
            raise LiveError(f"unknown case ids: {missing}")
        cases = [by_id[c] for c in case_ids]
    return LivePlan(
        route_key=route_key,
        run_dir=Path(run_dir),
        max_calls=max_calls,
        timeout_s=timeout_s,
        allow_network=allow_network,
        cases=cases,
        api_key_env=_api_key_env_for(route_key),
        suite_path=str(suite_path),
        suite_digest=suite_digest(suite),
    )


def record_error_result(
    case: Case,
    *,
    error_kind: str,
    detail: str,
    latency_ms: float | None,
    endpoint: str,
    request: Any,
    http_status: int | None = None,
) -> CaseResult:
    """A transport/HTTP/parse failure is a NON-choice error, inspectable,
    with no invented cost or success. The exact attempted prompt is retained
    so even a failed attempt keeps its reproducibility anchor."""
    return CaseResult(
        case_id=case.id,
        source_group=case.source_group,
        split=case.split,
        digest=case_digest(case),
        outcome=OUTCOME_ERROR,
        action=None,
        probabilities=None,
        model=None,
        confidence=None,
        http_status=http_status,
        endpoint=endpoint,
        request=request,
        error_kind=error_kind,
        error_detail=detail,
        raw=None,
        usage=None,
        cost=None,
        latency_ms=latency_ms,
        correct=None,
    )


def collect(
    plan: LivePlan,
    *,
    client: HttpClient | None = None,
    checkpoint: bool = False,
) -> Record:
    """Run the live collection. NOT called in this build.

    A future authorized operator invokes this via the CLI. Tests exercise
    it against a mock HTTP client at the transport boundary (no network,
    no credentials).

    When ``checkpoint`` is true, a partial record is written after every
    case so an interrupted run stays inspectable. This is NOT automatic
    resume: the partial record can be inspected/replayed with coverage
    checks, and a retry requires a fresh run directory.
    """
    plan.validate()
    api_key = os.environ.get(plan.api_key_env)
    if not api_key:
        raise LiveError(
            f"missing credentials: set {plan.api_key_env} in the environment "
            "(no env-file loading, no credentials in records)"
        )
    prof = get_route(plan.route_key)
    client = client or HttpClient(timeout_s=plan.timeout_s)
    results: list[CaseResult] = []

    def _snapshot(results_so_far: list[CaseResult]) -> None:
        if not checkpoint:
            return
        rec = _assemble_record(plan, prof, list(results_so_far))
        write_record(plan.run_dir, rec, clobber=True)

    _snapshot(results)  # claim the run dir with an empty partial record
    for i, case in enumerate(plan.cases):
        if i >= plan.max_calls:
            raise LiveError("call limit reached mid-run; this should be unreachable")
        # Build the prompt once and retain it verbatim: the record must keep the
        # exact outbound request (endpoint + body) even on a transport failure.
        body = build_request(plan.route_key, case)
        headers = _build_headers(plan.route_key, api_key)
        try:
            tr = client.post_json(prof.endpoint, headers, body)
        except (OSError, socket.error, ssl.SSLError, http.client.HTTPException, LiveError) as exc:
            results.append(
                record_error_result(
                    case, error_kind="transport", detail=repr(exc), latency_ms=None,
                    endpoint=prof.endpoint, request=body,
                )
            )
            _snapshot(results)
            continue
        if 300 <= tr.status < 400:
            results.append(
                record_error_result(
                    case, error_kind="redirect_refused",
                    detail=f"status {tr.status}; redirects refused to protect credentials",
                    latency_ms=tr.latency_ms, endpoint=prof.endpoint, request=body,
                    http_status=tr.status,
                )
            )
            _snapshot(results)
            continue
        try:
            payload = json.loads(tr.body.decode("utf-8")) if tr.body else None
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            results.append(
                record_error_result(
                    case, error_kind="parse", detail=repr(exc), latency_ms=tr.latency_ms,
                    endpoint=prof.endpoint, request=body,
                    http_status=tr.status,
                )
            )
            _snapshot(results)
            continue
        norm = prof.normalize(tr.status, payload)
        # usage/cost reported as-is; null/unknown when absent. We NEVER turn a
        # price table into an observed bill.
        usage = None
        cost = None
        if isinstance(payload, dict):
            if isinstance(payload.get("usage"), dict):
                usage = payload["usage"]
            if isinstance(payload.get("cost"), dict):
                cost = payload["cost"]
        # Only a normal positive choice is scored. unknown/refusal/error are
        # never counted as correct and derive no invented correctness.
        correct = (norm.action in case.acceptable) if norm.outcome == "ok" else None
        results.append(
            CaseResult(
                case_id=case.id,
                source_group=case.source_group,
                split=case.split,
                digest=case_digest(case),
                outcome=norm.outcome,
                action=norm.action,
                probabilities=norm.probabilities,
                model=norm.model,
                confidence=norm.confidence,
                http_status=tr.status,
                endpoint=prof.endpoint,
                request=body,
                refusal_reason=norm.refusal_reason,
                error_kind=norm.error_kind,
                error_detail=norm.error_detail,
                raw=norm.raw,
                usage=usage,
                cost=cost,
                latency_ms=tr.latency_ms,
                correct=correct,
            )
        )
        _snapshot(results)
    return _assemble_record(plan, prof, results)


def _assemble_record(plan: LivePlan, prof, results: list[CaseResult]) -> Record:
    return Record(
        provenance="live",
        route=plan.route_key,
        native_model=prof.native_model,
        suite_path=plan.suite_path,
        suite_digest=plan.suite_digest,
        protocol=protocol_profiles(),
        results=results,
        synthetic=False,
        notes="Live provider responses; transport failures recorded as non-choice errors.",
        planned_case_ids=[case.id for case in plan.cases],
    )
