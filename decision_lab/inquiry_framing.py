"""Finite evidence sufficiency × caution framing experiment, without transport.

Only projected visible material enters native bodies. Retained rounds are replayed
against regenerated manifests. A partial snapshot can be inspected/replaced by a
monotonic collector update, but cannot prepare a fresh round.
"""
from __future__ import annotations

import base64
import copy
import json
from collections import Counter

from . import api_lab as al, collection
from .evidence_workflow import _read, _seal, _check_seal, _sum_numbers, _sum_usage, _sum_costs

SCHEMA = "decisions-lab.inquiry-framing/1"
DESIGN_SCHEMA = "decisions-lab.inquiry-framing-design/1"
CELLS = ("sufficient_neutral", "sufficient_warning", "missing_neutral", "missing_warning")
NOTICE = "The initial claim may be stale, misfiled, incomplete, unsupported, or correct."
FINALS = ("commit:allow", "commit:hold", "abstain")
LOSSES = {"query": 1, "wrong_commit": 10, "abstain": 3, "api_failure": 12}
QUERY_CONTRACT = ("query:record 只返回本题同一份原始记录的完整副本；不会带来更新、其他文档或额外条件。"
                  "如果完整记录已经出现在初始材料中，查询返回的原文与已见原文相同。"
                  "规则及该完整记录决定唯一的允许或不允许结论。")
INSTRUCTIONS = ("按公开规则选择一个列出的动作，最小化查询成本与终局损失之和。"
                "commit:allow 表示按规则允许，commit:hold 表示按规则不允许；"
                "abstain 是暂不作决定的业务动作；unknown 是无法返回动作的 API 状态。")


def build_design(seed=20261107):
    """Eight fixed authored templates; seed identifies scheduling, not random truth."""
    al.require(type(seed) is int, "seed must be an integer")
    authored = [
        ("inspection", "绝缘检查", "实测绝缘电阻大于或等于 12.5 MΩ 时允许启用，否则不允许。",
         "记录对象：青砾灯台备用电箱。", "实测绝缘电阻：15.0 MΩ。", "实测绝缘电阻：10.0 MΩ。"),
        ("quorum", "表决门槛", "九名有表决权的成员中，赞成票至少六票则允许通过，否则不允许。",
         "记录对象：澄湾展厅开馆提案；有表决权的成员共九名。", "本次赞成票数：七票。", "本次赞成票数：五票。"),
        ("permit-window", "许可时窗", "活动日落在 2026-01-10 至 2026-01-20（含两个端点）则允许入场，否则不允许。",
         "记录对象：白汀观测棚单次活动。", "活动日：2026-01-15。", "活动日：2026-01-21。"),
        ("signer", "签发人资格", "仅韩墨或许岚签发的记录允许归档；其他签发人均不允许。",
         "记录对象：松泽站设备交接单。", "签发人：韩墨。", "签发人：周砚。"),
        ("dual-condition", "双重条件", "只有封条完好且温度检查合格才允许接收；任一不满足则不允许。",
         "记录对象：星埠样品箱；封条状态：完好。", "温度检查：合格。", "温度检查：不合格。"),
        ("exception", "明示例外", "载重不超过十吨时允许通行；超过十吨时仅持有效救援证者允许，否则不允许。",
         "记录对象：岚桥通行车辆；载重：十四吨。", "救援证状态：有效。", "救援证状态：无救援证。"),
        ("resource-balance", "余额分配", "新增申请量不超过总配额减去已占用量时允许分配，否则不允许。",
         "记录对象：鹿原实验室耗材；总配额十八份，已占用七份。", "本次新增申请：九份。", "本次新增申请：十二份。"),
        ("reservation", "预约匹配", "原始预约记录的房间和开始时间均与本次申请完全一致时允许使用，否则不允许。",
         "本次申请：在 R3 房间于 10:00 开始使用；仅核对房间与开始时间。",
         "原始预约记录：R3 房间，10:00 开始。", "原始预约记录：R4 房间，10:00 开始。"),
    ]
    items = []
    for index, (ident, title, rule, common, yes, no) in enumerate(authored):
        items.append({"id": ident, "title": title, "rule": rule, "initial_text": common,
                      "preliminary_claim": "初步建议：允许。" if index % 2 == 0 else "初步建议：不允许。",
                      "worlds": [{"id": "a", "record": common + "\n" + yes, "gold": "commit:allow"},
                                 {"id": "b", "record": common + "\n" + no, "gold": "commit:hold"}]})
    return {"schema": DESIGN_SCHEMA, "seed": seed, "items": items, "cells": list(CELLS),
            "losses": dict(LOSSES), "query_contract": QUERY_CONTRACT, "notice": NOTICE}


