"""Seeded finite synthetic worlds. Editorial oracles are never provider input."""
from __future__ import annotations

import copy
import random
from fractions import Fraction

KINDS = ("probability", "documents", "rules", "geometry")
ALIASES = {"finite-probability": "probability", "entity-documents": "documents",
           "boolean-rules": "rules", "geometric-relations": "geometry"}
SPLITS = ("train",) * 12 + ("dev",) * 4 + ("calibration",) * 2 + ("test",) * 2


def states_for(n):
    if type(n) is not int or n not in (2, 3):
        raise ValueError("variables must be 2 or 3")
    return [format(i, f"0{n}b") for i in range(2 ** n)]


def _fraction(value):
    return str(Fraction(value))


def probability_oracle(world):
    if set(world) != {"weights", "loss_matrix"}:
        raise ValueError("invalid probability world fields")
    weights = world["weights"]
    if not weights or any(type(x) is not int or x <= 0 for x in weights):
        raise ValueError("weights must be positive integers")
    losses = world["loss_matrix"]
    if not losses or any(len(v) != len(weights) or any(type(x) is not int or x < 0 for x in v)
                         for v in losses.values()):
        raise ValueError("invalid loss matrix")
    total = sum(weights)
    expected = {a: sum(Fraction(w, total) * loss for w, loss in zip(weights, row))
                for a, row in losses.items()}
    best = min(expected.values())
    return {"probabilities": [_fraction(Fraction(w, total)) for w in weights],
            "expected_loss": {a: _fraction(v) for a, v in expected.items()},
            "best_actions": sorted(a for a, v in expected.items() if v == best),
            "proof": "Enumerate every mutually exclusive state; minimize exact rational expected loss."}


def document_oracle(world):
    if set(world) != {"entity", "documents"} or not isinstance(world["entity"], str):
        raise ValueError("invalid document world")
    docs = world["documents"]
    if (not isinstance(docs, list) or not docs
            or any(not isinstance(d, dict) or set(d) != {"id", "version", "status", "policy"}
                   or not isinstance(d["id"], str) or type(d["version"]) is not int or d["version"] < 1
                   or d["status"] != "ready" or d["policy"] not in ("permit", "deny") for d in docs)
            or len({d["version"] for d in docs}) != len(docs) or len({d["id"] for d in docs}) != len(docs)):
        raise ValueError("documents need unique versions/IDs and explicit ready status and policy")
    latest = max(docs, key=lambda d: d["version"])
    evidence = next(d for d in docs if d["id"] == latest["id"])
    action = "activate" if latest["policy"] == "permit" else "hold"
    return {"gold_fields": {"entity": world["entity"], "status": "ready"},
            "best_actions": [action], "minimal_evidence": [evidence["id"]],
            "proof": "The largest explicit version supersedes older versions; latest policy determines action."}


def geometry_relation(a, b):
    if any(len(x) != 4 or any(type(v) is not int for v in x) or x[0] >= x[2] or x[1] >= x[3]
           for x in (a, b)):
        raise ValueError("rectangles require four integer coordinates and positive area")
    if a[0] < b[0] and a[1] < b[1] and a[2] > b[2] and a[3] > b[3]:
        return "contains"
    dx = min(a[2], b[2]) - max(a[0], b[0])
    dy = min(a[3], b[3]) - max(a[1], b[1])
    if dx < 0 or dy < 0:
        return "disjoint"
    if dx == 0 or dy == 0:
        return "touching"
    raise ValueError("overlap is outside the generated relation contract")


