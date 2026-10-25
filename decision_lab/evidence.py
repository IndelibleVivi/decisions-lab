"""Finite, partially observable active-evidence research; no external execution.

Query cost and terminal loss share one synthetic utility unit. The public contract
includes the hypothesis/observation table, but never the actual hidden world.
Records are replayable inputs, not authenticated evidence of a live model run.
"""
from __future__ import annotations

import copy
import math
import random
from collections import defaultdict
from functools import lru_cache

SUITE_SCHEMA = "decisions-lab.evidence-suite/1"
RUN_SCHEMA = "decisions-lab.evidence-run/1"
REPORT_SCHEMA = "decisions-lab.evidence-report/1"
POLICIES = ("checklist", "stop", "myopic", "optimal")
FAILURES = ("unknown", "refusal", "error", "missing")
EPSILON = 1e-10


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _number(value):
    try:
        return type(value) in (float, int) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def _identifier(value):
    return isinstance(value, str) and bool(value) and ":" not in value


def validate_suite(suite):
    """Validate a bounded finite design, including complete loss/observation maps."""
    _require(isinstance(suite, dict) and suite.get("schema") == SUITE_SCHEMA, "invalid evidence suite schema")
    scenarios = suite.get("scenarios")
    _require(isinstance(scenarios, list) and bool(scenarios), "scenarios must be a nonempty list")
    seen = set()
    for scenario in scenarios:
        _require(isinstance(scenario, dict), "scenario must be an object")
        sid = scenario.get("id")
        _require(_identifier(sid) and sid not in seen, "invalid or duplicate scenario id")
        seen.add(sid)
        for key in ("title", "description", "source_family", "split"):
            _require(isinstance(scenario.get(key), str) and bool(scenario[key]), f"missing scenario {key}")
        for key in ("budget", "max_queries"):
            _require(type(scenario.get(key)) is int and scenario[key] >= 0, f"{key} must be a nonnegative integer")
        for key in ("abstain_loss", "failure_loss"):
            _require(_number(scenario.get(key)), f"invalid {key}")
        hypotheses, queries, decisions = (scenario.get(k) for k in ("hypotheses", "queries", "decisions"))
        _require(isinstance(hypotheses, list) and 1 <= len(hypotheses) <= 16, "need 1..16 hypotheses")
        _require(isinstance(queries, list) and len(queries) <= 8, "need at most 8 queries")
        _require(isinstance(decisions, list) and 1 <= len(decisions) <= 16, "need 1..16 decisions")
        id_sets = []
        for name, rows in (("hypothesis", hypotheses), ("query", queries), ("decision", decisions)):
            _require(all(isinstance(r, dict) for r in rows), f"invalid {name}")
            ids = [r.get("id") for r in rows]
            _require(all(_identifier(i) for i in ids) and len(set(ids)) == len(ids), f"invalid or duplicate {name} id")
            id_sets.append(set(ids))
        hids, qids, dids = id_sets
        _require(not qids & dids, "query and decision ids must be distinct")
        for query in queries:
            _require(isinstance(query.get("label"), str) and bool(query["label"]), "query label required")
            _require(type(query.get("cost")) is int and query["cost"] >= 0, "query cost must be nonnegative integer")
        for hypothesis in hypotheses:
            _require(_number(hypothesis.get("prior")) and hypothesis["prior"] > 0, "prior must be positive finite")
            observations = hypothesis.get("observations")
            _require(isinstance(observations, dict) and set(observations) == qids, "incomplete observation table")
            _require(all(isinstance(v, str) for v in observations.values()), "observations must be strings")
        _require(math.isclose(sum(h["prior"] for h in hypotheses), 1.0, rel_tol=0, abs_tol=EPSILON), "priors must sum to one")
        for decision in decisions:
            _require(isinstance(decision.get("label"), str) and bool(decision["label"]), "decision label required")
            losses = decision.get("losses")
            _require(isinstance(losses, dict) and set(losses) == hids, "incomplete loss table")
            _require(all(_number(v) for v in losses.values()), "loss must be nonnegative finite")
        maximum = max([scenario["abstain_loss"], scenario["failure_loss"]] +
                      [loss for d in decisions for loss in d["losses"].values()])
        try:
            bounded_total = maximum + sum(q["cost"] for q in queries)
            _require(math.isfinite(bounded_total), "total utility must be finite")
        except OverflowError as exc:
            raise ValueError("total utility must be finite") from exc


