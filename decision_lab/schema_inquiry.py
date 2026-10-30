"""Finite schema witnesses composed with the existing active-evidence engine.

The authored worlds are local scoring material. Compilation publishes every
hypothetical observation but never the selected actual world. Projections are
synthetic oracle controls, not claims of successful model extraction.
"""
from __future__ import annotations

import copy
from itertools import combinations
import json

from . import api_lab as al, evidence, generators

DESIGN_SCHEMA = "decisions-lab.schema-design/1"
AUDIT_SCHEMA = "decisions-lab.schema-audit/1"
FIELDS = {
    "entity": "目标实体",
    "status": "登记状态",
    "current_version": "现行版本号",
    "current_policy": "现行条款",
    "archive_policy": "旧版条款",
}
DEFAULT_FIELDS = ("entity", "status")
MECHANISMS = ("current-policy", "version-binding", "unavailable", "already-sufficient")
LABELS = {"activate": "按现行条款启用", "hold": "按现行条款暂不启用"}
RULE = "目标实体以最大版本号的条款为准；permit 对应 activate，deny 对应 hold。ready 状态本身不授予启用。"


def _key(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))


def _intersection(rows):
    return set.intersection(*(set(row["optimal_actions"]) for row in rows))


def _groups(rows, selected):
    groups = {}
    for row in rows:
        key = (row["source_family"], _key({name: row["values"][name] for name in selected}))
        groups.setdefault(key, []).append(row)
    return list(groups.values())


def _repairs(rows, selected, omitted):
    repairs = []
    for size in range(1, len(omitted) + 1):
        for extra in combinations(omitted, size):
            if any(set(previous) <= set(extra) for previous in repairs):
                continue
            if all(_intersection(group) for group in _groups(rows, selected + list(extra))):
                repairs.append(list(extra))
    return repairs


def audit(rows, selected_fields):
    """Exhaustively check a bounded, explicitly authored finite domain.

    A group needs a common optimal action, not merely pairwise intersections.
    Witnesses have minimum cardinality (lexical tie break); repairs are all
    inclusion-minimal extra field sets within the declared observable columns.
    No conclusion extends beyond these rows and their author-supplied labels.
    """
    al.require(isinstance(rows, list) and 1 <= len(rows) <= 128, "audit needs 1–128 finite rows")
    al.require(isinstance(selected_fields, (list, tuple)), "selected_fields must be a list")
    al.require(all(isinstance(name, str) for name in selected_fields)
               and len(set(selected_fields)) == len(selected_fields), "duplicate/invalid selected fields")
    ids, columns = set(), None
    for row in rows:
        al.require(isinstance(row, dict), "audit row must be an object")
        ident, family, values, optimal = (row.get(k) for k in ("id", "source_family", "values", "optimal_actions"))
        al.require(isinstance(ident, str) and ident and ident not in ids, "duplicate/invalid audit row ID")
        ids.add(ident)
        al.require(isinstance(family, str) and family, "source_family required")
        al.require(isinstance(values, dict) and 1 <= len(values) <= 8
                   and all(isinstance(k, str) and k for k in values), "use 1–8 observable fields")
        _key(values)
        columns = set(values) if columns is None else columns
        al.require(set(values) == columns, "all finite rows must declare the same fields (missing = null)")
        al.require(isinstance(optimal, list) and optimal and all(isinstance(a, str) and a for a in optimal)
                   and len(set(optimal)) == len(optimal), "optimal_actions must be nonempty unique strings")
    al.require(set(selected_fields) <= columns, "unknown selected field")
    al.require(all(sum(r["source_family"] == family for r in rows) <= 12
                   for family in {r["source_family"] for r in rows}), "at most 12 worlds per source family")
    selected = sorted(selected_fields)
    omitted = sorted(columns - set(selected))
    groups = _groups(sorted(rows, key=lambda r: r["id"]), selected)
    findings = []
    for group in groups:
        common = sorted(_intersection(group))
        witness = []
        if not common:
            for size in range(2, len(group) + 1):
                witness = next((list(part) for part in combinations(group, size) if not _intersection(part)), [])
                if witness:
                    break
        findings.append({"source_family": group[0]["source_family"],
                         "projection": {name: copy.deepcopy(group[0]["values"][name]) for name in selected},
                         "row_ids": [row["id"] for row in group], "common_optimal_actions": common,
                         "sufficient": bool(common), "witness": copy.deepcopy(witness),
                         "minimal_repairs": _repairs(group, selected, omitted) if not common else [],
                         "omitted_differences": [name for name in omitted
                             if len({_key(row["values"][name]) for row in group}) > 1]})
    repairs = []
    if any(not item["sufficient"] for item in findings):
        repairs = _repairs(rows, selected, omitted)
    return {"schema": AUDIT_SCHEMA, "selected_fields": selected, "available_fields": sorted(columns),
            "rows": len(rows), "source_families": len({r["source_family"] for r in rows}),
            "groups": findings, "insufficient_groups": sum(not g["sufficient"] for g in findings),
            "sufficient": all(g["sufficient"] for g in findings), "minimal_repairs": repairs,
            "scope": "Within each declared source family and these finite authored rows only; no open-text proof.",
            "projection_provenance": "synthetic oracle projection; not model extraction", "live_verified": False}


