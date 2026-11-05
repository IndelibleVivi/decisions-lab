"""Finite counterevidence inquiry composed with the active-evidence engine.

The source worlds are local scoring material. A model sees the initial dossier,
public query labels, and only observations it actually reads. Hypotheses,
posteriors, source family names, and the selected actual world stay local.
"""
from __future__ import annotations

import copy
import json

from . import api_lab as al, evidence

DESIGN_SCHEMA = "decisions-lab.counterevidence-design/1"
TRACE_SCHEMA = "decisions-lab.counterevidence-trace/1"
TARGET = "项目 aurora"
DECISION_YEAR = 2026
FAMILIES = (
    "stale-version",
    "wrong-entity",
    "omitted-exception",
    "unsupported-authority",
    "unavailable-source",
    "already-sufficient",
)
TITLES = {
    "stale-version": "旧版支持与生效版本",
    "wrong-entity": "同名实体的材料混入",
    "omitted-exception": "适用条件中的关键例外",
    "unsupported-authority": "发布者权限与适用范围",
    "unavailable-source": "原始来源不可得",
    "already-sufficient": "初步材料已经足够",
}
TASK = "核对目标对象的当前决定，并判断材料是否适用于该对象、时点、条件和权限。"
RULE = (
    "只采用目标实体、适用时点、适用条件和发布权限均满足的原始来源。"
    "版本号较大不自动授予效力；没有可采用的原始来源时不能补猜。"
    "业务上的暂缓（abstain）与 API 失败不同。"
)
DECISION_LABELS = {"allow": "允许", "hold": "不批准"}


def _key(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))


def _source(source_id, title, text, *, entity=TARGET, effective_from=2026, effective_to=None,
            condition="any", authority="origin", available=True, proposition=None):
    return {
        "id": source_id,
        "title": title,
        "text": text,
        "entity": entity,
        "effective_from": effective_from,
        "effective_to": effective_to,
        "condition": condition,
        "authority": authority,
        "available": available,
        "proposition": proposition,
    }


def _initial(claim, excerpt, source_id, attached=()):
    return {
        "claim": claim,
        "excerpt": excerpt,
        "source_id": source_id,
        "locator": {"source": source_id, "start": 0, "end": len(excerpt),
                    "unit": "unicode_codepoint", "range": "half_open"},
        "attached_sources": [_source_observation(source) for source in attached],
    }


def _case(world_id, prior, facts, sources, initial, audits):
    return {"id": world_id, "prior": prior, "facts": facts, "sources": sources,
            "initial": initial, "audits": audits}