def _validate_scenario(scenario):
    validate_suite({"schema": SUITE_SCHEMA, "scenarios": [scenario]})


def build_suite(seed=0):
    """Seven distinct invented mechanisms, enumerated over every hidden world.

    Seed changes presentation order only; it does not create independent sources.
    """
    _require(type(seed) is int and seed >= 0, "seed must be a nonnegative integer")
    scenarios = []

    def add(sid, title, description, priors, observations, query_specs, losses,
            budget=2, max_queries=2, abstain=3):
        hids = [f"h{i}" for i in range(len(priors))]
        scenarios.append({"id": sid, "title": title, "description": description,
                          "source_family": sid, "split": "test", "budget": budget,
                          "max_queries": max_queries, "abstain_loss": float(abstain), "failure_loss": 12.0,
                          "hypotheses": [{"id": hid, "prior": prior, "observations": dict(obs)}
                                         for hid, prior, obs in zip(hids, priors, observations)],
                          "queries": [{"id": qid, "label": label, "cost": cost}
                                      for qid, label, cost in query_specs],
                          "decisions": [{"id": did, "label": label, "losses": dict(zip(hids, values))}
                                        for did, label, values in losses]})

    add("key-evidence", "一条关键证据", "核对当前登记后选择对应路线。", [.5, .5],
        [{"register": "当前路线甲"}, {"register": "当前路线乙"}],
        [("register", "读取当前登记", 1)],
        [("route-a", "路线甲", [0, 10]), ("route-b", "路线乙", [10, 0])])
    add("xor-complement", "两问互补", "两个独立位的异或值决定路线；单独一个位无决策信息。", [.25] * 4,
        [{"left": str(a), "right": str(b)} for a in (0, 1) for b in (0, 1)],
        [("left", "读取左位", 1), ("right", "读取右位", 1)],
        [("even", "两位相同", [0, 10, 10, 0]), ("odd", "两位不同", [10, 0, 0, 10])])
    add("uninformative", "查询无信息", "无关索引在所有世界返回相同文本，不能改善当前先验。", [.8, .2],
        [{"index": "无关索引相同"}] * 2, [("index", "读取无关索引", 1)],
        [("usual", "常见路线", [0, 4]), ("rare", "罕见路线", [4, 0])], abstain=2)
    add("robust-stop", "已有稳健答案", "细节虽未知，安全路线在所有世界都最优。", [.5, .5],
        [{"detail": "风向东"}, {"detail": "风向西"}], [("detail", "读取风向", 1)],
        [("safe", "安全路线", [0, 0]), ("risky", "冒险路线", [2, 4])])
    add("unavailable", "证据不可得", "所需登记没有保留；重复读取缺失材料无法辨别世界。", [.5, .5],
        [{"archive": "登记缺失，无法取得"}] * 2, [("archive", "读取缺失登记", 1)],
        [("accept", "接受", [0, 10]), ("reject", "拒绝", [10, 0])])
    add("asymmetric-prior", "先验与非对称代价", "稀有异常先验为一成，但误放行的代价更大。", [.9, .1],
        [{"audit": "正常"}, {"audit": "异常"}], [("audit", "读取审计结论", 1)],
        [("allow", "放行", [0, 50]), ("hold", "拦截", [4, 0])], abstain=4)
    add("stale-entity", "旧版本与实体干扰", "旧版和另一实体都给出甲；只有目标实体的现行版本有效。", [.5, .5],
        [{"old": "目标旧版：甲；邻实体：甲", "current": "目标现行：甲"},
         {"old": "目标旧版：甲；邻实体：甲", "current": "目标现行：乙"}],
        [("old", "读取旧版与邻实体", 1), ("current", "读取目标现行版本", 1)],
        [("current-a", "按现行甲", [0, 10]), ("current-b", "按现行乙", [10, 0])])
    rng = random.Random(seed)
    for scenario in scenarios:
        rng.shuffle(scenario["hypotheses"])
        rng.shuffle(scenario["decisions"])
    suite = {"schema": SUITE_SCHEMA, "seed": seed, "provenance": "synthetic",
             "description": "原创有限部分可观察主动取证设计；合成控制不证明模型收益。", "scenarios": scenarios}
    validate_suite(suite)
    return suite


