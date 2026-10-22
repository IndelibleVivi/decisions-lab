"""Read-only common view of native evidence; no value-contract conversion."""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import json

from . import api_lab as al
from . import typed_values as tv
from . import collection

SCHEMA = "decisions-lab.run-ledger/1"


def _trial(request, question_id, result=None):
    rubric = request.get("rubric", {})
    identity = request.get("trial", {})
    row = {"request_id": request["id"], "question_id": question_id,
           "unit_id": identity.get("unit_id", rubric.get("group", request["id"])),
           "source_family": identity.get("source_family", rubric.get("group", request["id"])),
           "condition": identity.get("condition", rubric.get("condition", "baseline")),
           "replicate": identity.get("replicate", 0), "seed": identity.get("seed"),
           "split": identity.get("split", "unspecified"), "outcome": "missing", "correct": None,
           "loss": None, "confidence": None, "latency_ms": None, "cost": None}
    if result:
        row.update({k: result.get(k) for k in ("outcome", "correct", "confidence")})
        row["loss"] = float(not result["correct"]) if isinstance(result.get("correct"), bool) else None
        row["value"] = result.get("value")
    return row


def from_api(manifest, entries, *, metadata=None):
    al.validate_manifest(manifest)
    # Missing responses are actual planned missing slots, not synthetic failures.
    report = al.evaluate(manifest, entries) if entries else {"requests": [], "reported_request_usage": []}
    results = {r["request_id"]: r for r in report["requests"]}
    trials = []
    for request in manifest["requests"]:
        answers = {q["question_id"]: q for q in results.get(request["id"], {}).get("questions", [])}
        for qid in al.native_questions(request["body"], manifest["route"]):
            trials.append(_trial(request, qid, answers.get(qid)))
    dataset = {"route": manifest["route"], "requests": [
        {"id": r["id"], "trial": r.get("trial"), "rubric": r["rubric"],
         "body": {k: v for k, v in r["body"].items() if k != "model"},
         "required_headers": r["required_headers"]} for r in sorted(manifest["requests"], key=lambda r: r["id"])]}
    return {"schema": SCHEMA, "dataset_id": al.digest(dataset), "manifest_digest": manifest["manifest_digest"],
            "route": manifest["route"], "requested_model": manifest["model"],
            **(metadata or {}), "trials": trials, "requests": report["reported_request_usage"]}


def _typed_trials(request, evaluated):
    evaluation = evaluated.get("evaluation", {}) if evaluated else {}
    field_results = evaluation.get("fields", evaluation.get("source_fields", {}).get("fields", {}))
    try:
        native_answers = tv._response_envelope(evaluated["raw"]).get("answers", {}) if evaluated else {}
    except (tv.TypedValuesError, KeyError):
        native_answers = {}
    rows = []
    for name in request["body"]["fields"]:
        info = field_results.get(name, native_answers.get(name, {}))
        correct = info.get("entity_version_correct", info.get("exact_match"))
        native = {"outcome": evaluated["outcome"], "correct": correct,
                  "confidence": info.get("confidence"), "value": info.get("value")} if evaluated else None
        row = _trial(request, name, native)
        row["metric"] = "entity_version_field_accuracy" if correct is not None else "native_field_not_binary_scored"
        if evaluation.get("kind") == "interval_evaluation":
            row["interval_evaluation"] = copy.deepcopy(evaluation)
        rows.append(row)
    return rows


def from_collection(data):
    plan = data["plan"]
    collection.validate_plan(plan)
    latest = {}
    metrics = []
    for attempt in data["attempts"]:
        latest[attempt["request_id"]] = attempt
        metrics.append({"request_id": attempt["request_id"], "attempt": attempt["attempt"],
                        "latency_ms": attempt["elapsed_ms"], "cost": attempt["cost"],
                        "usage": attempt["usage"], "delivery": attempt["delivery"], "state": attempt["state"]})
    entries = []
    for ident, attempt in latest.items():
        entries.append({"request_id": ident, "response": attempt["parsed"],
                        "http_status": attempt["http_status"], "latency_ms": attempt["elapsed_ms"],
                        **({"error": attempt["state"]} if attempt["state"] != "ok" else {})})
    metadata = {"provenance": data["provenance"], "synthetic": data["synthetic"], "live_verified": False}
    if plan["kind"] == "api-lab":
        ledger = from_api(plan["manifest"], entries, metadata=metadata)
    else:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "suite.json"
            path.write_text(json.dumps(plan["suite"], ensure_ascii=False), encoding="utf-8")
            suite = tv.load_suite(path)
        trials = []
        for request in plan["requests"]:
            attempt = latest.get(request["id"])
            evaluated = None
            if attempt:
                entry = tv.ResponseEntry(case_id=request["case_id"], experiment_id=request["experiment"],
                                         raw=attempt["parsed"], http_status=attempt["http_status"],
                                         outcome_hint="native" if attempt["state"] == "ok" else "error",
                                         value_source="native", error_detail=None if attempt["state"] == "ok" else attempt["state"])
                evaluated = tv.make_result(suite, suite.by_id()[request["case_id"]], entry, span_convention=None)
            trials.extend(_typed_trials(request, evaluated))
        ledger = {"schema": SCHEMA, "dataset_id": plan["suite_digest"], "route": "clairic",
                  "requested_model": "clairic", **metadata, "trials": trials}
    # Aggregate all attempts once per native request, retaining unknown accounting.
    grouped = {}
    for item in metrics:
        grouped.setdefault(item["request_id"], []).append(item)
    ledger["requests"] = [{"request_id": ident,
                           "latency_ms": sum(a["latency_ms"] for a in attempts) if all(a["latency_ms"] is not None for a in attempts) else None,
                           "cost": _sum_costs(attempts), "attempts": attempts} for ident, attempts in grouped.items()]
    ledger["attempts"] = metrics
    ledger["collection_state"] = data["state"]
    return ledger


