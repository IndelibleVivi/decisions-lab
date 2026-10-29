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
        for field in ("loss", "confidence", "latency_ms", "retained_failure_loss"):
            value = row.get(field)
            if value is not None and (not _number(value) or value < 0):
                raise ComparisonError(f"invalid {field}")
        measure = row.get("measurement")
        if measure is not None:
            if (not isinstance(measure, dict) or any(not isinstance(measure.get(k), str) or not measure[k]
                                                     for k in ("id", "unit", "semantics"))):
                raise ComparisonError("invalid measurement definition")
            value = measure.get("value")
            if value is not None and (not _number(value) or value < 0):
                raise ComparisonError("invalid measurement value")
            if row["outcome"] != "ok" and value is not None:
                raise ComparisonError("non-ok measurement must remain null")
            if row["outcome"] == "ok" and value != row.get("loss"):
                raise ComparisonError("measurement value differs from loss")
        signal = row.get("selection_signal")
        if signal is not None:
            if (not isinstance(signal, dict) or any(not isinstance(signal.get(k), str) or not signal[k]
                                                    for k in ("id", "semantics"))
                    or type(signal.get("formula_known")) is not bool
                    or signal.get("value") != row.get("confidence")):
                raise ComparisonError("invalid selection signal or confidence mismatch")
        if row.get("confidence") is not None and row["confidence"] > 1:
            raise ComparisonError("confidence must be within [0, 1]")
    return families, splits


def _filtered(rows, split=None, condition=None):
    return [r for r in rows if (split is None or r["split"] == split)
            and (condition is None or r["condition"] == condition)]


def _loss(row, failure_loss):
    if row["outcome"] != "ok":
        retained = row.get("retained_failure_loss")
        if retained is not None and not math.isclose(retained, failure_loss, rel_tol=0, abs_tol=1e-12):
            raise ComparisonError("failure_loss differs from retained task loss; use the frozen retained_failure_loss")
        return failure_loss
    if row.get("loss") is not None:
        return float(row["loss"])
    if row.get("correct") is not None:
        return float(not row["correct"])
    raise ComparisonError("ok trial needs loss or correct for workflow loss")


def evidence_origin(run):
    """Keep source claims visible; a comparison cannot authenticate live calls."""
    synthetic = run.get("synthetic")
    if synthetic is not None and type(synthetic) is not bool:
        raise ComparisonError("synthetic provenance must be boolean or null")
    return {"provenance": run.get("provenance"), "synthetic": synthetic,
            "route": run.get("route"), "requested_model": run.get("requested_model"),
            "source_records": copy.deepcopy(run.get("source_records")), "live_verified": False}


def _summary(rows, failure_loss):
    counts = Counter(r["outcome"] for r in rows)
    answered = [r for r in rows if r["outcome"] == "ok" and r.get("correct") is not None]
    # Error is a distinct metric; unknown correctness never becomes an error label.
    error_known = all(r["outcome"] != "ok" or r.get("correct") is not None for r in rows)
    role_rows = [r for r in rows if r.get("metric") == "role_workflow_loss"]
    return {"planned": len(rows), "outcomes": {k: counts[k] for k in sorted(OUTCOMES)},
            "role_metrics": {"planned": len(role_rows),
                             "unsafe": sum(r.get("unsafe") is True for r in role_rows),
                             "guard_rejected": sum(r.get("guard_rejected") is True for r in role_rows)} if role_rows else None,
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
                         threshold=None, selection_signal=None):
    """Return a JSON plan to save BEFORE viewing test outcomes; no inference of timing."""
    plan = {"schema": PLAN_SCHEMA, "dataset_id": copy.deepcopy(dataset_id),
            "comparison": list(comparison), "metric": metric, "failure_loss": failure_loss,
            "split": split, "condition": condition, "calibration_split": calibration_split,
            "threshold": threshold, "threshold_selection_split": calibration_split if threshold is not None else None,
            "unit_aggregation": "unit_id", "cluster": "source_family", "delta": "right-left"}
    if selection_signal is not None:
        plan["selection_signal"] = copy.deepcopy(selection_signal)
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
    signal = plan.get("selection_signal")
    if signal is not None and (not isinstance(signal, dict) or "value" in signal
            or any(not isinstance(signal.get(k), str) or not signal[k] for k in ("id", "semantics"))
            or type(signal.get("formula_known")) is not bool):
        raise ComparisonError("invalid planned selection signal")
    if plan.get("threshold") is not None:
        if not _number(plan["threshold"]) or not 0 <= plan["threshold"] <= 1:
            raise ComparisonError("invalid planned threshold")
        if plan.get("threshold_selection_split") != "calibration":
            raise ComparisonError("test threshold tuning is forbidden")
    if plan.get("unit_aggregation") != "unit_id" or plan.get("cluster") != "source_family" or plan.get("delta") != "right-left":
        raise ComparisonError("unsupported analysis design")