def _walk(scenario, history, world_id=None):
    """Rebuild every derived field. With a world, verify each actual observation."""
    _require(isinstance(history, list), "history must be a list")
    hypotheses = {h["id"]: h for h in scenario["hypotheses"]}
    if world_id is not None:
        _require(isinstance(world_id, str) and world_id in hypotheses, "unknown world_id")
    queries = {q["id"]: q for q in scenario["queries"]}
    decisions = {d["id"] for d in scenario["decisions"]}
    compatible, asked, spent, terminal = list(hypotheses), set(), 0, None
    canonical_history = []
    for entry in history:
        _require(terminal is None, "history continues after terminal")
        _require(isinstance(entry, dict), "history entry must be an object")
        if "failure" in entry:
            _require(set(entry) == {"failure"} and entry["failure"] in FAILURES, "invalid failure status")
            terminal = {"kind": "failure", "status": entry["failure"]}
        else:
            action = entry.get("action")
            _require(isinstance(action, str), "history action must be a string")
            if action.startswith("query:"):
                qid = action[6:]
                _require(qid in queries and qid not in asked, "unknown or repeated query")
                query = queries[qid]
                _require(len(asked) < scenario["max_queries"] and spent + query["cost"] <= scenario["budget"], "query exceeds budget or max_queries")
                _require(set(entry) == {"action", "observation"} and isinstance(entry["observation"], str), "query needs exactly one observation")
                observation = entry["observation"]
                if world_id is not None:
                    _require(hypotheses[world_id]["observations"][qid] == observation, "observation contradicts actual world")
                compatible = [hid for hid in compatible if hypotheses[hid]["observations"][qid] == observation]
                _require(bool(compatible), "incompatible observations")
                asked.add(qid)
                spent += query["cost"]
            elif action.startswith("commit:"):
                _require(set(entry) == {"action"} and action[7:] in decisions, "unknown terminal decision")
                terminal = {"kind": "commit", "decision_id": action[7:]}
            else:
                _require(action == "abstain" and set(entry) == {"action"}, "invalid action")
                terminal = {"kind": "abstain"}
        canonical_history.append(copy.deepcopy(entry))
    result = {"scenario_id": scenario["id"], "history": canonical_history, "spent": spent, "terminal": terminal}
    if world_id is not None:
        result["world_id"] = world_id
    return result, compatible, asked


def initial_state(scenario, world_id):
    _validate_scenario(scenario)
    return _walk(scenario, [], world_id)[0]


def _canonical(scenario, state):
    _validate_scenario(scenario)
    _require(isinstance(state, dict) and "world_id" in state, "local state requires world_id")
    rebuilt, compatible, asked = _walk(scenario, state.get("history"), state["world_id"])
    _require(state == rebuilt, "state differs from initial state plus history")
    return rebuilt, compatible, asked


def _actions(scenario, spent, asked, terminal):
    if terminal is not None:
        return []
    actions = ["abstain"] + [f"commit:{d['id']}" for d in scenario["decisions"]]
    if len(asked) < scenario["max_queries"]:
        actions += [f"query:{q['id']}" for q in scenario["queries"]
                    if q["id"] not in asked and spent + q["cost"] <= scenario["budget"]]
    return actions


