"""Offline native multi-question requests, retained evidence and independent scoring."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import math
import os
import re
import struct
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import api_tasks as tasks

EXPERIMENTS = tasks.EXPERIMENTS
DEFAULT_SUITE = "experiments/api-capabilities/suite.json"
DEFAULT_MODELS = {"decisions": "gpt-6-luna", "jev": "jev-1.14.0"}
ENDPOINTS = {"decisions": "https://api.openai.com/v1/decisions",
             "jev": "https://api.typesafe.ai/v1/systemone"}
ROUTES = tuple(DEFAULT_MODELS)
MANIFEST_VERSION = "decisions-lab.api-manifest/1"
RECORD_VERSION = "decisions-lab.api-record/1"
RESPONSE_VERSION = "decisions-lab.api-responses/1"
EVALUATOR_VERSION = "api-capabilities/1"


class ApiLabError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ApiLabError(message)


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def token(value):
    return (type(value).__name__, json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False))


def digest(value):
    # These digests are consumed by replay to detect changed retained evidence.
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def nonfinite(value):
        raise ApiLabError(f"non-finite JSON number: {value}")

    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs,
                          parse_constant=nonfinite)
        json.dumps(data, allow_nan=False)  # Reject overflowed numeric literals too.
        return data
    except (OSError, UnicodeError, ValueError, OverflowError) as exc:
        if isinstance(exc, ApiLabError):
            raise
        raise ApiLabError(f"cannot read JSON {path}: {exc}") from exc


def _write(path, data):
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                             encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass
class Suite:
    raw: dict
    rows: list

    def selected(self, experiment=None):
        if experiment:
            require(experiment in {row["experiment"] for row in self.rows},
                    f"unknown experiment: {experiment}")
        return [row for row in self.rows if not experiment or row["experiment"] == experiment]


def load_suite(path=DEFAULT_SUITE):
    data = read_json(path)
    require(isinstance(data, dict) and data.get("schema") == "decisions-lab.api-suite/1",
            "unsupported API suite schema")
    if "cases" in data:
        rows = data["cases"]
    else:
        require(data.get("generator") == "decision_lab.api_tasks/1", "unknown suite generator")
        rows = tasks.all_cases()
    require(isinstance(rows, list) and rows, "suite requires cases")
    ids = [row.get("id") for row in rows]
    require(all(isinstance(value, str) and value for value in ids) and len(ids) == len(set(ids)),
            "suite case IDs must be nonempty and unique")
    return Suite(data, rows)


def select_rows(suite, *, experiment=None, case_ids=None, limit=None):
    rows = suite.selected(experiment)
    if case_ids:
        require(len(case_ids) == len(set(case_ids)), "duplicate case IDs")
        require(set(case_ids) <= {row["id"] for row in rows}, "case ID outside selected experiment")
        rows = [row for row in rows if row["id"] in case_ids]
    if limit is not None:
        require(limit > 0, "limit must be positive")
        rows = rows[:limit]
    require(rows, "selection is empty")
    return rows


def _native_question(question, route):
    kind = question["type"]
    common = {"type": kind, "instructions": question["instructions"]}
    if route == "decisions":
        common["name"] = question["id"]
        if kind == "choice":
            common["choices"] = copy.deepcopy(question["choices"])
        elif kind == "score":
            common["levels"] = copy.deepcopy(question["levels"])
        return common
    if kind == "choice":
        require(all(isinstance(item["value"], str) for item in question["choices"]),
                "Jev criterion IDs must be strings; typed Boolean Choice values are OpenAI-specific")
        common["criteria"] = {item["value"]: item["description"] for item in question["choices"]}
    elif kind == "predicate":
        common["type"] = "noul"
    elif kind == "score":
        common["criteria"] = [level.get("description") or level["label"] for level in question["levels"]]
    return common


def native_questions(body, route):
    questions = body.get("questions")
    if route == "decisions":
        require(isinstance(questions, list) and 1 <= len(questions) <= 400,
                "OpenAI questions must contain 1..400 items")
        require(all(isinstance(q, dict) for q in questions), "question must be an object")
        ids = [q.get("name") for q in questions]
        require(all(isinstance(value, str) and value for value in ids), "named questions required")
        require(len(ids) == len(set(ids)), "duplicate question names")
        return dict(zip(ids, questions))
    require(isinstance(questions, dict) and questions, "Jev questions must be a nonempty map")
    require(all(isinstance(key, str) and key and isinstance(q, dict) for key, q in questions.items()),
            "invalid Jev question map")
    return questions


def _values(question, route):
    return ([item["value"] for item in question["choices"]] if route == "decisions"
            else list(question["criteria"]))


def _check_native(body, headers, route):
    require(isinstance(body, dict), "native request must be an object")
    allowed = {"model", "input", "questions"} if route == "decisions" else {"model", "state", "questions", "assets"}
    require(set(body) <= allowed, "unsupported native request fields")
    require(isinstance(body.get("model"), str) and body["model"], "request model required")
    if route == "decisions":
        require(isinstance(body.get("input"), str) and body["input"], "this profile requires nonempty text input")
    else:
        require(isinstance(body.get("state"), (str, dict, list)) and body.get("state") != "", "state required")
    require(isinstance(headers, dict) and set(headers) <= {"TypeSafe-Danger-Zone-Images"},
            "only the documented non-secret image header is retained")
    questions = native_questions(body, route)
    for qid, q in questions.items():
        kind = q.get("type")
        supported = ("choice", "predicate", "score") if route == "decisions" else ("choice", "noul", "score")
        require(kind in supported, f"unsupported primitive {kind}")
        allowed_question = {"type", "instructions", "name", "choices", "levels"} if route == "decisions" else {"type", "instructions", "criteria"}
        require(set(q) <= allowed_question, f"{qid}: unsupported question fields")
        require(isinstance(q.get("instructions"), str) and q["instructions"], "instructions required")
        if kind == "choice":
            if route == "decisions":
                require(isinstance(q.get("choices"), list) and all(isinstance(c, dict) and set(c) <= {"value", "description"}
                        and "value" in c and ("description" not in c or isinstance(c["description"], str))
                        for c in q["choices"]), "invalid Choice entries")
            else:
                require(isinstance(q.get("criteria"), dict), "Jev Choice requires criteria")
            values = _values(q, route)
            require(len(values) >= 2 and (route != "decisions" or len(values) <= 255), "invalid option count")
            require(all(isinstance(v, (str, bool)) for v in values), "Choice values must be string or Boolean")
            require(len(values) == len({token(v) for v in values}), "duplicate typed Choice values")
        if kind == "score":
            levels = q.get("levels" if route == "decisions" else "criteria")
            require(isinstance(levels, list) and len(levels) >= 2, "Score requires at least two levels")
            if route == "jev":
                require(len(levels) <= 10 and all(isinstance(level, str) for level in levels), "Jev Score requires 2..10 descriptions")
            if route == "decisions":
                require(all(isinstance(level, dict) and isinstance(level.get("label"), str)
                            and set(level) <= {"label", "description"} for level in levels), "invalid Score levels")
                require(len({level["label"] for level in levels}) == len(levels), "duplicate Score labels")
    assets = body.get("assets", {})
    require(isinstance(assets, dict), "assets must be a map")
    if assets:
        require(route == "jev" and headers.get("TypeSafe-Danger-Zone-Images") == "true", "image header required")
        def strings(value):
            if isinstance(value, str):
                yield value
            elif isinstance(value, dict):
                for child in value.values():
                    yield from strings(child)
            elif isinstance(value, list):
                for child in value:
                    yield from strings(child)
        references = list(strings(body.get("state")))
        for q in questions.values():
            references.extend(strings(q.get("instructions")))
            references.extend(strings(q.get("criteria")))
        for key, asset in assets.items():
            require(isinstance(key, str) and re.fullmatch(r"[A-Za-z0-9_-]+", key), "unsafe asset key")
            pattern = r"(?<![A-Za-z0-9_-])" + re.escape(key) + r"(?![A-Za-z0-9_-])"
            require(any(re.search(pattern, text) for text in references), "unreferenced asset")
            require(isinstance(asset, dict) and set(asset) == {"type", "format", "data_base64"}
                    and asset["type"] == "image" and asset["format"] == "png", "this profile exports PNG assets")
            try:
                blob = base64.b64decode(asset["data_base64"], validate=True)
                require(blob[:8] == b"\x89PNG\r\n\x1a\n" and len(blob) >= 33, "invalid PNG")
                w, h = struct.unpack(">II", blob[16:24])
                require(280 <= w <= 1568 and 280 <= h <= 1568, "PNG dimensions outside documented bounds")
                require(len(blob) <= 16 * 1024 * 1024, "PNG exceeds documented size")
            except (ValueError, TypeError, struct.error) as exc:
                raise ApiLabError(f"invalid image asset: {exc}") from exc
    return questions


def prepare_payload(suite, rows, *, route, model=None):
    require(route in ROUTES, "unknown route")
    model = model or DEFAULT_MODELS[route]
    requests = []
    for case in rows:
        require(case["experiment"] != "visual-criteria" or route == "jev",
                "visual-criteria requires Jev native criteria assets")
        questions = [_native_question(q, route) for q in case["questions"]]
        body = {"model": model, "input" if route == "decisions" else "state": copy.deepcopy(case["input"]),
                "questions": questions if route == "decisions" else dict(zip([q["id"] for q in case["questions"]], questions))}
        rubric = copy.deepcopy(case["rubric"])
        assets = rubric.pop("assets", None)
        headers = {}
        if assets:
            body["assets"] = assets
            headers = {"TypeSafe-Danger-Zone-Images": "true"}
        item = {"id": case["id"], "experiment": case["experiment"], "body": body,
                "required_headers": headers, "rubric": rubric}
        item["request_digest"] = digest({"body": body, "required_headers": headers})
        item["rubric_digest"] = digest(rubric)
        requests.append(item)
    manifest = {"schema": MANIFEST_VERSION, "route": route, "model": model, "endpoint": ENDPOINTS[route],
                "docs_verified_at": "2026-10-22", "live_verified": False, "requests": requests}
    manifest["manifest_digest"] = digest(manifest)
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest):
    require(isinstance(manifest, dict) and manifest.get("schema") == MANIFEST_VERSION, "unsupported manifest")
    route = manifest.get("route")
    require(route in ROUTES and manifest.get("live_verified") is False, "invalid manifest provenance")
    original = dict(manifest); supplied = original.pop("manifest_digest", None)
    require(supplied == digest(original), "manifest digest mismatch")
    requests = manifest.get("requests")
    require(isinstance(requests, list) and requests, "empty manifest")
    require(all(isinstance(item, dict) for item in requests), "request snapshots must be objects")
    ids = [item.get("id") for item in requests]
    require(all(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_+.-]*", value) for value in ids)
            and len(ids) == len(set(ids)), "unsafe/duplicate/invalid request IDs")
    for request in requests:
        body, headers, rubric = request.get("body"), request.get("required_headers"), request.get("rubric")
        require(request.get("request_digest") == digest({"body": body, "required_headers": headers}), "request digest mismatch")
        require(request.get("rubric_digest") == digest(rubric), "rubric digest mismatch")
        questions = _check_native(body, headers, route)
        require(body["model"] == manifest.get("model"), "requested model mismatch")
        _check_rubric(rubric, questions, route)
        _check_experiment_rubric(request)
    return {"requests": len(requests), "questions": sum(len(native_questions(r["body"], route)) for r in requests)}


def _check_experiment_rubric(request):
    rubric = request["rubric"]
    experiment = request.get("experiment")
    require(isinstance(experiment, str) and experiment, "experiment ID required")
    if experiment == "rule-compile":
        require(rubric.get("structure") in ("compiled", "per-state", "underspecified"), "invalid rule structure")
        if rubric["structure"] != "underspecified":
            require(isinstance(rubric.get("truth_table"), str) and
                    re.fullmatch("[01]{4}", rubric["truth_table"]), "rule truth table required")
            require(isinstance(rubric.get("group"), str), "rule group required")
        if rubric["structure"] == "compiled":
            tables = rubric.get("choice_tables")
            require(isinstance(tables, dict) and tables and all(isinstance(t, str) and re.fullmatch("[01]{4}", t)
                    for t in tables.values()), "compiled choice table mapping required")
    elif experiment == "probability":
        world = rubric.get("world")
        require(isinstance(world, dict) and set(world) == set(tasks.STATES) and
                all(finite(p) and 0 <= p <= 1 for p in world.values()) and
                abs(sum(world.values()) - 1) <= 1e-6, "valid probability world required")
        require(isinstance(rubric.get("group"), str) and rubric.get("condition") in
                ("single", "bundled", "joint", "coarse", "fine"), "invalid probability condition")
    elif experiment == "visual-criteria":
        require(rubric.get("family") in ("contains", "touching", "disjoint") and
                isinstance(rubric.get("group"), str) and isinstance(rubric.get("mapping"), dict),
                "visual relation and mapping required")


def _check_rubric(rubric, questions, route):
    require(isinstance(rubric, dict) and isinstance(rubric.get("questions"), dict), "rubric questions required")
    require(set(rubric["questions"]) == set(questions), "rubric question IDs do not match request")
    for qid, grade in rubric["questions"].items():
        require(isinstance(grade, dict), "grade must be an object")
        q = questions[qid]
        if q["type"] == "choice":
            require(grade.get("kind") == "choice" and isinstance(grade.get("acceptable"), list)
                    and grade["acceptable"], "Choice needs an acceptable set")
            require({token(v) for v in grade["acceptable"]} <= {token(v) for v in _values(q, route)},
                    "rubric contains foreign choice")
        elif q["type"] in ("predicate", "noul"):
            require(grade.get("kind") == "boolean" and isinstance(grade.get("expected"), bool), "Boolean truth required")
        else:
            require(grade.get("kind") == "number" and finite(grade.get("expected")), "numeric truth required")


def _distribution(values, probabilities):
    require(len(values) == len(probabilities), "incomplete probability distribution")
    require(all(finite(p) and 0 <= p <= 1 for p in probabilities), "invalid probability")
    require(abs(sum(probabilities) - 1) <= 1e-6, "probabilities do not sum to one")
    return [{"value": v, "probability": float(p)} for v, p in zip(values, probabilities)]


def _confidence(answer):
    value = answer.get("confidence")
    require(finite(value) and 0 <= value <= 1, "invalid or missing confidence")
    return float(value)


def normalize_answer(question, answer, route):
    require(isinstance(answer, dict), "answer must be an object")
    kind = question["type"]
    if answer.get("type") == "refusal" and route == "decisions":
        return {"outcome": "refusal", "type": "refusal", "value": None}
    require(answer.get("type") == kind, "answer primitive does not match request")
    if kind in ("predicate", "noul"):
        value = answer.get("probability" if kind == "predicate" else "noul")
        require(finite(value) and 0 <= value <= 1, "invalid predicate probability")
        return {"outcome": "ok", "type": kind, "value": float(value), "confidence": None}
    confidence = _confidence(answer)
    if kind == "choice":
        values = _values(question, route)
        require(token(answer.get("choice")) in {token(v) for v in values}, "foreign Choice value")
        raw = answer.get("probabilities")
        if route == "decisions":
            require(isinstance(raw, list) and all(isinstance(p, dict) and "value" in p and "probability" in p for p in raw),
                    "Choice probabilities must be native entries")
            keys = [token(p["value"]) for p in raw]
            require(len(keys) == len(set(keys)) and set(keys) == {token(v) for v in values}, "missing/duplicate/foreign probability values")
            mapping = {token(p["value"]): p["probability"] for p in raw}
            probabilities = [mapping[token(v)] for v in values]
        else:
            require(isinstance(raw, dict) and set(raw) == set(values), "probability keys do not match criteria")
            probabilities = [raw[v] for v in values]
        distribution = _distribution(values, probabilities)
        chosen = next(p["probability"] for p in distribution if token(p["value"]) == token(answer["choice"]))
        require(chosen >= max(probabilities) - 1e-9, "selected Choice is not an argmax")
        return {"outcome": "ok", "type": kind, "value": answer["choice"],
                "probabilities": distribution, "confidence": confidence}
    levels = question["levels"] if route == "decisions" else question["criteria"]
    raw = answer.get("probabilities")
    if route == "decisions":
        require(isinstance(raw, list) and all(isinstance(p, dict) for p in raw), "Score probabilities must be entries")
        require(len(raw) == len(levels), "incomplete Score probabilities")
        labels = [p.get("label") for p in raw]
        require(len(set(labels)) == len(labels) and set(labels) == {level["label"] for level in levels}, "foreign/duplicate Score labels")
        mapping = {p["label"]: p for p in raw}
        probabilities = []
        for index, level in enumerate(levels):
            p = mapping[level["label"]]
            require(type(p.get("value")) is int and p["value"] == index, "invalid Score level index")
            probabilities.append(p.get("probability"))
    else:
        require(isinstance(raw, dict) and set(raw) == {str(i) for i in range(len(levels))},
                "Jev Score probabilities must map level indices to mass")
        probabilities = [raw[str(i)] for i in range(len(levels))]
        if "legend" in answer:
            require(answer["legend"] == {str(i): label for i, label in enumerate(levels)}, "Score legend mismatch")
    distribution = _distribution(list(range(len(levels))), probabilities)
    value = answer.get("score")
    require(finite(value) and 0 <= value <= len(levels) - 1, "invalid Score")
    return {"outcome": "ok", "type": kind, "value": float(value), "confidence": confidence,
            "probabilities": distribution,
            "distribution_mean": sum(p["value"] * p["probability"] for p in distribution)}


def normalize_request(request, entry, route):
    questions = native_questions(request["body"], route)
    global_error, issues, aligned = None, [], {}
    raw = entry.get("response")
    status = entry.get("http_status")
    if entry.get("error"):
        global_error = f"transport: {entry['error']}"
    elif status is not None and not 200 <= status < 300:
        global_error = f"http_{status}"
    elif not isinstance(raw, dict) or not isinstance(raw.get("model"), str) or not raw["model"]:
        global_error = "response requires model and native answers"
    else:
        answers = raw.get("answers")
        if route == "decisions" and isinstance(answers, list):
            expected_ids = list(questions)
            for index, answer in enumerate(answers):
                if not isinstance(answer, dict) or not isinstance(answer.get("name"), str) or answer["name"] not in questions:
                    issues.append("foreign, unnamed or malformed answer")
                    continue
                name = answer["name"]
                if name in aligned:
                    aligned[name] = {"alignment_error": "duplicate answer"}
                elif len(answers) == len(questions) and name != expected_ids[index]:
                    aligned[name] = {"alignment_error": "answer order differs from request"}
                else:
                    aligned[name] = answer
        elif route == "jev" and isinstance(answers, dict):
            aligned = {key: value for key, value in answers.items() if key in questions}
            if set(answers) - set(questions):
                issues.append("foreign answer keys")
        else:
            global_error = "answers do not match the native route shape"
    results = []
    for qid, question in questions.items():
        error = global_error
        answer = aligned.get(qid)
        if not error and answer is None:
            error = "missing answer"
        if not error and isinstance(answer, dict) and "alignment_error" in answer:
            error = answer["alignment_error"]
        if route == "jev" and isinstance(answer, dict) and answer.get("name") is not None and answer["name"] != qid:
            error = "answer name mismatch"
        if not error:
            try:
                normalized = normalize_answer(question, answer, route)
            except (ApiLabError, TypeError, ValueError, KeyError) as exc:
                error = f"response_contract: {exc}"
        if error:
            normalized = {"outcome": "error", "type": question["type"], "value": None, "detail": error}
        results.append({"question_id": qid, **normalized})
    return {"request_id": request["id"], "questions": results, "contract_issues": issues,
            "requested_model": request["body"]["model"],
            "returned_model": raw.get("model") if isinstance(raw, dict) else None}


def validate_responses(entries, manifest, *, allow_partial=False):
    require(isinstance(entries, list) and entries, "responses must be a nonempty array")
    known = {request["id"] for request in manifest["requests"]}
    ids = []
    for entry in entries:
        require(isinstance(entry, dict) and isinstance(entry.get("request_id"), str), "request_id required")
        ids.append(entry["request_id"])
        require(set(entry) <= {"request_id", "response", "http_status", "error", "latency_ms", "usage", "cost"},
                "unknown response envelope fields")
        status = entry.get("http_status")
        require(status is None or (type(status) is int and 100 <= status <= 599), "invalid HTTP status")
        latency = entry.get("latency_ms")
        require(latency is None or (finite(latency) and latency >= 0), "invalid reported latency")
    require(len(ids) == len(set(ids)), "duplicate request_id")
    require(set(ids) <= known, "foreign request_id")
    require(allow_partial or set(ids) == known, "missing responses; use --allow-partial explicitly")


def load_responses(path):
    value = read_json(path)
    require(isinstance(value, dict) and value.get("schema") == RESPONSE_VERSION, "unsupported responses schema")
    require(value.get("synthetic") is None or isinstance(value["synthetic"], bool), "invalid synthetic source marker")
    return value


def synthetic_entries(manifest):
    """Editorial fixtures, never a model or an independently measured baseline."""
    entries = []
    route = manifest["route"]
    for request in manifest["requests"]:
        answers = {}
        for qid, q in native_questions(request["body"], route).items():
            grade = request["rubric"]["questions"][qid]
            if q["type"] == "choice":
                chosen = grade["acceptable"][0]
                values = _values(q, route)
                probs = [1.0 if token(v) == token(chosen) else 0.0 for v in values]
                answer = {"type": "choice", "choice": chosen, "confidence": .9,
                          "probabilities": ([{"value": v, "probability": p} for v, p in zip(values, probs)]
                                            if route == "decisions" else dict(zip(values, probs)))}
            elif q["type"] in ("predicate", "noul"):
                answer = {"type": q["type"], "probability" if route == "decisions" else "noul":
                          .9 if grade["expected"] else .1}
            else:
                count = len(q["levels"] if route == "decisions" else q["criteria"])
                position = min(range(count), key=lambda i: abs(i - grade["expected"]))
                probs = [1.0 if i == position else 0.0 for i in range(count)]
                answer = {"type": "score", "score": float(position), "confidence": .9,
                          "probabilities": ([{"label": level["label"], "value": i, "probability": probs[i]}
                                             for i, level in enumerate(q["levels"])] if route == "decisions" else {str(i): p for i, p in enumerate(probs)})}
            if route == "decisions":
                answer["name"] = qid
            answers[qid] = answer
        entries.append({"request_id": request["id"], "http_status": 200,
                        "response": {"model": manifest["model"],
                                     "answers": list(answers.values()) if route == "decisions" else answers}})
    # Deliberate, intelligible negative controls; separate from the editorial fixture generator.
    for request, entry in zip(manifest["requests"], entries):
        qs = native_questions(request["body"], route)
        answers = entry["response"]["answers"]
        by_id = dict(zip(qs, answers)) if route == "decisions" else answers
        condition = request["rubric"].get("condition")
        if request["experiment"] == "rule-compile" and condition == "reversed":
            qid = next(iter(qs)); answer = by_id[qid]
            alternate = next(v for v in _values(qs[qid], route) if token(v) != token(answer["choice"]) and v != "insufficient")
            answer["choice"] = alternate
            answer["probabilities"] = ([{"value": v, "probability": 1.0 if v == alternate else 0.0}
                                        for v in _values(qs[qid], route)] if route == "decisions"
                                       else {v: 1.0 if v == alternate else 0.0 for v in _values(qs[qid], route)})
        if request["experiment"] == "probability" and request["rubric"].get("group") == "split":
            if condition in ("coarse", "fine"):
                masses = {"A": .6, "B": .4} if condition == "coarse" else {"A1": .375, "A2": .375, "B": .25}
                q = next(iter(qs.values())); answer = next(iter(by_id.values()))
                chosen = max(masses, key=masses.get); answer["choice"] = chosen
                answer["probabilities"] = ([{"value": v, "probability": masses[v]} for v in _values(q, route)]
                                            if route == "decisions" else masses)
        if request["experiment"] == "visual-criteria" and condition == "swapped-image":
            by_id["relation"]["choice"] = "K1"
            by_id["relation"]["probabilities"] = {"K1": 1., "K2": 0., "K3": 0.}
    # One partial refusal and one malformed question leave sibling answers usable.
    multi = [(r, e) for r, e in zip(manifest["requests"], entries)
             if r["experiment"] in EXPERIMENTS and len(native_questions(r["body"], route)) > 1]
    if multi:
        request, entry = multi[0]
        first = next(iter(native_questions(request["body"], route)))
        if route == "decisions":
            entry["response"]["answers"][0] = {"type": "refusal", "name": first}
        else:
            entry["response"]["answers"][first] = {"type": "noul", "noul": 2.}
    if len(multi) > 1:
        request, entry = multi[1]
        first = next(iter(native_questions(request["body"], route)))
        question = native_questions(request["body"], route)[first]
        answer = entry["response"]["answers"][0] if route == "decisions" else entry["response"]["answers"][first]
        answer["confidence" if question["type"] in ("choice", "score") else
               ("probability" if route == "decisions" else "noul")] = -1.
    return entries


def _grade(normalized, grade):
    if normalized["outcome"] != "ok":
        return None
    value = normalized["value"]
    if grade["kind"] == "choice":
        if token(value) in {token(v) for v in grade.get("unknown_values", [])}:
            normalized["outcome"] = "unknown"
            return None
        return token(value) in {token(v) for v in grade["acceptable"]}
    if grade["kind"] == "boolean":
        return (value >= .5) == grade["expected"]
    return abs(value - grade["expected"]) <= grade.get("tolerance", 1e-6)


def _mass(question):
    return {p["value"]: p["probability"] for p in question.get("probabilities", [])}


def _reports(requests, normalized):
    by_id = {item["request_id"]: item for item in normalized}
    rules, probabilities, visuals = [], defaultdict(dict), defaultdict(dict)
    counterexamples = []
    for request in requests:
        if request["id"] not in by_id:
            continue
        result = by_id[request["id"]]
        rubric = request["rubric"]
        questions = {q["question_id"]: q for q in result["questions"]}
        for qid, q in questions.items():
            if q["outcome"] != "ok" or q["correct"] is False:
                counterexamples.append({"request_id": request["id"], "question_id": qid,
                                        "outcome": q["outcome"], "actual": q["value"],
                                        "rubric": rubric["questions"][qid], "detail": q.get("detail")})
        experiment = request["experiment"]
        if experiment == "rule-compile":
            predicted = None
            if rubric.get("structure") == "compiled":
                choice = questions["function"]
                if choice["outcome"] == "ok":
                    predicted = rubric["choice_tables"].get(choice["value"])
            elif rubric.get("structure") == "per-state":
                if all(q["outcome"] == "ok" for q in questions.values()):
                    predicted = "".join("1" if questions["s" + state]["value"] >= .5 else "0"
                                        for state in tasks.STATES)
            actual_truth = rubric.get("truth_table")
            differences = ([{"state": state, "expected": a, "actual": b}
                            for state, a, b in zip(tasks.STATES, actual_truth, predicted) if a != b]
                           if actual_truth is not None and predicted is not None else None)
            rules.append({"request_id": request["id"], "group": rubric.get("group"),
                          "function_index": rubric.get("function_index"), "wording": rubric.get("wording"),
                          "structure": rubric.get("structure"), "condition": rubric.get("condition"),
                          "predicted_table": predicted, "expected_table": actual_truth,
                          "hamming_error": len(differences) if differences is not None else None,
                          "counterexample_states": differences,
                          "correct": all(q["correct"] is True for q in questions.values())})
        elif experiment == "probability":
            group, condition = rubric["group"], rubric["condition"]
            target = probabilities[group]
            target["truth"] = tasks.world_truth(rubric["world"])
            if condition in ("single", "bundled"):
                values = target.setdefault(condition, {})
                for qid, q in questions.items():
                    if q["outcome"] == "ok":
                        values[qid.removeprefix("p_")] = float(q["value"])
            else:
                q = next(iter(questions.values()))
                target[condition] = _mass(q) if q["outcome"] == "ok" else None
        elif experiment == "visual-criteria":
            q = questions["relation"]
            visuals[rubric["group"]][rubric["condition"]] = {
                "value": q["value"], "correct": q["correct"], "outcome": q["outcome"],
                "defined_relation": rubric["mapping"].get(q["value"]), "truth": rubric["family"]}
    probability_reports = []
    for group, results in probabilities.items():
        item = {"group": group, **results}
        single, bundled = results.get("single", {}), results.get("bundled", {})
        item["single_bundled_delta"] = {event: abs(single[event] - bundled[event])
                                        if event in single and event in bundled else None
                                        for event in results["truth"]}
        item["numeric_truth_error"] = {condition: {
            event: abs(values[event] - truth) if event in values else None
            for event, truth in results["truth"].items()}
            for condition, values in (("single", single), ("bundled", bundled))}
        item["coherence"] = {}
        for condition, values in (("single", single), ("bundled", bundled)):
            if set(results["truth"]) <= set(values):
                a, b, both, either, xor = (values[e] for e in ("a", "b", "and", "or", "xor"))
                violations = []
                if not max(0., a + b - 1) - 1e-6 <= both <= min(a, b) + 1e-6:
                    violations.append("intersection_bounds")
                if abs(either - a - b + both) > 1e-6:
                    violations.append("union_identity")
                if abs(xor - a - b + 2 * both) > 1e-6:
                    violations.append("xor_identity")
                item["coherence"][condition] = {"complete": True, "violations": violations}
            else:
                item["coherence"][condition] = {"complete": False, "violations": None}
        coarse, fine = results.get("coarse"), results.get("fine")
        item["coarse_fine_mass_delta"] = (coarse["A"] - fine["A1"] - fine["A2"] if coarse and fine else None)
        joint = results.get("joint")
        item["joint_projected_marginals"] = tasks.world_truth(joint) if joint else None
        probability_reports.append(item)
    consistency = []
    for group in sorted({r["group"] for r in rules if r["structure"] == "compiled"}):
        variants = [r for r in rules if r["group"] == group and r["structure"] == "compiled"]
        tables = [r["predicted_table"] for r in variants]
        complete = len(variants) == 3 and all(t is not None for t in tables)
        consistency.append({"group": group, "complete": complete,
                            "same_prediction": len(set(tables)) == 1 if complete else None,
                            "all_correct": all(r["correct"] for r in variants) if complete else None})
    wording = []
    for index in sorted({r["function_index"] for r in rules if r["function_index"] is not None}):
        pair = [r for r in rules if r["function_index"] == index and r["structure"] == "compiled"
                and r["condition"] == "baseline"]
        if len(pair) == 2:
            complete = all(r["predicted_table"] is not None for r in pair)
            wording.append({"function_index": index, "complete": complete,
                            "same_prediction": pair[0]["predicted_table"] == pair[1]["predicted_table"] if complete else None})
    paired = []
    for group, conditions in visuals.items():
        before, after = conditions.get("image"), conditions.get("swapped-image")
        if before and after and before["outcome"] == after["outcome"] == "ok":
            paired.append({"group": group, "changed_label": before["value"] != after["value"],
                           "followed_definitions": before["correct"] is True and after["correct"] is True})
    return {"rule_compile": {"cases": rules, "order_id_consistency": consistency, "wording_consistency": wording},
            "probability": probability_reports, "visual_criteria": {"cases": dict(visuals), "definition_swap": paired},
            "counterexamples": counterexamples[:30],
            "probability_note": "Numeric event answers, native option mass and confidence are separate objects; self-consistency does not establish accuracy."}


def evaluate(manifest, entries, *, overrides=None):
    validate_manifest(manifest)
    validate_responses(entries, manifest, allow_partial=True)
    requests = copy.deepcopy(manifest["requests"])
    version = EVALUATOR_VERSION
    if overrides is not None:
        require(isinstance(overrides, dict) and isinstance(overrides.get("version"), str), "rubric version required")
        changes = overrides.get("requests")
        require(isinstance(changes, dict) and set(changes) <= {r["id"] for r in requests}, "foreign rubric request")
        for request in requests:
            if request["id"] in changes:
                _check_rubric(changes[request["id"]], native_questions(request["body"], manifest["route"]), manifest["route"])
                request["rubric"] = changes[request["id"]]
                _check_experiment_rubric(request)
        version = overrides["version"]
    entries_by_id = {entry["request_id"]: entry for entry in entries}
    normalized = []
    for request in requests:
        if request["id"] not in entries_by_id:
            continue
        result = normalize_request(request, entries_by_id[request["id"]], manifest["route"])
        for q in result["questions"]:
            q["correct"] = _grade(q, request["rubric"]["questions"][q["question_id"]])
        normalized.append(result)
    all_questions = [q for result in normalized for q in result["questions"]]
    counts = Counter(q["outcome"] for q in all_questions)
    expected_questions = sum(len(native_questions(r["body"], manifest["route"])) for r in requests)
    total_valid = counts["ok"]
    report = {"schema": "decisions-lab.api-evaluation/1", "evaluator_version": EVALUATOR_VERSION,
              "route": manifest["route"], "requested_model": manifest["model"],
              "configured_endpoint": manifest.get("endpoint"),
              "rubric_version": version, "live_verified": False,
              "coverage": {"expected_requests": len(requests), "received_requests": len(entries),
                           "missing_requests": len(requests) - len(entries),
                           "expected_questions": expected_questions, "received_question_slots": len(all_questions),
                           "missing_question_slots": expected_questions - len(all_questions),
                           **{key: counts[key] for key in ("ok", "unknown", "refusal", "error")}},
              "accuracy_on_valid_answers": sum(q["correct"] is True for q in all_questions) / total_valid if total_valid else None,
              "requests": normalized, **_reports(requests, normalized)}
    usage = []
    for entry in entries:
        raw = entry.get("response")
        usage.append({"request_id": entry["request_id"], "http_status": entry.get("http_status"),
                      "usage": entry.get("usage", raw.get("usage") if isinstance(raw, dict) else None),
                      "latency_ms": entry.get("latency_ms"), "cost": entry.get("cost"),
                      "returned_model": raw.get("model") if isinstance(raw, dict) else None})
    report["reported_request_usage"] = usage
    return report


def build_record(manifest, entries, *, provenance, allow_partial=False, imported_synthetic=None):
    validate_manifest(manifest)
    require(provenance in ("synthetic", "imported"), "unknown record provenance")
    validate_responses(entries, manifest, allow_partial=allow_partial)
    require(imported_synthetic is None or isinstance(imported_synthetic, bool), "invalid synthetic marker")
    record = {"schema": RECORD_VERSION, "created_at": datetime.now(timezone.utc).isoformat(),
              "provenance": provenance, "synthetic": True if provenance == "synthetic" else imported_synthetic, "live_verified": False,
              "manifest": copy.deepcopy(manifest), "responses": copy.deepcopy(entries)}
    record["evidence_digest"] = digest(record)
    return record


def _checked_record(path):
    path = Path(path)
    if path.is_dir():
        path /= "record.json"
    record = read_json(path)
    require(isinstance(record, dict) and record.get("schema") == RECORD_VERSION
            and record.get("provenance") in ("synthetic", "imported")
            and record.get("live_verified") is False, "invalid record provenance/schema")
    require(record.get("synthetic") is None or isinstance(record["synthetic"], bool), "invalid synthetic marker")
    require(record["provenance"] != "synthetic" or record.get("synthetic") is True, "synthetic provenance needs marker")
    retained = dict(record); supplied = retained.pop("evidence_digest", None)
    require(supplied == digest(retained), "retained evidence digest mismatch")
    return record


def replay_record(path, *, overrides=None):
    record = _checked_record(path)
    result = evaluate(record["manifest"], record["responses"], overrides=overrides)
    result["provenance"] = record["provenance"]
    result["synthetic"] = record["synthetic"]
    return result


def _safe_output(path, *, directory=False):
    path = Path(path).expanduser()
    root = Path(__file__).resolve().parents[1]
    resolved = path.resolve()
    if resolved.is_relative_to(root):
        require(resolved != root and resolved.relative_to(root).parts[0] == "runs",
                "run/evaluation output inside the repository must be under runs/")
    require(not path.exists(), f"output already exists: {path}")
    if directory:
        path.mkdir(parents=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_record(run_dir, record):
    # Validate and compute before creating the destination.
    evaluation = evaluate(record["manifest"], record["responses"])
    directory = _safe_output(run_dir, directory=True)
    _write(directory / "record.json", record)
    _write(directory / "evaluation.json", {**evaluation, "provenance": record["provenance"],
                                          "synthetic": record["synthetic"]})
    if record["synthetic"]:
        _write(directory / "responses.json", {"schema": RESPONSE_VERSION, "synthetic": True,
                                             "responses": record["responses"]})
        _write(directory / "manifest.json", record["manifest"])
    for request in record["manifest"]["requests"]:
        assets = request["body"].get("assets", {})
        if assets:
            for key, asset in assets.items():
                directory_path = directory / "evidence" / request["id"]
                directory_path.mkdir(parents=True, exist_ok=True)
                # Asset keys and request IDs are validated before being used as paths.
                require(Path(key).name == key and key not in (".", ".."), "unsafe asset key")
                (directory_path / (key + ".png")).write_bytes(base64.b64decode(asset["data_base64"]))
    return directory / "record.json"


def write_evaluation(path, report):
    output = _safe_output(path)
    _write(output, report)
    return output


def validate_suite(suite):
    counts = Counter(row["experiment"] for row in suite.rows)
    requests_by_route = {}
    for route in ROUTES:
        supported = [row for row in suite.rows if route == "jev" or row["experiment"] != "visual-criteria"]
        if supported:
            manifest = prepare_payload(suite, supported, route=route)
            requests_by_route[route] = validate_manifest(manifest)
    return {"provider_status": "NOT_RUN", "cases": dict(counts), "routes": requests_by_route}