def _meta(ledger, field):
    return ledger.get(field, ledger.get("metadata", {}).get(field))


def _scientific_tasks(run):
    # Recompute from retained native input, never trust caller-authored task IDs.
    from . import ledger as ledger_module
    try:
        native = run["native_manifest"]
        projected = ledger_module.from_api(native, [])
    except (KeyError, ValueError, TypeError) as exc:
        raise ComparisonError("scientific pairing requires a valid retained native manifest") from exc
    if (run.get("dataset_id") != projected["dataset_id"]
            or run.get("manifest_digest") != projected["manifest_digest"]
            or run.get("route") != projected["route"]
            or run.get("requested_model") != projected["requested_model"]
            or run.get("treatment") != projected["treatment"]
            or run.get("native_execution") != projected["native_execution"]
            or run.get("task_contracts") != projected["task_contracts"]):
        raise ComparisonError("native identity or task contract differs from retained manifest")
    contracts = {r["request_id"]: r["contract"] for r in projected["task_contracts"]}
    expected = {tuple(r[f] for f in KEY_FIELDS): r for r in projected["trials"]}
    actual = {tuple(r[f] for f in KEY_FIELDS): r for r in run["trials"]}
    if actual.keys() != expected.keys():
        raise ComparisonError("scientific pairing requires the full native planned set")
    tasks = {}
    for key, row in actual.items():
        ref = expected[key]
        if any(row.get(f) != ref.get(f) for f in (*KEY_FIELDS, "request_id", "source_family", "split", "seed")):
            raise ComparisonError("trial identity differs from retained native task")
        declared = {k: v for k, v in row.get("measurement", {}).items() if k != "value"}
        intended = {k: v for k, v in ref["measurement"].items() if k != "value"}
        if declared != intended:
            raise ComparisonError("measurement differs from retained task")
        tasks[key] = {"request_id": row["request_id"], "question_id": row["question_id"],
                      "contract": contracts[row["request_id"]],
                      "source_family": row["source_family"], "split": row["split"], "seed": row.get("seed")}
    return tasks


def make_pairing_spec(left_ledger, right_ledger):
    """Freeze explicit scientific alignment, independent of response availability.

    Native dataset and execution identities remain intact. This is an inspectable
    contract, not authentication or proof of preregistration.
    """
    for run in (left_ledger, right_ledger):
        _validate(run["trials"])
    a, b = _scientific_tasks(left_ledger), _scientific_tasks(right_ledger)
    if not a.keys() & b.keys():
        raise ComparisonError("no shared scientific task slots")
    mapping = []
    for key in sorted(a.keys() | b.keys(), key=repr):
        ar, br = a.get(key), b.get(key)
        if ar and br and any(ar[k] != br[k] for k in ("contract", "source_family", "split", "seed")):
            raise ComparisonError("scientific task/gold/units/measurement mismatch")
        mapping.append({"trial": dict(zip(KEY_FIELDS, key)), "left": copy.deepcopy(ar), "right": copy.deepcopy(br)})
    def native(run):
        return {"dataset_id": _meta(run, "dataset_id"), "manifest_digest": run.get("manifest_digest"),
                "route": run.get("route"), "requested_model": run.get("requested_model")}
    return {"schema": "decisions-lab.scientific-pairing/1", "left_native": native(left_ledger),
            "right_native": native(right_ledger), "mapping": mapping}