def visible_state(scenario, state):
    """Publish the known design and evidence, never the selected actual world."""
    canonical, _, _ = _canonical(scenario, state)
    return visible_from_history(scenario, canonical["history"])


def visible_from_history(scenario, history):
    """Public-only reconstruction, also usable by native request bridges."""
    _validate_scenario(scenario)
    canonical, compatible, asked = _walk(scenario, history)
    mass = sum(h["prior"] for h in scenario["hypotheses"] if h["id"] in compatible)
    view = {key: copy.deepcopy(scenario[key]) for key in
            ("id", "title", "description", "source_family", "split", "budget", "max_queries",
             "abstain_loss", "failure_loss", "hypotheses", "queries", "decisions")}
    view.update(canonical)
    view["remaining_budget"] = scenario["budget"] - canonical["spent"]
    view["compatible_hypotheses"] = compatible
    view["posterior"] = {h["id"]: h["prior"] / mass for h in scenario["hypotheses"] if h["id"] in compatible}
    view["available_actions"] = _actions(scenario, canonical["spent"], asked, canonical["terminal"])
    return view


def available_actions(scenario, state):
    return visible_state(scenario, state)["available_actions"]


def _solver(scenario):
    hypotheses = {h["id"]: h for h in scenario["hypotheses"]}
    queries = {q["id"]: q for q in scenario["queries"]}
    terminals = ["abstain"] + [f"commit:{d['id']}" for d in scenario["decisions"]]
    losses = {f"commit:{d['id']}": d["losses"] for d in scenario["decisions"]}

    def terminal_values(compatible):
        mass = sum(hypotheses[hid]["prior"] for hid in compatible)
        values = {action: sum(hypotheses[hid]["prior"] * losses[action][hid] for hid in compatible) / mass
                  for action in terminals if action != "abstain"}
        return {"abstain": scenario["abstain_loss"], **values}

    def branches(compatible, qid):
        grouped = defaultdict(list)
        mass = sum(hypotheses[hid]["prior"] for hid in compatible)
        for hid in compatible:
            grouped[hypotheses[hid]["observations"][qid]].append(hid)
        return [(sum(hypotheses[hid]["prior"] for hid in group) / mass, tuple(group))
                for group in grouped.values()]

    @lru_cache(maxsize=None)
    def values(compatible, asked, mode):
        result = terminal_values(compatible)
        spent = sum(queries[qid]["cost"] for qid in asked)
        if mode != "stop" and len(asked) < scenario["max_queries"]:
            for qid, query in queries.items():
                if qid in asked or spent + query["cost"] > scenario["budget"]:
                    continue
                future = 0.0
                for probability, group in branches(compatible, qid):
                    later = terminal_values(group) if mode == "myopic" else values(group, tuple(sorted((*asked, qid))), "optimal")
                    future += probability * min(later.values())
                result[f"query:{qid}"] = query["cost"] + future
        return result

    def pick(action_values):
        minimum = min(action_values.values())
        # Stable lexical tie resolution; terminal always precedes equally good query.
        tied = [a for a, v in action_values.items() if abs(v - minimum) <= EPSILON]
        return min(tied, key=lambda a: (a.startswith("query:"), a))

    @lru_cache(maxsize=None)
    def policy_value(compatible, asked, policy):
        action_values = values(compatible, asked, "stop" if policy == "checklist" else policy)
        if policy == "checklist":
            spent = sum(queries[qid]["cost"] for qid in asked)
            remaining = [qid for qid in queries if qid not in asked and spent + queries[qid]["cost"] <= scenario["budget"]]
            action = f"query:{remaining[0]}" if remaining and len(asked) < scenario["max_queries"] else pick(action_values)
        else:
            action = pick(action_values)
        if not action.startswith("query:"):
            return terminal_values(compatible)[action]
        qid = action[6:]
        return queries[qid]["cost"] + sum(p * policy_value(group, tuple(sorted((*asked, qid))), policy)
                                           for p, group in branches(compatible, qid))

    return values, pick, policy_value


