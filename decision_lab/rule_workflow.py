"""Exhaustive offline compile/verify/repair experiments, never live model evidence."""
from __future__ import annotations

import copy
import random

from .generators import states_for, validate_dataset

COMPILERS = ("exact", "imperfect", "memorize")
CONTROLS = ("counterexample", "repeated-original", "random-feedback")


def verify_program(world, proposal, seen_states=()):
    """A proposal is an explicit complete table plus the rule version it compiled."""
    states = states_for(world["variables"])
    if not isinstance(proposal, dict) or set(proposal) != {"rule_version", "truth_table"}:
        raise ValueError("proposal needs exactly rule_version and truth_table")
    table = proposal["truth_table"]
    if (type(proposal["rule_version"]) is not int or not isinstance(table, dict)
            or set(table) != set(states) or any(type(v) is not bool for v in table.values())):
        raise ValueError("proposal must declare a version and complete boolean truth table")
    truth = world["truth_table"]
    errors = [s for s in states if table[s] != truth[s]]
    weights = world["critical_weights"]
    stale = proposal["rule_version"] != world["rule_version"]
    if any(s not in states for s in seen_states):
        raise ValueError("feedback state outside finite world")
    held_out = [s for s in states if s not in seen_states]
    return {"function_correct": not errors and not stale, "stale_program": stale,
            "hamming_distance": len(errors), "hamming_rate": len(errors) / len(states),
            "weighted_loss": sum(weights[s] for s in errors) / sum(weights.values()),
            "minimal_counterexample": errors[0] if errors else None,
            "held_out_states": held_out,
            "held_out_scope": "states never supplied as feedback to this proposal",
            "held_out_hamming_distance": sum(s in errors for s in held_out),
            "checked_states": states}


def solve_rule(rule_input):
    """Exact local solver for the generated explicit positive-state rule grammar."""
    states = states_for(rule_input["variables"])
    prefix = "Trigger exactly on states "
    rule = rule_input.get("rule")
    if not isinstance(rule, str) or not rule.startswith(prefix):
        raise ValueError("unsupported explicit rule grammar")
    suffix = rule[len(prefix):]
    positive = suffix.split(",") if suffix else []
    if len(positive) != len(set(positive)) or any(s not in states for s in positive):
        raise ValueError("invalid positive rule states")
    return {s: s in positive for s in states}


def _compile(world, rule_input, compiler, feedback, control):
    truth = solve_rule(rule_input)
    states = list(truth)
    if compiler == "exact":
        table = dict(truth)
    elif compiler == "imperfect":
        table = dict(truth)
        for s in states[:2]:
            table[s] = not table[s]
        if control != "repeated-original":
            for item in feedback:
                table[item["state"]] = item["expected"]
    else:
        # Deliberately bad compiler: memorizes provided examples but never generalizes.
        table = {s: not truth[s] for s in states}
        if control != "repeated-original":
            for item in feedback:
                table[item["state"]] = item["expected"]
    return {"rule_version": world["rule_version"], "truth_table": table}


