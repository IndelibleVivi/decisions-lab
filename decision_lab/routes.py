"""Provider route contracts and normalization.

Two native routes are supported, each with its OWN request/response
shape. We do NOT invent a uniform provider-confidence formula; each route
keeps its native probability/confidence semantics, raw response and typed
outcome.

Documentation provenance
------------------------
The encoded field shapes below were verified against the official
documentation on 2026-10-09 by the project coordinator, who inspected:

* TypeSafe: https://docs.typesafe.ai/api and
  https://docs.typesafe.ai/primitives/choice
* OpenAI:   https://developers.openai.com/api/docs/guides/decisions

This is *documentation* evidence, not live evidence. No request was made
to either provider in this build. ``protocol_profiles`` reports
``docs_verified_at=2026-10-09`` and ``live_verified=false``. Any future
doc drift is expected to surface as a strict validation error during
normalization, never as a silent misparse.

Request invariants
------------------
Both native requests carry ONLY model-visible task input plus the option
list and its descriptions. There is no top-level correlation id in either
documented request: operational ids stay LOCAL. Labels (``acceptable``,
``rationale``, ``split``, ``source_group``, ``id``) never leave the
process - this is enforced structurally by ``assert_request_is_clean``.

Response semantics (kept distinct, never merged)
------------------------------------------------
* ``ok``      - a normal typed choice among the offered options.
* ``unknown`` - the model explicitly selected the ordinary ``unknown``
  option. This is a positive answer, NOT an API refusal and NOT a
  malformed response. ``needs_more_context`` remains a separate positive
  task action.
* ``refusal`` - a documented provider refusal answer (OpenAI only; the
  TypeSafe docs do not document a refusal field).
* ``error``   - missing/malformed/foreign response, HTTP or transport
  failure. A missing choice is a malformed response, never ``unknown``.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

from .cases import ALLOWED_ACTIONS, Case

#: Action the model may return as an ordinary explicit "no offered action
#: fits" option. Semantically DISTINCT from ``needs_more_context`` (a
#: positive task action), from an API refusal and from an error.
UNKNOWN_ACTION = "unknown"

#: The full option set offered to a provider: the four task actions plus an
#: ordinary fifth ``unknown`` option.
OFFERED_OPTIONS: tuple[str, ...] = (*ALLOWED_ACTIONS, UNKNOWN_ACTION)

#: Per-option descriptions supplied in the request. These describe what
#: each option MEANS (the task rubric), which is a legitimate part of the
#: question - not a label for the case. ``unknown`` is included as an
#: ordinary option, with no invented "abstain" flag.
OPTION_DESCRIPTIONS: dict[str, str] = {
    "inspect_source": (
        "Go to the source that the document explicitly points at (a diff, "
        "commit, upstream page or changelog) and check the original facts there."
    ),
    "compare_contract": (
        "Compare the change against the caller/interface contract to decide "
        "whether a signature, field, meaning or compatibility actually changed."
    ),
    "read_in_context": (
        "Read the change together with the current caller or runtime context "
        "to decide whether it truly applies here."
    ),
    "needs_more_context": (
        "The supplied input is missing or contains placeholders, so no sound "
        "judgement is possible until more context is supplied."
    ),
    "unknown": (
        "None of the offered next-reading/checking actions fits the supplied "
        "input. Choose this when no offered action is appropriate; do not "
        "guess."
    ),
}

#: Typed outcome kinds. ``ok`` and ``unknown`` are model answers; everything
#: else is a non-choice that must be recorded distinctly.
OUTCOME_OK = "ok"
OUTCOME_UNKNOWN = "unknown"          # explicit unknown option returned by the model
OUTCOME_REFUSAL = "refusal"          # provider refused to answer
OUTCOME_ERROR = "error"              # transport/HTTP/parse failure (not a model judgment)

#: Documented normalization tolerance: probabilities should sum to ~1.
PROBABILITY_SUM_TOLERANCE = 1e-6
#: Tolerance for the "selected choice matches argmax" check (allows ties).
ARGMAX_TOLERANCE = 1e-9


@dataclass
class NormalizedResponse:
    """Route-agnostic but semantically faithful normalization result."""

    outcome: str
    action: str | None
    probabilities: dict[str, float] | None
    model: str | None
    confidence: float | None = None
    refusal_reason: str | None = None
    error_kind: str | None = None
    error_detail: str | None = None
    raw: Any = None

    @property
    def is_normal_choice(self) -> bool:
        return self.outcome in (OUTCOME_OK, OUTCOME_UNKNOWN)


def _short(payload: Any) -> str:
    try:
        s = json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        s = repr(payload)
    return s[:200]


def _is_finite_number(value: Any) -> bool:
    """True only for a real, finite int/float (never bool, NaN or Inf)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


