"""Replayable round bridge to api-lab native records; never performs network I/O.

A round applies atomically. Missing responses/answers and uncertain deliveries
must be resolved in the retained collector before application. Digests detect
accidental edits and bind retained requests; they are not signatures.
"""
from __future__ import annotations

import base64
import copy
import json
from pathlib import Path

from . import api_lab as al
from . import collection, comparison, evidence

SCHEMA = "decisions-lab.evidence-workflow/1"
COMPARE_SCHEMA = "decisions-lab.evidence-comparison/1"
POLICY = "native"


def _seal(value):
    value["evidence_digest"] = al.digest({k: v for k, v in value.items() if k != "evidence_digest"})
    return value


def _check_seal(value):
    al.require(value.get("evidence_digest") == al.digest({k: v for k, v in value.items() if k != "evidence_digest"}),
               "retained evidence digest mismatch")


def _read(value):
    if isinstance(value, (str, Path)):
        path = Path(value)
        if path.is_dir():
            path /= "collection.json" if (path / "collection.json").exists() else "record.json"
        value = al.read_json(path)
    al.require(isinstance(value, dict), "retained source must be an object or JSON path")
    return copy.deepcopy(value)


def start(suite, *, route, model=None, account_id=None, replicates=1, query_mode="adaptive"):
    evidence.validate_suite(suite)
    al.require(query_mode in ("adaptive", "read-all"), "invalid query mode")
    if "schema_design" in suite:
        from .schema_inquiry import inspect_suite
        inspect_suite(suite)
    value = {"schema": SCHEMA, "suite": copy.deepcopy(suite), "policy": POLICY,
             "route": route, "model": al.route_model(route, model), "account_id": account_id,
             "replicates": replicates, "planned": evidence.planned_episodes(suite, POLICY, replicates),
             "rounds": []}
    if query_mode == "read-all":
        value["query_mode"] = query_mode
    _manifest(value, _initial(value), 0)  # validate native route/config before retaining a workflow
    return _seal(value)


def _initial(workflow):
    scenarios = {s["id"]: s for s in workflow["suite"]["scenarios"]}
    states = {}
    for plan in workflow["planned"]:
        scenario = scenarios[plan["scenario_id"]]
        state = evidence.initial_state(scenario, plan["world_id"])
        if workflow.get("query_mode") == "read-all":
            al.require(len(scenario["queries"]) <= scenario["max_queries"]
                       and sum(q["cost"] for q in scenario["queries"]) <= scenario["budget"],
                       "read-all requires a budget that covers every query")
            for query in scenario["queries"]:
                state = evidence.step(scenario, state, "query:" + query["id"])
        states[plan["id"]] = state
    return states


def _manifest(workflow, states, turn):
    scenarios = {s["id"]: s for s in workflow["suite"]["scenarios"]}
    rows = []
    for index, plan in enumerate(workflow["planned"]):
        state = states[plan["id"]]
        if state["terminal"] is not None:
            continue
        visible = evidence.visible_state(scenarios[plan["scenario_id"]], state)
        if workflow.get("query_mode") == "read-all" and "schema_design" in workflow["suite"]:
            from .schema_inquiry import episode_evidence
            visible["source_text"] = episode_evidence(workflow["suite"], {**plan, "history": []})["source"]
        actions = visible["available_actions"]
        choices = [{"value": a, "description": a} for a in actions]
        choices.append({"value": "unknown", "description": "API unknown: cannot return an action; distinct from business abstain."})
        # The public finite design includes all hypothetical observations/losses.
        # Neither the selected actual hypothesis nor local episode/trial IDs enter body.
        rows.append({"id": f"e{index:04d}.t{turn:04d}", "experiment": "active-evidence",
                     "input": json.dumps(visible, ensure_ascii=False, sort_keys=True),
                     "questions": [{"id": "action", "type": "choice",
                         "instructions": "Choose the next legal action to minimize total query cost plus terminal loss. Query reveals only its local synthetic observation. commit ends the episode; abstain is a business decision. unknown is API failure. Return one listed action.",
                         "choices": choices}],
                     "rubric": {"questions": {"action": {"kind": "choice", "acceptable": list(actions)}}},
                     "trial": {"unit_id": plan["id"], "source_family": plan["source_family"],
                               "condition": f"turn-{turn}", "replicate": plan["replicate"],
                               "split": plan["split"], "seed": workflow["suite"].get("seed")}})
    if not rows:
        return None
    return al.prepare_payload(al.Suite({}, rows), rows, route=workflow["route"], model=workflow["model"],
                              account_id=workflow["account_id"])


