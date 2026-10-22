"""Small prepared native contract probes; provider status remains NOT_RUN."""
from . import api_lab as al


def prepare_probes(route, model=None):
    questions = [
        {"id": "label", "type": "choice", "instructions": "Choose the label literally present in the input.",
         "choices": [{"value": "red", "description": "The word red"}, {"value": "blue", "description": "The word blue"}]},
        {"id": "present", "type": "predicate", "instructions": "Is the literal word red present?"},
        {"id": "strength", "type": "score", "instructions": "Rate the explicitly stated strength.",
         "levels": [{"label": "low", "description": "low strength"}, {"label": "high", "description": "high strength"}]},
    ]
    grades = {"label": {"kind": "choice", "acceptable": ["red"]},
              "present": {"kind": "boolean", "expected": True},
              "strength": {"kind": "number", "expected": 1.0}}
    rows = [{"id": f"probe-{q['id']}", "experiment": "contract-probe", "input": "red; strength=high",
             "questions": [q], "rubric": {"questions": {q["id"]: grades[q["id"]]}}} for q in questions]
    rows.append({"id": "probe-mixed", "experiment": "contract-probe", "input": "red; strength=high",
                 "questions": questions, "rubric": {"questions": grades}})
    return al.prepare_payload(al.Suite({"schema": "decisions-lab.api-suite/1"}, rows), rows, route=route, model=model)