def build_design(seed=20261106):
    """Build six fixed mechanisms with two explicit worlds each."""
    al.require(type(seed) is int and seed >= 0, "seed must be a nonnegative integer")
    families = []

    def add(name, cases):
        families.append({"id": name, "title": TITLES[name], "cases": cases})

    add("stale-version", [
        _case("stale-version/a", 0.5, {"observation_closed": True, "board_approved": True},
              [_source("policy-2024", "旧版目标政策", "目标项目可以启用。",
                       effective_from=2024, effective_to=2025, proposition="allow"),
               _source("policy-2026", "现行目标政策", "目标项目可以启用。", proposition="allow")],
              _initial("allow", "初步材料称项目 aurora 可以启用。", "initial-review"),
              {"version": {"source": "policy-2026", "label": "核对目标对象的现行版本"},
               "background": {"source": "policy-2024", "label": "读取目标对象的背景文件"}}),
        _case("stale-version/b", 0.5, {"observation_closed": True, "board_approved": True},
              [_source("policy-2024", "旧版目标政策", "目标项目可以启用。",
                       effective_from=2024, effective_to=2025, proposition="allow"),
               _source("policy-2026", "现行目标政策", "自 2026 年起，目标项目不得启用。",
                       proposition="hold")],
              _initial("allow", "初步材料称项目 aurora 可以启用。", "initial-review"),
              {"version": {"source": "policy-2026", "label": "核对目标对象的现行版本"},
               "background": {"source": "policy-2024", "label": "读取目标对象的背景文件"}}),
    ])

    add("wrong-entity", [
        _case("wrong-entity/a", 0.5, {"observation_closed": True, "board_approved": True},
              [_source("target", "目标实体决定", "项目 aurora 不得启用。", proposition="hold"),
               _source("neighbor", "邻实体决定", "项目 borealis 可以启用。",
                       entity="项目 borealis", proposition="allow")],
              _initial("allow", "同名材料称项目 aurora 可以启用。", "initial-review"),
              {"target": {"source": "target", "label": "核对目标实体的原始决定"},
               "neighbor": {"source": "neighbor", "label": "读取邻实体的规定"}}),
        _case("wrong-entity/b", 0.5, {"observation_closed": True, "board_approved": True},
              [_source("target", "目标实体决定", "项目 aurora 可以启用。", proposition="allow"),
               _source("neighbor", "邻实体决定", "项目 borealis 可以启用。",
                       entity="项目 borealis", proposition="allow")],
              _initial("allow", "同名材料称项目 aurora 可以启用。", "initial-review"),
              {"target": {"source": "target", "label": "核对目标实体的原始决定"},
               "neighbor": {"source": "neighbor", "label": "读取邻实体的规定"}}),
    ])

    add("omitted-exception", [
        _case("omitted-exception/a", 0.5, {"observation_closed": False, "board_approved": True},
              [_source("terms", "目标项目条款", "项目 aurora 仍在观察期；观察期结束前不得启用。",
                       condition="observation_active", proposition="hold")],
              _initial("allow", "初步材料称项目 aurora 可以启用。", "initial-review"),
              {"exceptions": {"source": "terms", "label": "核对条款中的适用例外"}}),
        _case("omitted-exception/b", 0.5, {"observation_closed": True, "board_approved": True},
              [_source("terms", "目标项目条款", "观察期已经结束，可以启用。",
                       condition="observation_closed", proposition="allow")],
              _initial("allow", "初步材料称项目 aurora 可以启用。", "initial-review"),
              {"exceptions": {"source": "terms", "label": "核对条款中的适用例外"}}),
    ])

    add("unsupported-authority", [
        _case("unsupported-authority/a", 0.5, {"observation_closed": True, "board_approved": False},
              [_source("notice", "候选发布通知", "项目 aurora 可以启用。",
                       authority="draft", proposition="allow"),
               _source("rule", "权限与批准记录", "只有理事会批准后可以启用；目前没有批准记录。",
                       proposition="hold")],
              _initial("allow", "候选材料称项目 aurora 可以启用。", "initial-review"),
              {"authority": {"source": "rule", "label": "核对批准权限与原始记录"},
               "notice": {"source": "notice", "label": "读取候选发布通知"}}),
        _case("unsupported-authority/b", 0.5, {"observation_closed": True, "board_approved": True},
              [_source("notice", "候选发布通知", "项目 aurora 可以启用。",
                       authority="draft", proposition="allow"),
               _source("rule", "权限与批准记录", "理事会批准了项目 aurora 的启用。",
                       proposition="allow")],
              _initial("allow", "候选材料称项目 aurora 可以启用。", "initial-review"),
              {"authority": {"source": "rule", "label": "核对批准权限与原始记录"},
               "notice": {"source": "notice", "label": "读取候选发布通知"}}),
    ])

    add("unavailable-source", [
        _case("unavailable-source/a", 0.5, {"observation_closed": True, "board_approved": False},
              [_source("missing", "目标原始审批文件", "项目 aurora 不得启用。",
                       available=False, proposition="hold"),
               _source("archive", "历史审批文件", "项目 aurora 可以启用。",
                       effective_from=2024, effective_to=2025, proposition="allow")],
              _initial("allow", "初步材料称项目 aurora 可以启用，但原始审批尚未核对。", "initial-review"),
              {"current": {"source": "missing", "label": "尝试读取当前原始审批文件"},
               "archive": {"source": "archive", "label": "读取历史审批文件"}}),
        _case("unavailable-source/b", 0.5, {"observation_closed": True, "board_approved": True},
              [_source("missing", "目标原始审批文件", "项目 aurora 可以启用。",
                       available=False, proposition="allow"),
               _source("archive", "历史审批文件", "项目 aurora 可以启用。",
                       effective_from=2024, effective_to=2025, proposition="allow")],
              _initial("allow", "初步材料称项目 aurora 可以启用，但原始审批尚未核对。", "initial-review"),
              {"current": {"source": "missing", "label": "尝试读取当前原始审批文件"},
               "archive": {"source": "archive", "label": "读取历史审批文件"}}),
    ])

    current = _source("current", "当前目标决定", "项目 aurora 可以启用。", proposition="allow")
    add("already-sufficient", [
        _case(f"already-sufficient/{world}", 0.5,
              {"observation_closed": True, "board_approved": True}, [copy.deepcopy(current)],
              _initial("allow", "已附当前目标决定的完整原文。", "initial-review", [current]),
              {"confirm": {"source": "current", "label": "复核当前目标决定"}})
        for world in ("a", "b")
    ])

    design = {
        "schema": DESIGN_SCHEMA,
        "seed": seed,
        "provenance": "synthetic",
        "description": "原创有限反证调查设计；来源、规则和标签均为合成材料。",
        "task": TASK,
        "rules": RULE,
        "target": TARGET,
        "decision_time": DECISION_YEAR,
        "families": families,
    }
    validate_design(design)
    return design


