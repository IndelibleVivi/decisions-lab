"""Bounded sequential collection of retained native requests.

Collection evidence wraps api-lab / typed-values, without changing their values.
No network is possible without an explicit switch, budget and credential. A saved
in-flight attempt is uncertain, never silently replayed after interruption.
"""
from __future__ import annotations

import base64
import copy
import json
import http.client
import os
from pathlib import Path
import random
import re
import time
from datetime import datetime, timezone

from . import api_lab as al
from . import typed_values as tv
from .live import HttpClient

SCHEMA = "decisions-lab.collection/1"
PLAN_SCHEMA = "decisions-lab.collection-plan/1"


def now():
    return datetime.now(timezone.utc).isoformat()


def _strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON response key")
        result[key] = value
    return result


def api_plan(manifest):
    al.validate_manifest(manifest)
    return {"schema": PLAN_SCHEMA, "kind": "api-lab", "route": manifest["route"],
            "manifest": copy.deepcopy(manifest), "requests": copy.deepcopy(manifest["requests"])}


def typed_plan(suite, cases, *, replicates=1):
    al.require(type(replicates) is int and replicates > 0, "replicates must be positive")
    rows = []
    for case in cases:
        for rep in range(replicates):
            rows.append({"id": case.case_id if replicates == 1 else f"{case.case_id}.rep{rep}",
                         "case_id": case.case_id, "experiment": case.experiment_id,
                         "body": copy.deepcopy(case.request), "required_headers": {},
                         "trial": {"unit_id": case.case_id, "source_family": case.source_group,
                                   "condition": case.raw.get("condition", case.case_id),
                                   "replicate": rep, "split": case.raw.get("split", "unspecified"), "seed": None}})
    return {"schema": PLAN_SCHEMA, "kind": "typed-values", "route": "clairic",
            "suite_digest": suite.digest(), "suite": copy.deepcopy(suite.raw), "requests": rows}


