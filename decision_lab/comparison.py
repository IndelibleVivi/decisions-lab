"""Offline paired comparisons. No provider calls or third-party dependencies."""
from __future__ import annotations

from collections import Counter, defaultdict
import copy
import math
import random
from statistics import mean

SCHEMA = "decisions-lab.run-ledger/1"
PLAN_SCHEMA = "decisions-lab.analysis-plan/1"
OUTCOMES = {"ok", "unknown", "refusal", "error", "missing"}
KEY_FIELDS = ("unit_id", "condition", "replicate", "question_id")


class ComparisonError(ValueError):
    """Invalid or incomparable analysis inputs."""


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _rows(rows):
    return rows.get("trials", []) if isinstance(rows, dict) else list(rows)


def _validate(rows):
    keys, families, splits = set(), {}, {}
    for row in rows:
        if not isinstance(row, dict):
            raise ComparisonError("trial must be an object")
        for field in (*KEY_FIELDS, "source_family", "split", "request_id"):
            if field not in row or row[field] is None:
                raise ComparisonError(f"trial missing {field}")
        for field in ("unit_id", "condition", "question_id", "source_family", "split", "request_id"):
            if not isinstance(row[field], str) or not row[field]:
                raise ComparisonError(f"trial {field} must be nonempty text")
        if type(row["replicate"]) is not int or row["replicate"] < 0:
            raise ComparisonError("trial replicate must be a nonnegative integer")
        key = tuple(row[f] for f in KEY_FIELDS)
        try:
            duplicate = key in keys
            keys.add(key)
        except TypeError as exc:
            raise ComparisonError("trial identity fields must be hashable") from exc
        if duplicate:
            raise ComparisonError(f"duplicate trial key: {key!r}")
        unit, family, split = row["unit_id"], row["source_family"], row["split"]
        try:
            hash((unit, family, split, row["request_id"]))
        except TypeError as exc:
            raise ComparisonError("trial grouping fields must be hashable") from exc
        if unit in families and families[unit] != family:
            raise ComparisonError("unit source_family mapping differs")
        if family in splits and splits[family] != split:
            raise ComparisonError("source_family cannot span splits")
        families[unit], splits[family] = family, split
        if row.get("outcome") not in OUTCOMES:
            raise ComparisonError("invalid outcome")
        if row.get("correct") is not None and not isinstance(row["correct"], bool):
            raise ComparisonError("correct must be boolean or null")
        if row["outcome"] != "ok" and row.get("correct") is not None:
            raise ComparisonError("non-ok trial cannot claim correctness")
        for field in ("loss", "confidence", "latency_ms"):
            value = row.get(field)
            if value is not None and (not _number(value) or value < 0):
                raise ComparisonError(f"invalid {field}")
        if row.get("confidence") is not None and row["confidence"] > 1:
            raise ComparisonError("confidence must be within [0, 1]")
    return families, splits


def _filtered(rows, split=None, condition=None):
    return [r for r in rows if (split is None or r["split"] == split)
            and (condition is None or r["condition"] == condition)]


def _loss(row, failure_loss):
    if row["outcome"] != "ok":
        return failure_loss
    if row.get("loss") is not None:
        return float(row["loss"])
    if row.get("correct") is not None:
        return float(not row["correct"])
    raise ComparisonError("ok trial needs loss or correct for workflow loss")


def _summary(rows, failure_loss):
    counts = Counter(r["outcome"] for r in rows)
    answered = [r for r in rows if r["outcome"] == "ok" and r.get("correct") is not None]
    # Error is a distinct metric; unknown correctness never becomes an error label.
    error_known = all(r["outcome"] != "ok" or r.get("correct") is not None for r in rows)
    return {"planned": len(rows), "outcomes": {k: counts[k] for k in sorted(OUTCOMES)},
            "workflow_loss": mean(_loss(r, failure_loss) for r in rows) if rows else None,
            "error_loss": mean(float(not r["correct"]) if r["outcome"] == "ok" else failure_loss
                               for r in rows) if rows and error_known else None,
            "conditional_accuracy": mean(r["correct"] for r in answered) if answered else None,
            "conditional_accuracy_n": len(answered)}