def build_design(seed=20261030):
    """Four mechanisms, two explicit worlds each; seed does not add sources."""
    dataset = generators.generate_dataset("documents", seed=seed, units=4)
    families = []
    titles = ("字段相同，现行条款相反", "旧版与邻实体干扰", "关键条款无法取得", "已有共同最优行动")
    for index, (mechanism, title) in enumerate(zip(MECHANISMS, titles)):
        base = next(r for r in dataset["rows"] if r["source_family"] == f"documents-{seed}-{index:05d}"
                    and r["condition"] == "base")
        world = copy.deepcopy(base["latent_world"])
        cases = []
        for n in range(2):
            item = copy.deepcopy(world)
            current = max(item["documents"], key=lambda d: d["version"])
            current["policy"] = "permit" if n == 0 or mechanism == "already-sufficient" else "deny"
            if mechanism == "already-sufficient":
                min(item["documents"], key=lambda d: d["version"])["policy"] = "permit" if n else "deny"
            if mechanism == "version-binding":
                item["documents"].reverse()
            cases.append({"id": f"world-{n}", "world": item, "prior": 0.5})
        families.append({"id": mechanism, "title": title, "mechanism": mechanism,
                         "current_available": mechanism != "unavailable", "cases": cases})
    return {"schema": DESIGN_SCHEMA, "seed": seed, "fields": list(DEFAULT_FIELDS), "families": families}


def validate_design(design):
    al.require(isinstance(design, dict) and design.get("schema") == DESIGN_SCHEMA, "invalid schema inquiry design")
    al.require(set(design) == {"schema", "seed", "fields", "families"}, "unknown schema design fields")
    al.require(type(design["seed"]) is int and design["seed"] >= 0, "seed must be nonnegative integer")
    selected = design["fields"]
    al.require(isinstance(selected, list) and all(isinstance(n, str) for n in selected)
               and len(set(selected)) == len(selected) and set(selected) <= set(FIELDS), "invalid schema fields")
    families = design["families"]
    al.require(isinstance(families, list) and 1 <= len(families) <= 8, "use 1–8 finite families")
    seen = set()
    for family in families:
        al.require(isinstance(family, dict) and set(family) == {
            "id", "title", "mechanism", "current_available", "cases"}, "invalid family shape")
        ident = family["id"]
        al.require(isinstance(ident, str) and ident and ":" not in ident and ident not in seen, "invalid family ID")
        seen.add(ident)
        al.require(isinstance(family["title"], str) and family["title"]
                   and family["mechanism"] in MECHANISMS and type(family["current_available"]) is bool,
                   "invalid family metadata")
        cases = family["cases"]
        al.require(isinstance(cases, list) and 1 <= len(cases) <= 8, "use 1–8 worlds per family")
        case_ids = set()
        for case in cases:
            al.require(isinstance(case, dict) and set(case) == {"id", "world", "prior"}, "invalid finite case")
            cid = case["id"]
            al.require(isinstance(cid, str) and cid and ":" not in cid and cid not in case_ids, "invalid world ID")
            case_ids.add(cid)
            al.require(al.finite(case["prior"]) and not isinstance(case["prior"], bool)
                       and case["prior"] > 0, "positive prior required")
            generators.document_oracle(case["world"])
            al.require(len(case["world"]["documents"]) >= 2,
                       "schema inquiry requires distinct archive and current documents")
        al.require(abs(sum(c["prior"] for c in cases) - 1) < 1e-10, "family priors must sum to one")
    return design


def _material(family, case):
    world = case["world"]
    current = max(world["documents"], key=lambda d: d["version"])
    archive = min(world["documents"], key=lambda d: d["version"])
    lines = [f"目标实体：{world['entity']}；登记状态：ready。", RULE]
    passages = {}
    for doc in world["documents"]:
        if doc is current and not family["current_available"]:
            line = f"实体 {world['entity']}；版本 {doc['version']}；现行条款未保留，无法核对。"
        else:
            line = f"实体 {world['entity']}；版本 {doc['version']}；状态 {doc['status']}；条款 {doc['policy']}。"
        lines.append(line)
        if doc is current:
            passages["current"] = line
        if doc is archive:
            passages["archive"] = line
    lines.append("邻实体：neighbor；版本 9；状态 ready；条款 permit；不适用于目标。")
    source = "\n".join(lines)
    values = {"entity": world["entity"], "status": "ready", "current_version": current["version"],
              "current_policy": current["policy"] if family["current_available"] else None,
              "archive_policy": archive["policy"]}
    return source, passages, values


