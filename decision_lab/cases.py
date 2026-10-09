"""Case schema, loading and validation for the next-action experiment.

A case studies a supplied public document/change plus supplied task/claim
context, and declares one or more ``acceptable`` next reading/checking
actions. The lab only recommends an action; it never executes one.

Design rules enforced here (see ``experiments/next-action/README.md``):

* Every case has a stable ``id``, a ``source_group``, a ``split``
  (``dev``/``test``), a ``task`` input, at least one ``acceptable``
  action and a non-empty ``rationale``.
* All language variants of one source document live in the same
  ``source_group`` and therefore the same ``split``.
* ``acceptable`` actions may list several defensible options; we never
  fabricate a single unique correct action.
* Labels/harness metadata (``acceptable``, ``rationale``, ``split``,
  ``source_group``, ``id``) must NEVER be sent to a provider. Only the
  ``task`` input is model-visible. See ``routes.build_request``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: The set of permitted POSITIVE next-action options a case may accept.
#: Meaning is fixed by the contract (README) and must not drift silently.
#: The explicit ``unknown`` option (see ``routes.UNKNOWN_ACTION``) is an
#: ordinary model-visible choice offered on every request, but it is NOT a
#: task action and therefore never appears in a case's ``acceptable`` set.
ALLOWED_ACTIONS = ("inspect_source", "compare_contract", "read_in_context", "needs_more_context")

ALLOWED_SPLITS = ("dev", "test")

REQUIRED_FIELDS = ("id", "source_group", "split", "task", "acceptable", "rationale")

#: Fields that are editorial/label metadata and are never model-visible.
LABEL_FIELDS = ("acceptable", "rationale", "split", "source_group", "id")


class CaseError(ValueError):
    """Raised for malformed case data. Message is intended for humans."""


@dataclass
class TaskInput:
    """The model-visible task input.

    ``document`` is the supplied public document/change text. ``claim`` is
    the supplied task/claim context the reader is judging. ``question`` is
    the framing question. ``source_ref`` is an optional short public
    reference (a URL/path name), never private data.
    """

    document: str
    question: str = "What is the single best next reading/checking action?"
    claim: str = ""
    source_ref: str = ""


@dataclass
class Case:
    id: str
    source_group: str
    split: str
    task: TaskInput
    acceptable: list[str]
    rationale: str
    notes: str = ""

    def model_input(self) -> dict[str, Any]:
        """Return the ONLY data a provider may see for this case.

        Labels, split, source_group, id and rationale are deliberately
        excluded. This is the single choke point for label-leakage safety.
        """
        return {
            "document": self.task.document,
            "question": self.task.question,
            "claim": self.task.claim,
            "source_ref": self.task.source_ref,
        }


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise CaseError(msg)


def parse_case(raw: Any, *, where: str = "<case>") -> Case:
    _require(isinstance(raw, dict), f"{where}: case must be a JSON object")
    for fname in REQUIRED_FIELDS:
        _require(fname in raw, f"{where}: missing required field {fname!r}")

    cid = raw["id"]
    _require(isinstance(cid, str) and cid.strip(), f"{where}: 'id' must be a non-empty string")

    group = raw["source_group"]
    _require(
        isinstance(group, str) and group.strip(),
        f"{where}: 'source_group' must be a non-empty string",
    )

    split = raw["split"]
    _require(
        split in ALLOWED_SPLITS,
        f"{where}: 'split' must be one of {ALLOWED_SPLITS}, got {split!r}",
    )

    task_raw = raw["task"]
    _require(isinstance(task_raw, dict), f"{where}: 'task' must be an object")
    document = task_raw.get("document", "")
    _require(isinstance(document, str), f"{where}: 'task.document' must be a string")
    question = task_raw.get("question", "What is the single best next reading/checking action?")
    _require(isinstance(question, str) and question.strip(), f"{where}: 'task.question' must be a string")
    claim = task_raw.get("claim", "")
    _require(isinstance(claim, str), f"{where}: 'task.claim' must be a string")
    source_ref = task_raw.get("source_ref", "")
    _require(isinstance(source_ref, str), f"{where}: 'task.source_ref' must be a string")
    # A case must carry *some* model-visible text to reason about; an empty
    # task is a legitimate "needs_more_context" case only if the question
    # itself conveys the task (which it always does), but at least one text
    # field should be non-empty so the task is not vacuous.
    _require(
        document.strip() or claim.strip() or question.strip(),
        f"{where}: task has no text at all (document/claim/question all empty)",
    )

    acceptable = raw["acceptable"]
    _require(
        isinstance(acceptable, list) and len(acceptable) >= 1,
        f"{where}: 'acceptable' must be a non-empty list",
    )
    seen: set[str] = set()
    for act in acceptable:
        _require(isinstance(act, str), f"{where}: each acceptable action must be a string")
        _require(
            act in ALLOWED_ACTIONS,
            f"{where}: acceptable action {act!r} not in {ALLOWED_ACTIONS}",
        )
        _require(act not in seen, f"{where}: duplicate acceptable action {act!r}")
        seen.add(act)

    rationale = raw["rationale"]
    _require(
        isinstance(rationale, str) and rationale.strip(),
        f"{where}: 'rationale' must be a non-empty string",
    )
    notes = raw.get("notes", "")
    _require(isinstance(notes, str), f"{where}: 'notes' must be a string")

    return Case(
        id=cid.strip(),
        source_group=group.strip(),
        split=split,
        task=TaskInput(
            document=document,
            question=question,
            claim=claim,
            source_ref=source_ref,
        ),
        acceptable=list(acceptable),
        rationale=rationale.strip(),
        notes=notes,
    )


@dataclass
class Suite:
    cases: list[Case] = field(default_factory=list)

    def by_id(self) -> dict[str, Case]:
        return {c.id: c for c in self.cases}

    def split(self, name: str) -> list[Case]:
        return [c for c in self.cases if c.split == name]


def load_suite(path: str | Path) -> Suite:
    """Load and fully validate a JSON suite file.

    Raises :class:`CaseError` with a human-readable message on any
    problem: malformed JSON, bad schema, duplicate ids, empty suite, or
    a source group that spans both splits.
    """
    p = Path(path)
    if not p.is_file():
        raise CaseError(f"suite file not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CaseError(f"{p}: invalid JSON: {exc}") from exc

    if isinstance(data, dict):
        raw_cases = data.get("cases")
    else:
        raw_cases = data
    _require(isinstance(raw_cases, list), f"{p}: expected a JSON list or {{'cases': [...]}} object")

    suite = Suite()
    for i, rc in enumerate(raw_cases):
        suite.cases.append(parse_case(rc, where=f"{p}[{i}]"))

    validate_suite(suite, where=str(p))
    return suite


def validate_suite(suite: Suite, *, where: str = "<suite>") -> None:
    """Cross-case validation: usable size, unique ids, clean split isolation."""
    _require(len(suite.cases) >= 1, f"{where}: suite is empty; provide at least one case")

    seen_ids: set[str] = set()
    for c in suite.cases:
        if c.id in seen_ids:
            raise CaseError(f"{where}: duplicate case id {c.id!r}")
        seen_ids.add(c.id)

    # A source group must not leak across splits: all its language variants
    # belong to exactly one split.
    group_splits: dict[str, set[str]] = {}
    for c in suite.cases:
        group_splits.setdefault(c.source_group, set()).add(c.split)
    for group, splits in group_splits.items():
        if len(splits) > 1:
            raise CaseError(
                f"{where}: source_group {group!r} spans multiple splits {sorted(splits)}; "
                "keep all language variants of one source in a single split"
            )