def validate_design(design):
    al.require(isinstance(design, dict) and type(design.get("seed")) is int, "invalid framing design")
    al.require(al.digest(design) == al.digest(build_design(design["seed"])), "design differs from the authored revision-1 task contract")
    return design


def _planned(design, replicates):
    al.require(type(replicates) is int and replicates > 0, "replicates must be positive")
    return [{"id": f"{item['id']}.{world['id']}.{cell}.r{rep}", "item_id": item["id"],
             "world_id": world["id"], "cell": cell, "replicate": rep}
            for item in design["items"] for world in item["worlds"] for cell in CELLS for rep in range(replicates)]


def start(design, *, route="decisions", model=None, replicates=2):
    validate_design(design)
    al.require(route == "decisions", "inquiry framing currently supports native Decisions only")
    workflow = {"schema": SCHEMA, "design": copy.deepcopy(design), "route": route,
                "model": al.route_model(route, model), "replicates": replicates,
                "planned": _planned(design, replicates), "rounds": []}
    _manifest(workflow, _initial(workflow), 0)
    return _seal(workflow)


def _initial(workflow):
    return {p["id"]: {**copy.deepcopy(p), "first_status": "missing", "first_action": None,
                      "terminal_status": "missing", "terminal_action": None, "history": []}
            for p in workflow["planned"]}


def _task(workflow, plan):
    item = next(i for i in workflow["design"]["items"] if i["id"] == plan["item_id"])
    world = next(w for w in item["worlds"] if w["id"] == plan["world_id"])
    return item, world


def _visible(workflow, plan, turn):
    item, world = _task(workflow, plan)
    dossier = {"claim": item["preliminary_claim"],
               "source_text": world["record"] if plan["cell"].startswith("sufficient_") else item["initial_text"]}
    if plan["cell"].endswith("_warning"):
        dossier.update(provisional=True, notice=NOTICE)
    visible = {"rule": item["rule"], "initial_dossier": dossier, "query_contract": QUERY_CONTRACT,
               "losses": dict(LOSSES)}
    if turn == 1:
        visible.update(previous_action="query:record", revealed_record=world["record"])
    return visible


def _manifest(workflow, states, turn):
    if turn > 1:
        return None
    rows = []
    for index, plan in enumerate(workflow["planned"]):
        if turn == 1 and states[plan["id"]]["first_action"] != "query:record":
            continue
        actions = list(FINALS) + (["query:record"] if turn == 0 else [])
        rows.append({"id": f"f{index:04d}.t{turn}", "experiment": "inquiry-framing",
                     "input": json.dumps(_visible(workflow, plan, turn), ensure_ascii=False, sort_keys=True),
                     "questions": [{"id": "action", "type": "choice", "instructions": INSTRUCTIONS,
                                    "choices": [{"value": a, "description": a} for a in actions + ["unknown"]]}],
                     "rubric": {"questions": {"action": {"kind": "choice", "acceptable": actions}}},
                     "trial": {"unit_id": plan["id"], "source_family": plan["item_id"],
                               "condition": f"{plan['cell']}.t{turn}", "replicate": plan["replicate"],
                               "split": "development", "seed": workflow["design"]["seed"]}})
    if not rows:
        return None
    return al.prepare_payload(al.Suite({}, rows), rows, route="decisions", model=workflow["model"])