def finite_rows(design):
    validate_design(design)
    rows = []
    for family in design["families"]:
        for case in family["cases"]:
            source, _, values = _material(family, case)
            rows.append({"id": family["id"] + "/" + case["id"], "source_family": family["id"],
                         "source": source, "values": values,
                         "optimal_actions": generators.document_oracle(case["world"])["best_actions"]})
    return rows


def audit_design(design):
    result = audit(finite_rows(design), design["fields"])
    titles = {family["id"]: family["title"] for family in design["families"]}
    for group in result["groups"]:
        group["title"] = titles[group["source_family"]]
    return result


def _observation(family, case, query):
    source, passages, _ = _material(family, case)
    quote = passages[query]
    current = max(case["world"]["documents"], key=lambda d: d["version"])
    doc = current if query == "current" else min(case["world"]["documents"], key=lambda d: d["version"])
    return _key({"entity": case["world"]["entity"], "version": doc["version"],
                 "available": query != "current" or family["current_available"], "quote": quote,
                 "locator": {"source": "provided-dossier/" + doc["id"], "start": 0,
                             "end": len(quote), "unit": "unicode_codepoint", "range": "half_open"}})


def compile_suite(design):
    """Condition on the chosen schema, then reuse E2 histories and native I/O."""
    checked = audit_design(design)
    families = {f["id"]: f for f in design["families"]}
    scenarios = []
    for index, group in enumerate(checked["groups"]):
        family = families[group["source_family"]]
        cases = [c for c in family["cases"] if family["id"] + "/" + c["id"] in group["row_ids"]]
        mass = sum(c["prior"] for c in cases)
        scenarios.append({"id": f"{family['id']}-g{index}", "title": family["title"],
            "description": _key({"rules": RULE, "fields": group["projection"],
                "projection_provenance": "synthetic oracle fields",
                "note": "Known finite hypotheses; the actual world is hidden. A query reveals the actual source excerpt. Archive/neighbor do not supersede current version."}),
            "source_family": family["id"], "split": "development", "budget": 2, "max_queries": 2,
            "projection_group_prior_mass": mass,
            "abstain_loss": 3.0, "failure_loss": 12.0,
            "hypotheses": [{"id": c["id"], "prior": c["prior"] / mass,
                "observations": {q: _observation(family, c, q) for q in ("archive", "current")}} for c in cases],
            "queries": [{"id": "archive", "label": "读取目标旧版条款", "cost": 1},
                        {"id": "current", "label": "核对目标现行版本条款（若未保留则返回缺失）", "cost": 1}],
            "decisions": [{"id": a, "label": label,
                "losses": {c["id"]: 0.0 if a in generators.document_oracle(c["world"])["best_actions"] else 10.0
                           for c in cases}} for a, label in LABELS.items()]})
    result = {"schema": evidence.SUITE_SCHEMA, "seed": design["seed"], "provenance": "synthetic",
              "description": "Schema witness → bounded source inquiry; authored oracle fields, native decisions.",
              "schema_design": copy.deepcopy(design), "scenarios": scenarios}
    evidence.validate_suite(result)
    return result


def inspect_suite(suite):
    """Recompute retained metadata instead of trusting cached witness claims."""
    design = suite.get("schema_design")
    if design is None:
        return None
    al.require(compile_suite(design) == suite, "schema design differs from compiled evidence suite")
    return audit_design(design)


def episode_evidence(suite, row, *, source_visible=False):
    """Local inspector only: actual source and per-step remaining ambiguity."""
    design = suite["schema_design"]
    family = next(f for f in design["families"] if f["id"] == row["source_family"])
    case = next(c for c in family["cases"] if c["id"] == row["world_id"])
    scenario = next(s for s in suite["scenarios"] if s["id"] == row["scenario_id"])
    source, _, values = _material(family, case)
    steps, history = [], []
    for entry in row["history"]:
        visible = evidence.visible_from_history(scenario, history)
        info = evidence.decision_from_visible(scenario, visible)
        steps.append({"available_actions": visible["available_actions"],
                      "compatible_hypotheses": visible["compatible_hypotheses"],
                      "common_optimal_actions": info["robust_actions"],
                      "remaining_budget": visible["remaining_budget"], "chosen": copy.deepcopy(entry)})
        history.append(entry)
    return {"source": source, "projected_fields": {n: values[n] for n in design["fields"]},
            "source_documents": {json.loads(_observation(family, case, q))["locator"]["source"]:
                                 json.loads(_observation(family, case, q))["quote"] for q in ("archive", "current")},
            "steps": steps, "source_visible_to_model": source_visible,
            "notice": ("All available source material is included in the terminal model request."
                       if source_visible else "Full source is local inspector evidence; adaptive requests contain only revealed observations.")}