def oracle(scenario, state, mode="optimal"):
    """Use posterior belief only; actual world selects observations, never actions."""
    return decision_from_visible(scenario, visible_state(scenario, state), mode)


def decision_from_visible(scenario, visible, mode="optimal"):
    """Public-state oracle; rejects forged posterior, budget, history and menus."""
    _require(mode in POLICIES, "unknown oracle mode")
    _require(isinstance(visible, dict), "visible state must be an object")
    rebuilt = visible_from_history(scenario, visible.get("history"))
    _require(rebuilt == visible, "visible state differs from public history")
    _require(visible["terminal"] is None, "terminal state has no next action")
    compatible = tuple(visible["compatible_hypotheses"])
    asked = tuple(sorted(e["action"][6:] for e in visible["history"] if e.get("action", "").startswith("query:")))
    values, pick, policy_value = _solver(scenario)
    action_values = values(compatible, asked, "stop" if mode == "checklist" else mode)
    if mode == "checklist":
        queries = [a for a in visible["available_actions"] if a.startswith("query:")]
        action = queries[0] if queries else pick(action_values)
        # Report values under checklist continuation, not an unrelated optimal tree.
        action_values = {**action_values}
        if queries:
            query = next(q for q in scenario["queries"] if f"query:{q['id']}" == action)
            action_values[action] = policy_value(compatible, asked, "checklist")
    else:
        action = pick(action_values)
    # Robust terminal decisions are an intersection of per-world argmins; Bayes
    # stop additionally includes abstention, which is not a terminal decision ID.
    robust = []
    for decision in scenario["decisions"]:
        if all(abs(decision["losses"][hid] - min(d["losses"][hid] for d in scenario["decisions"])) <= EPSILON
               for hid in compatible):
            robust.append(f"commit:{decision['id']}")
    return {"action": action, "expected_loss": policy_value(compatible, asked, mode),
            "action_values": dict(action_values), "robust_actions": sorted(robust),
            "stop_risk": min(values(compatible, asked, "stop").values()),
            "optimal_risk": min(values(compatible, asked, "optimal").values())}


def choose_action(scenario, visible, policy="optimal"):
    return decision_from_visible(scenario, visible, policy)["action"]


def step(scenario, state, action):
    canonical, _, _ = _canonical(scenario, state)
    _require(canonical["terminal"] is None, "cannot step terminal state")
    _require(isinstance(action, str) and action in available_actions(scenario, canonical), "illegal, repeated or over-budget action")
    entry = {"action": action}
    if action.startswith("query:"):
        hypothesis = next(h for h in scenario["hypotheses"] if h["id"] == canonical["world_id"])
        entry["observation"] = hypothesis["observations"][action[6:]]
    return _walk(scenario, canonical["history"] + [entry], canonical["world_id"])[0]


def finish_failure(scenario, state, status):
    canonical, _, _ = _canonical(scenario, state)
    _require(canonical["terminal"] is None, "cannot fail terminal state")
    _require(status in FAILURES, "failure must be unknown/refusal/error/missing")
    return _walk(scenario, canonical["history"] + [{"failure": status}], canonical["world_id"])[0]


def state_from_history(scenario, world_id, history):
    """Rebuild retained actions/observations with actual-world consistency checks."""
    _validate_scenario(scenario)
    return _walk(scenario, history, world_id)[0]


