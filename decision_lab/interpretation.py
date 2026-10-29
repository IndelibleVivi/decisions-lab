"""Version-addressable offline interpretation of E1, E2 and E3 evidence.

This module is copied with the local Python sources when Studio freezes a study.
Imported JSON is data only; no source code or commands are loaded from a bundle.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile

from . import api_lab as al
from . import evidence_workflow as ew
from . import typed_dag as td
from . import collection

VERSION = "studio-interpretation/1"


def evaluate_record(record):
    al.require(isinstance(record, dict), "native evidence must be a JSON object")
    schema = record.get("schema")
    if schema == collection.SCHEMA:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "collection.json"
            path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            retained = collection.load_collection(path)
        al.require(retained["plan"]["kind"] == "api-lab", "E1 requires an api-lab collection")
        al.require(retained.get("provenance") == "collector" and retained.get("live_verified") is False,
                   "invalid collector provenance")
        from .ledger import from_collection
        ledger = from_collection(retained)
        trials = ledger["trials"]
        coverage = {outcome: sum(t["outcome"] == outcome for t in trials)
                    for outcome in ("ok", "unknown", "refusal", "error", "missing")}
        coverage.update(expected_questions=len(trials), missing_question_slots=coverage["missing"])
        return {"kind": "api-lab", "report": {"coverage": coverage, "synthetic": retained.get("synthetic"),
                 "provenance": "collector", "live_verified": False}, "ledger": ledger}
    if schema == al.RECORD_VERSION:
        # Use the existing reader so provenance and evidence binding are checked.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            report = al.replay_record(path)
            from .ledger import from_api
            ledger = from_api(record["manifest"], record["responses"], metadata={"provenance": record["provenance"], "synthetic": record["synthetic"]})
        return {"kind": "api-lab", "report": report, "ledger": ledger}
    if schema == ew.SCHEMA:
        return {"kind": "active-evidence", "report": ew.report(record)}
    if schema == td.SCHEMA:
        return {"kind": "typed-dag", "report": td.report(record)}
    raise al.ApiLabError("Studio supports api-lab records, active-evidence and typed-dag workflows")


def analyse(payload):
    """Interpret all conditions without losing the dedicated native evaluators."""
    records = payload["records"]
    al.require(isinstance(records, dict) and records, "analysis requires conditions")
    evaluated = {key: evaluate_record(value) for key, value in records.items()}
    al.require(len({value["kind"] for value in evaluated.values()}) == 1,
               "conditions must belong to the same experiment family")
    keys = list(records)
    comparisons = []
    for other in keys[1:]:
        left, right = keys[0], other
        try:
            kind = evaluated[left]["kind"]
            if kind == "active-evidence":
                result = ew.compare(records[left], records[right])
            elif kind == "typed-dag":
                result = td.compare(records[left], records[right])
            else:
                from . import comparison
                a, b = evaluated[left]["ledger"], evaluated[right]["ledger"]
                # The pairing owner validates scientific identity as well as native IDs.
                pair_spec = payload.get("pairings", {}).get(other)
                kwargs = {"pairing": pair_spec} if pair_spec is not None else {}
                result = comparison.compare_runs(a, b, bootstrap_samples=200, **kwargs)
            comparisons.append({"left": left, "right": right, "result": result, "error": None})
        except ValueError as exc:
            comparisons.append({"left": left, "right": right, "result": None, "error": str(exc)})
    return {"version": VERSION, "conditions": evaluated, "comparisons": comparisons,
            "live_verified": False}


def differences(before, after, path="", limit=100):
    """A bounded, exact report difference; missing is distinct from JSON null."""
    changes = []
    def visit(a, b, pointer):
        if len(changes) >= limit:
            return
        if type(a) is type(b) and isinstance(a, dict):
            for key in sorted(set(a) | set(b)):
                child = pointer + "/" + str(key).replace("~", "~0").replace("/", "~1")
                if key not in a or key not in b:
                    changes.append({"path": child, "before_present": key in a,
                                    "after_present": key in b, "before": a.get(key), "after": b.get(key)})
                else:
                    visit(a[key], b[key], child)
                if len(changes) >= limit:
                    break
        elif type(a) is type(b) and isinstance(a, list) and len(a) == len(b):
            for i, (x, y) in enumerate(zip(a, b)):
                visit(x, y, pointer + f"/{i}")
        elif type(a) is not type(b) or a != b:
            changes.append({"path": pointer or "/", "before": copy.deepcopy(a), "after": copy.deepcopy(b),
                            "before_present": True, "after_present": True})
    visit(before, after, path)
    return {"equal": before == after, "changes": changes, "truncated": len(changes) >= limit}