def compare_runs(left, right, *, seed=0, bootstrap_samples=2000, failure_loss=1.0,
                 split=None, condition=None, min_clusters=8, plan=None, metric=None, pairing=None, _measurement_group=None):
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
    if pairing is not None and pairing != make_pairing_spec(left, right):
        raise ComparisonError("pairing differs from frozen scientific mapping")
    if pairing is None and ld is not None and rd is not None and ld != rd:
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
    if _measurement_group is not None:
        a = [r for r in a if _measurement_key(r) == _measurement_group]
        b = [r for r in b if _measurement_key(r) == _measurement_group]
    for row in a + b:
        retained = row.get("retained_failure_loss")
        if retained is not None and not math.isclose(retained, failure_loss, rel_tol=0, abs_tol=1e-12):
            raise ComparisonError("failure_loss differs from retained task loss; use the frozen retained_failure_loss")
    if plan is not None and plan.get("threshold") is not None:
        observed_signal = _signal(a + b)
        expected_signal = plan.get("selection_signal", {"id": "legacy_unspecified_confidence",
                                    "semantics": "legacy confidence; formula unknown", "formula_known": False})
        if observed_signal != expected_signal:
            raise ComparisonError("frozen plan selection signal differs from trial signal")
        def apply_threshold(row):
            if row["outcome"] == "ok" and (row.get("confidence") is None or row["confidence"] < plan["threshold"]):
                return {**row, "original_outcome": "ok", "outcome": "unknown", "correct": None, "loss": None,
                        **({"measurement": {**row["measurement"], "value": None}} if row.get("measurement") else {})}
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
                   "loss": None, "confidence": None, "latency_ms": None, "cost": None,
                   "unsafe": None, "guard_rejected": None, "semantic_action": None, "choice": None}
        if missing.get("measurement") is not None:
            missing["measurement"] = {**missing["measurement"], "value": None}
        if missing.get("selection_signal") is not None:
            missing["selection_signal"] = {**missing["selection_signal"], "value": None}
        ar, br = ar if ar is not None else missing, br if br is not None else missing
        if (ar.get("metric") == "role_workflow_loss" or br.get("metric") == "role_workflow_loss") and ar.get("metric") != br.get("metric"):
            raise ComparisonError("role loss metric differs; regenerate old ledgers from retained native records")
        am, bm = ar.get("measurement"), br.get("measurement")
        if bool(am) != bool(bm) and (am or bm).get("id") == "absolute_error":
            raise ComparisonError("numeric measurement missing; regenerate old ledgers from retained native records")
        if am is not None and bm is not None and any(am.get(f) != bm.get(f) for f in ("id", "unit", "semantics")):
            raise ComparisonError("measurement differs across runs")
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
                      "left_unsafe": ar.get("unsafe"), "right_unsafe": br.get("unsafe"),
                      "left_guard_rejected": ar.get("guard_rejected"), "right_guard_rejected": br.get("guard_rejected"),
                      "left_measurement": copy.deepcopy(ar.get("measurement")), "right_measurement": copy.deepcopy(br.get("measurement")),
                      "left_selection_signal": copy.deepcopy(ar.get("selection_signal")), "right_selection_signal": copy.deepcopy(br.get("selection_signal")),
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
    groups = sorted({_measurement_key(r) for r in a + b}, key=repr)
    ci = None
    reason = "fewer than min_clusters source families; descriptive only"
    if len(families) >= min_clusters and len(groups) <= 1:
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
    report = {"schema": "decisions-lab.comparison/1", "metric": metric, "delta_direction": "right-left",
            "evidence": {"left": evidence_origin(left), "right": evidence_origin(right),
                         "note": "Source markers are retained claims; comparison does not authenticate provider calls."},
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
            "units": unit_rows, "trace": trace, "analysis_plan": copy.deepcopy(plan),
            "pairing": copy.deepcopy(pairing)}
    report["by_measurement"] = []
    if _measurement_group is None and len(groups) > 1:
        report["by_measurement"] = [
            {"measurement": dict(zip(("id", "unit", "semantics"), group)),
             "report": compare_runs(left, right, seed=seed, bootstrap_samples=bootstrap_samples,
                                    failure_loss=failure_loss, split=split, condition=condition,
                                    min_clusters=min_clusters, plan=plan, metric=metric, pairing=pairing,
                                    _measurement_group=group)} for group in groups]
        for side in ("left", "right"):
            report[side]["workflow_loss"] = None
        for key in ("left_loss", "right_loss", "delta", "ci95"):
            report["estimate"][key] = None
        report["estimate"]["inference"] = "not-aggregated"
        report["estimate"]["reason"] = "heterogeneous measurements; inspect by_measurement"
        for unit in report["units"]:
            for key in ("left_loss", "right_loss", "delta"):
                unit[key] = None
    return report