def _validate_probabilities(probs: Any, *, where: str) -> dict[str, float]:
    """Validate a native ``{option_id: probability}`` mapping.

    Rejects: empty maps, non-string keys, non-finite/boolean values and
    values outside ``[0, 1]``, plus a total that is not within the
    documented tolerance of 1. Known-option membership is checked by the
    caller via ``_check_known_options``.
    """
    if not isinstance(probs, dict) or not probs:
        raise ValueError(f"{where}: probabilities must be a non-empty object")
    out: dict[str, float] = {}
    for k, v in probs.items():
        if not isinstance(k, str):
            raise ValueError(f"{where}: probability keys must be strings")
        if not _is_finite_number(v):
            raise ValueError(f"{where}: probability for {k!r} must be a finite number")
        fv = float(v)
        if not (0.0 <= fv <= 1.0):
            raise ValueError(f"{where}: probability for {k!r} out of [0,1]: {fv}")
        out[k] = fv
    total = sum(out.values())
    if abs(total - 1.0) > PROBABILITY_SUM_TOLERANCE:
        raise ValueError(
            f"{where}: probabilities sum to {total!r}, not within "
            f"{PROBABILITY_SUM_TOLERANCE} of 1"
        )
    return out


def _check_known_options(probs: dict[str, float], *, where: str) -> None:
    extras = [k for k in probs if k not in OFFERED_OPTIONS]
    if extras:
        raise ValueError(f"{where}: foreign option keys {sorted(extras)}")
    missing = [k for k in OFFERED_OPTIONS if k not in probs]
    if missing:
        raise ValueError(f"{where}: missing option keys {sorted(missing)}")


def _check_selected_is_argmax(probs: dict[str, float], choice: str, *, where: str) -> None:
    top = max(probs.values())
    if probs.get(choice, -1.0) < top - ARGMAX_TOLERANCE:
        raise ValueError(
            f"{where}: selected choice {choice!r} is not an argmax of the "
            "returned distribution"
        )


class RouteProfile:
    """A native provider protocol profile. One per real documented contract."""

    key: str = ""
    label: str = ""
    endpoint: str = ""
    provider: str = ""
    native_model: str = ""
    docs_url: str = ""
    #: Dotted path to the answer's native per-option probabilities (metadata).
    probability_field: str = ""
    #: Dotted path to the answer's native selected-option id (metadata).
    choice_field: str = ""
    #: Dotted path to the answer's separate native confidence (metadata).
    confidence_field: str = ""
    notes: str = ""

    def request_body(self, case: Case) -> dict[str, Any]:
        """Build the native request body. Only ``case.model_input()`` is visible."""
        raise NotImplementedError

    def normalize(self, http_status: int, payload: Any) -> NormalizedResponse:
        raise NotImplementedError


def _request_state(case: Case) -> dict[str, str]:
    """The model-visible task input as a plain mapping.

    No label field is reachable: ``Case.model_input`` is the single choke
    point and returns only document/question/claim/source_ref.
    """
    return case.model_input()


def _choice_criteria() -> dict[str, str]:
    return {opt: OPTION_DESCRIPTIONS[opt] for opt in OFFERED_OPTIONS}