def _decode(source, expected):
    """Inspect partial native evidence. No parser or provider transport is added."""
    source = _read(source)
    _check_seal(source)
    synthetic = source.get("synthetic")
    al.require(synthetic is None or type(synthetic) is bool, "invalid synthetic marker")
    al.require(source.get("live_verified") is False, "invalid live provenance")
    provenance = source.get("provenance")
    entries, metrics, uncertain = [], {}, set()
    if source.get("schema") == al.RECORD_VERSION:
        al.require(provenance in ("synthetic", "imported") and (provenance != "synthetic" or synthetic is True),
                   "invalid native record provenance")
        manifest = source.get("manifest")
        entries = source.get("responses")
    else:
        al.require(source.get("schema") == collection.SCHEMA and provenance == "collector", "invalid native source")
        plan = source.get("plan")
        rows = collection.validate_plan(plan)
        al.require(plan["kind"] == "api-lab", "framing requires api-lab collection")
        manifest = plan["manifest"]
        al.require(source.get("endpoint") == manifest["endpoint"], "collection endpoint differs")
        ids = [r["id"] for r in rows]
        order = source.get("order")
        al.require(isinstance(order, list) and len(order) == len(ids) and set(order) == set(ids), "invalid schedule")
        al.require(isinstance(source.get("attempts"), list), "invalid attempts")
        grouped = {}
        for a in source["attempts"]:
            al.require(isinstance(a, dict) and a.get("request_id") in ids, "foreign attempt")
            group = grouped.setdefault(a["request_id"], [])
            al.require(type(a.get("attempt")) is int and a["attempt"] == len(group), "invalid attempt sequence")
            al.require(a.get("state") in ("in_flight", "ok", "http_error", "parse_error", "transport_error", "cancelled"),
                       "invalid attempt state")
            al.require(a.get("delivery") in ("uncertain", "response_received"), "invalid delivery state")
            if a.get("parse_status") == "parsed":
                try:
                    raw = json.loads(base64.b64decode(a["raw_body_base64"], validate=True).decode(),
                                     object_pairs_hook=collection._strict_pairs)
                except (KeyError, ValueError, UnicodeError) as exc:
                    raise al.ApiLabError("invalid retained raw bytes") from exc
                al.require(raw == a.get("parsed"), "parsed response differs from retained bytes")
            group.append(a)
        for ident, group in grouped.items():
            last = group[-1]
            if last["state"] == "in_flight" or last["delivery"] == "uncertain":
                uncertain.add(ident)
            else:
                entries.append({"request_id": ident, "response": last.get("parsed"), "http_status": last.get("http_status"),
                                **({"error": last["state"]} if last["state"] != "ok" else {})})
            metrics[ident] = {"attempts": len(group), "usage": _sum_usage([a.get("usage") for a in group]),
                              "latency_ms": _sum_numbers([a.get("elapsed_ms") for a in group]),
                              "cost": _sum_costs([a.get("cost") for a in group])}
    al.require(manifest == expected, "source manifest differs from the frozen current round")
    al.validate_manifest(manifest)
    al.validate_responses(entries, manifest, allow_partial=True)
    evaluated = al.evaluate(manifest, entries)
    by_id = {r["request_id"]: r for r in evaluated["requests"]}
    envelopes = {e["request_id"]: e for e in entries}
    if provenance != "collector":
        for m in evaluated["reported_request_usage"]:
            raw = envelopes[m["request_id"]].get("response")
            cost = m.get("cost") or (raw.get("cost") if isinstance(raw, dict) else None)
            metrics[m["request_id"]] = {"attempts": None, "usage": m.get("usage"), "cost": cost,
                                         "latency_ms": m.get("latency_ms")}
    decoded, native = [], []
    for request in manifest["requests"]:
        ident = request["id"]
        status, action = ("uncertain" if ident in uncertain else "missing"), None
        result = by_id.get(ident)
        if result is not None:
            q = result["questions"][0]
            status, action = q["outcome"], q.get("value")
            e = envelopes[ident]
            if q.get("detail") == "missing answer" or (e.get("response") is None and not e.get("error")
                    and (e.get("http_status") is None or 200 <= e["http_status"] < 300)):
                status, action = "missing", None
            elif result["contract_issues"]:
                status, action = "error", None
            elif status == "ok" and action == "unknown":
                status, action = "unknown", None
        decoded.append({"episode_id": request["trial"]["unit_id"], "status": status, "action": action})
        if ident in metrics:
            metric = {"request_id": ident, "episode_id": request["trial"]["unit_id"],
                      "provenance": provenance, "synthetic": synthetic, **metrics[ident]}
            if synthetic is True:
                metric.update(usage=None, cost=None, latency_ms=None)
            native.append(metric)
    return source, decoded, native