def oracle_for(kind, world):
    if kind == "probability":
        return probability_oracle(world)
    if kind == "documents":
        return document_oracle(world)
    if kind == "rules":
        required = {"variables", "truth_table", "candidate_table", "rule_version", "critical_weights"}
        if set(world) not in (required, required | {"variable_names"}):
            raise ValueError("invalid rule world fields")
        states = states_for(world["variables"])
        if (type(world["rule_version"]) is not int or world["rule_version"] < 1
                or set(world["critical_weights"]) != set(states)
                or any(type(v) is not int or v <= 0 for v in world["critical_weights"].values())):
            raise ValueError("invalid rule version or critical weights")
        truth = world["truth_table"]
        proposal = world["candidate_table"]
        if any(set(t) != set(states) or any(type(v) is not bool for v in t.values()) for t in (truth, proposal)):
            raise ValueError("truth tables must contain every state and boolean outputs")
        errors = [s for s in states if truth[s] != proposal[s]]
        return {"truth_table": truth, "counterexample": errors[0] if errors else None,
                "proof": "Enumerate states in binary lexicographic order; first disagreement is minimal."}
    if kind == "geometry":
        if (set(world) != {"a", "b", "colors"} or not isinstance(world["colors"], list)
                or len(world["colors"]) != 2 or any(not isinstance(c, str) for c in world["colors"])):
            raise ValueError("invalid geometry world")
        return {"relation": geometry_relation(world["a"], world["b"]),
                "proof": "Integer interval bounds prove strict containment, boundary contact, or separation."}
    raise ValueError("unsupported generator kind")


def _request_for(kind, world):
    if kind == "rules":
        value = {"variables": world["variables"], "variable_names": world.get("variable_names"),
                 "rule_version": world["rule_version"],
                 "rule": "Trigger exactly on states " + ",".join(s for s, v in world["truth_table"].items() if v)}
    else:
        value = copy.deepcopy(world)
    return {"kind": kind, "input": value}


def provider_request(row):
    """Explicit allowlist: do not serialize latent_world or editorial oracle."""
    try:
        request = row["request"]
        kind = request["kind"]
        oracle_for(kind, row["latent_world"])
        expected = _request_for(kind, row["latent_world"])
        if request != expected:
            raise ValueError("request does not match safe projection")
        return copy.deepcopy(expected)
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError("malformed provider request source") from exc


def generate_dataset(kind, seed=0, units=20):
    if not isinstance(kind, str):
        raise ValueError("kind must be a string")
    kind = ALIASES.get(kind, kind)
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if type(seed) is not int or type(units) is not int or not 1 <= units <= 10000:
        raise ValueError("seed must be an integer; units must be an integer in 1..10000")
    rng = random.Random(seed)
    rows = []
    for i in range(units):
        family = f"{kind}-{seed}-{i:05d}"
        worlds = []
        if kind == "probability":
            world = {"weights": [rng.randint(1, 12) for _ in range(4)],
                     "loss_matrix": {a: [rng.randint(0, 9) for _ in range(4)] for a in ("a", "b", "c")}}
            worlds = [("base", world, "identity"), ("weight-scale", {**world, "weights": [x * 3 for x in world["weights"]]}, "equal")]
        elif kind == "documents":
            policy = rng.choice(["permit", "deny"])
            world = {"entity": f"entity-{i}", "documents": [
                {"id": "v1", "version": 1, "status": "ready", "policy": "deny"},
                {"id": "v2", "version": 2, "status": "ready", "policy": policy}]}
            twin = copy.deepcopy(world)
            twin["documents"][-1]["policy"] = "deny" if policy == "permit" else "permit"
            reordered = copy.deepcopy(world)
            reordered["documents"].reverse()
            worlds = [("base", world, "identity"), ("document-order", reordered, "equal"),
                      ("schema-insufficiency", twin, "same-gold-disjoint-actions")]
        elif kind == "rules":
            n = 2 + i % 2
            states = states_for(n)
            truth = {s: bool(rng.randrange(2)) for s in states}
            candidate = dict(truth)
            candidate[rng.choice(states)] ^= True
            world = {"variables": n, "truth_table": truth, "candidate_table": candidate,
                     "rule_version": 1, "critical_weights": {s: 5 if s == states[-1] else 1 for s in states}}
            renamed = copy.deepcopy(world)
            renamed["variable_names"] = [f"P{j}" for j in range(n)]
            worlds = [("base", world, "identity"), ("variable-rename", renamed, "equal")]
        else:
            relation = ("contains", "touching", "disjoint")[i % 3]
            a = [0, 0, 10, 10]
            b = {"contains": [2, 2, 4, 4], "touching": [10, 2, 12, 4], "disjoint": [12, 2, 14, 4]}[relation]
            world = {"a": a, "b": b, "colors": ["red", "blue"]}
            translated = {**world, "a": [v + 17 for v in a], "b": [v + 17 for v in b]}
            scaled = {**world, "a": [v * 3 for v in a], "b": [v * 3 for v in b]}
            worlds = [("base", world, "identity"), ("color", {**world, "colors": ["green", "yellow"]}, "equal"),
                      ("translation", translated, "equal"), ("scale", scaled, "equal")]
        for condition, world, relation in worlds:
            rows.append({"unit_id": f"{family}:{condition}", "source_family": family,
                         "latent_world": copy.deepcopy(world), "condition": condition, "replicate": 0,
                         "seed": seed, "split": SPLITS[i % len(SPLITS)],
                         "transformation": {"base_unit_id": f"{family}:base", "expected_relation": relation},
                         "request": _request_for(kind, world), "oracle": oracle_for(kind, world)})
    result = {"schema_version": "generated/v1", "kind": kind, "seed": seed, "units": units,
              "evidence": "synthetic", "provider_status": "NOT_RUN", "rows": rows}
    validate_dataset(result)
    return result