class JevProfile(RouteProfile):
    """TypeSafe native System One route (pinned model ``jev-1.13.0``)."""

    key = "jev"
    label = "TypeSafe native Jev"
    endpoint = "https://api.typesafe.ai/v1/systemone"
    provider = "typesafe"
    native_model = "jev-1.13.0"
    docs_url = "https://docs.typesafe.ai/api"
    probability_field = "answers.next_action.probabilities"
    choice_field = "answers.next_action.choice"
    confidence_field = "answers.next_action.confidence"
    notes = (
        "POST /v1/systemone with {model, state, questions}. No top-level "
        "request id. TypeSafe documents no refusal field: unsupported shapes "
        "are errors."
    )

    def request_body(self, case: Case) -> dict[str, Any]:
        state = _request_state(case)
        return {
            "model": self.native_model,
            "state": {
                "document": state["document"],
                "claim": state["claim"],
                "question": state["question"],
                "source_ref": state["source_ref"],
            },
            "questions": {
                "next_action": {
                    "type": "choice",
                    "instructions": state["question"],
                    "criteria": _choice_criteria(),
                }
            },
        }

    def normalize(self, http_status: int, payload: Any) -> NormalizedResponse:
        if http_status != 200:
            return NormalizedResponse(
                outcome=OUTCOME_ERROR, action=None, probabilities=None, model=None,
                error_kind=f"http_{http_status}", error_detail=_short(payload),
                raw=payload,
            )
        if not isinstance(payload, dict):
            return NormalizedResponse(
                outcome=OUTCOME_ERROR, action=None, probabilities=None, model=None,
                error_kind="parse", error_detail="response is not a JSON object",
                raw=payload,
            )
        model = payload.get("model")
        if not isinstance(model, str) or not model:
            model = None
        # No documented refusal field for TypeSafe: do not invent one.
        answers = payload.get("answers")
        if not isinstance(answers, dict) or set(answers) != {"next_action"}:
            return NormalizedResponse(
                outcome=OUTCOME_ERROR, action=None, probabilities=None, model=model,
                error_kind="parse", error_detail="answers must contain only 'next_action'", raw=payload,
            )
        answer = answers.get("next_action")
        if not isinstance(answer, dict):
            return NormalizedResponse(
                outcome=OUTCOME_ERROR, action=None, probabilities=None, model=model,
                error_kind="parse",
                error_detail="answers has no 'next_action' entry", raw=payload,
            )
        if answer.get("type") != "choice":
            return NormalizedResponse(
                outcome=OUTCOME_ERROR, action=None, probabilities=None, model=model,
                error_kind="parse",
                error_detail=f"next_action.type must be 'choice', got {answer.get('type')!r}",
                raw=payload,
            )
        try:
            probs = _validate_probabilities(
                answer.get("probabilities"),
                where="jev.answers.next_action.probabilities",
            )
            _check_known_options(probs, where="jev.answers.next_action.probabilities")
        except ValueError as exc:
            return NormalizedResponse(
                outcome=OUTCOME_ERROR, action=None, probabilities=None, model=model,
                error_kind="parse", error_detail=str(exc), raw=payload,
            )
        choice = answer.get("choice")
        if not isinstance(choice, str) or choice not in OFFERED_OPTIONS:
            # A missing/foreign choice is malformed, never 'unknown'.
            return NormalizedResponse(
                outcome=OUTCOME_ERROR, action=None, probabilities=probs, model=model,
                error_kind="parse", error_detail=f"invalid choice value {choice!r}",
                raw=payload,
            )
        try:
            _check_selected_is_argmax(probs, choice, where="jev.answers.next_action")
        except ValueError as exc:
            return NormalizedResponse(
                outcome=OUTCOME_ERROR, action=None, probabilities=probs, model=model,
                error_kind="parse", error_detail=str(exc), raw=payload,
            )
        confidence = answer.get("confidence")
        if not _is_finite_number(confidence) or not 0.0 <= confidence <= 1.0:
            return NormalizedResponse(
                outcome=OUTCOME_ERROR, action=None, probabilities=probs, model=model,
                error_kind="parse",
                error_detail="next_action.confidence must be a finite number in [0,1]",
                raw=payload,
            )
        outcome = OUTCOME_UNKNOWN if choice == UNKNOWN_ACTION else OUTCOME_OK
        return NormalizedResponse(
            outcome=outcome, action=choice, probabilities=probs, model=model,
            confidence=float(confidence), raw=payload,
        )