def _rebuild(value):
    w = _read(value)
    al.require(w.get("schema") == SCHEMA, "invalid framing workflow")
    al.require(set(w) == {"schema", "design", "route", "model", "replicates", "planned", "rounds", "evidence_digest"},
               "unexpected workflow fields")
    _check_seal(w)
    validate_design(w["design"])
    al.require(w["route"] == "decisions" and w["model"] == al.route_model("decisions", w["model"]), "invalid route/model")
    al.require(al.digest(w["planned"]) == al.digest(_planned(w["design"], w["replicates"])), "planned identities changed")
    al.require(isinstance(w["rounds"], list) and len(w["rounds"]) <= 2, "invalid round count")
    states, metrics, pending = _initial(w), [], None
    for turn, source in enumerate(w["rounds"]):
        expected = _manifest(w, states, turn)
        al.require(expected is not None, "round after terminal completion")
        _, decoded, native = _decode(source, expected)
        incomplete = any(x["status"] in ("missing", "uncertain") for x in decoded)
        if incomplete:
            al.require(turn == len(w["rounds"]) - 1, "new round after unresolved evidence")
            pending = expected
        for row in decoded:
            state = states[row["episode_id"]]
            status, action = row["status"], row["action"]
            if turn == 0:
                state.update(first_status=status, first_action=action if status == "ok" else None)
            if status in ("missing", "uncertain"):
                state["terminal_status"] = status
                continue
            state["history"].append({"round": turn, "status": status, "action": action})
            if status != "ok":
                state.update(terminal_status=status, terminal_action=None)
            elif action == "query:record":
                al.require(turn == 0, "second query is illegal")
            else:
                al.require(action in FINALS, "illegal terminal action")
                state.update(terminal_status="ok", terminal_action=action)
        metrics.extend({"round": turn, **m} for m in native)
    return w, states, metrics, pending


def prepare_round(workflow):
    w, states, _, pending = _rebuild(workflow)
    al.require(pending is None, "round remains pending; resume/resolve its retained collection, then apply it again")
    return _manifest(w, states, len(w["rounds"]))


def apply_round(workflow, collection_or_record):
    w, states, _, pending = _rebuild(workflow)
    expected = pending or _manifest(w, states, len(w["rounds"]))
    al.require(expected is not None, "all episodes terminal")
    source, _, _ = _decode(collection_or_record, expected)
    if pending is not None:
        old = w["rounds"][-1]
        al.require(source.get("schema") == old.get("schema") and source.get("provenance") == old.get("provenance")
                   and source.get("synthetic") == old.get("synthetic"), "pending source provenance changed")
        if source["schema"] == collection.SCHEMA:
            before = old["attempts"]
            after = source["attempts"]
            al.require(len(after) >= len(before), "pending attempts removed")
            for a, b in zip(before, after):
                if a["state"] == "in_flight" or a["delivery"] == "uncertain":
                    al.require((a["request_id"], a["attempt"]) == (b["request_id"], b["attempt"]), "pending identity changed")
                else:
                    al.require(a == b, "received attempt changed")
        else:
            after = {e["request_id"]: e for e in source["responses"]}
            al.require(all(after.get(e["request_id"]) == e for e in old["responses"]), "received response changed")
        w["rounds"][-1] = source
    else:
        w["rounds"].append(source)
    w = _seal(w)
    _rebuild(w)
    return w


def _stats(episodes):
    n = len(episodes)
    first = Counter(e["first_status"] for e in episodes)
    terminal = Counter(e["terminal_status"] for e in episodes)
    counts = {"query": sum(e["first_action"] == "query:record" for e in episodes),
              "abstain": sum(e["first_action"] == "abstain" for e in episodes),
              "correct_direct_commit": sum(e["first_action"] == e["gold"] for e in episodes),
              "supported_direct_commit": sum(e["first_action"] == e["gold"] and e["cell"].startswith("sufficient_") for e in episodes),
              "unsupported_direct_commit": sum(e["first_action"] in FINALS[:2] and
                  (e["cell"].startswith("missing_") or e["first_action"] != e["gold"]) for e in episodes)}
    correct = sum(e["correct_commit"] for e in episodes)
    wrong = sum(e["wrong_commit"] for e in episodes)
    abstained = sum(e["terminal_action"] == "abstain" for e in episodes)
    failed = sum(terminal[s] for s in ("error", "unknown", "refusal"))
    missing = terminal["missing"] + terminal["uncertain"]
    terminal_loss = correct * 0 + wrong * LOSSES["wrong_commit"] + abstained * LOSSES["abstain"] + failed * LOSSES["api_failure"]
    return {"planned": n, "first_observed": first["ok"], "first_unobservable": n - first["ok"],
            "first_statuses": dict(first), "first_counts": counts,
            "first_query_rate": counts["query"] / n if n and first["ok"] == n else None,
            "first_abstain_rate": counts["abstain"] / n if n and first["ok"] == n else None,
            "completed": n - missing, "missing": missing, "terminal_statuses": dict(terminal),
            "correct_commit": correct, "wrong_commit": wrong, "abstained": abstained, "api_failed": failed,
            "query_count": counts["query"], "query_cost": counts["query"] * LOSSES["query"],
            "observed_terminal_loss": terminal_loss, "terminal_loss": terminal_loss if not missing else None,
            "total_loss": terminal_loss + counts["query"] * LOSSES["query"] if not missing else None}


