"""Replayable typed extraction -> Decimal computation -> native decision DAG.

The module is a thin bridge over existing contracts. Clairic extraction uses
``typed_values`` records/collections, native decisions use ``api_lab`` records
and ``evidence_workflow`` decoding, and collection plans remain in
``collection``'s format. It performs no network, credential, or model I/O.
"""
from __future__ import annotations

import base64
import copy
import json
import random
import re
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from . import api_lab as al
from . import collection
from . import evidence_workflow as ew
from . import typed_values as tv

SCHEMA = "decisions-lab.typed-dag/1"
SUITE_SCHEMA = "decisions-lab.typed-dag-suite/1"
REPORT_SCHEMA = "decisions-lab.typed-dag-report/1"
COMPARE_SCHEMA = "decisions-lab.typed-dag-comparison/1"

ARMS = ("direct", "fields-only", "source-linked")
INTERVENTIONS = (None, "extraction", "calculation", "retrieval")
ACTIONS = tv.DOWNSTREAM_ACTIONS
DEMO_POLICIES = (
    "oracle",
    "wrong-field",
    "wrong-evidence",
    "wrong-version",
    "wrong-decision",
)

RULE_TEXT = (
    "任务规则：金额=数量*单价+运费；仅当金额不超过 1200.00 CNY 且"
    "目标实体现行版本无未解决争议时建议继续；存在未解决争议时建议"
    "核对争议；缺少必要事实时建议补材料。"
)
OPTIONS = {
    "suggest_continue": "金额不超限且目标现行状态无未解决争议。",
    "inspect_dispute": "目标现行状态存在未解决争议。",
    "needs_more_context": "缺少金额或目标现行状态，不能安全判断。",
    "unknown": "给定动作均不适配当前问题。",
}