def _condition_applies(condition, facts):
    if condition == "any":
        return True
    if condition == "observation_closed":
        return facts["observation_closed"]
    if condition == "observation_active":
        return not facts["observation_closed"]
    if condition == "board_approved":
        return facts["board_approved"]
    if condition == "board_unapproved":
        return not facts["board_approved"]
    raise ValueError("unknown source applicability condition")


def _resolved_decision(case, target=TARGET, decision_time=DECISION_YEAR):
    applicable = []
    for source in case["sources"]:
        # Availability limits observation, not the latent source's legal effect.
        if source["authority"] != "origin":
            continue
        if source["entity"] != target:
            continue
        if not source["effective_from"] <= decision_time:
            continue
        if source["effective_to"] is not None and decision_time > source["effective_to"]:
            continue
        if not _condition_applies(source["condition"], case["facts"]):
            continue
        applicable.append(source)
    propositions = {source["proposition"] for source in applicable}
    al.require(len(applicable) == 1 and propositions <= {"allow", "hold"},
               "finite worlds require exactly one applicable original source")
    return applicable[0]["proposition"]


def _validate_observation(observation, source):
    if not source["available"]:
        al.require(observation == {"source_id": source["id"], "available": False,
                                  "notice": "原始审批文件未保留，无法取得内容。"},
                   "unavailable audit must not reveal source content or metadata")
        return
    al.require(set(observation) == {
        "source_id", "title", "available", "excerpt", "locator",
        "entity", "effective_from", "effective_to", "scope", "authority",
    }, "invalid audit observation shape")
    locator = observation["locator"]
    al.require(locator["source"] == observation["source_id"] and locator["start"] == 0
               and locator["end"] == len(observation["excerpt"])
               and locator["unit"] == "unicode_codepoint" and locator["range"] == "half_open",
               "audit locator must exactly cover the excerpt")
    al.require(observation["excerpt"] == source["text"], "available audit must reveal source text")