def _source(value, expected):
    """Validate retained source and project its final native entries, without guessing provenance."""
    value = _read(value)
    _check_seal(value)
    synthetic = value.get("synthetic")
    al.require(synthetic is None or type(synthetic) is bool, "invalid synthetic marker")
    al.require(value.get("live_verified") is False, "invalid source live provenance")
    metrics = {}
    if value.get("schema") == al.RECORD_VERSION:
        provenance = value.get("provenance")
        al.require(provenance in ("synthetic", "imported"), "invalid native record provenance")
        al.require(provenance != "synthetic" or synthetic is True, "synthetic record needs marker")
        manifest, entries = value.get("manifest"), value.get("responses")
        if isinstance(entries, list):
            for entry in entries:
                al.require(isinstance(entry, dict), "invalid response envelope")
                metrics[entry.get("request_id")] = {"attempts": None, "latency_ms": entry.get("latency_ms"),
                                                     "usage": entry.get("usage"), "cost": entry.get("cost")}
    else:
        al.require(value.get("schema") == collection.SCHEMA and value.get("provenance") == "collector",
                   "source must be native api-record or collection")
        provenance = "collector"
        plan = value.get("plan")
        rows = collection.validate_plan(plan)
        al.require(plan["kind"] == "api-lab", "evidence requires api-lab collection")
        manifest = plan["manifest"]
        al.require(value.get("endpoint", manifest["endpoint"]) == manifest["endpoint"], "collection endpoint differs from manifest")
        ids = [r["id"] for r in rows]
        al.require(isinstance(value.get("order"), list) and len(value["order"]) == len(ids)
                   and set(value["order"]) == set(ids), "invalid collection schedule")
        attempts = value.get("attempts")
        al.require(isinstance(attempts, list), "collection attempts must be a list")
        grouped = {}
        seen = set()
        for attempt in attempts:
            al.require(isinstance(attempt, dict), "invalid collection attempt")
            ident, number = attempt.get("request_id"), attempt.get("attempt")
            al.require(ident in ids and type(number) is int and number >= 0 and (ident, number) not in seen,
                       "foreign/duplicate/invalid collection attempt")
            seen.add((ident, number))
            al.require(attempt.get("state") in ("in_flight", "ok", "http_error", "parse_error", "transport_error", "cancelled"),
                       "invalid collection attempt state")
            if attempt.get("raw_body_base64") is not None and attempt.get("parse_status") == "parsed":
                try:
                    raw = json.loads(base64.b64decode(attempt["raw_body_base64"], validate=True).decode("utf-8"),
                                     object_pairs_hook=collection._strict_pairs)
                except (ValueError, UnicodeError) as exc:
                    raise al.ApiLabError("invalid retained response bytes") from exc
                al.require(raw == attempt.get("parsed"), "parsed response differs from retained bytes")
            prior = grouped.setdefault(ident, [])
            al.require(number == len(prior), "attempt sequence differs from retained order")
            prior.append(attempt)
        entries = []
        for ident, group in grouped.items():
            last = group[-1]
            al.require(last.get("state") != "in_flight" and last.get("delivery") != "uncertain",
                       "uncertain delivery cannot apply; resolve retained collector first")
            entry = {"request_id": ident, "response": last.get("parsed"), "http_status": last.get("http_status"),
                     "latency_ms": last.get("elapsed_ms")}
            if last["state"] != "ok":
                entry["error"] = last["state"]
            entries.append(entry)
            metrics[ident] = {"attempts": len(group),
                "latency_ms": _sum_numbers([a.get("elapsed_ms") for a in group]),
                "usage": _sum_usage([a.get("usage") for a in group]),
                "cost": _sum_costs([a.get("cost") for a in group])}
    al.require(manifest == expected, "source manifest differs from current round (stale, foreign or changed request)")
    al.validate_manifest(manifest)
    al.validate_responses(entries, manifest)  # deliberately atomic: no partial applications
    if provenance != "collector":
        # Use api-lab's native usage projection, then retain reported native costs
        # when the import envelope has no accounting override.
        for item in al.evaluate(manifest, entries)["reported_request_usage"]:
            ident = item["request_id"]
            entry = next(e for e in entries if e["request_id"] == ident)
            raw = entry.get("response")
            native = raw.get("result", raw) if manifest["route"] in al.CLOUDFLARE_ROUTES and isinstance(raw, dict) else raw
            cost = item.get("cost")
            if cost is None and isinstance(native, dict):
                cost = native.get("cost")
            if cost is None and isinstance(raw, dict):
                cost = raw.get("cost")
            metrics[ident].update(usage=item.get("usage"), cost=cost, latency_ms=item.get("latency_ms"))
    for entry in entries:
        al.require(entry.get("response") is not None or bool(entry.get("error"))
                   or (entry.get("http_status") is not None and not 200 <= entry["http_status"] < 300),
                   "missing native response; round remains pending")
    by_id = {e["request_id"]: e for e in entries}
    decoded = []
    for request in manifest["requests"]:
        native = al.normalize_request(request, by_id[request["id"]], manifest["route"])
        al.require(not native["contract_issues"], "native answer alignment issue")
        question = native["questions"][0]
        al.require(question.get("detail") != "missing answer", "missing native answer; round remains pending")
        outcome = question["outcome"]
        action = question.get("value")
        failure = "unknown" if outcome == "ok" and action == "unknown" else outcome if outcome != "ok" else None
        metric = {**metrics[request["id"]], "request_id": request["id"],
                  "episode_id": request["trial"]["unit_id"], "provenance": provenance, "synthetic": synthetic}
        if synthetic is True:
            metric.update(latency_ms=None, usage=None, cost=None)
        decoded.append({"episode_id": request["trial"]["unit_id"], "action": action, "failure": failure,
                        "native": metric})
    return value, decoded