def _sum_costs(attempts):
    costs = [a.get("cost") for a in attempts]
    if not costs or not all(isinstance(c, dict) and al.finite(c.get("amount")) and c["amount"] >= 0
                            and isinstance(c.get("currency"), str) and c["currency"] for c in costs):
        return None
    if len({c["currency"] for c in costs}) != 1:
        return None
    return {"amount": sum(c["amount"] for c in costs), "currency": costs[0]["currency"]}


def from_typed(path, suite_path=tv.DEFAULT_SUITE):
    replay = tv.replay_record(path, suite_path)
    _, record = tv._load_record_data(path)
    suite = tv.load_suite(suite_path)
    trials = []
    for result in replay["cases"]:
        case = suite.by_id()[result["case_id"]]
        request = {"id": case.case_id, "body": case.request,
                   "trial": {"unit_id": case.case_id, "source_family": case.source_group,
                             "condition": case.raw.get("condition", case.case_id), "split": case.raw.get("split", "unspecified")}}
        trials.extend(_typed_trials(request, result))
    return {"schema": SCHEMA, "dataset_id": suite.digest(), "route": "clairic", "requested_model": "clairic",
            "provenance": record["provenance"], "synthetic": record["synthetic"], "trials": trials,
            "requests": [{"request_id": c, "latency_ms": None, "cost": None} for c in record["selected_case_ids"]]}


def from_legacy(path, suite_path):
    """Conservative read-only adapter; old missing planned sets mean full suite.

    Model defaults are irrelevant here. The supported legacy request format is
    still checked against the task with its retained requested model substituted.
    This does not migrate or overwrite the historical file.
    """
    from . import record as legacy
    from .cases import load_suite
    from .routes import build_request, get_route
    record = legacy.load_record(path)
    suite = load_suite(suite_path)
    al.require(record.suite_digest == legacy.suite_digest(suite), "legacy suite changed")
    al.require(record.provenance in ("baseline", "demo", "live"), "unknown legacy provenance")
    al.require(record.synthetic == (record.provenance != "live"), "legacy synthetic metadata mismatch")
    by_id = {}
    cases = suite.by_id()
    for result in record.results:
        al.require(result.case_id not in by_id and result.case_id in cases, "duplicate/foreign legacy result")
        case = cases[result.case_id]
        al.require(result.digest == legacy.case_digest(case) and result.source_group == case.source_group and result.split == case.split,
                   "legacy case changed")
        correct = result.action in case.acceptable if result.outcome == "ok" else None
        al.require(result.correct is correct, "legacy correctness changed")
        if record.provenance == "live":
            al.require(isinstance(record.native_model, str) and record.native_model, "legacy requested model missing")
            expected = build_request(record.route, case)
            expected["model"] = record.native_model
            al.require(result.request == expected and result.endpoint == get_route(record.route).endpoint, "legacy retained request changed")
            if result.outcome != "error":
                normalized = get_route(record.route).normalize(result.http_status, result.raw)
                al.require(all(getattr(normalized, k) == getattr(result, k) for k in ("outcome", "action", "probabilities", "model", "confidence")), "legacy raw result mismatch")
        by_id[result.case_id] = result
    planned = record.planned_case_ids
    if planned is not None:
        al.require(isinstance(planned, list) and planned and all(isinstance(i, str) for i in planned)
                   and len(set(planned)) == len(planned) and set(planned) <= set(cases), "invalid legacy planned set")
        al.require(set(by_id) <= set(planned), "legacy result outside planned set")
    trials = []
    for case in suite.cases:
        if planned is not None and case.id not in planned:
            continue
        result = by_id.get(case.id)
        request = {"id": case.id, "trial": {"unit_id": case.id, "source_family": case.source_group,
                                            "condition": "baseline", "split": case.split}}
        trials.append(_trial(request, "action", {"outcome": result.outcome, "correct": result.correct,
                                                "confidence": result.confidence, "value": result.action} if result else None))
    return {"schema": SCHEMA, "dataset_id": record.suite_digest, "provenance": record.provenance,
            "synthetic": record.synthetic, "route": record.route, "requested_model": record.native_model,
            "planned_set_basis": "retained_planned_case_ids" if planned is not None else "legacy_full_suite; subset intent unavailable",
            "trials": trials, "requests": [{"request_id": r.case_id, "latency_ms": r.latency_ms, "cost": r.cost} for r in record.results]}


def load_ledger(path, *, suite_path=None):
    path = Path(path)
    if path.is_dir():
        candidates = [path / name for name in ("collection.json", "record.json", "typed-values-record.json", "ledger.json") if (path / name).is_file()]
        al.require(len(candidates) == 1, "ambiguous/missing record; choose exact file")
        path = candidates[0]
    data = al.read_json(path)
    if data.get("schema") == SCHEMA:
        return copy.deepcopy(data)
    if data.get("schema") == collection.SCHEMA:
        return from_collection(collection.load_collection(path))
    if data.get("schema") == al.RECORD_VERSION:
        checked = al._checked_record(path)
        return from_api(checked["manifest"], checked["responses"], metadata={k: checked[k] for k in ("provenance", "synthetic")})
    if data.get("record_version") == tv.RECORD_VERSION:
        return from_typed(path, suite_path or tv.DEFAULT_SUITE)
    al.require(data.get("record_version") == 1, "unsupported native record")
    return from_legacy(path, suite_path or "experiments/next-action/cases.json")