def run_rule_workflow(dataset, compiler="imperfect", control="counterexample", max_rounds=8,
                      uses=100, seed=0, proposals=None):
    """Run base families. `max_rounds` counts repairs after the initial compile.

    Imported proposals map base unit IDs to lists of complete versioned tables.
    Random control samples states without looking for errors. Repeated-original
    resubmits the unchanged source with no feedback. No provider is contacted.
    """
    validate_dataset(dataset)
    if dataset["kind"] != "rules":
        raise ValueError("rule workflow requires a rules dataset")
    if compiler not in COMPILERS or control not in CONTROLS:
        raise ValueError("unknown compiler or control")
    if any(type(x) is not int for x in (max_rounds, uses, seed)) or not 0 <= max_rounds <= 100 or uses < 1:
        raise ValueError("max_rounds must be 0..100; uses must be positive; seed must be integer")
    bases = [r for r in dataset["rows"] if r["condition"] == "base"]
    if proposals is not None:
        if not isinstance(proposals, dict) or set(proposals) != {r["unit_id"] for r in bases}:
            raise ValueError("imported proposals must cover exactly every base unit")
        for row in bases:
            values = proposals[row["unit_id"]]
            if not isinstance(values, list) or not values or len(values) > max_rounds + 1:
                raise ValueError("imported proposal list must contain 1..max_rounds+1 entries")
            for value in values:
                verify_program(row["latent_world"], value)
    rng = random.Random(seed)
    traces = []
    for row in bases:
        world = row["latent_world"]
        feedback, rounds = [], []
        imported = proposals[row["unit_id"]] if proposals is not None else None
        limit = len(imported) if imported is not None else max_rounds + 1
        for index in range(limit):
            proposal = copy.deepcopy(imported[index]) if imported is not None else _compile(world, row["request"]["input"], compiler, feedback, control)
            verification = verify_program(world, proposal, [f["state"] for f in feedback])
            item = {"round": index, "phase": "compile" if index == 0 else "repair",
                    "proposal_source": "imported" if imported is not None else f"synthetic-{compiler}",
                    "feedback_received": copy.deepcopy(feedback), "proposal": proposal,
                    "verification": verification, "feedback_emitted": None}
            rounds.append(item)
            if verification["function_correct"]:
                break
            if index + 1 < limit:
                state = verification["minimal_counterexample"]
                if control == "random-feedback":
                    state = rng.choice(list(world["truth_table"]))
                if control != "repeated-original" and state is not None:
                    event = {"state": state, "expected": world["truth_table"][state],
                             "actual": proposal["truth_table"][state],
                             "kind": "counterexample" if control == "counterexample" else "random-state"}
                    feedback.append(event)
                    item["feedback_emitted"] = copy.deepcopy(event)
        final = rounds[-1]["verification"]
        # A changed rule may make an otherwise correct cached table obsolete.
        updated = copy.deepcopy(world)
        updated["rule_version"] += 1
        changed_state = states_for(world["variables"])[-1]
        updated["truth_table"][changed_state] = not updated["truth_table"][changed_state]
        stale_check = verify_program(updated, rounds[-1]["proposal"])
        refreshed = {"rule_version": updated["rule_version"], "truth_table": dict(updated["truth_table"])}
        traces.append({"unit_id": row["unit_id"], "source_family": row["source_family"], "split": row["split"],
                       "rounds": rounds, "final": final, "repair_rounds": len(rounds) - 1,
                       "stop_reason": "verified" if final["function_correct"] else "proposal-budget-exhausted",
                       "rule_update": {"changed_state": changed_state, "updated_world": updated,
                                       "stale_verification": stale_check, "fresh_proposal": refreshed,
                                       "fresh_verification": verify_program(updated, refreshed)},
                       "overhead": {"proposal_count": len(rounds), "provider_calls": 0,
                                    "synthetic_compiler_calls": 0 if imported is not None else len(rounds),
                                    "imported_proposals": len(rounds) if imported is not None else 0,
                                    "verification_state_evaluations": len(rounds) * len(world["truth_table"]),
                                    "uses": uses, "proposal_count_per_use": len(rounds) / uses,
                                    "application_provider_calls_per_use": 0,
                                    "latency_ms": None, "cost": None,
                                    "latency_status": "UNKNOWN", "cost_status": "UNKNOWN"}})
    return {"schema_version": "rule-workflow/v1", "evidence": "synthetic" if proposals is None else "imported",
            "provider_status": "NOT_RUN", "model_utility_evidence": False,
            "interpretation": "Exhaustive correctness of local tables; deterministic repairs do not establish model utility.",
            "dataset": copy.deepcopy(dataset),
            "configuration": {"compiler": compiler, "control": control, "max_rounds": max_rounds,
                              "uses": uses, "seed": seed, "proposals": copy.deepcopy(proposals)},
            "traces": traces,
            "summary": {"families": len(traces),
                        "fully_correct": sum(t["final"]["function_correct"] for t in traces),
                        "mean_hamming_rate": sum(t["final"]["hamming_rate"] for t in traces) / len(traces),
                        "mean_weighted_loss": sum(t["final"]["weighted_loss"] for t in traces) / len(traces),
                        "proposal_count": sum(t["overhead"]["proposal_count"] for t in traces), "provider_calls": 0}}


def replay_workflow(record):
    """Recompute the complete record; reject edited traces, feedback, or metrics."""
    if not isinstance(record, dict) or record.get("schema_version") != "rule-workflow/v1":
        raise ValueError("invalid workflow record schema")
    try:
        replayed = run_rule_workflow(record["dataset"], **record["configuration"])
    except (KeyError, TypeError) as exc:
        raise ValueError("malformed workflow record") from exc
    if replayed != record:
        raise ValueError("workflow replay mismatch")
    return {"valid": True, "summary": replayed["summary"], "provider_status": "NOT_RUN"}


validate_workflow = replay_workflow