def evaluate_episode(scenario, state):
    canonical, _, _ = _canonical(scenario, state)
    terminal = canonical["terminal"]
    _require(terminal is not None, "episode has no terminal outcome; finish as missing first")
    kind = terminal["kind"]
    hid = canonical["world_id"]
    best = min(d["losses"][hid] for d in scenario["decisions"])
    if kind == "commit":
        loss = next(d["losses"][hid] for d in scenario["decisions"] if d["id"] == terminal["decision_id"])
    else:
        loss = scenario["abstain_loss"] if kind == "abstain" else scenario["failure_loss"]
    risks, regret = [], 0.0
    prefix = []
    for entry in canonical["history"]:
        before = visible_from_history(scenario, prefix)
        info = decision_from_visible(scenario, before, "optimal")
        if "failure" in entry:
            conditional = scenario["failure_loss"] - info["optimal_risk"]
        else:
            conditional = info["action_values"][entry["action"]] - info["optimal_risk"]
        regret += conditional
        prefix.append(entry)
        if entry.get("action", "").startswith("query:"):
            after = visible_from_history(scenario, prefix)
            after_info = decision_from_visible(scenario, after, "optimal")
            risks.append({"query_id": entry["action"][6:], "observation": entry["observation"],
                          "spent": after["spent"], "stop_risk_before": info["stop_risk"],
                          "stop_risk_after": after_info["stop_risk"], "optimal_risk_before": info["optimal_risk"],
                          "optimal_risk_after": after_info["optimal_risk"], "conditional_action_regret": conditional})
    return {"terminal_loss": loss, "query_cost": canonical["spent"], "total_loss": loss + canonical["spent"],
            "query_count": len(risks), "wrong_commit": kind == "commit" and loss > best + EPSILON,
            "abstained": kind == "abstain", "failed": kind == "failure", "missing": kind == "failure" and terminal["status"] == "missing",
            "failure_status": terminal.get("status"), "completed": kind != "failure" or terminal["status"] != "missing",
            "query_risks": risks, "path_cumulative_conditional_action_regret": regret,
            "initial_optimal_expected_loss": oracle(scenario, initial_state(scenario, hid))["expected_loss"]}


def planned_episodes(suite, policy, replicates=1):
    validate_suite(suite)
    _require(isinstance(policy, str) and bool(policy), "policy name required")
    _require(type(replicates) is int and replicates >= 1, "replicates must be a positive integer")
    return [{"id": f"{len(s['id'])}:{s['id']}/{len(h['id'])}:{h['id']}/{r}", "scenario_id": s["id"], "world_id": h["id"],
             "replicate": r, "policy": policy, "source_family": s["source_family"], "split": s["split"]}
            for s in suite["scenarios"] for h in s["hypotheses"] for r in range(replicates)]


def run_suite(suite, policy="optimal", replicates=1):
    _require(policy in POLICIES, "synthetic run requires a built-in policy")
    planned = planned_episodes(suite, policy, replicates)
    scenarios = {s["id"]: s for s in suite["scenarios"]}
    record = {"schema": RUN_SCHEMA, "suite": copy.deepcopy(suite), "policy": policy, "replicates": replicates,
              "synthetic": True, "provenance": "synthetic", "live_verified": False,
              "planned": planned, "episodes": []}
    for plan in planned:
        scenario = scenarios[plan["scenario_id"]]
        state = initial_state(scenario, plan["world_id"])
        while state["terminal"] is None:
            state = step(scenario, state, choose_action(scenario, visible_state(scenario, state), policy))
        record["episodes"].append({"id": plan["id"], "history": state["history"]})
    return record


