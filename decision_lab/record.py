"""Run records, recording, replay and evaluation.

A *record* is a JSON document describing one completed (or partially
completed) run. It is written to a NEW local run directory and links the
exact cases + route + model + protocol used, so replay is reproducible
without arbitrary hashing. Only where a real input-integrity check is
needed (replay must detect that a recorded case no longer matches the
suite) do we store a lightweight content digest.

Record provenance kinds:
  * ``baseline``  - deterministic offline rules; ``synthetic`` = true
  * ``demo``      - constructed/recorded examples, marked ``synthetic``
  * ``live``      - real provider responses (only produced by collect-live)

Evaluation separates:
  * correctness coverage over cases that produced a normal choice,
  * attempted failures (transport/HTTP/parse),
  * unknown and refusal rates,
  * selective coverage (how many cases were actually answered).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .baseline import judge
from .cases import Case, Suite, load_suite
from .routes import (
    OFFERED_OPTIONS,
    OUTCOME_ERROR,
    OUTCOME_OK,
    OUTCOME_REFUSAL,
    OUTCOME_UNKNOWN,
    build_request,
    get_route,
)

RECORD_VERSION = 1

PROVENANCE_SYNTHETIC = "synthetic"
PROVENANCE_LIVE = "live"

#: Tolerances for record-integrity validation. They mirror the route-layer
#: normalizer so a corrupted/foreign record cannot be counted as correct.
_PROB_SUM_TOLERANCE = 1e-6
_ARGMAX_TOLERANCE = 1e-9


class RecordError(ValueError):
    """Failure while writing a record directory or replaying one."""


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


def case_digest(case: Case) -> str:
    """Stable digest of a case's model-visible input plus its identity.

    Replay uses this to detect that a recorded case no longer matches the
    suite it claims to come from. It is derived from real input fields.
    """
    payload = {
        "id": case.id,
        "split": case.split,
        "source_group": case.source_group,
        "task": case.model_input(),
        "acceptable": list(case.acceptable),
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()[:32]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def suite_digest(suite: Suite) -> str:
    h = hashlib.sha256()
    for c in suite.cases:
        h.update(case_digest(c).encode("utf-8"))
    return "sha256:" + h.hexdigest()[:32]


@dataclass
class CaseResult:
    case_id: str
    source_group: str
    split: str
    digest: str
    outcome: str
    action: str | None
    probabilities: dict[str, float] | None
    model: str | None
    confidence: float | None = None
    http_status: int | None = None
    #: The exact outbound request retained for reproducibility. ``endpoint``
    #: is the fixed native URL and ``request`` is the exact JSON body that was
    #: sent (or would have been sent). NEVER contains credentials/headers.
    endpoint: str | None = None
    request: Any = None
    refusal_reason: str | None = None
    error_kind: str | None = None
    error_detail: str | None = None
    raw: Any = None
    usage: dict[str, Any] | None = None
    cost: dict[str, Any] | None = None
    latency_ms: float | None = None
    correct: bool | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "source_group": self.source_group,
            "split": self.split,
            "digest": self.digest,
            "outcome": self.outcome,
            "action": self.action,
            "probabilities": self.probabilities,
            "model": self.model,
            "confidence": self.confidence,
            "http_status": self.http_status,
            "endpoint": self.endpoint,
            "request": self.request,
            "refusal_reason": self.refusal_reason,
            "error_kind": self.error_kind,
            "error_detail": self.error_detail,
            "raw": self.raw,
            "usage": self.usage,
            "cost": self.cost,
            "latency_ms": self.latency_ms,
            "correct": self.correct,
        }


@dataclass
class Record:
    provenance: str          # "baseline" | "demo" | "live"
    route: str               # route key, or "baseline"
    native_model: str | None
    suite_path: str
    suite_digest: str
    protocol: dict[str, Any]
    results: list[CaseResult]
    synthetic: bool
    created_at: str = ""
    notes: str = ""
    version: int = RECORD_VERSION
    planned_case_ids: list[str] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_version": self.version,
            "created_at": self.created_at or _now(),
            "provenance": self.provenance,
            "synthetic": self.synthetic,
            "route": self.route,
            "native_model": self.native_model,
            "suite_path": self.suite_path,
            "suite_digest": self.suite_digest,
            "protocol": self.protocol,
            "notes": self.notes,
            "results": [r.as_dict() for r in self.results],
            "planned_case_ids": self.planned_case_ids,
        }


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_json_atomic(path: Path, data: Any) -> None:
    """Write JSON via a sibling temp file + atomic rename.

    An interrupt mid-write cannot corrupt or truncate a previously valid
    record: the destination only ever flips between complete files.
    """
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)

def _forbid_source_path(path: Path) -> None:
    parts = {p.lower() for p in path.parts}
    # Source trees that must never receive run output.
    for banned in ("catalog", "research", "experiments", "tests"):
        if banned in parts:
            raise RecordError(f"refuse to write run output into {banned}/ source tree: {path}")


def write_record(run_dir: str | Path, record: Record, *, clobber: bool = False) -> Path:
    """Write a record into a NEW run directory. Refuses to clobber."""
    d = Path(run_dir)
    if d.exists() and any(d.iterdir()) and not clobber:
        raise RecordError(
            f"run directory {d} already exists and is non-empty; refuse to clobber"
        )
    _forbid_source_path(d)
    d.mkdir(parents=True, exist_ok=True)
    out = d / "record.json"
    if out.exists() and not clobber:
        raise RecordError(f"{out} already exists; refuse to clobber")
    _write_json_atomic(out, record.as_dict())
    return out


# --------------------------------------------------------------------------
# baseline / demo runs (offline, synthetic)
# --------------------------------------------------------------------------
def run_baseline(suite: Suite, *, suite_path: str) -> Record:
    results: list[CaseResult] = []
    for case in suite.cases:
        j = judge(case.model_input())
        results.append(
            CaseResult(
                case_id=case.id,
                source_group=case.source_group,
                split=case.split,
                digest=case_digest(case),
                outcome=OUTCOME_OK,
                action=j.action,
                probabilities=None,
                model="baseline-rules-v1",
                correct=(j.action in case.acceptable),
                raw=j.as_dict(),
            )
        )
    return Record(
        provenance="baseline",
        route="baseline",
        native_model=None,
        suite_path=suite_path,
        suite_digest=suite_digest(suite),
        protocol={"kind": "baseline_rules", "offline": True},
        results=results,
        synthetic=True,
        notes="Deterministic offline rules baseline; synthetic demonstration only.",
    )


def _pick_wrong(case: Case) -> str:
    for act in ("inspect_source", "compare_contract", "read_in_context", "needs_more_context"):
        if act not in case.acceptable:
            return act
    return "inspect_source"


def _demo_distribution(selected: str) -> dict[str, float]:
    """A synthetic probability distribution over the FULL offered option set
    that is valid (finite, in [0,1], sums to 1) and whose argmax is
    ``selected``. Constructed for reader demonstration only."""
    others = [opt for opt in OFFERED_OPTIONS if opt != selected]
    mass = 0.6
    rest = (1.0 - mass) / len(others)
    dist = {opt: rest for opt in others}
    dist[selected] = mass
    return dist


def run_demo(suite: Suite, *, suite_path: str) -> Record:
    """Offline demo run: baseline judgments, plus one deliberately wrong and
    one deliberately unknown example so a reader can SEE a failed judgment
    and a non-choice. Everything is constructed/synthetic, NOT model inference.
    """
    cases = suite.cases
    wrong_idx = None
    for i, c in enumerate(cases):
        if judge(c.model_input()).action not in c.acceptable:
            wrong_idx = i
            break
    if wrong_idx is None:
        wrong_idx = 0

    # Choose a different case for the explicit-unknown demonstration so the
    # record keeps exactly one result per suite case (replay stays faithful).
    unknown_idx = None
    for i in range(len(cases)):
        if i != wrong_idx:
            unknown_idx = i
            break

    results: list[CaseResult] = []
    for i, case in enumerate(cases):
        if i == wrong_idx:
            wrong_action = _pick_wrong(case)
            results.append(
                CaseResult(
                    case_id=case.id, source_group=case.source_group, split=case.split,
                    digest=case_digest(case), outcome=OUTCOME_OK, action=wrong_action,
                    probabilities=_demo_distribution(wrong_action),
                    model="demo-constructed-wrong",
                    correct=False,
                    raw={"kind": "constructed_demo", "synthetic": True,
                         "note": "deliberately wrong answer for reader demonstration"},
                )
            )
        elif i == unknown_idx:
            results.append(
                CaseResult(
                    case_id=case.id, source_group=case.source_group, split=case.split,
                    digest=case_digest(case), outcome=OUTCOME_UNKNOWN, action="unknown",
                    probabilities=_demo_distribution("unknown"),
                    model="demo-constructed-unknown",
                    correct=None,
                    raw={"kind": "constructed_demo", "synthetic": True,
                         "note": "explicit unknown action; not a refusal or transport error"},
                )
            )
        else:
            j = judge(case.model_input())
            results.append(
                CaseResult(
                    case_id=case.id, source_group=case.source_group, split=case.split,
                    digest=case_digest(case), outcome=OUTCOME_OK, action=j.action,
                    probabilities=_demo_distribution(j.action),
                    model="demo-constructed",
                    correct=(j.action in case.acceptable),
                    raw={"kind": "constructed_demo", "synthetic": True, "reasons": j.reasons},
                )
            )
    return Record(
        provenance="demo",
        route="baseline",
        native_model=None,
        suite_path=suite_path,
        suite_digest=suite_digest(suite),
        protocol={"kind": "constructed_demo", "offline": True, "synthetic": True},
        results=results,
        synthetic=True,
        notes=(
            "Offline constructed demo: includes one deliberately wrong answer and one "
            "explicit unknown. All responses are SYNTHETIC, not model inference."
        ),
    )


# --------------------------------------------------------------------------
# replay / evaluation
# --------------------------------------------------------------------------
@dataclass
class EvalReport:
    total: int
    answered: int               # normal choices
    correct: int
    accuracy: float | None      # over answered
    unknown: int
    refusal: int
    errors: int
    attempted: int              # answered + unknown + refusal + errors == total
    coverage: float             # answered / total
    selective_coverage: float   # answered / total (explicit name)
    by_split: dict[str, dict[str, int]] = field(default_factory=dict)
    errors_detail: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "answered": self.answered,
            "correct": self.correct,
            "accuracy": self.accuracy,
            "unknown": self.unknown,
            "refusal": self.refusal,
            "errors": self.errors,
            "attempted": self.attempted,
            "coverage": self.coverage,
            "selective_coverage": self.selective_coverage,
            "by_split": self.by_split,
            "errors_detail": self.errors_detail,
        }


def validate_case_result(r: CaseResult) -> None:
    """Reject a corrupted per-case result before it can be counted.

    A record loaded from disk is untrusted input. We enforce outcome /
    action / probability consistency so that a hand-edited or foreign
    record cannot masquerade as a correct answer:

    * ``ok``      requires an offered task action (never ``unknown``) and,
      when probabilities are present, that the action is their argmax over
      a valid finite distribution summing to ~1.
    * ``unknown`` requires exactly the ``unknown`` action.
    * ``refusal`` requires ``action is None``.
    * ``error``   requires ``error_kind`` and ``action is None``; its
      probabilities are informational only.
    * ``correct`` may only be true for an ``ok`` outcome.
    """
    if not isinstance(r.outcome, str):
        raise RecordError(f"case {r.case_id!r}: outcome must be a string")
    if r.confidence is not None and not _is_finite_number(r.confidence):
        raise RecordError(f"case {r.case_id!r}: confidence must be finite or null")
    if r.confidence is not None and not 0 <= r.confidence <= 1:
        raise RecordError(f"case {r.case_id!r}: confidence must be in [0,1]")
    if r.correct is not None and not isinstance(r.correct, bool):
        raise RecordError(f"case {r.case_id!r}: correct must be boolean or null")

    if r.probabilities is not None:
        _validate_record_probabilities(r)

    if r.outcome == OUTCOME_OK:
        if r.action is None or r.action == "unknown" or r.action not in OFFERED_OPTIONS:
            raise RecordError(
                f"case {r.case_id!r}: outcome 'ok' requires a positive action, got {r.action!r}"
            )
        if r.probabilities is not None:
            _check_record_argmax(r)
    elif r.outcome == OUTCOME_UNKNOWN:
        if r.action != "unknown":
            raise RecordError(
                f"case {r.case_id!r}: outcome 'unknown' requires action 'unknown', "
                f"got {r.action!r}"
            )
        if r.probabilities is not None:
            _check_record_argmax(r)
        if r.correct is True:
            raise RecordError(
                f"case {r.case_id!r}: an 'unknown' result cannot be marked correct"
            )
    elif r.outcome == OUTCOME_REFUSAL:
        if r.action is not None:
            raise RecordError(
                f"case {r.case_id!r}: refusal must not carry an action, got {r.action!r}"
            )
        if r.correct is True:
            raise RecordError(f"case {r.case_id!r}: a refusal cannot be marked correct")
    elif r.outcome == OUTCOME_ERROR:
        if r.action is not None:
            raise RecordError(
                f"case {r.case_id!r}: an error must not carry an action, got {r.action!r}"
            )
        if not r.error_kind:
            raise RecordError(f"case {r.case_id!r}: an error must carry an error_kind")
        if r.correct is True:
            raise RecordError(f"case {r.case_id!r}: an error cannot be marked correct")
    else:
        raise RecordError(f"case {r.case_id!r}: unknown outcome kind {r.outcome!r}")


def _validate_record_probabilities(r: CaseResult) -> None:
    probs = r.probabilities
    if not isinstance(probs, dict) or not probs:
        raise RecordError(
            f"case {r.case_id!r}: probabilities must be a non-empty object or null"
        )
    if set(probs) != set(OFFERED_OPTIONS):
        raise RecordError(f"case {r.case_id!r}: probabilities must include every offered option")
    total = 0.0
    for k, v in probs.items():
        if k not in OFFERED_OPTIONS:
            raise RecordError(f"case {r.case_id!r}: foreign probability key {k!r}")
        if not _is_finite_number(v) or not (0.0 <= float(v) <= 1.0):
            raise RecordError(
                f"case {r.case_id!r}: probability for {k!r} must be finite and in [0,1]"
            )
        total += float(v)
    if abs(total - 1.0) > _PROB_SUM_TOLERANCE:
        raise RecordError(
            f"case {r.case_id!r}: probabilities sum to {total!r}, not within "
            f"{_PROB_SUM_TOLERANCE} of 1"
        )


def _check_record_argmax(r: CaseResult) -> None:
    probs = r.probabilities or {}
    top = max(probs.values())
    if probs.get(r.action, -1.0) < top - _ARGMAX_TOLERANCE:
        raise RecordError(
            f"case {r.case_id!r}: recorded action {r.action!r} is not an argmax of "
            "its own probability distribution"
        )


def _check_retained_request(record: Record, r: CaseResult, case: Case) -> None:
    """Bind a retained outbound request to its case on replay.

    A live record promises reproducibility: it must retain the exact prompt
    (endpoint + request body) per case. On replay we check that the retained
    body still equals what the CURRENT adapter builds for that case, so a
    tampered/foreign body or silent adapter drift is caught rather than
    silently trusted. Records without a retained request (baseline/demo) are
    skipped.
    """
    if r.request is None and r.endpoint is None:
        if record.provenance == "live":
            raise RecordError(f"case {r.case_id!r}: live record is missing its outbound request")
        return
    if r.request is None or r.endpoint is None:
        raise RecordError(
            f"case {r.case_id!r}: retained request must include both endpoint and body"
        )
    if record.route not in ("jev", "decisions"):
        raise RecordError(
            f"case {r.case_id!r}: retained request present for non-provider route "
            f"{record.route!r}"
        )
    prof = get_route(record.route)
    if r.endpoint != prof.endpoint:
        raise RecordError(
            f"case {r.case_id!r}: retained endpoint {r.endpoint!r} does not match "
            f"route {record.route!r} endpoint {prof.endpoint!r}"
        )
    expected = build_request(record.route, case)
    if r.request != expected:
        raise RecordError(
            f"case {r.case_id!r}: retained request body does not match the current "
            "adapter output; refusing to evaluate a stale or tampered prompt"
        )


def evaluate(record: Record, suite: Suite, *, suite_path: str | None = None) -> EvalReport:
    """Replay a record against a suite, checking it is complete and matching.

    Raises :class:`RecordError` if the record is missing cases, has
    duplicates, has foreign (unknown) cases, or if the recorded case
    context (id/digest) no longer matches the suite.
    """
    suite_cases = {c.id: c for c in suite.cases}

    if record.provenance in ("baseline", "demo"):
        if record.synthetic is not True or record.route != "baseline" or record.native_model is not None:
            raise RecordError("synthetic run provenance/route/model metadata is inconsistent")
    elif record.provenance == "live":
        if record.synthetic is not False or record.route not in ("jev", "decisions"):
            raise RecordError("live run provenance/route metadata is inconsistent")
        route_model_check(record, record.route)
        if record.native_model != get_route(record.route).native_model:
            raise RecordError("live record must name its requested model")
    else:
        raise RecordError(f"unknown provenance: {record.provenance!r}")

    if suite_path is not None and Path(suite_path).resolve() != Path(record.suite_path).resolve():
        raise RecordError(
            f"replay suite {suite_path} does not match record suite {record.suite_path}"
        )
    if suite_digest(suite) != record.suite_digest:
        raise RecordError(
            "suite content digest differs from the one recorded; the suite changed "
            "since the run, so replay would not be faithful"
        )

    seen: set[str] = set()
    for r in record.results:
        if r.case_id in seen:
            raise RecordError(f"record contains duplicate case id {r.case_id!r}")
        seen.add(r.case_id)
        if r.case_id not in suite_cases:
            raise RecordError(f"record contains foreign case id {r.case_id!r} not in suite")

    planned = record.planned_case_ids
    if planned is not None:
        if (not isinstance(planned, list) or not planned or any(not isinstance(i, str) for i in planned)
                or len(planned) != len(set(planned)) or not set(planned) <= set(suite_cases)):
            raise RecordError("invalid planned_case_ids")
        if not seen <= set(planned):
            raise RecordError("result outside planned_case_ids")
    missing = (set(suite_cases) if planned is None else set(planned)) - seen
    if missing:
        raise RecordError(
            f"record is missing cases {sorted(missing)}; refusing to evaluate a subset as complete"
        )

    for r in record.results:
        case = suite_cases[r.case_id]
        if r.split != case.split or r.source_group != case.source_group:
            raise RecordError(f"case {r.case_id!r}: split/source group differs from the suite")
        expected_correct = (r.action in case.acceptable) if r.outcome == OUTCOME_OK else None
        if r.correct is not expected_correct:
            raise RecordError(f"case {r.case_id!r}: stored correctness disagrees with the suite labels")
        if r.digest != case_digest(case):
            raise RecordError(
                f"case {r.case_id!r} input/context differs from what was recorded "
                "(task or labels changed); refusing to evaluate"
            )
        _check_retained_request(record, r, case)
        if record.provenance == "live" and r.outcome != OUTCOME_ERROR:
            if r.http_status != 200 or isinstance(r.http_status, bool):
                raise RecordError(f"case {r.case_id!r}: a live answer must retain HTTP 200")
            normalized = get_route(record.route).normalize(r.http_status, r.raw)
            for field in ("outcome", "action", "probabilities", "model", "confidence", "refusal_reason"):
                if getattr(normalized, field) != getattr(r, field):
                    raise RecordError(f"case {r.case_id!r}: normalized {field} disagrees with raw response")

    total = len(record.results)
    answered = correct = unknown = refusal = errors = 0
    by_split: dict[str, dict[str, int]] = {}
    errors_detail: list[dict[str, Any]] = []
    for r in record.results:
        validate_case_result(r)
        bs = by_split.setdefault(r.split, {"total": 0, "answered": 0, "correct": 0, "unknown": 0})
        bs["total"] += 1
        if r.outcome == OUTCOME_OK:
            answered += 1
            bs["answered"] += 1
            if r.correct:
                correct += 1
                bs["correct"] += 1
        elif r.outcome == OUTCOME_UNKNOWN:
            unknown += 1
            bs["unknown"] += 1
        elif r.outcome == OUTCOME_REFUSAL:
            refusal += 1
        elif r.outcome == OUTCOME_ERROR:
            errors += 1
            errors_detail.append(
                {"case_id": r.case_id, "error_kind": r.error_kind, "error_detail": r.error_detail}
            )
        else:
            raise RecordError(f"case {r.case_id!r}: unknown outcome kind {r.outcome!r}")

    attempted = answered + unknown + refusal + errors
    accuracy = (correct / answered) if answered else None
    coverage = answered / total if total else 0.0
    return EvalReport(
        total=total,
        answered=answered,
        correct=correct,
        accuracy=accuracy,
        unknown=unknown,
        refusal=refusal,
        errors=errors,
        attempted=attempted,
        coverage=coverage,
        selective_coverage=coverage,
        by_split=by_split,
        errors_detail=errors_detail,
    )


def load_record(path: str | Path) -> Record:
    p = Path(path)
    if p.is_dir():
        p = p / "record.json"
    if not p.is_file():
        raise RecordError(f"record not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RecordError(f"{p}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RecordError(f"{p}: record must be a JSON object")
    if data.get("record_version") != RECORD_VERSION:
        raise RecordError(
            f"{p}: unsupported record_version {data.get('record_version')!r} "
            f"(expected {RECORD_VERSION})"
        )
    if not isinstance(data.get("results"), list):
        raise RecordError(f"{p}: results must be an array")
    if not isinstance(data.get("synthetic"), bool):
        raise RecordError(f"{p}: synthetic must be a boolean")
    for field in ("route", "provenance", "suite_path", "suite_digest"):
        if not isinstance(data.get(field), str):
            raise RecordError(f"{p}: {field} must be a string")
    results = []
    for r in data["results"]:
        if not isinstance(r, dict) or not isinstance(r.get("case_id"), str):
            raise RecordError(f"{p}: each result must be an object with a string case_id")
        result = CaseResult(
            case_id=r["case_id"],
            source_group=r.get("source_group", ""),
            split=r.get("split", ""),
            digest=r.get("digest", ""),
            outcome=r.get("outcome", ""),
            action=r.get("action"),
            probabilities=r.get("probabilities"),
            model=r.get("model"),
            confidence=r.get("confidence"),
            http_status=r.get("http_status"),
            endpoint=r.get("endpoint"),
            request=r.get("request"),
            refusal_reason=r.get("refusal_reason"),
            error_kind=r.get("error_kind"),
            error_detail=r.get("error_detail"),
            raw=r.get("raw"),
            usage=r.get("usage"),
            cost=r.get("cost"),
            latency_ms=r.get("latency_ms"),
            correct=r.get("correct"),
        )
        validate_case_result(result)
        results.append(result)
    return Record(
        provenance=data.get("provenance", ""),
        route=data.get("route", ""),
        native_model=data.get("native_model"),
        suite_path=data.get("suite_path", ""),
        suite_digest=data.get("suite_digest", ""),
        protocol=data.get("protocol", {}),
        results=results,
        synthetic=bool(data.get("synthetic", False)),
        created_at=data.get("created_at", ""),
        notes=data.get("notes", ""),
        version=data.get("record_version", RECORD_VERSION),
        planned_case_ids=data.get("planned_case_ids"),
    )


def load_and_evaluate(record_path: str | Path, suite_path: str | Path) -> EvalReport:
    record = load_record(record_path)
    suite = load_suite(suite_path)
    return evaluate(record, suite, suite_path=str(suite_path))


# --------------------------------------------------------------------------
# probability / threshold evaluation (only when explicitly selected)
# --------------------------------------------------------------------------
def probability_stats(record: Record, *, statistic: str = "maxP") -> dict[str, Any]:
    """Report route-native probabilities, converted with a documented stat.

    We never invent a uniform provider confidence. ``statistic='maxP'``
    uses the maximum per-option probability when a route returns a
    distribution; routes without probabilities yield ``None`` per case.
    """
    if statistic != "maxP":
        raise RecordError(f"unsupported statistic {statistic!r}; only 'maxP' is defined")
    out: dict[str, Any] = {"statistic": statistic, "cases": []}
    for r in record.results:
        if not r.probabilities:
            out["cases"].append({"case_id": r.case_id, "score": None})
            continue
        _validate_record_probabilities(r)
        out["cases"].append({"case_id": r.case_id, "score": max(r.probabilities.values())})
    return out


def threshold_coverage(record: Record, *, threshold: float, statistic: str = "maxP") -> dict[str, Any]:
    """Fraction of cases whose selected statistic >= threshold, plus accuracy
    among those. Only valid when the record carries probabilities."""
    if not _is_finite_number(threshold):
        raise RecordError(f"threshold must be a finite number, got {threshold!r}")
    if not (0.0 <= float(threshold) <= 1.0):
        raise RecordError(f"threshold must be within [0,1], got {threshold}")
    stats = probability_stats(record, statistic=statistic)
    by_id = {r.case_id: r for r in record.results}
    covered = [
        c for c in stats["cases"]
        if c["score"] is not None and c["score"] >= float(threshold)
        and by_id[c["case_id"]].outcome == OUTCOME_OK
    ]
    correct = sum(1 for c in covered if by_id[c["case_id"]].correct)
    return {
        "statistic": statistic,
        "threshold": float(threshold),
        "covered": len(covered),
        "total": len(record.results),
        "correct": correct,
        "accuracy": (correct / len(covered)) if covered else None,
    }


def route_model_check(record: Record, route_key: str) -> None:
    """Raise if a record's route/model does not match the requested route."""
    prof = get_route(route_key)
    if record.route != route_key:
        raise RecordError(f"record route {record.route!r} does not match requested {route_key!r}")
    if record.native_model and record.native_model != prof.native_model:
        raise RecordError(
            f"record model {record.native_model!r} does not match route {route_key!r} "
            f"expected {prof.native_model!r}"
        )