def _request_metrics(ledger, selected_rows):
    ids = {r["request_id"] for r in selected_rows if r["request_id"] is not None}
    requests = ledger.get("requests")
    if requests is None:
        grouped = defaultdict(list)
        for r in selected_rows:
            grouped[r["request_id"]].append(r)
        requests = []
        for request_id, group in grouped.items():
            values = {}
            for field in ("latency_ms", "cost"):
                known = [r[field] for r in group if r.get(field) is not None]
                if known and any(v != known[0] for v in known):
                    raise ComparisonError(f"inconsistent request {field}")
                values[field] = known[0] if known else None
            requests.append({"request_id": request_id, **values})
    if not isinstance(requests, list):
        raise ComparisonError("requests must be an array")
    chosen, seen = [], set()
    for req in requests:
        request_id = req.get("request_id")
        if request_id in seen:
            raise ComparisonError("duplicate request metrics")
        seen.add(request_id)
        if request_id in ids:
            chosen.append(req)
    chosen.extend({"request_id": rid} for rid in ids - seen)
    latencies = [r.get("latency_ms") for r in chosen]
    if any(v is not None and (not _number(v) or v < 0) for v in latencies):
        raise ComparisonError("invalid request latency")
    costs, units = [], set()
    for req in chosen:
        cost = req.get("cost")
        if cost is None:
            costs.append(None)
        elif isinstance(cost, dict):
            amount, unit = cost.get("amount"), cost.get("currency")
            if not _number(amount) or amount < 0 or not isinstance(unit, str) or not unit:
                raise ComparisonError("invalid request cost")
            costs.append(float(amount))
            units.add(unit)
        elif _number(cost) and cost >= 0:
            costs.append(float(cost))
            units.add(None)  # Bare amounts have no safely aggregable currency.
        else:
            raise ComparisonError("invalid request cost")
    complete_cost = bool(chosen) and all(v is not None for v in costs) and len(units) == 1 and None not in units
    complete_latency = bool(chosen) and all(v is not None for v in latencies)
    return {"requests": len(chosen), "latency_ms_total": sum(latencies) if complete_latency else None,
            "latency_ms_mean": mean(latencies) if complete_latency else None,
            "latency_known_requests": sum(v is not None for v in latencies),
            "cost_total": sum(costs) if complete_cost else None,
            "cost_currency": next(iter(units)) if complete_cost else None,
            "cost_known_requests": sum(v is not None for v in costs),
            "scope": "whole requests touching selected trials; shared request usage counted once"}


def freeze_analysis_plan(*, dataset_id, comparison, metric="workflow_loss", failure_loss=1.0,
                         split="test", condition=None, calibration_split="calibration",
                         threshold=None):
    """Return a JSON plan to save BEFORE viewing test outcomes; no inference of timing."""
    plan = {"schema": PLAN_SCHEMA, "dataset_id": copy.deepcopy(dataset_id),
            "comparison": list(comparison), "metric": metric, "failure_loss": failure_loss,
            "split": split, "condition": condition, "calibration_split": calibration_split,
            "threshold": threshold, "threshold_selection_split": calibration_split if threshold is not None else None,
            "unit_aggregation": "unit_id", "cluster": "source_family", "delta": "right-left"}
    _check_plan(plan)
    return plan


def _check_plan(plan):
    if plan.get("schema") != PLAN_SCHEMA or plan.get("dataset_id") is None:
        raise ComparisonError("analysis plan needs schema and dataset_id")
    if not isinstance(plan.get("comparison"), list) or len(plan["comparison"]) != 2:
        raise ComparisonError("plan comparison must contain left and right run_id")
    if plan.get("metric") not in {"workflow_loss", "error_loss"}:
        raise ComparisonError("unsupported planned metric")
    if not _number(plan.get("failure_loss")) or plan["failure_loss"] < 0:
        raise ComparisonError("invalid planned failure_loss")
    if plan.get("split") != "test" or plan.get("calibration_split") != "calibration":
        raise ComparisonError("confirmatory plan requires calibration/test separation")
    if plan.get("threshold") is not None:
        if not _number(plan["threshold"]) or not 0 <= plan["threshold"] <= 1:
            raise ComparisonError("invalid planned threshold")
        if plan.get("threshold_selection_split") != "calibration":
            raise ComparisonError("test threshold tuning is forbidden")
    if plan.get("unit_aggregation") != "unit_id" or plan.get("cluster") != "source_family" or plan.get("delta") != "right-left":
        raise ComparisonError("unsupported analysis design")


def _meta(ledger, field):
    return ledger.get(field, ledger.get("metadata", {}).get(field))