def _rebuild(value):
    workflow = _read(value)
    al.require(workflow.get("schema") == SCHEMA and workflow.get("policy") == POLICY, "invalid evidence workflow")
    allowed = {"schema", "suite", "policy", "route", "model", "account_id", "replicates", "planned", "rounds", "evidence_digest"}
    al.require(set(workflow) in (allowed, allowed | {"query_mode"})
               and workflow.get("query_mode", "adaptive") in ("adaptive", "read-all"),
               "unknown workflow fields/query mode; derived state must not be retained")
    _check_seal(workflow)
    evidence.validate_suite(workflow["suite"])
    if "schema_design" in workflow["suite"]:
        from .schema_inquiry import inspect_suite
        inspect_suite(workflow["suite"])
    al.require(workflow["planned"] == evidence.planned_episodes(workflow["suite"], POLICY, workflow["replicates"]),
               "workflow planned identities changed")
    al.require(isinstance(workflow["rounds"], list), "rounds must be a list")
    states, metrics = _initial(workflow), []
    scenarios = {s["id"]: s for s in workflow["suite"]["scenarios"]}
    for turn, source in enumerate(workflow["rounds"]):
        manifest = _manifest(workflow, states, turn)
        al.require(manifest is not None, "round retained after all episodes terminal")
        _, decoded = _source(source, manifest)
        for item in decoded:
            ident = item["episode_id"]
            state = states[ident]
            scenario = scenarios[state["scenario_id"]]
            states[ident] = (evidence.finish_failure(scenario, state, item["failure"]) if item["failure"]
                             else evidence.step(scenario, state, item["action"]))
            metrics.append({"round": turn, **item["native"]})
    return workflow, states, metrics


def prepare_round(workflow):
    """Return one api-lab manifest for all pending episodes; None when terminal."""
    workflow, states, _ = _rebuild(workflow)
    return _manifest(workflow, states, len(workflow["rounds"]))


def apply_round(workflow, source):
    """Return a new workflow only after every current request is resolved."""
    workflow, states, _ = _rebuild(workflow)
    manifest = _manifest(workflow, states, len(workflow["rounds"]))
    al.require(manifest is not None, "all episodes terminal; no round to apply")
    retained, _ = _source(source, manifest)
    workflow["rounds"].append(retained)
    result = _seal(workflow)
    _rebuild(result)
    return result