class DecisionsProfile(RouteProfile):
    """OpenAI native Decisions route (model ``gpt-6-luna``)."""

    key = "decisions"
    label = "OpenAI native Decisions"
    endpoint = "https://api.openai.com/v1/decisions"
    provider = "openai"
    native_model = "gpt-6-luna"
    docs_url = "https://developers.openai.com/api/docs/guides/decisions"
    probability_field = "answers[].probabilities[].probability"
    choice_field = "answers[].choice"
    confidence_field = "answers[].confidence"
    notes = (
        "POST /v1/decisions with {model, input, questions:[...]}. No decision "
        "object, metadata or allow_unknown flag. Refusal is an answer with "
        "type='refusal', kept distinct from a choice answer."
    )

    def request_body(self, case: Case) -> dict[str, Any]:
        state = _request_state(case)
        return {
            "model": self.native_model,
            "input": json.dumps(state, ensure_ascii=False, sort_keys=True),
            "questions": [
                {
                    "type": "choice",
                    "name": "next_action",
                    "instructions": state["question"],
                    "choices": [
                        {"value": opt, "description": OPTION_DESCRIPTIONS[opt]}
                        for opt in OFFERED_OPTIONS
                    ],
                }
            ],
        }

    def normalize(self, http_status: int, payload: Any) -> NormalizedResponse:
        if http_status != 200:
            return NormalizedResponse(
                outcome=OUTCOME_ERROR, action=None, probabilities=None, model=None,
                error_kind=f"http_{http_status}", error_detail=_short(payload),
                raw=payload,
            )
        if not isinstance(payload, dict):
            return NormalizedResponse(
                outcome=OUTCOME_ERROR, action=None, probabilities=None, model=None,
                error_kind="parse", error_detail="response is not a JSON object",
                raw=payload,
            )
        model = payload.get("model")
        if not isinstance(model, str) or not model:
            model = None
        answers = payload.get("answers")
        if not isinstance(answers, list) or not answers:
            return NormalizedResponse(
                outcome=OUTCOME_ERROR, action=None, probabilities=None, model=model,
                error_kind="parse", error_detail="missing 'answers' array", raw=payload,
            )
        matches = [
            a for a in answers
            if isinstance(a, dict) and a.get("name") == "next_action"
        ]
        if len(answers) != 1 or len(matches) != 1:
            return NormalizedResponse(
                outcome=OUTCOME_ERROR, action=None, probabilities=None, model=model,
                error_kind="parse",
                error_detail="expected exactly one answer named 'next_action'", raw=payload,
            )
        answer = matches[0]
        atype = answer.get("type")
        if atype == "refusal":
            return NormalizedResponse(
                outcome=OUTCOME_REFUSAL, action=None, probabilities=None, model=model,
                refusal_reason=str(answer.get("refusal") or "refusal"), raw=payload,
            )
        if atype != "choice":
            return NormalizedResponse(
                outcome=OUTCOME_ERROR, action=None, probabilities=None, model=model,
                error_kind="parse",
                error_detail=(
                    f"next_action.type must be 'choice' or 'refusal', got {atype!r}"
                ),
                raw=payload,
            )
        raw_probs = answer.get("probabilities")
        if not isinstance(raw_probs, list) or not raw_probs:
            return NormalizedResponse(
                outcome=OUTCOME_ERROR, action=None, probabilities=None, model=model,
                error_kind="parse",
                error_detail="choice answer must expose a non-empty probabilities array",
                raw=payload,
            )
        probs: dict[str, float] = {}
        for entry in raw_probs:
            if not isinstance(entry, dict):
                return NormalizedResponse(
                    outcome=OUTCOME_ERROR, action=None, probabilities=None, model=model,
                    error_kind="parse",
                    error_detail="probabilities entries must be objects", raw=payload,
                )
            value = entry.get("value")
            if not isinstance(value, str):
                return NormalizedResponse(
                    outcome=OUTCOME_ERROR, action=None, probabilities=None, model=model,
                    error_kind="parse",
                    error_detail="probability 'value' must be a string", raw=payload,
                )
            if value in probs:
                return NormalizedResponse(
                    outcome=OUTCOME_ERROR, action=None, probabilities=None, model=model,
                    error_kind="parse",
                    error_detail=f"duplicate probability value {value!r}", raw=payload,
                )
            prob = entry.get("probability")
            if not _is_finite_number(prob):
                return NormalizedResponse(
                    outcome=OUTCOME_ERROR, action=None, probabilities=None, model=model,
                    error_kind="parse",
                    error_detail=f"probability for {value!r} must be a finite number",
                    raw=payload,
                )
            fv = float(prob)
            if not (0.0 <= fv <= 1.0):
                return NormalizedResponse(
                    outcome=OUTCOME_ERROR, action=None, probabilities=None, model=model,
                    error_kind="parse",
                    error_detail=f"probability for {value!r} out of [0,1]: {fv}",
                    raw=payload,
                )
            probs[value] = fv
        try:
            _check_known_options(
                probs, where="decisions.answers.next_action.probabilities"
            )
        except ValueError as exc:
            return NormalizedResponse(
                outcome=OUTCOME_ERROR, action=None, probabilities=None, model=model,
                error_kind="parse", error_detail=str(exc), raw=payload,
            )
        total = sum(probs.values())
        if abs(total - 1.0) > PROBABILITY_SUM_TOLERANCE:
            return NormalizedResponse(
                outcome=OUTCOME_ERROR, action=None, probabilities=None, model=model,
                error_kind="parse",
                error_detail=(
                    f"probabilities sum to {total!r}, not within "
                    f"{PROBABILITY_SUM_TOLERANCE} of 1"
                ),
                raw=payload,
            )
        choice = answer.get("choice")
        if not isinstance(choice, str) or choice not in OFFERED_OPTIONS:
            return NormalizedResponse(
                outcome=OUTCOME_ERROR, action=None, probabilities=probs, model=model,
                error_kind="parse", error_detail=f"invalid choice value {choice!r}",
                raw=payload,
            )
        try:
            _check_selected_is_argmax(
                probs, choice, where="decisions.answers.next_action"
            )
        except ValueError as exc:
            return NormalizedResponse(
                outcome=OUTCOME_ERROR, action=None, probabilities=probs, model=model,
                error_kind="parse", error_detail=str(exc), raw=payload,
            )
        confidence = answer.get("confidence")
        if not _is_finite_number(confidence) or not 0.0 <= confidence <= 1.0:
            return NormalizedResponse(
                outcome=OUTCOME_ERROR, action=None, probabilities=probs, model=model,
                error_kind="parse",
                error_detail="next_action.confidence must be a finite number in [0,1]",
                raw=payload,
            )
        outcome = OUTCOME_UNKNOWN if choice == UNKNOWN_ACTION else OUTCOME_OK
        return NormalizedResponse(
            outcome=outcome, action=choice, probabilities=probs, model=model,
            confidence=float(confidence), raw=payload,
        )