def replay(record):
    """Recompute the full denominator and all losses; cached scores are ignored.

    A valid changed suite/history is a new synthetic input and gets rescored. This
    is consistency validation, not signing or proof of original/live provenance.
    """
    _require(isinstance(record, dict) and record.get("schema") == RUN_SCHEMA, "invalid evidence run schema")
    suite = record.get("suite")
    validate_suite(suite)
    synthetic = record.get("synthetic")
    _require(synthetic is None or type(synthetic) is bool, "invalid synthetic marker")
    policy, replicates = record.get("policy"), record.get("replicates")
    expected_plan = planned_episodes(suite, policy, replicates)
    _require(record.get("planned") == expected_plan, "planned identities differ from frozen suite/policy/replicates")
    # A record may retain live transport observations elsewhere. Replay never
    # upgrades an asserted live_verified flag into verified provider evidence.
    episodes = record.get("episodes")
    _require(isinstance(episodes, list), "episodes must be a list")
    entries, ids = {}, {p["id"] for p in expected_plan}
    for episode in episodes:
        _require(isinstance(episode, dict) and episode.get("id") in ids, "unplanned episode")
        _require(episode["id"] not in entries, "duplicate episode")
        entries[episode["id"]] = episode
    scenarios = {s["id"]: s for s in suite["scenarios"]}
    rows = []
    for plan in expected_plan:
        scenario = scenarios[plan["scenario_id"]]
        retained = entries.get(plan["id"])
        state = state_from_history(scenario, plan["world_id"], retained.get("history") if retained else [])
        if retained and "state" in retained:
            _require(retained["state"] == state, "cached state contradicts retained history")
        if state["terminal"] is None:
            state = finish_failure(scenario, state, "missing")
        score = evaluate_episode(scenario, state)
        initial = initial_state(scenario, plan["world_id"])
        policy_expected = oracle(scenario, initial, policy)["expected_loss"] if policy in POLICIES else None
        # A history changed to another valid policy is re-scored as observed;
        # expected policy regret is available only when every retained action
        # follows that named policy (missing trajectories are never inferred).
        follows = retained is not None and score["completed"] and not score["failed"]
        prefix = initial
        for entry in state["history"]:
            if "failure" in entry:
                follows = False
                break
            if policy not in POLICIES or entry["action"] != oracle(scenario, prefix, policy)["action"]:
                follows = False
            prefix = step(scenario, prefix, entry["action"])
        rows.append({**plan, **score, "history": copy.deepcopy(state["history"]),
                     "follows_named_policy": follows, "policy_expected_loss": policy_expected if follows else None,
                     "expected_regret": policy_expected - score["initial_optimal_expected_loss"] if follows else None})

    def summarize(group):
        planned = len(group)
        completed = sum(r["completed"] for r in group)
        sums = {key: sum(r[key] for r in group) for key in
                ("terminal_loss", "query_cost", "total_loss", "query_count", "wrong_commit", "abstained", "failed", "missing")}
        # Enumeration is not prior sampling: report equal-row metrics separately
        # from prior-weighted expected utilities. Repeats share source families.
        weights = []
        for row in group:
            scenario = scenarios[row["scenario_id"]]
            prior = next(h["prior"] for h in scenario["hypotheses"] if h["id"] == row["world_id"])
            weights.append(prior / replicates)
        mass = sum(weights)
        prior_mean = sum(w * row["total_loss"] for w, row in zip(weights, group)) / mass
        expected_known = all(row["expected_regret"] is not None for row in group)
        return {"planned": planned, "completed": completed, "coverage": completed / planned,
                **sums, "mean_total_loss": sums["total_loss"] / planned,
                "prior_weighted_mean_total_loss": prior_mean,
                "policy_expected_loss": sum(w * row["policy_expected_loss"] for w, row in zip(weights, group)) / mass if expected_known else None,
                "expected_regret": sum(w * row["expected_regret"] for w, row in zip(weights, group)) / mass if expected_known else None,
                "path_cumulative_conditional_action_regret": sum(row["path_cumulative_conditional_action_regret"] for row in group),
                "source_families": len({r["source_family"] for r in group}),
                "failure_statuses": {status: sum(r["failure_status"] == status for r in group) for status in FAILURES}}

    families = sorted({r["source_family"] for r in rows})
    return {"schema": REPORT_SCHEMA, "policy": policy, "replicates": replicates,
            "synthetic": synthetic, "provenance": record.get("provenance", "unverified"),
            "live_verified": False, "scoring": "recomputed from frozen suite and retained histories",
            "source_family_note": "Mechanism clusters; enumeration and repeats do not establish independent sampling.",
            "summary": summarize(rows), "families": {family: summarize([r for r in rows if r["source_family"] == family]) for family in families},
            "episodes": rows}