def _validate_dataset(dataset):
    if not isinstance(dataset, dict) or dataset.get("schema_version") != "generated/v1" or dataset.get("kind") not in KINDS:
        raise ValueError("invalid dataset schema/kind")
    kind = dataset["kind"]
    if (type(dataset.get("seed")) is not int or type(dataset.get("units")) is not int
            or not 1 <= dataset["units"] <= 10000 or dataset.get("evidence") != "synthetic"
            or dataset.get("provider_status") != "NOT_RUN"):
        raise ValueError("invalid dataset metadata")
    rows = dataset.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("dataset must have rows")
    ids, families = set(), {}
    for row in rows:
        try:
            if row["unit_id"] in ids or row["split"] not in SPLITS or type(row["replicate"]) is not int or row["replicate"] != 0 or row["seed"] != dataset["seed"]:
                raise ValueError("duplicate unit or invalid metadata")
            ids.add(row["unit_id"])
            families.setdefault(row["source_family"], []).append(row)
            if row["oracle"] != oracle_for(kind, row["latent_world"]):
                raise ValueError("oracle mismatch")
            if row["request"] != _request_for(kind, row["latent_world"]):
                raise ValueError("editorial truth leaked into request")
        except (KeyError, TypeError, IndexError, AttributeError) as exc:
            raise ValueError("malformed dataset row") from exc
    expected_families = {f"{kind}-{dataset['seed']}-{i:05d}": i for i in range(dataset["units"])}
    if set(families) != set(expected_families):
        raise ValueError("family count or identity mismatch")
    conditions = {"probability": {"base", "weight-scale"},
                  "documents": {"base", "document-order", "schema-insufficiency"},
                  "rules": {"base", "variable-rename"},
                  "geometry": {"base", "color", "translation", "scale"}}[kind]
    for family, family_rows in families.items():
        if (len(family_rows) != len(conditions) or {r["condition"] for r in family_rows} != conditions
                or any(r["split"] != SPLITS[expected_families[family] % len(SPLITS)] for r in family_rows)
                or any(r["unit_id"] != f"{family}:{r['condition']}" for r in family_rows)):
            raise ValueError("family variants or stable split mismatch")
        bases = [r for r in family_rows if r["condition"] == "base"]
        if len(bases) != 1 or len({r["split"] for r in family_rows}) != 1:
            raise ValueError("family leakage or missing base")
        base = bases[0]
        for row in family_rows:
            trans = row["transformation"]
            if trans["base_unit_id"] != base["unit_id"]:
                raise ValueError("wrong transformation base")
            relation = trans["expected_relation"]
            expected = ("identity" if row["condition"] == "base" else
                        "same-gold-disjoint-actions" if row["condition"] == "schema-insufficiency" else "equal")
            if relation != expected:
                raise ValueError("condition/relation mismatch")
            left, right = base["oracle"], row["oracle"]
            if relation == "same-gold-disjoint-actions":
                if left["gold_fields"] != right["gold_fields"] or set(left["best_actions"]) & set(right["best_actions"]):
                    raise ValueError("invalid schema insufficiency pair")
            elif relation in ("identity", "equal"):
                if left != right:
                    raise ValueError("transformation changed truth")
            else:
                raise ValueError("unknown expected relation")
    return {"valid": True, "rows": len(rows), "families": len(families), "provider_status": "NOT_RUN"}


def validate_dataset(dataset):
    try:
        return _validate_dataset(dataset)
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError("malformed generated dataset") from exc


check_dataset = validate_dataset