def validate_design(design):
    """Validate the bounded authored domain and recompute every source decision."""
    al.require(isinstance(design, dict) and design.get("schema") == DESIGN_SCHEMA,
               "invalid counterevidence design")
    al.require(set(design) == {
        "schema", "seed", "provenance", "description", "task", "rules", "target",
        "decision_time", "families",
    }, "unknown counterevidence design fields")
    al.require(type(design["seed"]) is int and design["seed"] >= 0,
               "seed must be a nonnegative integer")
    al.require(design["provenance"] == "synthetic" and isinstance(design["description"], str)
               and bool(design["description"]), "synthetic design provenance required")
    al.require(design["task"] == TASK and design["rules"] == RULE,
               "task and rules must match the finite evaluator")
    al.require(design["target"] == TARGET and design["decision_time"] == DECISION_YEAR,
               "fixed target and decision time required")
    families = design["families"]
    al.require(isinstance(families, list) and len(families) == len(FAMILIES)
               and [f.get("id") for f in families] == list(FAMILIES),
               "counterevidence requires six fixed source families")
    for family in families:
        al.require(isinstance(family, dict) and set(family) == {"id", "title", "cases"},
                   "invalid source family shape")
        al.require(family["title"] == TITLES[family["id"]], "fixed source family title required")
        cases = family["cases"]
        al.require(isinstance(cases, list) and len(cases) == 2,
                   "each source family needs exactly two worlds")
        ids = set()
        menus = []
        for case in cases:
            al.require(isinstance(case, dict) and set(case) == {
                "id", "prior", "facts", "sources", "initial", "audits",
            }, "invalid source world")
            world_id = case["id"]
            al.require(isinstance(world_id, str) and world_id.startswith(family["id"] + "/")
                       and world_id not in ids, "invalid or duplicate source world ID")
            ids.add(world_id)
            al.require(al.finite(case["prior"]) and not isinstance(case["prior"], bool)
                       and case["prior"] > 0, "positive source prior required")
            facts = case["facts"]
            al.require(isinstance(facts, dict) and set(facts) == {"observation_closed", "board_approved"}
                       and all(type(value) is bool for value in facts.values()),
                       "finite source facts required")
            sources = case["sources"]
            al.require(isinstance(sources, list) and 1 <= len(sources) <= 3,
                       "one to three source documents")
            source_ids = set()
            for source in sources:
                al.require(isinstance(source, dict) and set(source) == {
                    "id", "title", "text", "entity", "effective_from", "effective_to",
                    "condition", "authority", "available", "proposition",
                }, "invalid source document")
                al.require(isinstance(source["id"], str) and source["id"]
                           and source["id"] not in source_ids, "invalid or duplicate source ID")
                source_ids.add(source["id"])
                al.require(isinstance(source["title"], str) and source["title"]
                           and isinstance(source["text"], str) and source["text"],
                           "source title and text required")
                al.require(isinstance(source["entity"], str) and source["entity"],
                           "source entity required")
                al.require(type(source["effective_from"]) is int
                           and (source["effective_to"] is None
                                or type(source["effective_to"]) is int)
                           and source["effective_from"] <= (source["effective_to"]
                                                           if source["effective_to"] is not None
                                                           else source["effective_from"]),
                           "invalid source effective range")
                al.require(source["condition"] in {
                    "any", "observation_closed", "observation_active",
                    "board_approved", "board_unapproved",
                }, "invalid source applicability condition")
                al.require(source["authority"] in {"origin", "draft"},
                           "source authority must be origin or draft")
                al.require(type(source["available"]) is bool, "source availability must be boolean")
                al.require(source["proposition"] in {"allow", "hold"},
                           "latent source proposition must be allow or hold")
            initial = case["initial"]
            al.require(isinstance(initial, dict)
                       and set(initial) == {"claim", "excerpt", "source_id", "locator", "attached_sources"},
                       "invalid initial dossier")
            al.require(initial["claim"] in DECISION_LABELS
                       and isinstance(initial["excerpt"], str) and initial["excerpt"],
                       "explicit provisional claim required")
            al.require(initial["source_id"] == "initial-review", "initial source ID is fixed")
            al.require(initial["locator"] == {
                "source": "initial-review", "start": 0, "end": len(initial["excerpt"]),
                "unit": "unicode_codepoint", "range": "half_open",
            }, "initial locator must exactly cover the excerpt")
            al.require(isinstance(initial["attached_sources"], list), "initial sources must be a list")
            for attached in initial["attached_sources"]:
                source = next((s for s in sources if s["id"] == attached.get("source_id")), None)
                al.require(source is not None and source["available"], "initial source must be available")
                al.require(attached == _source_observation(source), "initial source differs from original")
            audits = case["audits"]
            al.require(isinstance(audits, dict) and 1 <= len(audits) <= 3,
                       "one to three named audits")
            for query_id, audit in audits.items():
                al.require(isinstance(query_id, str) and query_id
                           and isinstance(audit, dict)
                           and set(audit) == {"source", "label"}
                           and audit["source"] in source_ids
                           and isinstance(audit["label"], str) and audit["label"],
                           "invalid audit map")
                source = next(item for item in sources if item["id"] == audit["source"])
                _validate_observation(_audit_observation(family, case, query_id), source)
            menus.append([(key, item["label"]) for key, item in audits.items()])
            _resolved_decision(case, design["target"], design["decision_time"])
        al.require(menus[0] == menus[1], "paired worlds need identical audit menus")
        al.require(cases[0]["initial"] == cases[1]["initial"], "paired worlds need identical initial materials")
        al.require(abs(sum(case["prior"] for case in cases) - 1) < 1e-10,
                   "world priors must sum to one")
    return {"families": len(families),
            "worlds": sum(len(family["cases"]) for family in families)}