def demo(suite, *, route="decisions", model=None, account_id=None, replicates=1, policy="optimal", query_mode="adaptive"):
    """Run a named synthetic control through native round records, with no transport.

    Actions read only the serialized native body. Probability/confidence values
    are deterministic format fixtures, never estimated model confidence/usage.
    """
    al.require(policy in evidence.POLICIES, "demo requires a built-in synthetic policy")
    workflow = start(suite, route=route, model=model, account_id=account_id, replicates=replicates, query_mode=query_mode)
    while (manifest := prepare_round(workflow)) is not None:
        entries = []
        for request in manifest["requests"]:
            body = request["body"]
            visible = json.loads(body["input" if route == "decisions" else "state"])
            visible.pop("source_text", None)  # finite oracle reads the same public state; source is redundant after all queries
            action = evidence.choose_action(visible, visible, policy)
            question = al.native_questions(body, route)["action"]
            values = ([choice["value"] for choice in question["choices"]] if route == "decisions"
                      else list(question["criteria"]))
            answer = {"type": "choice", "choice": action, "confidence": 1.0,
                      "probabilities": ([{"value": value, "probability": float(value == action)} for value in values]
                                        if route == "decisions" else {value: float(value == action) for value in values})}
            if route == "decisions":
                answer["name"] = "action"
            response = {"model": body["model"], "answers": [answer] if route == "decisions" else {"action": answer}}
            if route in al.CLOUDFLARE_ROUTES:
                response = {"success": True, "errors": [], "result": response}
            entries.append({"request_id": request["id"], "http_status": 200, "response": response})
        workflow = apply_round(workflow, al.build_record(manifest, entries, provenance="synthetic"))
    return workflow


def _sum_numbers(values):
    return sum(values) if values and all(al.finite(v) and v >= 0 for v in values) else None


def _sum_usage(values):
    if not values or not all(isinstance(v, dict) and v for v in values):
        return None
    keys = set(values[0])
    if not all(set(v) == keys for v in values):
        return None
    result = {k: (_sum_usage([v[k] for v in values]) if isinstance(values[0][k], dict)
                  else _sum_numbers([v[k] for v in values])) for k in sorted(keys)}
    return result if all(v is not None for v in result.values()) else None


def _sum_costs(values):
    if not values or not all(isinstance(v, dict) and al.finite(v.get("amount")) and v["amount"] >= 0
                             and isinstance(v.get("currency"), str) and v["currency"] for v in values):
        return None
    if len({v["currency"] for v in values}) != 1:
        return None
    return {"amount": sum(v["amount"] for v in values), "currency": values[0]["currency"]}


def _run(workflow, states, metrics):
    markers = [m["synthetic"] for m in metrics]
    synthetic = True if markers and all(m is True for m in markers) else False if markers and all(m is False for m in markers) else None
    return {"schema": evidence.RUN_SCHEMA, "suite": copy.deepcopy(workflow["suite"]), "policy": POLICY,
            "route": workflow["route"], "requested_model": workflow["model"],
            "source_records": [{"round": turn, "provenance": source.get("provenance"),
                                "synthetic": source.get("synthetic")}
                               for turn, source in enumerate(workflow["rounds"])],
            "replicates": workflow["replicates"], "planned": copy.deepcopy(workflow["planned"]),
            "episodes": [{"id": ident, "history": copy.deepcopy(state["history"])} for ident, state in states.items()],
            "synthetic": synthetic, "provenance": "native-workflow", "live_verified": False}


def report(workflow):
    workflow, states, metrics = _rebuild(workflow)
    run = _run(workflow, states, metrics)
    result = evidence.replay(run)
    result["synthetic"] = run["synthetic"]  # unknown provenance is not asserted non-synthetic/live
    result["run"] = run
    summary = result["summary"]
    decisions = summary["planned"] - summary["failed"]
    summary.update(terminal_decisions=decisions, committed=decisions - summary["abstained"],
                   api_failed=summary["failed"] - summary["missing"], pending=summary["missing"],
                   decision_coverage=decisions / summary["planned"],
                   commit_coverage=(decisions - summary["abstained"]) / summary["planned"],
                   abstain_coverage=summary["abstained"] / summary["planned"],
                   api_failure_coverage=(summary["failed"] - summary["missing"]) / summary["planned"],
                   missing_coverage=summary["missing"] / summary["planned"],
                   completed_definition="Resolved terminal outcome including API failure; missing remains incomplete.")
    result["native"] = {"turns": len(workflow["rounds"]), "request_count": len(metrics),
                        "attempt_count": _sum_numbers([m["attempts"] for m in metrics]),
                        "call_count": _sum_numbers([m["attempts"] for m in metrics]),
                        "call_count_basis": "Retained collector outbound attempts; imported/synthetic calls are unknown.",
                        "latency_ms": _sum_numbers([m["latency_ms"] for m in metrics]),
                        "usage": _sum_usage([m["usage"] for m in metrics]),
                        "cost": _sum_costs([m["cost"] for m in metrics]), "requests": metrics,
                        "live_verified": False}
    if "query_mode" in workflow:
        result["query_mode"] = workflow["query_mode"]
        result["query_mode_note"] = "Every local synthetic query is revealed and charged before the first native decision. These source reads are not provider calls."
    for row in result["episodes"]:
        row["native_requests"] = [{"round": m["round"], "request_id": m["request_id"]}
                                  for m in metrics if m["episode_id"] == row["id"]]
    if "schema_design" in workflow["suite"]:
        from . import schema_inquiry
        result["schema_audit"] = schema_inquiry.inspect_suite(workflow["suite"])
        for row in result["episodes"]:
            row["schema_evidence"] = schema_inquiry.episode_evidence(
                workflow["suite"], row, source_visible=workflow.get("query_mode") == "read-all")
        result["schema_weighting"] = "Condition on each schema projection group, then weight scenarios equally. Changing fields changes that conditional design; do not pool or compare across schemas."
    return result