def _effects(episodes):
    by_pair = {}
    for e in episodes:
        key = (e["item_id"], e["world_id"], e["replicate"])
        by_pair.setdefault(key, {})[e["cell"]] = e
    al.require(all(set(v) == set(CELLS) for v in by_pair.values()), "unbalanced factorial pairing")
    contrasts = {"warning_sufficient": {"sufficient_warning": 1, "sufficient_neutral": -1},
                 "warning_missing": {"missing_warning": 1, "missing_neutral": -1},
                 "missing_minus_sufficient_neutral": {"missing_neutral": 1, "sufficient_neutral": -1},
                 "missing_minus_sufficient_warning": {"missing_warning": 1, "sufficient_warning": -1},
                 "interaction": {"missing_warning": 1, "missing_neutral": -1, "sufficient_warning": -1, "sufficient_neutral": 1}}
    result = {}
    for name, weights in contrasts.items():
        observed = [group for group in by_pair.values() if all(group[c]["first_status"] == "ok" for c in weights)]
        value = (sum(sum(weight * int(group[c]["first_action"] == "query:record") for c, weight in weights.items())
                     for group in observed) / len(by_pair)) if len(observed) == len(by_pair) else None
        result[name] = {"query_rate_difference": value, "planned_pairs": len(by_pair), "observed_pairs": len(observed)}
    return result


def report(workflow):
    w, states, metrics, pending = _rebuild(workflow)
    episodes = []
    for state in states.values():
        _, world = _task(w, state)
        commit = state["terminal_status"] == "ok" and state["terminal_action"] in FINALS[:2]
        episodes.append({**state, "gold": world["gold"], "correct_commit": bool(commit and state["terminal_action"] == world["gold"]),
                         "wrong_commit": bool(commit and state["terminal_action"] != world["gold"]),
                         "correct": state["terminal_action"] == world["gold"] if commit else None})
    cells = {c: _stats([e for e in episodes if e["cell"] == c]) for c in CELLS}
    families = {}
    for item in w["design"]["items"]:
        subset = [e for e in episodes if e["item_id"] == item["id"]]
        families[item["id"]] = {"title": item["title"], "cells": {c: _stats([e for e in subset if e["cell"] == c]) for c in CELLS},
                                "effects": _effects(subset)}
    markers = [m["synthetic"] for m in metrics]
    synthetic = True if markers and all(v is True for v in markers) else False if markers and all(v is False for v in markers) else None
    return {"schema": "decisions-lab.inquiry-framing-report/1", "summary": _stats(episodes), "cells": cells,
            "families": families, "effects": _effects(episodes), "episodes": episodes, "pending_round": pending is not None,
            "synthetic": synthetic, "live_verified": False,
            "native": {"request_count": len(metrics), "call_count": _sum_numbers([m["attempts"] for m in metrics]),
                       "usage": _sum_usage([m["usage"] for m in metrics]), "cost": _sum_costs([m["cost"] for m in metrics]),
                       "latency_ms": _sum_numbers([m["latency_ms"] for m in metrics]), "requests": metrics},
            "scope": "Eight authored templates; worlds/repeats correlated. No population intervals or model ranking. Source markers are not live certification."}


def demo(design, *, replicates=2, policy="oracle", route="decisions", model=None):
    al.require(policy in ("oracle", "always-query", "stop"), "unknown synthetic control")
    w = start(design, route=route, model=model, replicates=replicates)
    while (manifest := prepare_round(w)) is not None:
        entries = al.synthetic_entries(manifest)
        for request, entry in zip(manifest["requests"], entries):
            plan = next(p for p in w["planned"] if p["id"] == request["trial"]["unit_id"])
            _, world = _task(w, plan)
            initial = ".t0" in request["trial"]["condition"]
            missing = plan["cell"].startswith("missing_")
            action = ("query:record" if initial and (policy == "always-query" or policy == "oracle" and missing)
                      else "abstain" if initial and policy == "stop" and missing else world["gold"])
            answer = entry["response"]["answers"][0]
            answer.update(choice=action, confidence=1.0)
            for p in answer["probabilities"]:
                p["probability"] = float(p["value"] == action)
        w = apply_round(w, al.build_record(manifest, entries, provenance="synthetic"))
    return w