class TypedDagError(ValueError):
    """A readable DAG contract, binding, or replay failure."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TypedDagError(message)


def _read(value: Any) -> dict[str, Any]:
    if isinstance(value, (str, Path)):
        path = Path(value)
        if path.is_dir():
            path /= "collection.json" if (path / "collection.json").exists() else "record.json"
        value = al.read_json(path)
    _require(isinstance(value, dict), "retained source must be an object or JSON path")
    return copy.deepcopy(value)


def _seal(value: dict[str, Any]) -> dict[str, Any]:
    value["evidence_digest"] = al.digest(
        {key: item for key, item in value.items() if key != "evidence_digest"}
    )
    return value


def _check_seal(value: dict[str, Any], *, where: str) -> None:
    _require(
        value.get("evidence_digest")
        == al.digest(
            {key: item for key, item in value.items() if key != "evidence_digest"}
        ),
        f"{where}: retained evidence digest mismatch",
    )


def _decimal(value: Any, *, where: str, nullable: bool = False) -> Decimal | None:
    if value is None and nullable:
        return None
    _require(
        isinstance(value, (int, float, str))
        and not isinstance(value, bool)
        and str(value).strip() != "",
        f"{where}: expected a finite decimal or explicit null",
    )
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise TypedDagError(f"{where}: invalid decimal") from exc
    _require(result.is_finite(), f"{where}: decimal must be finite")
    return result


def _field(name: str, kind: str, instructions: str, **extra: Any) -> dict[str, Any]:
    del name
    return {"type": kind, "instructions": instructions, **extra}


def _status_line(source: str, prefix: str = "目标现行状态：") -> str | None:
    return next((line for line in source.splitlines() if line.startswith(prefix)), None)


def _distractor_line(source: str) -> str | None:
    for prefix in ("邻接状态：", "目标旧版状态：", "背景状态："):
        line = _status_line(source, prefix)
        if line is not None:
            return line
    return None


def _case(
    ident: str,
    family: str,
    variant: str,
    source: str,
    fields: dict[str, Any],
    gold_fields: dict[str, Any],
    qty: str | None,
    price: str | None,
    shipping: str | None,
    total: str | None,
    optimal: str,
) -> dict[str, Any]:
    evidence = _status_line(source)
    _require(evidence is not None, f"{ident}: target current-state line is required")
    return {
        "id": ident,
        "source_family": family,
        "variant": variant,
        "split": "test",
        "source": source,
        "fields": fields,
        "oracle": {
            "gold_fields": gold_fields,
            "gold_calculation": {
                "quantity": qty,
                "unit_price": price,
                "shipping": shipping,
                "total": total,
            },
            "gold_evidence": {
                "passage": evidence,
                "link_scope": "target current-state line only",
            },
            "optimal_action": optimal,
            "projection_actions": {},
            "losses": {
                "suggest_continue": 0.0 if optimal == "suggest_continue" else 8.0,
                "inspect_dispute": 0.0 if optimal == "inspect_dispute" else 8.0,
                "needs_more_context": (
                    0.0 if optimal == "needs_more_context" else 2.0
                ),
                "unknown": 12.0,
            },
            "failure_loss": 12.0,
        },
        "request": {
            "model": "clairic",
            "state": source,
            "fields": copy.deepcopy(fields),
            "options": {"return_state_text": True},
        },
    }


def build_suite(seed: int = 0) -> dict[str, Any]:
    """Build a bounded original suite with six distinct mechanisms.

    Seed permutes presentation order only. Replicates and conditions are added
    by ``start``; this function never claims independent sources.
    """

    _require(type(seed) is int and seed >= 0, "seed must be a nonnegative integer")
    number = lambda name, instructions, **extra: _field(
        name, "number", instructions, **extra
    )
    text = lambda name, instructions: _field(name, "text", instructions)
    common = {
        "quantity": number("quantity", "目标实体的货物数量。", decimals=0, unit="件"),
        "unit_price": number(
            "unit_price", "目标实体的单件价格，不含运费。",
            decimals=2, unit="CNY",
        ),
        "shipping": number("shipping", "目标实体的运费。", decimals=2, unit="CNY"),
        "computed_total": number(
            "computed_total",
            "目标实体的数量乘单价再加运费；不得猜测缺失操作数。",
            decimals=2, unit="CNY",
        ),
    }
    identity = {
        "target_entity": text(
            "target_entity", "题目指定目标的实体 ID；不要采用同名邻实体。"
        ),
        "target_version": text(
            "target_version", "题目指定目标当前适用的版本；不要采用旧版本。"
        ),
        "status_evidence": text(
            "status_evidence",
            "逐字摘录目标现行状态的整句；不要摘录邻实体、旧版本或背景说明。",
        ),
    }
    cases: list[dict[str, Any]] = []

    source = (
        RULE_TEXT
        + "\n目标记录：供应商北河，实体 E-101，版本 v2。"
        + "\n目标现行状态：三件已经验收，仓库与供应商记录一致，无未解决争议。"
        + "\n数量 3 件；单价 350.00 CNY；运费 50.00 CNY。"
    )
    fields = {**copy.deepcopy(common), **copy.deepcopy(identity)}
    gold = {
        "quantity": 3,
        "unit_price": 350.0,
        "shipping": 50.0,
        "computed_total": 1100.0,
        "target_entity": "E-101",
        "target_version": "v2",
        "status_evidence": _status_line(source),
    }
    cases.append(_case(
        "complete-simple", "complete-simple", "complete", source, fields, gold,
        "3", "350.00", "50.00", "1100.00", "suggest_continue",
    ))

    source = (
        RULE_TEXT
        + "\n目标记录：同名供应商北河，目标实体 E-201-E，版本 v2。"
        + "\n目标现行状态：三件已经验收，仓库与供应商记录一致，无未解决争议。"
        + "\n邻接记录：同名供应商北河，邻接实体 E-201-W，版本 v2。"
        + "\n邻接状态：供应商声称全部交付，仓库发现争议未解决。"
        + "\n目标金额：数量 2 件；单价 300.00 CNY；运费 40.00 CNY。"
    )
    fields = {**copy.deepcopy(common), **copy.deepcopy(identity)}
    gold = {
        "quantity": 2,
        "unit_price": 300.0,
        "shipping": 40.0,
        "computed_total": 640.0,
        "target_entity": "E-201-E",
        "target_version": "v2",
        "status_evidence": _status_line(source),
    }
    cases.append(_case(
        "same-name-entities", "same-name-entities", "target", source, fields, gold,
        "2", "300.00", "40.00", "640.00", "suggest_continue",
    ))

    source = (
        RULE_TEXT
        + "\n目标记录：实体 E-307，当前版本 v2。"
        + "\n目标现行状态：仓库复核后确认全部已验收，无未解决争议。"
        + "\n目标旧版状态：供应商当时称第三件损坏，争议未解决。"
        + "\n数量 3 件；单价 300.00 CNY；运费 50.00 CNY。"
    )
    fields = {**copy.deepcopy(common), **copy.deepcopy(identity)}
    gold = {
        "quantity": 3,
        "unit_price": 300.0,
        "shipping": 50.0,
        "computed_total": 950.0,
        "target_entity": "E-307",
        "target_version": "v2",
        "status_evidence": _status_line(source),
    }
    cases.append(_case(
        "current-version-correction", "current-version-correction", "current",
        source, fields, gold, "3", "300.00", "50.00", "950.00",
        "suggest_continue",
    ))

    source = (
        RULE_TEXT
        + "\n目标记录：实体 E-404，版本 v1。"
        + "\n目标现行状态：前两项已验收；第三项尚待仓库核对，无未解决争议。"
        + "\n数量 2 件；单价 400.00 CNY；运费记录未提供。"
    )
    gold = {
        "quantity": 2,
        "unit_price": 400.0,
        "shipping": None,
        "computed_total": None,
    }
    cases.append(_case(
        "missing-operand", "missing-operand", "missing-shipping", source,
        copy.deepcopy(common), gold, "2", "400.00", None, None,
        "needs_more_context",
    ))

    gap_fields = {
        "quantity": copy.deepcopy(common["quantity"]),
        "unit_price": copy.deepcopy(common["unit_price"]),
        "shipping": copy.deepcopy(common["shipping"]),
        "computed_total": copy.deepcopy(common["computed_total"]),
        "target_entity": copy.deepcopy(identity["target_entity"]),
        "target_version": copy.deepcopy(identity["target_version"]),
    }
    gap_text = (
        RULE_TEXT
        + "\n目标记录：实体 E-501，版本 v3。"
        + "\n数量 3 件；单价 350.00 CNY；运费 50.00 CNY。"
    )
    gap_gold = {
        "quantity": 3,
        "unit_price": 350.0,
        "shipping": 50.0,
        "computed_total": 1100.0,
        "target_entity": "E-501",
        "target_version": "v3",
    }
    source = (
        gap_text
        + "\n目标现行状态：三件已经验收，仓库记录一致，无未解决争议。"
    )
    cases.append(_case(
        "schema-gap-continue", "schema-gap-pair", "clean", source,
        gap_fields, gap_gold, "3", "350.00", "50.00", "1100.00",
        "suggest_continue",
    ))
    source = (
        gap_text
        + "\n目标现行状态：第三件尚未验收，仓库更正供应商说法，争议未解决。"
    )
    cases.append(_case(
        "schema-gap-dispute", "schema-gap-pair", "disputed", source,
        copy.deepcopy(gap_fields), copy.deepcopy(gap_gold),
        "3", "350.00", "50.00", "1100.00", "inspect_dispute",
    ))

    source = (
        RULE_TEXT
        + "\n目标记录：实体 E-612，版本 v4。"
        + "\n背景状态：供应商早先声称全部已交付。"
        + "\n目标现行状态：仓库随后更正第三件尚未验收，争议未解决。"
        + "\n数量 4 件；单价 200.00 CNY；运费 40.00 CNY。"
    )
    fields = {**copy.deepcopy(common), **copy.deepcopy(identity)}
    gold = {
        "quantity": 4,
        "unit_price": 200.0,
        "shipping": 40.0,
        "computed_total": 840.0,
        "target_entity": "E-612",
        "target_version": "v4",
        "status_evidence": _status_line(source),
    }
    cases.append(_case(
        "evidence-link-repair", "evidence-link-repair", "corrected",
        source, fields, gold, "4", "200.00", "40.00", "840.00",
        "inspect_dispute",
    ))

    random.Random(seed).shuffle(cases)
    suite = {
        "schema": SUITE_SCHEMA,
        "seed": seed,
        "provenance": "synthetic",
        "description": (
            "原创有限 typed extraction→Decimal→native decision 设计；"
            "小样本与干预不证明模型收益。"
        ),
        "task_rules": RULE_TEXT,
        "options": copy.deepcopy(OPTIONS),
        "cases": cases,
    }
    validate_suite(suite)
    return suite


def _typed_raw(suite: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "decisions-lab.typed-values-examples/1",
        "experiments": [{
            "id": "extract-compute-decide",
            "cases": [{
                "id": case["id"],
                "source_group": case["source_family"],
                "request": copy.deepcopy(case["request"]),
                "editorial_oracle": {
                    "values": copy.deepcopy(case["oracle"]["gold_fields"])
                },
            } for case in suite["cases"]],
        }],
    }


def _typed_suite(suite: dict[str, Any]) -> tv.TypedSuite:
    raw = _typed_raw(suite)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "typed-dag-suite.json"
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        return tv.load_suite(path)


def validate_suite(suite: Any) -> dict[str, Any]:
    """Validate the finite public design without treating it as model truth."""

    suite = _read(suite)
    _require(suite.get("schema") == SUITE_SCHEMA, "invalid typed DAG suite schema")
    _require(suite.get("provenance") == "synthetic", "suite provenance must be synthetic")
    _require(type(suite.get("seed")) is int and suite["seed"] >= 0,
             "suite seed must be nonnegative")
    _require(suite.get("task_rules") == RULE_TEXT,
             "unsupported task rules; this finite suite uses the declared procurement rule")
    _require(suite.get("options") == OPTIONS, "suite action contract changed")
    cases = suite.get("cases")
    _require(isinstance(cases, list) and cases, "suite cases must be nonempty")
    seen: set[str] = set()
    for index, case in enumerate(cases):
        where = f"cases[{index}]"
        _require(isinstance(case, dict), f"{where}: case must be an object")
        ident = case.get("id")
        _require(isinstance(ident, str) and ident and ident not in seen,
                 f"{where}: invalid or duplicate id")
        seen.add(ident)
        for name in ("source_family", "variant", "split", "source"):
            _require(isinstance(case.get(name), str) and case[name],
                     f"{where}: {name} must be nonempty text")
        _require(case["split"] == "test", f"{where}: split must be test")
        fields = case.get("fields")
        request = case.get("request")
        oracle = case.get("oracle")
        _require(isinstance(fields, dict) and fields, f"{where}: fields required")
        _require(isinstance(request, dict), f"{where}: request required")
        _require(request.get("model") == "clairic", f"{where}: request model must be clairic")
        _require(request.get("state") == case["source"], f"{where}: request source differs")
        _require(request.get("fields") == fields, f"{where}: request fields differ")
        _require(set(request) <= tv.ALLOWED_REQUEST_KEYS,
                 f"{where}: unknown native request keys")
        _require(isinstance(oracle, dict), f"{where}: oracle must be an object")
        gold = oracle.get("gold_fields")
        _require(isinstance(gold, dict) and set(gold) == set(fields),
                 f"{where}: gold_fields must exactly match extraction schema")
        calculation = oracle.get("gold_calculation")
        _require(isinstance(calculation, dict), f"{where}: gold_calculation required")
        _require(set(calculation) == {"quantity", "unit_price", "shipping", "total"},
                 f"{where}: invalid gold_calculation keys")
        qty = _decimal(calculation["quantity"], where=f"{where}.quantity", nullable=True)
        price = _decimal(calculation["unit_price"], where=f"{where}.unit_price",
                         nullable=True)
        shipping = _decimal(calculation["shipping"], where=f"{where}.shipping",
                            nullable=True)
        total = _decimal(calculation["total"], where=f"{where}.total", nullable=True)
        complete = all(value is not None for value in (qty, price, shipping))
        _require((total is None) == (not complete),
                 f"{where}: total must be null exactly when operands are incomplete")
        if complete:
            _require(qty * price + shipping == total,
                     f"{where}: gold calculation is inconsistent")
        evidence = oracle.get("gold_evidence")
        _require(isinstance(evidence, dict), f"{where}: gold_evidence required")
        passage = evidence.get("passage")
        _require(isinstance(passage, str) and passage.startswith("目标现行状态：")
                 and passage in case["source"],
                 f"{where}: gold evidence must be the exact current target line")
        optimal = oracle.get("optimal_action")
        _require(optimal in ACTIONS, f"{where}: invalid optimal action")
        losses = oracle.get("losses")
        _require(isinstance(losses, dict) and set(losses) == set(ACTIONS),
                 f"{where}: complete designed action losses required")
        _require(all(al.finite(value) and value >= 0 for value in losses.values()),
                 f"{where}: losses must be nonnegative finite numbers")
        _require(losses.get(optimal) == 0, f"{where}: optimal action must have zero loss")
        _require(al.finite(oracle.get("failure_loss")) and oracle["failure_loss"] >= 0,
                 f"{where}: failure_loss must be nonnegative")
        _require(isinstance(oracle.get("projection_actions"), dict),
                 f"{where}: projection_actions must be an object")
        native = json.dumps(request, ensure_ascii=False)
        _require(not any(marker in native for marker in (
            "gold_fields", "optimal_action", "failure_loss", "gold_evidence",
        )), f"{where}: editorial truth leaked into extraction request")

    typed = _typed_suite(suite)
    _require([case["id"] for case in cases] == [case.case_id for case in typed.cases],
             "typed projection does not preserve suite order")

    # Recompute projections from public inputs; do not trust editable labels.
    for case in cases:
        gold = case["oracle"]["gold_fields"]
        calc = _calculate(case, gold, force_gold=False)
        for arm in ARMS:
            body = _projection_body(suite, case, arm, gold, calc, None)
            case["oracle"]["projection_actions"][arm] = _action_from_input(body)
        _require(case["oracle"]["projection_actions"]["direct"] == case["oracle"]["optimal_action"],
                 f"{case['id']}: oracle action conflicts with the visible task rule")

    pair = [case for case in cases if case["source_family"] == "schema-gap-pair"]
    _require(len(pair) >= 2, "suite needs the schema-insufficient pair")
    _require(pair[0]["oracle"]["gold_fields"] == pair[1]["oracle"]["gold_fields"]
             and pair[0]["oracle"]["optimal_action"]
             != pair[1]["oracle"]["optimal_action"],
             "schema-gap pair needs identical gold fields and disjoint optimal actions")
    _require(
        pair[0]["oracle"]["projection_actions"]["fields-only"]
        == pair[1]["oracle"]["projection_actions"]["fields-only"],
        "schema-gap fields-only projection must not distinguish the pair",
    )
    return suite


def _typed_plan(workflow: dict[str, Any]) -> dict[str, Any]:
    typed = _typed_suite(workflow["suite"])
    plan = collection.typed_plan(
        typed, typed.cases, replicates=workflow["replicates"]
    )
    for row in plan["requests"]:
        row["trial"]["condition"] = "typed-extraction"
    collection.validate_plan(plan)
    return plan


def _planned(
    suite: dict[str, Any], condition: str, replicates: int
) -> list[dict[str, Any]]:
    rows = []
    for case in suite["cases"]:
        for replicate in range(replicates):
            suffix = "" if replicate == 0 else f".r{replicate}"
            rows.append({
                "id": case["id"] + suffix,
                "case_id": case["id"],
                "source_family": case["source_family"],
                "condition": condition,
                "replicate": replicate,
                "split": case["split"],
                "seed": suite["seed"],
            })
    return rows


def start(
    suite: Any,
    *,
    route: str = "decisions",
    model: str | None = None,
    account_id: str | None = None,
    replicates: int = 1,
    condition: str = "fields-only",
    intervention: str | None = None,
) -> dict[str, Any]:
    """Create an immutable workflow for one arm and explicit intervention."""

    suite = validate_suite(suite)
    _require(condition in ARMS, f"unknown condition {condition!r}")
    _require(intervention in INTERVENTIONS, f"unknown intervention {intervention!r}")
    _require(condition != "direct" or intervention is None,
             "direct arm does not adopt extraction/calculation/retrieval gold")
    _require(intervention != "retrieval" or condition == "source-linked",
             "gold retrieval applies only to source-linked")
    _require(type(replicates) is int and replicates > 0,
             "replicates must be a positive integer")
    model = al.route_model(route, model)
    if route in al.CLOUDFLARE_ROUTES:
        _require(isinstance(account_id, str)
                 and re.fullmatch(r"[a-fA-F0-9]{32}", account_id),
                 "Cloudflare decision route requires a 32-hex account_id")
    workflow = {
        "schema": SCHEMA,
        "suite": copy.deepcopy(suite),
        "route": route,
        "model": model,
        "account_id": account_id,
        "replicates": replicates,
        "condition": condition,
        "intervention": intervention,
        "planned": _planned(suite, condition, replicates),
        "rounds": [],
    }
    result = _seal(workflow)
    _rebuild(result)
    return result


def _calculate(
    case: dict[str, Any],
    values: dict[str, Any],
    *,
    force_gold: bool,
) -> dict[str, Any]:
    selected = (
        case["oracle"]["gold_calculation"]
        if force_gold
        else {
            "quantity": values.get("quantity"),
            "unit_price": values.get("unit_price"),
            "shipping": values.get("shipping"),
        }
    )
    quantity = _decimal(
        selected["quantity"], where=f"{case['id']}.quantity", nullable=True
    )
    price = _decimal(
        selected["unit_price"], where=f"{case['id']}.unit_price", nullable=True
    )
    shipping = _decimal(
        selected["shipping"], where=f"{case['id']}.shipping", nullable=True
    )
    complete = all(value is not None for value in (quantity, price, shipping))
    total = quantity * price + shipping if complete else None
    gold_total = _decimal(
        case["oracle"]["gold_calculation"]["total"],
        where=f"{case['id']}.gold_total",
        nullable=True,
    )
    model_total = values.get("computed_total")
    if model_total is not None:
        model_total = str(
            _decimal(model_total, where=f"{case['id']}.model_total")
        )
    return {
        "source": "gold_synthetic" if force_gold else "decimal_code",
        "extracted": copy.deepcopy(values),
        "operands": {
            "quantity": None if quantity is None else str(quantity),
            "unit_price": None if price is None else str(price),
            "shipping": None if shipping is None else str(shipping),
        },
        "total": None if total is None else str(total),
        "complete": complete,
        "matches_gold": total == gold_total,
        "arithmetic_consistent": True if complete else None,
        "model_total": model_total,
        "model_total_matches_code": (
            Decimal(model_total) == total
            if model_total is not None and total is not None else None
        ),
    }


def _retrieval(
    case: dict[str, Any],
    values: dict[str, Any],
    intervention: str | None,
) -> dict[str, Any]:
    if intervention == "retrieval":
        passage = case["oracle"]["gold_evidence"]["passage"]
        return {
            "quote": passage,
            "source": "gold_synthetic",
            "valid": True,
            "matches_gold": True,
        }
    candidate = values.get("status_evidence")
    valid = (
        isinstance(candidate, str)
        and candidate.startswith("目标现行状态：")
        and candidate in case["source"]
    )
    return {
        "quote": candidate if valid else None,
        "source": "extracted" if valid else None,
        "valid": valid,
        "matches_gold": candidate == case["oracle"]["gold_evidence"]["passage"],
        "candidate": candidate,
    }


def _amount_from_source(source: str) -> Decimal | None:
    if "运费记录未提供" in source:
        return None
    match = re.search(
        r"数量\s*(\d+)\s*件[；;].*?单价\s*([\d.]+)\s*CNY[；;].*?"
        r"运费\s*([\d.]+)\s*CNY",
        source,
    )
    if not match:
        return None
    try:
        return (
            Decimal(match.group(1))
            * Decimal(match.group(2))
            + Decimal(match.group(3))
        )
    except InvalidOperation:
        return None


def _action_from_input(payload: dict[str, Any]) -> str:
    projection = payload.get("projection")
    if projection == "direct":
        status = _status_line(payload.get("source_text", ""))
        amount = _amount_from_source(payload.get("source_text", ""))
    else:
        calculation = payload.get("calculation") or {}
        try:
            operands = [
                _decimal(calculation.get(name), where=f"input.{name}", nullable=True)
                for name in ("quantity", "unit_price", "shipping")
            ]
            total = _decimal(
                calculation.get("total"), where="input.total", nullable=True
            )
        except TypedDagError:
            return "needs_more_context"
        if any(value is None for value in operands) or total is None:
            amount = None
        elif operands[0] * operands[1] + operands[2] != total:
            return "needs_more_context"
        else:
            amount = total
        if projection == "fields-only":
            status = (payload.get("fields") or {}).get("status_evidence")
        else:
            status = (payload.get("evidence") or {}).get("quote")
    if amount is None or not isinstance(status, str):
        return "needs_more_context"
    if not status.startswith("目标现行状态："):
        return "needs_more_context"
    if "无未解决争议" in status:
        return (
            "suggest_continue"
            if amount <= Decimal("1200.00")
            else "needs_more_context"
        )
    if any(marker in status for marker in (
        "争议未解决", "未解决争议", "尚未验收",
    )):
        return "inspect_dispute"
    return "needs_more_context"


def _projection_body(
    suite: dict[str, Any],
    case: dict[str, Any],
    arm: str,
    values: dict[str, Any],
    calculation: dict[str, Any],
    retrieval: dict[str, Any] | None,
) -> dict[str, Any]:
    base = {
        "question": "依照给定任务规则，建议下一步怎样处理目标记录？",
        "rules": suite["task_rules"],
        "projection": arm,
        "options": [
            {"value": action, "description": description}
            for action, description in suite["options"].items()
        ],
    }
    if arm == "direct":
        return {**base, "source_text": case["source"]}
    visible = {
        name: copy.deepcopy(value)
        for name, value in values.items()
        if name != "computed_total"
    }
    body = {
        **base,
        "fields": visible,
        "calculation": {
            **calculation["operands"],
            "total": calculation["total"],
            "complete": calculation["complete"],
        },
    }
    if arm == "source-linked":
        body["evidence"] = {
            "quote": None if retrieval is None else retrieval["quote"],
            "link": (
                None if retrieval is None or retrieval["quote"] is None else {
                    "source": "provided-task-text",
                    "start": case["source"].index(retrieval["quote"]),
                    "end": case["source"].index(retrieval["quote"]) + len(retrieval["quote"]),
                    "unit": "unicode_codepoint",
                    "range": "half_open",
                }
            ),
        }
    return body


def _case_map(workflow: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {case["id"]: case for case in workflow["suite"]["cases"]}


def _plan_map(plan: dict[str, Any]) -> dict[tuple[str, int], dict[str, Any]]:
    result = {}
    for row in plan["requests"]:
        if plan.get("kind") == "typed-values":
            case_id = row["case_id"]
        else:
            case_id = row["trial"]["unit_id"]
        result[(case_id, row["trial"]["replicate"])] = row
    return result


def _decision_plan(
    workflow: dict[str, Any],
    states: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    cases = _case_map(workflow)
    rows = []
    for planned in workflow["planned"]:
        state = states[planned["id"]]
        extraction = state["extraction"]
        if workflow["condition"] != "direct" and (
            extraction is None or extraction["outcome"] != "ok"
        ):
            continue
        case = cases[planned["case_id"]]
        if workflow["condition"] == "direct":
            values = {}
            calculation = {}
            retrieval = None
        else:
            values = extraction["values"]
            calculation = _calculate(
                case, values,
                force_gold=workflow["intervention"] == "calculation",
            )
            retrieval = (
                _retrieval(case, values, workflow["intervention"])
                if workflow["condition"] == "source-linked" else None
            )
        public_input = _projection_body(
            workflow["suite"], case, workflow["condition"], values,
            calculation, retrieval,
        )
        questions = [{
            "id": "action",
            "type": "choice",
            "instructions": (
                "只依据输入材料选择一个动作。unknown 表示 API 无法返回"
                "可采用的业务动作，不是业务补材料。"
            ),
            "choices": [
                {"value": action, "description": description}
                for action, description in workflow["suite"]["options"].items()
            ],
        }]
        native_input = json.dumps(
            public_input, ensure_ascii=False, sort_keys=True
        )
        rows.append({
            "id": f"typed-dag-{planned['case_id']}",
            "experiment": "typed-dag",
            "input": native_input,
            "questions": questions,
            "rubric": {"questions": {
                "action": {
                    "kind": "choice",
                    "acceptable": [case["oracle"]["optimal_action"]],
                }
            }},
            "trial": {
                "unit_id": planned["case_id"],
                "source_family": planned["source_family"],
                "condition": f"{workflow['condition']}:decide",
                "replicate": planned["replicate"],
                "split": planned["split"],
                "seed": workflow["suite"]["seed"],
            },
        })
    if not rows:
        return None
    manifest = al.prepare_payload(
        al.Suite({}, rows), rows, route=workflow["route"],
        model=workflow["model"], account_id=workflow["account_id"],
    )
    return collection.api_plan(manifest)


def _record_flags(record: dict[str, Any], *, where: str) -> tuple[str, bool | None]:
    synthetic = record.get("synthetic")
    _require(synthetic is None or type(synthetic) is bool,
             f"{where}: invalid synthetic marker")
    _require(record.get("live_verified") is False,
             f"{where}: live_verified must be false")
    provenance = record.get("provenance")
    _require(provenance in ("synthetic", "imported", "baseline", "demo"),
             f"{where}: unsupported source provenance")
    source_kind = (
        "synthetic" if provenance in ("synthetic", "baseline", "demo")
        else "imported"
    )
    _require(source_kind != "synthetic" or synthetic is True,
             f"{where}: synthetic provenance needs a true marker")
    return source_kind, synthetic


def _extract_values(
    typed: tv.TypedSuite,
    case: tv.TypedCase,
    raw: Any,
    value_source: str,
) -> tuple[str, dict[str, Any] | None, dict[str, Any] | None]:
    try:
        answers, envelope = tv._parse_answers(case, raw, value_source=value_source)
    except (tv.TypedValuesError, KeyError, TypeError, ValueError) as exc:
        return "error", None, {"detail": str(exc)}
    return "ok", {
        name: answer["value"] for name, answer in answers.items()
    }, envelope


def _typed_record_rows(
    source: dict[str, Any],
    expected_plan: dict[str, Any],
    typed: tv.TypedSuite,
) -> tuple[
    dict[tuple[str, int], dict[str, Any]],
    dict[str, dict[str, Any]],
    str,
    bool | None,
]:
    _require(source.get("record_version") == tv.RECORD_VERSION,
             "extraction record has an unsupported record_version")
    source_kind, synthetic = _record_flags(source, where="extraction record")
    _require(source.get("suite_digest") == typed.digest(),
             "extraction record suite differs from current workflow")
    selected = source.get("selected_case_ids")
    _require(isinstance(selected, list) and selected
             and len(selected) == len(set(selected)),
             "extraction record selected_case_ids are invalid")
    plan_rows = expected_plan["requests"]
    _require(all(row["trial"]["replicate"] == 0 for row in plan_rows),
             "typed-values record cannot bind replicates; use a typed collection")
    expected_ids = [row["case_id"] for row in plan_rows]
    _require(selected == expected_ids,
             "extraction record cases differ from the current plan")
    results = source.get("results")
    _require(isinstance(results, list) and len(results) == len(expected_ids),
             "extraction record must contain every planned case once")
    typed_cases = {case.case_id: case for case in typed.cases}
    seen: set[str] = set()
    rows: dict[tuple[str, int], dict[str, Any]] = {}
    metrics: dict[str, dict[str, Any]] = {}
    span_convention = tv._validate_span_convention(
        source.get("span_convention"),
        where="extraction record span_convention",
    )
    for index, result in enumerate(results):
        where = f"extraction record results[{index}]"
        _require(isinstance(result, dict), f"{where}: result must be an object")
        case_id = result.get("case_id")
        _require(case_id in expected_ids and case_id not in seen,
                 f"{where}: foreign or duplicate case")
        seen.add(case_id)
        case = typed_cases[case_id]
        _require(result.get("request") == case.request,
                 f"{where}: retained request differs")
        _require(result.get("request_digest") == tv.request_digest(case.request),
                 f"{where}: request digest mismatch")
        hint = result.get("outcome_hint")
        _require(hint in {
            "native", tv.OUTCOME_UNKNOWN, tv.OUTCOME_REFUSAL, tv.OUTCOME_ERROR,
        }, f"{where}: invalid outcome hint")
        value_source = result.get("value_source")
        _require(value_source in {"native", "synthetic"},
                 f"{where}: explicit value_source required")
        if source_kind == "synthetic":
            _require(value_source == "synthetic",
                     f"{where}: synthetic source needs synthetic values")
        _validate_typed_result_binding(
            result, case, span_convention=span_convention
        )
        status = result.get("http_status")
        _require(status is None or type(status) is int and 100 <= status <= 599,
                 f"{where}: invalid HTTP status")
        if hint == "native" and (status is None or 200 <= status < 300):
            outcome, values, envelope = _extract_values(
                typed, case, result.get("raw"), value_source
            )
        else:
            outcome, values, envelope = ("error" if hint == "native" else hint), None, None
        rows[(case_id, 0)] = {
            "outcome": outcome,
            "values": values,
            "detail": (
                result.get("error_detail") if outcome != "ok" else None
            ),
            "value_source": value_source,
        }
        metrics[case_id] = {
            "attempts": None,
            "latency_ms": None,
            "usage": None if synthetic is True
            else envelope.get("usage") if isinstance(envelope, dict) else None,
            "cost": None,
        }
    _require(seen == set(expected_ids),
             "extraction record is missing planned cases")
    return rows, metrics, source_kind, synthetic


def _validate_typed_result_binding(
    result: dict[str, Any],
    case: tv.TypedCase,
    *,
    span_convention: dict[str, str] | None,
) -> None:
    """Validate a native typed record without its fixed DAG evaluator."""

    del span_convention
    _require(result.get("case_id") == case.case_id,
             "typed record result case differs")
    _require(result.get("experiment_id") == case.experiment_id,
             "typed record result experiment differs")
    _require(result.get("source_group") == case.source_group,
             "typed record result source group differs")
    _require(result.get("case_digest") == tv.case_digest(case),
             "typed record result case digest differs")
    _require(result.get("request") == case.request,
             "typed record request differs from current suite")
    _require(result.get("request_digest") == tv.request_digest(case.request),
             "typed record request digest differs")
    hint = result.get("outcome_hint")
    _require(hint in {
        "native", tv.OUTCOME_UNKNOWN, tv.OUTCOME_REFUSAL, tv.OUTCOME_ERROR,
    }, "typed record outcome hint is invalid")
    value_source = result.get("value_source")
    _require(value_source in {"native", "synthetic"},
             "typed record value source must be native or synthetic")
    response_input = {
        "raw": result.get("raw"),
        "http_status": result.get("http_status"),
        "outcome_hint": hint,
        "error_detail": result.get("input_error_detail"),
        "value_source": value_source,
        "downstream_decisions": result.get("downstream_decisions") or {},
        "provenance_kind": result.get("provenance_kind", "native_values"),
    }
    _require(result.get("response_digest") == tv._sha(response_input),
             "typed record response digest differs from retained raw response")


def _collection_attempts(
    source: dict[str, Any], expected_plan: dict[str, Any]
) -> tuple[dict[str, list[dict[str, Any]]], str, bool | None]:
    _check_seal(source, where="collection")
    _require(source.get("schema") == collection.SCHEMA,
             "unsupported collection schema")
    _require(source.get("plan") == expected_plan,
             "collection plan is stale, foreign, or differs from current stage")
    collection.validate_plan(source["plan"])
    provenance = source.get("provenance")
    _require(provenance in ("collector", "synthetic"),
             "collection provenance must be collector or synthetic")
    synthetic = source.get("synthetic")
    _require(synthetic is None or type(synthetic) is bool,
             "collection synthetic marker must be boolean or null")
    _require(source.get("live_verified") is False,
             "collection live_verified must be false")
    source_kind = "collector" if provenance == "collector" else "synthetic"
    _require(source_kind != "synthetic" or synthetic is True,
             "synthetic collection needs a true marker")
    ids = [row["id"] for row in expected_plan["requests"]]
    order = source.get("order")
    _require(isinstance(order, list) and len(order) == len(ids)
             and len(set(order)) == len(order) and set(order) == set(ids),
             "invalid collection schedule")
    attempts = source.get("attempts")
    _require(isinstance(attempts, list), "collection attempts must be an array")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for index, attempt in enumerate(attempts):
        where = f"collection attempts[{index}]"
        _require(isinstance(attempt, dict), f"{where}: attempt must be an object")
        ident, number = attempt.get("request_id"), attempt.get("attempt")
        _require(ident in ids and type(number) is int and number >= 0,
                 f"{where}: foreign request or invalid attempt number")
        prior = grouped.setdefault(ident, [])
        _require(number == len(prior),
                 f"{where}: attempt sequence is not contiguous")
        _require(attempt.get("state") in (
            "in_flight", "ok", "http_error", "parse_error",
            "transport_error", "cancelled",
        ), f"{where}: invalid attempt state")
        encoded = attempt.get("raw_body_base64")
        if encoded is not None:
            try:
                raw_bytes = base64.b64decode(encoded, validate=True)
            except (ValueError, TypeError) as exc:
                raise TypedDagError(f"{where}: invalid retained response bytes") from exc
            try:
                raw = json.loads(raw_bytes.decode("utf-8"),
                                 object_pairs_hook=collection._strict_pairs)
            except (ValueError, UnicodeError):
                _require(attempt.get("parse_status") == "malformed"
                         and attempt.get("parsed") is None
                         and attempt.get("state") in ("parse_error", "http_error"),
                         f"{where}: malformed bytes disagree with retained parse state")
            else:
                _require(attempt.get("parse_status") == "parsed"
                         and raw == attempt.get("parsed"),
                         f"{where}: parsed response differs from retained bytes")
        else:
            _require(attempt.get("parsed") is None,
                     f"{where}: parsed response lacks retained bytes")
        prior.append(attempt)
    _require(set(grouped) == set(ids),
             "collection is missing planned requests")
    for ident, group in grouped.items():
        last = group[-1]
        _require(last.get("state") != "in_flight"
                 and last.get("delivery") != "uncertain",
                 f"collection request {ident!r} is uncertain; resolve before apply")
    return grouped, source_kind, synthetic


def _typed_collection_rows(
    source: dict[str, Any],
    expected_plan: dict[str, Any],
    typed: tv.TypedSuite,
) -> tuple[
    dict[tuple[str, int], dict[str, Any]],
    dict[str, dict[str, Any]],
    str,
    bool | None,
]:
    grouped, source_kind, synthetic = _collection_attempts(source, expected_plan)
    cases = {case.case_id: case for case in typed.cases}
    rows: dict[tuple[str, int], dict[str, Any]] = {}
    metrics: dict[str, dict[str, Any]] = {}
    for request in expected_plan["requests"]:
        ident = request["id"]
        case_id = request["case_id"]
        replicate = request["trial"]["replicate"]
        case = cases[case_id]
        group = grouped[ident]
        last = group[-1]
        state = last["state"]
        metrics[ident] = {
            "attempts": len(group),
            "latency_ms": None if synthetic is True else ew._sum_numbers([a.get("elapsed_ms") for a in group]),
            "usage": None if synthetic is True
            else _sum_usage([attempt.get("usage") for attempt in group]),
            "cost": None if synthetic is True
            else _sum_costs([attempt.get("cost") for attempt in group]),
        }
        if state == "ok":
            outcome, values, envelope = _extract_values(
                typed, case, last.get("parsed"), "native"
            )
            detail = (
                envelope.get("detail") if isinstance(envelope, dict) else None
            )
        else:
            outcome = (
                "error" if state in (
                    "http_error", "parse_error", "transport_error", "cancelled",
                ) else "unknown"
            )
            values, detail = None, state
        rows[(case_id, replicate)] = {
            "outcome": outcome,
            "values": values,
            "detail": detail,
            "value_source": "native",
        }
    return rows, metrics, source_kind, synthetic


def _decode_extract_source(
    workflow: dict[str, Any], plan: dict[str, Any], source: dict[str, Any]
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    str,
    bool | None,
]:
    typed = _typed_suite(workflow["suite"])
    if source.get("provenance") == "collector":
        endpoint = source.get("endpoint")
        _require(isinstance(endpoint, str) and re.fullmatch(
            r"https://api\.cloudflare\.com/client/v4/accounts/[a-fA-F0-9]{32}/ai/run/@cf/cloudflare/clairic", endpoint),
            "Clairic collection endpoint differs from the native route")
        if workflow["account_id"] is not None:
            _require(endpoint == collection.endpoint_for("clairic", workflow["account_id"]),
                     "Clairic account differs from the frozen workflow account")
    if source.get("record_version") == tv.RECORD_VERSION:
        rows, metrics, source_kind, synthetic = _typed_record_rows(
            source, plan, typed
        )
    else:
        rows, metrics, source_kind, synthetic = _typed_collection_rows(
            source, plan, typed
        )
    expected = {
        (item["case_id"], item["replicate"]) for item in workflow["planned"]
    }
    _require(set(rows) == expected,
             "extraction source does not cover the complete planned denominator")
    states = {}
    for planned in workflow["planned"]:
        row = rows[(planned["case_id"], planned["replicate"])]
        states[planned["id"]] = {
            "outcome": row["outcome"],
            "values": copy.deepcopy(row["values"]),
            "detail": row["detail"],
            "value_source": row["value_source"],
            "source_kind": source_kind,
            "synthetic": synthetic,
        }
    return states, metrics, source_kind, synthetic


def _decode_decide_source(
    workflow: dict[str, Any], plan: dict[str, Any], source: dict[str, Any]
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    str,
    bool | None,
]:
    retained, decoded = ew._source(source, plan["manifest"])
    by_request = _plan_map(plan)
    decoded_by_id = {row["native"]["request_id"]: row for row in decoded}
    states: dict[str, dict[str, Any]] = {}
    metrics: dict[str, dict[str, Any]] = {}
    for planned in workflow["planned"]:
        request = by_request.get((planned["case_id"], planned["replicate"]))
        if request is None:
            continue
        item = decoded_by_id[request["id"]]
        failure = item.get("failure")
        states[planned["id"]] = {
            "outcome": failure or "ok",
            "action": item.get("action"),
            "detail": failure,
            "source_kind": (
                "collector" if retained.get("provenance") == "collector"
                else "synthetic"
                if retained.get("provenance") in ("synthetic", "demo", "baseline")
                else "imported"
            ),
            "synthetic": retained.get("synthetic"),
        }
        metrics[request["id"]] = item["native"]
    source_kind = (
        "collector" if retained.get("provenance") == "collector"
        else "synthetic"
        if retained.get("provenance") in ("synthetic", "demo", "baseline")
        else "imported"
    )
    return states, metrics, source_kind, retained.get("synthetic")


def _initial_states(workflow: dict[str, Any]) -> dict[str, dict[str, Any]]:
    states = {
        planned["id"]: {"extraction": None, "decision": None}
        for planned in workflow["planned"]
    }
    if workflow["intervention"] == "extraction" \
            and workflow["condition"] != "direct":
        cases = _case_map(workflow)
        for planned in workflow["planned"]:
            states[planned["id"]]["extraction"] = {
                "outcome": "ok",
                "values": copy.deepcopy(
                    cases[planned["case_id"]]["oracle"]["gold_fields"]
                ),
                "detail": None,
                "value_source": "synthetic",
                "source_kind": "synthetic",
                "synthetic": True,
                "gold": True,
            }
    return states


def _expected_stage(
    workflow: dict[str, Any],
    states: dict[str, dict[str, Any]],
    stage_index: int,
) -> tuple[str | None, dict[str, Any] | None]:
    stages = ["decide"] if workflow["condition"] == "direct" \
        or workflow["intervention"] == "extraction" \
        else ["extract", "decide"]
    if stage_index >= len(stages):
        return None, None
    stage = stages[stage_index]
    if stage == "extract":
        return stage, _typed_plan(workflow)
    plan = _decision_plan(workflow, states)
    return (stage, plan) if plan is not None else (None, None)


def _rebuild(
    value: Any,
) -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    str | None,
    dict[str, Any] | None,
    list[dict[str, Any]],
]:
    workflow = _read(value)
    _require(workflow.get("schema") == SCHEMA, "invalid typed DAG workflow schema")
    expected_keys = {
        "schema", "suite", "route", "model", "account_id", "replicates",
        "condition", "intervention", "planned", "rounds", "evidence_digest",
    }
    _require(set(workflow) == expected_keys,
             "workflow has unknown or missing fields; derived state must not be retained")
    _check_seal(workflow, where="workflow")
    suite = validate_suite(workflow["suite"])
    _require(workflow["condition"] in ARMS, "workflow condition changed")
    _require(workflow["intervention"] in INTERVENTIONS,
             "workflow intervention changed")
    _require(type(workflow["replicates"]) is int and workflow["replicates"] > 0,
             "workflow replicates must be positive")
    _require(workflow["condition"] != "direct" or workflow["intervention"] is None,
             "direct arm cannot adopt a gold stage")
    _require(workflow["intervention"] != "retrieval" or workflow["condition"] == "source-linked",
             "gold retrieval requires source-linked")
    _require(workflow["planned"] == _planned(
        suite, workflow["condition"], workflow["replicates"]
    ), "workflow planned identities changed")
    _require(workflow["model"] == al.route_model(
        workflow["route"], workflow["model"]
    ), "workflow model differs from route")
    _require(isinstance(workflow["rounds"], list),
             "workflow rounds must be an array")
    states = _initial_states(workflow)
    stages: list[dict[str, Any]] = []
    if workflow["intervention"] == "extraction" \
            and workflow["condition"] != "direct":
        stages.append({
            "stage": "extract",
            "source_kind": "synthetic",
            "provenance": "synthetic_gold_extraction",
            "synthetic": True,
            "plan": None,
            "metrics": {},
        })
    for index, record in enumerate(workflow["rounds"]):
        _require(isinstance(record, dict), f"round {index}: must be an object")
        _require(set(record) == {"stage", "plan", "plan_digest", "source"},
                 f"round {index}: invalid retained fields")
        stage, expected = _expected_stage(workflow, states, index)
        _require(stage is not None and expected is not None,
                 f"round {index}: retained after terminal stage")
        _require(record.get("stage") == stage
                 and record.get("plan") == expected
                 and record.get("plan_digest") == al.digest(expected),
                 f"round {index}: stale, foreign, or changed stage request")
        if stage == "extract":
            decoded, metrics, source_kind, synthetic = _decode_extract_source(
                workflow, expected, record["source"]
            )
            for ident, item in decoded.items():
                states[ident]["extraction"] = item
        else:
            decoded, metrics, source_kind, synthetic = _decode_decide_source(
                workflow, expected, record["source"]
            )
            for ident, item in decoded.items():
                states[ident]["decision"] = item
        stages.append({
            "stage": stage,
            "source_kind": source_kind,
            "provenance": record["source"].get("provenance"),
            "synthetic": synthetic,
            "plan": expected,
            "metrics": metrics,
        })
    stage, plan = _expected_stage(workflow, states, len(workflow["rounds"]))
    return workflow, states, stage, plan, stages


def prepare_stage(workflow: Any) -> dict[str, Any] | None:
    """Return the current retained collection plan, or ``None`` when terminal."""

    _, _, _, plan, _ = _rebuild(workflow)
    return copy.deepcopy(plan)


def apply_stage(workflow: Any, source: Any) -> dict[str, Any]:
    """Atomically append one fully bound native record or verified collection."""

    current, _, stage, expected, _ = _rebuild(workflow)
    _require(stage is not None and expected is not None,
             "workflow is terminal; no stage can be applied")
    retained = _read(source)
    # Decode before mutation. Missing, duplicate, or tampered input never
    # produces a partially advanced workflow.
    if stage == "extract":
        _decode_extract_source(current, expected, retained)
    else:
        _decode_decide_source(current, expected, retained)
    updated = copy.deepcopy(current)
    updated["rounds"].append({
        "stage": stage,
        "plan": copy.deepcopy(expected),
        "plan_digest": al.digest(expected),
        "source": retained,
    })
    result = _seal(updated)
    _rebuild(result)
    return result


def _sum_usage(values: list[Any]) -> dict[str, Any] | None:
    return ew._sum_usage(values)


def _sum_costs(values: list[Any]) -> dict[str, Any] | None:
    return ew._sum_costs(values)


def _field_diff(
    expected: dict[str, Any], actual: dict[str, Any] | None
) -> list[dict[str, Any]]:
    if actual is None:
        return []
    differences = []
    for name, value in expected.items():
        observed = actual.get(name)
        same = observed == value
        if isinstance(value, (int, float)) and not isinstance(value, bool) \
                and observed is not None:
            try:
                same = Decimal(str(value)) == Decimal(str(observed))
            except InvalidOperation:
                same = False
        if not same:
            differences.append({
                "field": name,
                "expected": value,
                "actual": observed,
            })
    return differences


def _row_report(
    workflow: dict[str, Any],
    planned: dict[str, Any],
    state: dict[str, dict[str, Any]],
    decision_source_kind: str | None,
) -> dict[str, Any]:
    case = _case_map(workflow)[planned["case_id"]]
    extraction = state["extraction"]
    decision = state["decision"]
    calculation = None
    retrieval = None
    public_input = None
    projected = None
    if workflow["condition"] == "direct":
        public_input = _projection_body(
            workflow["suite"], case, "direct", {}, {}, None
        )
        projected = _action_from_input(public_input)
    elif extraction is not None and extraction["outcome"] == "ok":
        values = extraction["values"]
        calculation = _calculate(
            case, values,
            force_gold=workflow["intervention"] == "calculation",
        )
        retrieval = (
            _retrieval(case, values, workflow["intervention"])
            if workflow["condition"] == "source-linked" else None
        )
        public_input = _projection_body(
            workflow["suite"], case, workflow["condition"], values,
            calculation, retrieval,
        )
        projected = _action_from_input(public_input)

    if decision is not None:
        outcome = decision["outcome"]
        action = decision.get("action")
        terminal = True
        loss = (
            case["oracle"]["losses"][action]
            if outcome == "ok"
            else case["oracle"]["failure_loss"]
        )
    elif extraction is not None and extraction["outcome"] != "ok":
        outcome, action, terminal = extraction["outcome"], None, True
        loss = case["oracle"]["failure_loss"]
    else:
        outcome, action, terminal, loss = "missing", None, False, None

    differences = (
        _field_diff(case["oracle"]["gold_fields"], extraction["values"])
        if extraction is not None and extraction["outcome"] == "ok" else []
    )
    status_field_present = "status_evidence" in case["fields"]
    attribution = {
        "extraction": (
            "missing" if extraction is None
            else "failure" if extraction["outcome"] != "ok"
            else "exact" if not differences else "field_error"
        ),
        "schema": (
            "not_applicable" if workflow["condition"] == "direct"
            else "sufficient" if status_field_present
            else "information_missing"
        ),
        "calculation": (
            "not_applicable" if workflow["condition"] == "direct"
            else "not_run" if calculation is None
            else "missing_operand" if not calculation["complete"]
            else "exact" if calculation["matches_gold"]
            else "upstream_operand_error"
        ),
        "retrieval": (
            "not_applicable" if workflow["condition"] != "source-linked"
            else "not_run" if retrieval is None
            else "exact" if retrieval["matches_gold"]
            else "evidence_link_error"
        ),
        "decision": (
            "missing" if decision is None
            else "failure" if outcome != "ok"
            else "exact" if action == case["oracle"]["optimal_action"]
            else "decision_error"
        ),
    }
    return {
        "id": planned["id"],
        "case_id": planned["case_id"],
        "source_family": planned["source_family"],
        "condition": workflow["condition"],
        "replicate": planned["replicate"],
        "split": planned["split"],
        "extraction_outcome": (
            "missing" if extraction is None else extraction["outcome"]
        ),
        "decision_outcome": outcome,
        "action": action,
        "projected_action": projected,
        "optimal_action": case["oracle"]["optimal_action"],
        "correct": (
            action == case["oracle"]["optimal_action"]
            if outcome == "ok" else None
        ),
        "honest_under_projection": (
            action == projected if outcome == "ok" else None
        ),
        "terminal": terminal,
        "terminal_loss": loss,
        "adopted_fields": (
            None if extraction is None else copy.deepcopy(extraction["values"])
        ),
        "field_differences": differences,
        "calculation": calculation,
        "retrieval": retrieval,
        "body": public_input,
        "attribution": attribution,
        "source_kinds": {
            "extraction": (
                None if extraction is None else extraction["source_kind"]
            ),
            "calculation": (
                None if calculation is None else calculation["source"]
            ),
            "retrieval": None if retrieval is None else retrieval["source"],
            "decision": None if decision is None else decision_source_kind,
        },
    }


def _request_accounting(stages: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    requests = []
    for stage in stages:
        plan = stage.get("plan")
        metrics = stage.get("metrics") or {}
        attempts = [item.get("attempts") for item in metrics.values()]
        usages = [item.get("usage") for item in metrics.values()]
        costs = [item.get("cost") for item in metrics.values()]
        requests.extend({"stage": stage["stage"], "request_id": ident,
                         "source_kind": stage["source_kind"], "synthetic": stage["synthetic"],
                         **copy.deepcopy(metric)} for ident, metric in metrics.items())
        rows.append({
            "stage": stage["stage"],
            "source_kind": stage["source_kind"],
            "provenance": stage.get("provenance"),
            "synthetic": stage.get("synthetic"),
            "planned_requests": 0 if plan is None else len(plan["requests"]),
            "request_count": len(metrics),
            "attempt_count": (
                sum(attempts)
                if attempts and all(type(item) is int for item in attempts)
                else None
            ),
            "latency_ms": ew._sum_numbers([m.get("latency_ms") for m in metrics.values()]),
            "usage": _sum_usage(usages),
            "cost": _sum_costs(costs),
        })
    attempt_values = [row["attempt_count"] for row in rows
                      if row["request_count"]]
    usage_values = [row["usage"] for row in rows if row["request_count"]]
    cost_values = [row["cost"] for row in rows if row["request_count"]]
    call_values = [
        0 if row["synthetic"] is True
        else row["attempt_count"] if row["source_kind"] == "collector"
        and row["synthetic"] is False else None
        for row in rows if row["request_count"]
    ]
    return {
        "request_count": sum(row["request_count"] for row in rows),
        "call_count": sum(call_values) if all(type(v) is int for v in call_values) else None,
        "call_count_basis": "Retained collector outbound attempts; synthetic fixtures contribute zero; imported calls are unknown.",
        "attempt_count": (
            sum(attempt_values)
            if attempt_values
            and all(type(item) is int for item in attempt_values)
            else None
        ),
        "latency_ms": ew._sum_numbers([row["latency_ms"] for row in rows if row["request_count"]]),
        "usage": _sum_usage(usage_values),
        "cost": _sum_costs(cost_values),
        "stages": rows,
        "requests": requests,
    }


def report(workflow: Any) -> dict[str, Any]:
    """Re-decode retained sources and report the complete planned denominator."""

    workflow, states, next_stage, _, stages = _rebuild(workflow)
    decision_kinds = [
        stage["source_kind"] for stage in stages if stage["stage"] == "decide"
    ]
    decision_source_kind = decision_kinds[0] if decision_kinds else None
    rows = [
        _row_report(
            workflow, planned, states[planned["id"]], decision_source_kind
        )
        for planned in workflow["planned"]
    ]
    losses = [row["terminal_loss"] for row in rows]
    source_markers = [stage.get("synthetic") for stage in stages]
    synthetic = (
        True if source_markers
        and all(marker is True for marker in source_markers)
        else False if source_markers
        and all(marker is False for marker in source_markers)
        else None
    )
    by_condition: dict[str, dict[str, Any]] = {}
    for row in rows:
        group = by_condition.setdefault(row["condition"], {
            "planned": 0,
            "terminal": 0,
            "missing": 0,
            "correct": 0,
            "honest_under_projection": 0,
        })
        group["planned"] += 1
        group["terminal"] += int(row["terminal"])
        group["missing"] += int(not row["terminal"])
        group["correct"] += int(row["correct"] is True)
        group["honest_under_projection"] += int(
            row["honest_under_projection"] is True
        )
    by_family: dict[str, dict[str, Any]] = {}
    for row in rows:
        group = by_family.setdefault(row["source_family"], {
            "planned": 0,
            "terminal": 0,
            "missing": 0,
            "correct": 0,
        })
        group["planned"] += 1
        group["terminal"] += int(row["terminal"])
        group["missing"] += int(not row["terminal"])
        group["correct"] += int(row["correct"] is True)
    return {
        "schema": REPORT_SCHEMA,
        "suite_digest": al.digest(workflow["suite"]),
        "route": workflow["route"],
        "requested_model": workflow["model"],
        "condition": workflow["condition"],
        "intervention": workflow["intervention"],
        "replicates": workflow["replicates"],
        "planned": len(workflow["planned"]),
        "fully_terminal": all(row["terminal"] for row in rows),
        "next_stage": next_stage,
        "counts": {
            "planned": len(rows),
            "terminal": sum(row["terminal"] for row in rows),
            "missing": sum(not row["terminal"] for row in rows),
            "decision_ok": sum(
                row["decision_outcome"] == "ok" for row in rows
            ),
            **{
                status: sum(
                    row["decision_outcome"] == status for row in rows
                )
                for status in ("unknown", "refusal", "error")
            },
            "correct": sum(row["correct"] is True for row in rows),
            "business_abstained": sum(row["decision_outcome"] == "ok" and row["action"] == "needs_more_context" for row in rows),
            "honest_under_projection": sum(
                row["honest_under_projection"] is True for row in rows
            ),
        },
        "loss": {
            "complete": all(value is not None for value in losses),
            "total": (
                sum(losses)
                if all(value is not None for value in losses) else None
            ),
            "resolved": sum(value is not None for value in losses),
            "missing": sum(value is None for value in losses),
        },
        "by_condition": by_condition,
        "by_family": by_family,
        "source_records": [{
            "stage": stage["stage"],
            "source_kind": stage["source_kind"],
            "provenance": stage.get("provenance"),
            "synthetic": stage.get("synthetic"),
        } for stage in stages],
        "synthetic": synthetic,
        "live_verified": False,
        "gold_intervention": workflow["intervention"],
        "native": _request_accounting(stages),
        "rows": rows,
        "interval": None,
        "interval_note": (
            "No confidence interval: finite authored cases, repeats, and arms "
            "share source families and are not independent samples."
        ),
    }


def compare(left: Any, right: Any) -> dict[str, Any]:
    """Pair all planned cases/replicates; missing rows stay in the denominator."""

    left_workflow, right_workflow = _read(left), _read(right)
    left_report = report(left_workflow)
    right_report = report(right_workflow)
    a_extract = next((r for r in left_workflow["rounds"] if r["stage"] == "extract"), None)
    b_extract = next((r for r in right_workflow["rounds"] if r["stage"] == "extract"), None)
    shared_extraction = a_extract is not None and a_extract == b_extract
    _require(left_report["suite_digest"] == right_report["suite_digest"],
             "comparison requires the identical frozen suite")
    left_rows = {
        (row["case_id"], row["replicate"]): row
        for row in left_report["rows"]
    }
    right_rows = {
        (row["case_id"], row["replicate"]): row
        for row in right_report["rows"]
    }
    _require(set(left_rows) == set(right_rows),
             "comparison requires identical planned identities")
    rows = []
    for key in sorted(left_rows):
        a, b = left_rows[key], right_rows[key]
        paired = a["terminal"] and b["terminal"]
        delta = (
            b["terminal_loss"] - a["terminal_loss"]
            if paired and a["terminal_loss"] is not None
            and b["terminal_loss"] is not None else None
        )
        rows.append({
            "case_id": key[0],
            "replicate": key[1],
            "source_family": a["source_family"],
            "left_condition": a["condition"],
            "right_condition": b["condition"],
            "left_outcome": a["decision_outcome"],
            "right_outcome": b["decision_outcome"],
            "left_action": a["action"],
            "right_action": b["action"],
            "left_missing": not a["terminal"],
            "right_missing": not b["terminal"],
            "fully_observed_pair": paired,
            "left_correct": a["correct"],
            "right_correct": b["correct"],
            "left_loss": a["terminal_loss"],
            "right_loss": b["terminal_loss"],
            "delta_right_minus_left": delta,
        })
    observed = [row for row in rows if row["fully_observed_pair"]]
    return {
        "schema": COMPARE_SCHEMA,
        "suite_digest": left_report["suite_digest"],
        "left_condition": left_report["condition"],
        "right_condition": right_report["condition"],
        "shared_extraction_request_count": len(a_extract["plan"]["requests"]) if shared_extraction else 0,
        "accounting_note": "Each side reports its requests once; shared upstream costs must not be added across comparison sides.",
        "left_intervention": left_report["gold_intervention"],
        "right_intervention": right_report["gold_intervention"],
        "evidence": {
            "left": left_report["source_records"],
            "right": right_report["source_records"],
            "note": (
                "Synthetic, imported and collector sources remain distinct; "
                "no source claim is live authentication."
            ),
        },
        "summary": {
            "planned": len(rows),
            "fully_observed_pairs": len(observed),
            "left_missing": sum(row["left_missing"] for row in rows),
            "right_missing": sum(row["right_missing"] for row in rows),
            "left_correct": sum(row["left_correct"] is True for row in rows),
            "right_correct": sum(
                row["right_correct"] is True for row in rows
            ),
            "left_loss_total": left_report["loss"]["total"],
            "right_loss_total": right_report["loss"]["total"],
            "complete": len(observed) == len(rows),
            "paired_delta_total": (
                sum(row["delta_right_minus_left"] for row in rows)
                if len(observed) == len(rows) else None
            ),
            "conditional_observed_pairs": {
                "denominator": len(observed),
                "left_loss_total": sum(row["left_loss"] for row in observed),
                "right_loss_total": sum(row["right_loss"] for row in observed),
                "delta_total": sum(row["delta_right_minus_left"] for row in observed),
            },
        },
        "by_family": {
            family: {
                "planned": sum(
                    row["source_family"] == family for row in rows
                ),
                "fully_observed_pairs": sum(
                    row["source_family"] == family
                    and row["fully_observed_pair"] for row in rows
                ),
            }
            for family in sorted({
                row["source_family"] for row in rows
            })
        },
        "rows": rows,
        "interval": None,
        "live_verified": False,
    }


def _demo_extract_values(
    case: dict[str, Any], policy: str
) -> dict[str, Any]:
    values = copy.deepcopy(case["oracle"]["gold_fields"])
    if policy == "wrong-field":
        for name in ("quantity", "unit_price", "shipping"):
            if values.get(name) is not None:
                values[name] = float(Decimal(str(values[name])) + 1)
                break
    elif policy in ("wrong-evidence", "wrong-version"):
        distractor = _distractor_line(case["source"])
        if "status_evidence" in values and distractor is not None:
            values["status_evidence"] = distractor
        if policy == "wrong-version" and "target_version" in values:
            values["target_version"] = "v1"
    return values


def _demo_answers(
    case: dict[str, Any], values: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    return {
        name: {
            "type": case["fields"][name]["type"],
            "value": value,
            "confidence": 0.8,
        }
        for name, value in values.items()
    }


def _demo_extraction_source(
    workflow: dict[str, Any], policy: str
) -> dict[str, Any]:
    """Create a clearly synthetic typed record/collection fixture."""

    plan = prepare_stage(workflow)
    _require(plan is not None and plan.get("kind") == "typed-values",
             "current stage is not Clairic extraction")
    cases = _case_map(workflow)
    attempts = []
    for request in plan["requests"]:
        case_id = request["case_id"]
        values = _demo_extract_values(cases[case_id], policy)
        raw = {
            "model": "clairic",
            "answers": _demo_answers(cases[case_id], values),
            "truncated": False,
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
        attempts.append({
            "request_id": request["id"],
            "attempt": 0,
            "state": "ok",
            "delivery": "response_received",
            "http_status": 200,
            "parsed": raw,
            "parse_status": "parsed",
            "raw_body_base64": base64.b64encode(
                json.dumps(raw, ensure_ascii=False).encode("utf-8")
            ).decode("ascii"),
            "elapsed_ms": None,
            "usage": None,
            "cost": None,
        })
    source = {
        "schema": collection.SCHEMA,
        "plan": copy.deepcopy(plan),
        "endpoint": "offline://typed-dag",
        "provenance": "synthetic",
        "synthetic": True,
        "live_verified": False,
        "order": [request["id"] for request in plan["requests"]],
        "attempts": attempts,
        "state": "settled",
    }
    return _seal(source)


def _demo_decision_source(
    workflow: dict[str, Any], policy: str
) -> dict[str, Any]:
    plan = prepare_stage(workflow)
    _require(plan is not None and plan.get("kind") == "api-lab",
             "current stage is not a native decision")
    manifest = plan["manifest"]
    route = manifest["route"]
    entries = []
    for request in manifest["requests"]:
        body = request["body"]
        public_input = json.loads(body.get("input", body.get("state")))
        action = _action_from_input(public_input)
        if policy == "wrong-decision":
            action = next(value for value in ACTIONS if value != action)
        values = al._values(al.native_questions(body, route)["action"], route)
        answer = {
            "type": "choice",
            "choice": action,
            "confidence": 1.0,
            "probabilities": (
                [{"value": value, "probability": float(value == action)}
                 for value in values]
                if route == "decisions"
                else {value: float(value == action) for value in values}
            ),
        }
        if route == "decisions":
            answer["name"] = "action"
            response = {"model": manifest["model"], "answers": [answer]}
        else:
            response = {
                "model": manifest["model"],
                "answers": {"action": answer},
            }
        if route in al.CLOUDFLARE_ROUTES:
            response = {"success": True, "errors": [], "result": response}
        entries.append({
            "request_id": request["id"],
            "http_status": 200,
            "response": response,
        })
    return al.build_record(manifest, entries, provenance="synthetic")


def _demo_stage_source(
    workflow: Any, policy: str = "oracle"
) -> dict[str, Any]:
    """Return the next synthetic native-format source for this workflow."""

    _require(policy in DEMO_POLICIES, "unknown demo policy")
    current, _, stage, plan, _ = _rebuild(workflow)
    _require(stage is not None and plan is not None, "workflow is terminal")
    if stage == "extract":
        return _demo_extraction_source(current, policy)
    return _demo_decision_source(current, policy)


def demo(
    suite: Any | None = None,
    *,
    route: str = "decisions",
    model: str | None = None,
    account_id: str | None = None,
    replicates: int = 1,
    condition: str = "fields-only",
    intervention: str | None = None,
    policy: str = "oracle",
) -> dict[str, Any]:
    """Run a complete synthetic control through native-format stage records."""

    _require(policy in DEMO_POLICIES, "unknown demo policy")
    suite = build_suite() if suite is None else suite
    workflow = start(
        suite, route=route, model=model, account_id=account_id,
        replicates=replicates, condition=condition, intervention=intervention,
    )
    while prepare_stage(workflow) is not None:
        workflow = apply_stage(
            workflow, _demo_stage_source(workflow, policy)
        )
    return workflow