def compare_runs(left, right, *, seed=0, bootstrap_samples=2000, failure_loss=1.0,
                 split=None, condition=None, min_clusters=8, plan=None, metric=None):
    """Pair all planned keys; positive delta means right has higher loss.

    Union keys retain unpaired trials as explicit missing counterparts. The
    primary estimate weights units equally, averaging all variants/repeats first.
    """
    if not _number(failure_loss) or failure_loss < 0:
        raise ComparisonError("failure_loss must be finite and nonnegative")
    if isinstance(bootstrap_samples, bool) or not isinstance(bootstrap_samples, int) or bootstrap_samples < 1:
        raise ComparisonError("bootstrap_samples must be a positive integer")
    if isinstance(min_clusters, bool) or not isinstance(min_clusters, int) or min_clusters < 8:
        raise ComparisonError("min_clusters must be at least 8")
    for ledger in (left, right):
        if ledger.get("schema") != SCHEMA or not isinstance(ledger.get("trials"), list):
            raise ComparisonError("expected normalized run ledger")
    lf, ls = _validate(left["trials"])
    rf, rs = _validate(right["trials"])
    if any(lf[u] != rf[u] for u in lf.keys() & rf.keys()):
        raise ComparisonError("source_family mapping differs across runs")
    if any(ls[f] != rs[f] for f in ls.keys() & rs.keys()):
        raise ComparisonError("source_family split mapping differs across runs")
    ld, rd = _meta(left, "dataset_id"), _meta(right, "dataset_id")
    if ld is not None and rd is not None and ld != rd:
        raise ComparisonError("dataset_id differs across runs")
    if metric is not None and metric not in {"workflow_loss", "error_loss"}:
        raise ComparisonError("unsupported metric")
    if plan is not None:
        _check_plan(plan)
        if ld != plan["dataset_id"] or rd != plan["dataset_id"]:
            raise ComparisonError("dataset_id differs from frozen plan")
        if [_meta(left, "run_id"), _meta(right, "run_id")] != plan["comparison"]:
            raise ComparisonError("comparison differs from frozen plan")
        if failure_loss != plan["failure_loss"] or (split is not None and split != plan["split"]) or (condition is not None and condition != plan["condition"]):
            raise ComparisonError("analysis parameters differ from frozen plan")
        if metric is not None and metric != plan["metric"]:
            raise ComparisonError("metric differs from frozen plan")
        split, condition, metric = plan["split"], plan["condition"], plan["metric"]
    metric = metric or "workflow_loss"
    a = _filtered(left["trials"], split, condition)
    b = _filtered(right["trials"], split, condition)
    if plan is not None and plan.get("threshold") is not None:
        def apply_threshold(row):
            if row["outcome"] == "ok" and (row.get("confidence") is None or row["confidence"] < plan["threshold"]):
                return {**row, "original_outcome": "ok", "outcome": "unknown", "correct": None, "loss": None}
            return row
        a, b = [apply_threshold(r) for r in a], [apply_threshold(r) for r in b]
    ai = {tuple(r[f] for f in KEY_FIELDS): r for r in a}
    bi = {tuple(r[f] for f in KEY_FIELDS): r for r in b}
    keys = sorted(ai.keys() | bi.keys(), key=repr)
    trace, units, aligned_a, aligned_b = [], defaultdict(list), [], []
    for key in keys:
        ar, br = ai.get(key), bi.get(key)
        template = ar if ar is not None else br
        missing = {**template, "request_id": None, "outcome": "missing", "correct": None,
                   "loss": None, "confidence": None, "latency_ms": None, "cost": None}
        ar, br = ar if ar is not None else missing, br if br is not None else missing
        al, bl = _loss(ar, failure_loss), _loss(br, failure_loss)
        if metric == "error_loss":
            for row in (ar, br):
                if row["outcome"] == "ok" and row.get("correct") is None:
                    raise ComparisonError("planned error_loss requires correctness for every ok trial")
            al = float(not ar["correct"]) if ar["outcome"] == "ok" else failure_loss
            bl = float(not br["correct"]) if br["outcome"] == "ok" else failure_loss
        units[template["unit_id"]].append((template["source_family"], al, bl))
        aligned_a.append(ar)
        aligned_b.append(br)
        trace.append({**dict(zip(KEY_FIELDS, key)), "source_family": template["source_family"],
                      "split": template["split"], "left_request_id": ar["request_id"],
                      "right_request_id": br["request_id"], "left_outcome": ar["outcome"],
                      "right_outcome": br["outcome"], "left_original_outcome": ar.get("original_outcome", ar["outcome"]),
                      "right_original_outcome": br.get("original_outcome", br["outcome"]),
                      "left_correct": ar.get("correct"), "right_correct": br.get("correct"),
                      "left_confidence": ar.get("confidence"), "right_confidence": br.get("confidence"),
                      "left_loss": al, "right_loss": bl,
                      "delta": bl - al, "paired": key in ai and key in bi})
    unit_rows = [{"unit_id": u, "source_family": rows[0][0], "trials": len(rows),
                  "left_loss": mean(r[1] for r in rows), "right_loss": mean(r[2] for r in rows),
                  "delta": mean(r[2] - r[1] for r in rows)}
                 for u, rows in sorted(units.items(), key=lambda item: repr(item[0]))]
    clusters = defaultdict(list)
    for row in unit_rows:
        clusters[row["source_family"]].append(row["delta"])
    families = sorted(clusters, key=repr)
    ci = None
    reason = "fewer than min_clusters source families; descriptive only"
    if len(families) >= min_clusters:
        rng = random.Random(seed)
        draws = []
        for _ in range(bootstrap_samples):
            values = [v for _ in families for v in clusters[rng.choice(families)]]
            draws.append(mean(values))
        draws.sort()
        def percentile(p):
            x = (len(draws) - 1) * p
            lo = int(x)
            return draws[lo] + (draws[min(lo + 1, len(draws) - 1)] - draws[lo]) * (x - lo)
        ci = [percentile(.025), percentile(.975)]
        reason = None
    return {"schema": "decisions-lab.comparison/1", "metric": metric, "delta_direction": "right-left",
            "failure_loss": failure_loss, "split": split, "condition": condition,
            "planned": len(keys), "paired": len(ai.keys() & bi.keys()),
            "left_only": len(ai.keys() - bi.keys()), "right_only": len(bi.keys() - ai.keys()),
            "left": _summary(aligned_a, failure_loss), "right": _summary(aligned_b, failure_loss),
            "left_request_metrics": _request_metrics(left, a), "right_request_metrics": _request_metrics(right, b),
            "estimate": {"left_loss": mean(r["left_loss"] for r in unit_rows) if unit_rows else None,
                         "right_loss": mean(r["right_loss"] for r in unit_rows) if unit_rows else None,
                         "delta": mean(r["delta"] for r in unit_rows) if unit_rows else None,
                         "units": len(unit_rows), "clusters": len(families), "ci95": ci,
                         "inference": "cluster-bootstrap" if ci is not None else "descriptive-only",
                         "reason": reason, "seed": seed, "bootstrap_samples": bootstrap_samples},
            "units": unit_rows, "trace": trace, "analysis_plan": copy.deepcopy(plan)}