def _comparison_input(value):
    value = _read(value)
    if value.get("schema") == SCHEMA:
        workflow, states, metrics = _rebuild(value)
        value = _run(workflow, states, metrics)
    result = evidence.replay(value)
    return value, result


def compare(left, right):
    """Strict full-plan paired losses; repeats/worlds do not add source clusters."""
    left_run, left_report = _comparison_input(left)
    right_run, right_report = _comparison_input(right)
    al.require(left_run["suite"] == right_run["suite"], "comparison requires identical frozen suite")
    identities = lambda run: [{k: v for k, v in p.items() if k != "policy"} for p in run["planned"]]
    al.require(identities(left_run) == identities(right_run), "comparison requires identical planned identities")
    scenarios = {s["id"]: s for s in left_run["suite"]["scenarios"]}
    rows = []
    keys, sides = ("query_cost", "terminal_loss", "total_loss"), ("left", "right", "delta_right_minus_left")
    for a, b in zip(left_report["episodes"], right_report["episodes"]):
        scenario = scenarios[a["scenario_id"]]
        prior = next(h["prior"] for h in scenario["hypotheses"] if h["id"] == a["world_id"])
        row = {"id": a["id"], "scenario_id": a["scenario_id"], "source_family": a["source_family"],
               "prior_weight": prior / left_run["replicates"],
               "fully_observed": not a["missing"] and not b["missing"],
               "terminal_decision_pair": not a["failed"] and not b["failed"],
               "left_missing": a["missing"], "right_missing": b["missing"]}
        for key in keys:
            row[key] = {"left": a[key], "right": b[key], "delta_right_minus_left": b[key] - a[key]}
        rows.append(row)

    def weighted(group):
        mass = sum(r["prior_weight"] for r in group)
        return {key: {side: sum(r["prior_weight"] * r[key][side] for r in group) / mass
                      for side in sides} for key in keys}

    def summary(group):
        families = sorted({r["source_family"] for r in group})
        family_means = [weighted([r for r in group if r["source_family"] == family]) for family in families]
        return {"planned": len(group), "fully_observed_pairs": sum(r["fully_observed"] for r in group),
                "terminal_decision_pairs": sum(r["terminal_decision_pair"] for r in group),
                "left_missing": sum(r["left_missing"] for r in group), "right_missing": sum(r["right_missing"] for r in group),
                "aggregation": "Top-level loss metrics weight enumerated planned rows equally (not prior sampling).",
                **{key: {side: sum(r[key][side] for r in group) / len(group) for side in sides} for key in keys},
                "prior_weighted_scenario_equal": weighted(group),
                "prior_weighted_family_equal": {key: {side: sum(f[key][side] for f in family_means) / len(family_means)
                                                       for side in sides} for key in keys}}

    return {"schema": COMPARE_SCHEMA, "left_policy": left_run["policy"], "right_policy": right_run["policy"],
            "evidence": {"left": comparison.evidence_origin(left_run), "right": comparison.evidence_origin(right_run),
                         "note": "Synthetic, imported and collector records retain distinct source claims; no live authentication."},
            "summary": summary(rows), "families": {family: summary([r for r in rows if r["source_family"] == family])
                for family in sorted({r["source_family"] for r in rows})},
            "scenarios": {sid: summary([r for r in rows if r["scenario_id"] == sid]) for sid in sorted(scenarios)},
            "episodes": rows,
            "weighting": "Within scenario: frozen hypothesis priors, equal repeats. Scenario-equal averages scenarios; family-equal first averages scenarios within family, then families.",
            "fully_observed_definition": "Both trajectories retain terminal outcomes, including API failure; terminal_decision_pairs excludes failures.",
            "interval": None, "interval_note": "No confidence interval: finite worlds/repeats share source families.",
            "live_verified": False}