def _measurement_key(row):
    measurement = row.get("measurement")
    if measurement is None:
        return ("legacy_unspecified", "unspecified", "legacy loss contract")
    return tuple(measurement.get(key) for key in ("id", "unit", "semantics"))


def _signal(rows):
    signals = []
    for row in rows:
        signal = row.get("selection_signal")
        signature = ({k: v for k, v in signal.items() if k != "value"} if signal is not None else
                     {"id": "legacy_unspecified_confidence", "semantics": "legacy confidence; formula unknown", "formula_known": False})
        if signature not in signals:
            signals.append(signature)
    if len(signals) > 1:
        raise ComparisonError("different selection signals cannot share a threshold")
    return signals[0] if signals else None


def _observed_loss(rows):
    if not rows or len({_measurement_key(row) for row in rows}) > 1:
        return None
    return mean(_loss(row, 1.0) for row in rows)


def risk_coverage(rows):
    """Confidence thresholds with ties admitted together; failures stay in denominator.

    Only ok rows with valid correctness and confidence are selectable. A null
    confidence or unknown outcome is never converted into confidence zero.
    Risk is classification error; loss is separately observed workflow loss.
    """
    rows = _rows(rows)
    _validate(rows)
    signal = _signal(rows)
    eligible = [r for r in rows if r["outcome"] == "ok" and r.get("correct") is not None
                and r.get("confidence") is not None]
    result, selected = [], []
    grouped = defaultdict(list)
    for row in eligible:
        grouped[row["confidence"]].append(row)
    for score in sorted(grouped, reverse=True):
        selected.extend(grouped[score])
        result.append({"selection_signal": signal, "threshold": score, "selected": len(selected), "planned": len(rows),
                       "coverage": len(selected) / len(rows),
                       "risk": mean(not r["correct"] for r in selected),
                       "loss": _observed_loss(selected)})
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
            "reject_all": point is None, "selection_signal": _signal(rows)}


def evaluate_threshold(rows, threshold):
    """Apply a calibration selection object, unchanged, to held-out test rows."""
    rows = _require_split(rows, "test")
    if not isinstance(threshold, dict) or threshold.get("selection_split") != "calibration":
        raise ComparisonError("requires a calibration threshold selection object")
    if set(threshold.get("source_families", [])) & {r["source_family"] for r in rows}:
        raise ComparisonError("calibration and test source families overlap")
    if threshold.get("selection_signal") != _signal(rows):
        raise ComparisonError("threshold selection signal differs from evaluation signal")
    value = threshold.get("threshold")
    if value is not None and (not _number(value) or not 0 <= value <= 1):
        raise ComparisonError("invalid threshold")
    selected = [r for r in rows if value is not None and r["outcome"] == "ok"
                and r.get("correct") is not None and r.get("confidence") is not None
                and r["confidence"] >= value]
    return {"selection_signal": _signal(rows), "threshold": value, "evaluation_split": "test", "planned": len(rows),
            "selected": len(selected), "coverage": len(selected) / len(rows),
            "risk": mean(not r["correct"] for r in selected) if selected else None,
            "loss": _observed_loss(selected),
            "risk_guarantee": False}