def validate_plan(plan):
    al.require(isinstance(plan, dict) and plan.get("schema") == PLAN_SCHEMA, "invalid collection plan")
    rows = plan.get("requests")
    al.require(isinstance(rows, list) and rows, "empty planned set")
    if plan.get("kind") == "api-lab":
        al.validate_manifest(plan["manifest"])
        al.require(plan["route"] == plan["manifest"]["route"] and rows == plan["manifest"]["requests"],
                   "collection plan differs from retained manifest")
    else:
        al.require(plan.get("kind") == "typed-values" and plan.get("route") == "clairic", "invalid plan kind")
        # Reuse the actual typed-values loader, including all schema checks.
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "suite.json"
            path.write_text(json.dumps(plan["suite"], ensure_ascii=False), encoding="utf-8")
            suite = tv.load_suite(path)
        al.require(plan["suite_digest"] == suite.digest(), "typed suite changed")
        by_id = suite.by_id()
        for row in rows:
            case = by_id.get(row.get("case_id"))
            al.require(case is not None and row.get("body") == case.request and row.get("required_headers") == {},
                       "typed request differs from retained suite")
    ids = [row.get("id") for row in rows]
    al.require(all(isinstance(i, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_+.-]*", i) for i in ids)
               and len(set(ids)) == len(ids), "invalid/duplicate planned request IDs")
    slots, families, splits = set(), {}, {}
    for row in rows:
        trial = al._request_trial(row)
        unit, family, split = trial["unit_id"], trial["source_family"], trial["split"]
        al.require(unit not in families or families[unit] == family, "planned unit source family differs")
        al.require(family not in splits or splits[family] == split, "planned source family spans splits")
        families[unit], splits[family] = family, split
        questions = row["body"]["fields"] if plan["route"] == "clairic" else al.native_questions(row["body"], plan["route"])
        for qid in questions:
            key = (unit, trial["condition"], trial["replicate"], qid)
            al.require(key not in slots, "duplicate planned logical trial slot")
            slots.add(key)
    return rows


def question_count(plan, row):
    return len(row["body"]["fields"]) if plan["route"] == "clairic" else len(al.native_questions(row["body"], plan["route"]))


def endpoint_for(route, account_id=None):
    if route in al.ENDPOINTS:
        return al.ENDPOINTS[route]
    al.require(route == "clairic" and isinstance(account_id, str) and re.fullmatch(r"[a-fA-F0-9]{32}", account_id),
               "Clairic requires CLOUDFLARE_ACCOUNT_ID (32 hexadecimal characters)")
    return f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/cloudflare/clairic"


def _seal(snapshot):
    snapshot["evidence_digest"] = al.digest({k: v for k, v in snapshot.items() if k != "evidence_digest"})
    return snapshot


def load_collection(path):
    path = Path(path)
    if path.is_dir():
        path /= "collection.json"
    data = al.read_json(path)
    al.require(data.get("schema") == SCHEMA, "invalid collection schema")
    al.require(data.get("evidence_digest") == al.digest({k: v for k, v in data.items() if k != "evidence_digest"}),
               "collection evidence changed")
    rows = validate_plan(data["plan"])
    ids = [r["id"] for r in rows]
    al.require(set(data["order"]) == set(ids) and len(data["order"]) == len(ids), "invalid collection schedule")
    seen = set()
    for attempt in data["attempts"]:
        ident = (attempt["request_id"], attempt["attempt"])
        al.require(ident not in seen and ident[0] in ids, "foreign/duplicate attempt")
        seen.add(ident)
        al.require(attempt["state"] in ("in_flight", "ok", "http_error", "parse_error", "transport_error", "cancelled"),
                   "invalid attempt state")
    return data


def collect(plan, run_dir, *, allow_network=False, max_calls, max_questions,
            max_estimated_tokens, timeout_s=30.0, max_attempts=1, retry_delay_s=1.0,
            seed=0, resume=False, retry_uncertain=False, client=None, credential=None,
            account_id=None, cancel=None, sleep=time.sleep):
    """Budgets count ALL attempts, including retries and uncertain sends.

    The byte-based input token estimate is scheduling metadata, not a provider
    tokenizer or billing cap; output usage and money remain unknown if unreported.
    Concurrency is deliberately one. Ctrl-C checkpoints cancellation.
    """
    al.require(allow_network, "collection requires --allow-network; default commands are offline")
    rows = validate_plan(plan)
    for name, value in (("max_calls", max_calls), ("max_questions", max_questions),
                        ("max_estimated_tokens", max_estimated_tokens), ("max_attempts", max_attempts)):
        al.require(type(value) is int and value > 0, f"{name} must be a positive integer")
    al.require(al.finite(timeout_s) and 0 < timeout_s <= 300, "timeout must be in (0,300]")
    al.require(al.finite(retry_delay_s) and 0 <= retry_delay_s <= 60, "retry delay must be in [0,60]")
    costs = {r["id"]: {"questions": question_count(plan, r),
                       "estimated_tokens": len(json.dumps(r["body"], ensure_ascii=False).encode("utf-8"))} for r in rows}
    al.require(len(rows) <= max_calls and sum(v["questions"] for v in costs.values()) <= max_questions
               and sum(v["estimated_tokens"] for v in costs.values()) <= max_estimated_tokens,
               "planned set exceeds budget")
    route = plan["route"]
    env_name = {"decisions": "OPENAI_API_KEY", "jev": "TYPESAFE_API_KEY", "clairic": "CLOUDFLARE_API_TOKEN"}[route]
    endpoint = endpoint_for(route, account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID"))
    directory = Path(run_dir)
    al._safe_output(directory, directory=True) if not resume else _check_resume_dir(directory)
    output = directory / "collection.json"
    budget = {"max_calls": max_calls, "max_questions": max_questions,
              "max_estimated_tokens": max_estimated_tokens, "max_attempts": max_attempts}
    if resume:
        data = None  # load only while holding exclusive writer ownership below
    else:
        order = [r["id"] for r in rows]
        random.Random(seed).shuffle(order)
        data = {"schema": SCHEMA, "plan": copy.deepcopy(plan), "endpoint": endpoint,
                "provenance": "collector", "synthetic": False, "live_verified": False,
                "created_at": now(), "seed": seed, "order": order, "concurrency": 1,
                "budget": budget, "attempts": [], "state": "planned",
                "token_estimator": "UTF-8 serialized input bytes; excludes output and provider accounting",
                "reported_cost": None}
    key = credential if credential is not None else os.environ.get(env_name)
    al.require(isinstance(key, str) and bool(key.strip()), f"missing credential: {env_name}")
    directory.mkdir(parents=True, exist_ok=True)
    # Exclusive run ownership prevents simultaneous resume writers.
    lock = directory / ".collector.lock"
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise al.ApiLabError("collector lock exists; verify prior process stopped before removing stale lock") from exc
    os.close(lock_fd)
    def save():
        al._write(output, _seal(data))
    client = client or HttpClient(timeout_s=timeout_s)
    by_id = {r["id"]: r for r in rows}
    try:
        if resume:
            data = load_collection(output)
            al.require(data["plan"] == plan and data["endpoint"] == endpoint and data["budget"] == budget,
                       "resume plan/endpoint/budget differs from checkpoint")
        data["state"] = "running"
        save()
        for ident in data["order"]:
            row = by_id[ident]
            prior = [a for a in data["attempts"] if a["request_id"] == ident]
            if prior and prior[-1]["state"] == "ok":
                continue
            uncertain = bool(prior and prior[-1].get("delivery") == "uncertain")
            if uncertain and not retry_uncertain:
                continue
            if prior and not uncertain and prior[-1].get("http_status") != 429:
                continue
            while len(prior) < max_attempts:
                if (cancel and cancel()) or (directory / "CANCEL").exists():
                    data["state"] = "cancelled"
                    save()
                    return data
                used_questions = sum(costs[a["request_id"]]["questions"] for a in data["attempts"])
                used_tokens = sum(costs[a["request_id"]]["estimated_tokens"] for a in data["attempts"])
                if len(data["attempts"]) >= max_calls or used_questions + costs[ident]["questions"] > max_questions or used_tokens + costs[ident]["estimated_tokens"] > max_estimated_tokens:
                    data["state"] = "budget_exhausted"
                    save()
                    return data
                headers = {"Content-Type": "application/json", "Accept": "application/json",
                           **row.get("required_headers", {}), "Authorization": f"Bearer {key}"}
                attempt = {"request_id": ident, "attempt": len(prior), "started_at": now(),
                           "finished_at": None, "elapsed_ms": None, "state": "in_flight", "delivery": "uncertain",
                           "http_status": None, "raw_body_base64": None, "parsed": None, "parse_status": "not_received",
                           "usage": None, "cost": None, "retry_reason": None if not prior else ("uncertain_explicit" if uncertain else "http_429")}
                data["attempts"].append(attempt)
                save()  # the request may reach the provider after this point
                start = time.monotonic()
                interrupted = False
                try:
                    response = client.post_json(endpoint, headers, row["body"])
                    attempt["http_status"] = response.status
                    attempt["raw_body_base64"] = base64.b64encode(response.body).decode("ascii")
                    attempt["delivery"] = "response_received"
                    try:
                        payload = json.loads(response.body.decode("utf-8"), object_pairs_hook=_strict_pairs,
                                             parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
                        json.dumps(payload, allow_nan=False)
                        attempt["parsed"] = payload
                        attempt["parse_status"] = "parsed"
                        attempt["state"] = "ok" if 200 <= response.status < 300 else "http_error"
                        if isinstance(payload, dict):
                            attempt["usage"] = payload.get("usage", payload.get("result", {}).get("usage") if isinstance(payload.get("result"), dict) else None)
                            attempt["cost"] = payload.get("cost")
                    except (UnicodeError, ValueError):
                        attempt["state"] = "parse_error"
                        attempt["parse_status"] = "malformed"
                except KeyboardInterrupt:
                    attempt["state"] = "cancelled"
                    interrupted = True
                except (OSError, RuntimeError, http.client.HTTPException) as exc:
                    attempt["state"] = "transport_error"
                    attempt["error_kind"] = type(exc).__name__
                finally:
                    attempt["elapsed_ms"] = (time.monotonic() - start) * 1000
                    attempt["finished_at"] = now()
                    save()
                prior.append(attempt)
                if interrupted:
                    data["state"] = "cancelled"
                    save()
                    return data
                if attempt["http_status"] != 429 or len(prior) >= max_attempts:
                    break
                sleep(retry_delay_s)
        data["state"] = "settled" if all(any(a["request_id"] == i for a in data["attempts"]) for i in data["order"]) else "partial"
        save()
        return data
    finally:
        lock.unlink(missing_ok=True)


def _check_resume_dir(directory):
    root = Path(__file__).resolve().parents[1]
    resolved = directory.resolve()
    al.require(not resolved.is_relative_to(root) or resolved.is_relative_to(root / "runs"), "resume must use runs/ or outside source")
    al.require(directory.is_dir(), "resume directory is missing")