def _audit_observation(family, case, query_id):
    audit = case["audits"][query_id]
    source = next(item for item in case["sources"] if item["id"] == audit["source"])
    return _source_observation(source)


def _source_observation(source):
    if not source["available"]:
        return {"source_id": source["id"], "available": False,
                "notice": "原始审批文件未保留，无法取得内容。"}
    excerpt = source["text"]
    return {
        "source_id": source["id"],
        "title": source["title"],
        "available": source["available"],
        "excerpt": excerpt,
        "locator": {"source": source["id"], "start": 0, "end": len(excerpt),
                    "unit": "unicode_codepoint", "range": "half_open"},
        "entity": source["entity"],
        "effective_from": source["effective_from"],
        "effective_to": source["effective_to"],
        "scope": source["condition"],
        "authority": source["authority"],
    }


def _scenario(design, family):
    cases = family["cases"]
    mass = sum(case["prior"] for case in cases)
    queries = [
        {"id": query_id, "label": audit["label"], "cost": 1}
        for query_id, audit in cases[0]["audits"].items()
    ]
    resolved = {case["id"]: _resolved_decision(case) for case in cases}

    def losses(decision):
        result = {}
        for case in cases:
            result[case["id"]] = 0.0 if decision == resolved[case["id"]] else 10.0
        return result

    return {
        "id": family["id"],
        "title": family["title"],
        "description": RULE,
        "source_family": family["id"],
        "split": "development",
        "budget": 3,
        "max_queries": 3,
        "abstain_loss": 3.0,
        "failure_loss": 12.0,
        "counterevidence_family": family["id"],
        "counterevidence_initial": copy.deepcopy(cases[0]["initial"]),
        "counterevidence_task": design["task"],
        "counterevidence_rules": design["rules"],
        "counterevidence_target": design["target"],
        "counterevidence_decision_time": design["decision_time"],
        "hypotheses": [
            {
                "id": case["id"],
                "prior": case["prior"] / mass,
                "observations": {
                    query["id"]: _key(_audit_observation(family, case, query["id"]))
                    for query in queries
                },
            }
            for case in cases
        ],
        "queries": queries,
        "decisions": [
            {"id": decision, "label": DECISION_LABELS[decision], "losses": losses(decision)}
            for decision in ("allow", "hold")
        ],
    }


def compile_suite(design):
    """Compile fixed source worlds into the regular E2 suite schema."""
    validate_design(design)
    scenarios = [_scenario(design, family) for family in design["families"]]
    result = {
        "schema": evidence.SUITE_SCHEMA,
        "seed": design["seed"],
        "provenance": "synthetic",
        "description": "Counterevidence inquiry: source adequacy and stopping in finite synthetic worlds.",
        "counterevidence_design": copy.deepcopy(design),
        "scenarios": scenarios,
    }
    evidence.validate_suite(result)
    return result


def inspect_suite(suite):
    """Recompute a retained suite instead of trusting cached projection fields."""
    design = suite.get("counterevidence_design") if isinstance(suite, dict) else None
    if design is None:
        return None
    al.require(compile_suite(design) == suite,
               "counterevidence design differs from compiled evidence suite")
    return {
        "schema": "decisions-lab.counterevidence-audit/1",
        "families": len(design["families"]),
        "worlds": sum(len(family["cases"]) for family in design["families"]),
        "named_audits": len({query["id"] for scenario in suite["scenarios"]
                             for query in scenario["queries"]}),
        "rule": RULE,
        "live_verified": False,
    }


def _decode_observation(value):
    return json.loads(value)