def risk_coverage(rows):
    """Confidence thresholds with ties admitted together; failures stay in denominator.

    Only ok rows with valid correctness and confidence are selectable. A null
    confidence or unknown outcome is never converted into confidence zero.
    Risk is classification error; loss is separately observed workflow loss.
    """
    rows = _rows(rows)
    _validate(rows)
    eligible = [r for r in rows if r["outcome"] == "ok" and r.get("correct") is not None
                and r.get("confidence") is not None]
    result, selected = [], []
    grouped = defaultdict(list)
    for row in eligible:
        grouped[row["confidence"]].append(row)
    for score in sorted(grouped, reverse=True):
        selected.extend(grouped[score])
        result.append({"threshold": score, "selected": len(selected), "planned": len(rows),
                       "coverage": len(selected) / len(rows),
                       "risk": mean(not r["correct"] for r in selected),
                       "loss": mean(_loss(r, 1.0) for r in selected)})
    return result


def _require_split(rows, split):
    rows = _rows(rows)
    _validate(rows)
    if not rows or any(r["split"] != split for r in rows):
        raise ComparisonError(f"threshold operation requires only {split} split")
    return rows


def select_threshold(rows, *, target_risk=0.1):
    """Max empirical coverage meeting calibration risk; no risk guarantee."""
    if not _number(target_risk) or not 0 <= target_risk <= 1:
        raise ComparisonError("target_risk must be within [0, 1]")
    rows = _require_split(rows, "calibration")
    feasible = [p for p in risk_coverage(rows) if p["risk"] <= target_risk]
    point = feasible[-1] if feasible else None
    return {"threshold": point["threshold"] if point else None, "selection_split": "calibration",
            "source_families": sorted({r["source_family"] for r in rows}, key=repr),
            "target_risk": target_risk, "calibration": point, "risk_guarantee": False,
            "reject_all": point is None}


def evaluate_threshold(rows, threshold):
    """Apply a calibration selection object, unchanged, to held-out test rows."""
    rows = _require_split(rows, "test")
    if not isinstance(threshold, dict) or threshold.get("selection_split") != "calibration":
        raise ComparisonError("requires a calibration threshold selection object")
    if set(threshold.get("source_families", [])) & {r["source_family"] for r in rows}:
        raise ComparisonError("calibration and test source families overlap")
    value = threshold.get("threshold")
    if value is not None and (not _number(value) or not 0 <= value <= 1):
        raise ComparisonError("invalid threshold")
    selected = [r for r in rows if value is not None and r["outcome"] == "ok"
                and r.get("correct") is not None and r.get("confidence") is not None
                and r["confidence"] >= value]
    return {"threshold": value, "evaluation_split": "test", "planned": len(rows),
            "selected": len(selected), "coverage": len(selected) / len(rows),
            "risk": mean(not r["correct"] for r in selected) if selected else None,
            "loss": mean(_loss(r, 1.0) for r in selected) if selected else None,
            "risk_guarantee": False}