_ROUTES: dict[str, RouteProfile] = {
    "jev": JevProfile(),
    "decisions": DecisionsProfile(),
}

ROUTE_KEYS = tuple(_ROUTES)


def get_route(key: str) -> RouteProfile:
    if key not in _ROUTES:
        raise KeyError(f"unknown route {key!r}; choose from {ROUTE_KEYS}")
    return _ROUTES[key]


def all_routes() -> list[RouteProfile]:
    return [_ROUTES[k] for k in ROUTE_KEYS]


def protocol_profiles() -> dict[str, Any]:
    """Machine-readable provenance metadata about the encoded profiles."""
    return {
        "docs_verified_at": "2026-10-09",
        "live_verified": False,
        "verification_note": (
            "Field shapes were verified against the official docs listed per "
            "route on 2026-10-09. This is documentation evidence only: no live "
            "request was made, and live availability, quality and pricing are "
            "not asserted."
        ),
        "routes": {
            k: {
                "label": r.label,
                "docs_url": r.docs_url,
                "endpoint": r.endpoint,
                "native_model": r.native_model,
                "probability_field": r.probability_field,
                "choice_field": r.choice_field,
                "confidence_field": r.confidence_field,
            }
            for k, r in _ROUTES.items()
        },
    }


def build_request(route_key: str, case: Case) -> dict[str, Any]:
    """Build a native request body, enforcing the no-label-leak invariant."""
    route = get_route(route_key)
    body = route.request_body(case)
    assert_request_is_clean(body, case)
    return body


#: Fields that are editorial/label metadata and must never be transmitted.
_LABEL_KEYS = frozenset({"acceptable", "rationale", "split", "source_group", "id"})


def assert_request_is_clean(body: Any, case: Case) -> None:
    """Enforce the structural no-label-leak invariant.

    The check is STRUCTURAL rather than substring-based: it verifies that

    * no label field name appears as an object key anywhere, and
    * the model-visible text carries none of the recorded label *values*
      that are unique case identifiers (the acceptable list, the rationale
      text and the case id).

    It deliberately does NOT reject ordinary task text merely because a
    short ``source_group`` string happens to occur inside the document
    text: ``source_group``/``split`` are organisational names, not secret
    answers, and scanning for them as substrings would produce false
    positives on legitimate input. The ``acceptable`` list and
    ``rationale`` are the real label-bearing fields; they are checked by
    key and by value.
    """
    keys = _collect_keys(body)
    leaked_keys = keys & _LABEL_KEYS
    if leaked_keys:
        raise AssertionError(
            f"label leakage: label field(s) {sorted(leaked_keys)} present in request body"
        )
    blob = json.dumps(body, ensure_ascii=False, sort_keys=True)
    # The acceptable-answer list must never be transmitted, as a values list.
    acc_blob = json.dumps(list(case.acceptable), ensure_ascii=False)
    if acc_blob in blob:
        raise AssertionError("label leakage: acceptable answer list appears in request body")
    # Unique editorial rationale text must never appear verbatim.
    if case.rationale and case.rationale in blob:
        raise AssertionError("label leakage: rationale appears in request body")
    # The case id is an operational handle and must not be sent.
    if case.id in blob:
        raise AssertionError("label leakage: case id appears in request body")


def _collect_keys(node: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, str):
                out.add(k)
            out |= _collect_keys(v)
    elif isinstance(node, list):
        for v in node:
            out |= _collect_keys(v)
    return out