def _public_body(scenario, visible, *, query_mode):
    history = copy.deepcopy(visible.get("history", []))
    revealed = []
    for entry in history:
        if entry.get("action", "").startswith("query:") and "observation" in entry:
            revealed.append(_decode_observation(entry["observation"]))
    actions = list(visible.get("available_actions", []))
    if query_mode == "no-query":
        actions = [action for action in actions if not action.startswith("query:")]
        queries = []
    else:
        queries = copy.deepcopy(scenario["queries"])
    initial = scenario["counterevidence_initial"]
    return {
        "task": scenario["counterevidence_task"],
        "rules": scenario["counterevidence_rules"],
        "target": scenario["counterevidence_target"],
        "decision_time": scenario["counterevidence_decision_time"],
        "initial_dossier": {
            "provisional": True,
            "claim": initial["claim"],
            "excerpt": initial["excerpt"],
            "source_id": initial["source_id"],
            "locator": copy.deepcopy(initial["locator"]),
            "attached_sources": copy.deepcopy(initial["attached_sources"]),
            "notice": "The initial claim may be stale, misfiled, incomplete, unsupported, or correct.",
        },
        "queries": queries,
        "revealed": revealed,
        "budget": scenario["budget"],
        "remaining_budget": visible["remaining_budget"],
        "history": history,
        "terminal": copy.deepcopy(visible["terminal"]),
        "available_actions": actions,
        "losses": {
            "query": 1,
            "wrong_commit": 10,
            "abstain": scenario["abstain_loss"],
            "failure": scenario["failure_loss"],
        },
        "instructions": (
            "Initial claims can be wrong. Original source scope, authority, effective time, "
            "and conditions govern. Audit only when it can change the decision. "
            "commit ends the episode; abstain is a business decision and is not an API failure."
        ),
    }


def public_visible(scenario, state, *, query_mode="adaptive"):
    """Project a generic public state into the counterevidence model body."""
    al.require(isinstance(scenario, dict) and "counterevidence_initial" in scenario,
               "counterevidence scenario required")
    al.require(query_mode in {"adaptive", "no-query", "read-all"}, "invalid query mode")
    visible = evidence.visible_state(scenario, state)
    return _public_body(scenario, visible, query_mode=query_mode)


def visible_state(scenario, state, *, query_mode="adaptive"):
    """Return only the counterevidence-specific model-facing body."""
    return public_visible(scenario, state, query_mode=query_mode)


def episode_evidence(suite, episode, *, source_visible=False):
    """Return a privileged local trace with narrowly defined diagnostics."""
    design = suite.get("counterevidence_design")
    if design is None:
        return None
    scenario = next(s for s in suite["scenarios"] if s["id"] == episode["scenario_id"])
    family = next(f for f in design["families"]
                  if f["id"] == scenario["counterevidence_family"])
    case = next(c for c in family["cases"] if c["id"] == episode["world_id"])
    state = evidence.state_from_history(scenario, case["id"], episode.get("history", []))
    steps, prefix, no_information = [], [], []
    for entry in state["history"]:
        before = evidence.visible_from_history(scenario, prefix)
        steps.append({
            "chosen": copy.deepcopy(entry),
            "compatible_hypotheses": before["compatible_hypotheses"],
            "remaining_budget": before["remaining_budget"],
            "available_actions": before["available_actions"],
        })
        if entry.get("action", "").startswith("query:"):
            after = evidence.visible_from_history(scenario, prefix + [entry])
            if before["compatible_hypotheses"] == after["compatible_hypotheses"]:
                no_information.append(entry["action"][6:])
        prefix.append(entry)
    resolved = _resolved_decision(case)
    terminal = state.get("terminal") or {}
    final_action = (f"commit:{terminal['decision_id']}" if terminal.get("kind") == "commit"
                    else terminal.get("kind"))
    return {
        "schema": TRACE_SCHEMA,
        "local_privileged": True,
        "source_family": family["id"],
        "world_id": case["id"],
        "initial_claim": case["initial"]["claim"],
        "initial_dossier": copy.deepcopy(case["initial"]),
        "resolved_decision": resolved,
        "correct_terminal": f"commit:{resolved}",
        "initial_claim_correct": case["initial"]["claim"] == resolved,
        "source_documents": {source["id"]: copy.deepcopy(source) for source in case["sources"]},
        "steps": steps,
        "diagnostics": {
            "acted_against_initial_claim": (None if terminal.get("kind") not in {"commit", "abstain"}
                                           else final_action != f"commit:{case['initial']['claim']}"),
            "no_information_queries": no_information,
            "no_information_query_count": len(no_information),
            "scope": "Finite-model facts only; no inferred confidence, mental state, or general causal claim.",
        },
        "read_all_control": bool(source_visible),
        "report_notice": "Local inspector only; never send this report wholesale to a model.",
    }
