"""Offline typed-values experiment support.

This module deliberately does not reuse the next-action Choice record. A
Clairic response is a mapping of typed field answers, not an action plus a
probability distribution. The retained record therefore has its own suite,
request, response and replay bindings.

No function here performs network I/O or reads credentials. Imported
responses are external artifacts; a successful import never means that this
project verified them against a live provider.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import statistics
import time
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

RECORD_VERSION = "decisions-lab.typed-values-record/1"
RESPONSE_INPUT_VERSION = "decisions-lab.typed-values-responses/1"
DEFAULT_SUITE = "experiments/typed-values/examples.json"

PROVENANCE_BASELINE = "baseline"
PROVENANCE_DEMO = "demo"
PROVENANCE_IMPORT = "import"
PROVENANCES = {PROVENANCE_BASELINE, PROVENANCE_DEMO, PROVENANCE_IMPORT}

OUTCOME_OK = "ok"
OUTCOME_UNKNOWN = "unknown"
OUTCOME_REFUSAL = "refusal"
OUTCOME_ERROR = "error"
OUTCOMES = {OUTCOME_OK, OUTCOME_UNKNOWN, OUTCOME_REFUSAL, OUTCOME_ERROR}

EXPECTED_EXPERIMENTS = (
    "source-null-identity",
    "extract-compute-decide",
    "estimate-intervals",
)
EXPECTED_CASE_COUNT = 7
ALLOWED_FIELD_TYPES = {
    "text",
    "number",
    "date",
    "time",
    "datetime",
    "duration",
    "list",
    "estimate",
    "forecast",
}
ALLOWED_OPTIONS = {"return_state_text", "include_quantiles"}
DOWNSTREAM_ACTIONS = (
    "suggest_continue",
    "inspect_dispute",
    "needs_more_context",
    "unknown",
)
DOWNSTREAM_PATHS = ("direct", "extracted_only", "source_linked")
ALLOWED_FIELD_KEYS = {
    "type",
    "instructions",
    "decimals",
    "unit",
    "min",
    "max",
    "step",
    "items",
    "horizon",
}
ALLOWED_REQUEST_KEYS = {"model", "state", "fields", "options", "reference_date"}
ALLOWED_SPAN_UNITS = {"utf8", "codepoint", "utf16"}
ALLOWED_SPAN_ENDS = {"inclusive", "exclusive"}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MISSING = object()


class TypedValuesError(ValueError):
    """A user-readable typed-values contract or replay failure."""


def _sha(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()[:32]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _strict_json(path: str | Path) -> Any:
    """Read JSON while rejecting duplicate object keys."""

    p = Path(path)
    if not p.is_file():
        raise TypedValuesError(f"JSON file not found: {p}")

    def pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise TypedValuesError(f"{p}: duplicate JSON key {key!r}")
            out[key] = value
        return out

    def reject_constant(value: str) -> Any:
        raise TypedValuesError(f"{p}: non-finite JSON constant {value!r} is not allowed")

    def finite_float(value: str) -> float:
        number = float(value)
        _require(math.isfinite(number), f"{p}: JSON numbers must be finite")
        return number

    try:
        return json.loads(
            p.read_text(encoding="utf-8"),
            object_pairs_hook=pairs_hook,
            parse_constant=reject_constant,
            parse_float=finite_float,
        )
    except json.JSONDecodeError as exc:
        raise TypedValuesError(f"{p}: invalid JSON: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise TypedValuesError(f"{p}: JSON must be UTF-8: {exc}") from exc
    except ValueError as exc:
        raise TypedValuesError(f"{p}: invalid JSON value: {exc}") from exc


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TypedValuesError(message)


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False

def _describe_non_json(value: Any, *, depth: int = 0) -> Any:
    if depth > 6:
        return "<max-depth>"
    if isinstance(value, dict):
        return {
            str(key): _describe_non_json(item, depth=depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_describe_non_json(item, depth=depth + 1) for item in value[:20]]
    if isinstance(value, float) and not math.isfinite(value):
        return "<non-finite-float>"
    if isinstance(value, int) and not isinstance(value, bool):
        return value if value.bit_length() <= 256 else f"<integer:{value.bit_length()} bits>"
    return value


@dataclass
class TypedCase:
    experiment_id: str
    case_id: str
    source_group: str
    request: dict[str, Any]
    editorial_oracle: dict[str, Any]
    raw: dict[str, Any]

    @property
    def fields(self) -> dict[str, Any]:
        return self.request["fields"]

    @property
    def state(self) -> str:
        return self.request["state"]


@dataclass
class TypedSuite:
    source_path: Path
    raw: dict[str, Any]
    experiments: list[dict[str, Any]]
    cases: list[TypedCase] = field(default_factory=list)

    def by_id(self) -> dict[str, TypedCase]:
        return {case.case_id: case for case in self.cases}

    def experiment(self, experiment_id: str) -> dict[str, Any]:
        for experiment in self.experiments:
            if experiment.get("id") == experiment_id:
                return experiment
        raise TypedValuesError(f"unknown experiment id {experiment_id!r}")

    def digest(self) -> str:
        return _sha(self.raw)


def _validate_span_convention(value: Any, *, where: str) -> dict[str, str] | None:
    if value is None:
        return None
    _require(isinstance(value, dict), f"{where}: span_convention must be an object or null")
    unit = value.get("unit")
    end = value.get("end")
    _require(
        unit in ALLOWED_SPAN_UNITS,
        f"{where}: span unit must be one of {sorted(ALLOWED_SPAN_UNITS)}",
    )
    _require(
        end in ALLOWED_SPAN_ENDS,
        f"{where}: span end must be one of {sorted(ALLOWED_SPAN_ENDS)}",
    )
    extras = set(value) - {"unit", "end"}
    _require(not extras, f"{where}: unknown span_convention keys {sorted(extras)}")
    return {"unit": unit, "end": end}


def load_suite(path: str | Path = DEFAULT_SUITE) -> TypedSuite:
    """Load and validate the authored typed-values suite."""

    p = Path(path)
    data = _strict_json(p)
    where = str(p)
    _require(isinstance(data, dict), f"{where}: suite must be a JSON object")
    _require(
        data.get("schema") == "decisions-lab.typed-values-examples/1",
        f"{where}: unsupported or missing schema",
    )
    experiments = data.get("experiments")
    _require(isinstance(experiments, list), f"{where}: experiments must be an array")

    suite = TypedSuite(source_path=p, raw=data, experiments=experiments)
    seen_ids: set[str] = set()
    seen_groups: dict[str, str] = {}
    for exp_index, experiment in enumerate(experiments):
        ew = f"{where}.experiments[{exp_index}]"
        _require(isinstance(experiment, dict), f"{ew}: experiment must be an object")
        experiment_id = experiment.get("id")
        _require(
            isinstance(experiment_id, str) and experiment_id.strip(),
            f"{ew}: id must be a non-empty string",
        )
        cases = experiment.get("cases")
        _require(isinstance(cases, list) and cases, f"{ew}: cases must be a non-empty array")
        for case_index, raw_case in enumerate(cases):
            cw = f"{ew}.cases[{case_index}]"
            _require(isinstance(raw_case, dict), f"{cw}: case must be an object")
            case_id = raw_case.get("id")
            source_group = raw_case.get("source_group")
            _require(
                isinstance(case_id, str) and case_id.strip(),
                f"{cw}: id must be a non-empty string",
            )
            _require(
                isinstance(source_group, str) and source_group.strip(),
                f"{cw}: source_group must be a non-empty string",
            )
            _require(case_id not in seen_ids, f"{cw}: duplicate case id {case_id!r}")
            previous_exp = seen_groups.get(source_group)
            _require(
                previous_exp in (None, experiment_id),
                f"{cw}: source_group {source_group!r} spans experiments",
            )
            seen_ids.add(case_id)
            seen_groups[source_group] = experiment_id

            request = raw_case.get("request")
            _require(isinstance(request, dict), f"{cw}: request must be an object")
            extras = set(request) - ALLOWED_REQUEST_KEYS
            _require(not extras, f"{cw}.request: unknown keys {sorted(extras)}")
            _require(
                request.get("model") == "clairic",
                f"{cw}.request: model must be 'clairic'",
            )
            state = request.get("state")
            _require(
                isinstance(state, str) and bool(state.strip()),
                f"{cw}.request: state must be non-empty text",
            )
            request_fields = request.get("fields")
            _require(
                isinstance(request_fields, dict) and request_fields,
                f"{cw}.request: fields must be a non-empty object",
            )
            for field_name, config in request_fields.items():
                fw = f"{cw}.request.fields.{field_name}"
                _require(
                    isinstance(field_name, str) and field_name.strip(),
                    f"{cw}: field names must be non-empty strings",
                )
                _require(isinstance(config, dict), f"{fw}: field config must be an object")
                field_type = config.get("type")
                _require(
                    field_type in ALLOWED_FIELD_TYPES,
                    f"{fw}: unsupported field type {field_type!r}",
                )
                field_extras = set(config) - ALLOWED_FIELD_KEYS
                _require(
                    not field_extras,
                    f"{fw}: unknown config keys {sorted(field_extras)}",
                )
                instructions = config.get("instructions")
                _require(
                    isinstance(instructions, str) and bool(instructions.strip()),
                    f"{fw}: instructions must be non-empty text",
                )
                if field_type == "estimate":
                    for bound in ("min", "max"):
                        if bound in config:
                            _require(
                                _finite_number(config[bound]),
                                f"{fw}: {bound} must be a finite number",
                            )
                    if "min" in config and "max" in config:
                        _require(
                            float(config["min"]) <= float(config["max"]),
                            f"{fw}: min must not exceed max",
                        )
                    if "step" in config:
                        _require(
                            _finite_number(config["step"]) and config["step"] > 0,
                            f"{fw}: step must be a positive finite number",
                        )
            options = request.get("options", {})
            _require(isinstance(options, dict), f"{cw}.request: options must be an object")
            option_extras = set(options) - ALLOWED_OPTIONS
            _require(
                not option_extras,
                f"{cw}.request: unknown options {sorted(option_extras)}",
            )
            for option_name, option_value in options.items():
                _require(
                    isinstance(option_value, bool),
                    f"{cw}.request.options.{option_name}: must be a boolean",
                )

            oracle = raw_case.get("editorial_oracle")
            _require(isinstance(oracle, dict), f"{cw}: editorial_oracle must be an object")
            if experiment_id in {"source-null-identity", "extract-compute-decide"}:
                _require(
                    isinstance(oracle.get("values"), dict),
                    f"{cw}.editorial_oracle: values must be an object",
                )
            if experiment_id == "estimate-intervals":
                _require(
                    isinstance(oracle.get("elapsed_calendar_days"), int)
                    and not isinstance(oracle.get("elapsed_calendar_days"), bool),
                    f"{cw}.editorial_oracle: elapsed_calendar_days must be an integer",
                )

            suite.cases.append(
                TypedCase(
                    experiment_id=experiment_id,
                    case_id=case_id,
                    source_group=source_group,
                    request=request,
                    editorial_oracle=oracle,
                    raw=raw_case,
                )
            )

    experiment_ids = [experiment.get("id") for experiment in experiments]
    _require(
        len(experiment_ids) == len(set(experiment_ids)),
        f"{where}: duplicate experiment id",
    )
    actual_experiments = tuple(experiment_ids)
    _require(
        actual_experiments == EXPECTED_EXPERIMENTS,
        f"{where}: expected experiments {EXPECTED_EXPERIMENTS}, got {actual_experiments}",
    )
    _require(
        len(suite.cases) == EXPECTED_CASE_COUNT,
        f"{where}: expected {EXPECTED_CASE_COUNT} cases, got {len(suite.cases)}",
    )
    return suite


def case_digest(case: TypedCase) -> str:
    return _sha({"experiment_id": case.experiment_id, "case": case.raw})


def request_digest(request: dict[str, Any]) -> str:
    return _sha(request)


def select_cases(
    suite: TypedSuite,
    *,
    experiment_id: str | None = None,
    case_ids: list[str] | None = None,
) -> list[TypedCase]:
    if experiment_id is not None:
        suite.experiment(experiment_id)
    cases = [
        case
        for case in suite.cases
        if experiment_id is None or case.experiment_id == experiment_id
    ]
    if case_ids:
        _require(
            len(case_ids) == len(set(case_ids)),
            "duplicate --case-id values are not allowed",
        )
        by_id = suite.by_id()
        missing = [case_id for case_id in case_ids if case_id not in by_id]
        _require(not missing, f"unknown case ids: {missing}")
        selected_ids = set(case_ids)
        cases = [case for case in cases if case.case_id in selected_ids]
        absent_from_filter = selected_ids - {case.case_id for case in cases}
        _require(
            not absent_from_filter,
            f"case ids outside selected experiment: {sorted(absent_from_filter)}",
        )
    return cases


def prepare_payload(suite: TypedSuite, cases: list[TypedCase]) -> dict[str, Any]:
    """Export only native request bodies and local case identity."""

    return {
        "suite": str(suite.source_path.resolve()),
        "suite_digest": suite.digest(),
        "request_contract": {
            "model_id": "@cf/cloudflare/clairic",
            "evidence": "fixed repository snapshot; live_verified=false",
        },
        "requests": [
            {
                "experiment_id": case.experiment_id,
                "case_id": case.case_id,
                "request": case.request,
            }
            for case in cases
        ],
    }


@dataclass
class ResponseEntry:
    experiment_id: str
    case_id: str
    raw: Any = None
    http_status: int | None = None
    outcome_hint: str = "native"
    error_detail: str | None = None
    value_source: str | None = None
    downstream_decisions: dict[str, Any] | None = None
    provenance_kind: str = "native_values"

    def resolved_value_source(self) -> str:
        if self.provenance_kind == "empirical_history_baseline":
            return "synthetic"
        if self.value_source is not None:
            return self.value_source
        return "native" if self.http_status is not None else "synthetic"


def load_response_file(
    path: str | Path,
) -> tuple[list[ResponseEntry], dict[str, str] | None]:
    p = Path(path)
    data = _strict_json(p)
    _require(isinstance(data, dict), f"{p}: response file must be a JSON object")
    _require(
        data.get("schema") == RESPONSE_INPUT_VERSION,
        f"{p}: unsupported or missing schema (expected {RESPONSE_INPUT_VERSION!r})",
    )
    provenance = data.get("provenance", PROVENANCE_IMPORT)
    _require(
        provenance == PROVENANCE_IMPORT,
        f"{p}: response file provenance must be 'import'",
    )
    span_convention = _validate_span_convention(
        data.get("span_convention"), where=f"{p}: span_convention"
    )
    raw_responses = data.get("responses")
    _require(isinstance(raw_responses, list), f"{p}: responses must be an array")
    entries: list[ResponseEntry] = []
    for index, raw_entry in enumerate(raw_responses):
        where = f"{p}: responses[{index}]"
        _require(isinstance(raw_entry, dict), f"{where}: entry must be an object")
        case_id = raw_entry.get("case_id")
        experiment_id = raw_entry.get("experiment_id")
        _require(
            isinstance(case_id, str) and case_id,
            f"{where}: case_id must be a non-empty string",
        )
        _require(
            isinstance(experiment_id, str) and experiment_id,
            f"{where}: experiment_id must be a non-empty string",
        )
        allowed = {
            "experiment_id",
            "case_id",
            "response",
            "http_status",
            "kind",
            "detail",
            "value_source",
            "downstream_decisions",
        }
        extras = set(raw_entry) - allowed
        _require(not extras, f"{where}: unknown keys {sorted(extras)}")
        kind = raw_entry.get("kind", "native")
        _require(
            kind in {"native", OUTCOME_UNKNOWN, OUTCOME_REFUSAL, OUTCOME_ERROR},
            f"{where}: kind must be native, unknown, refusal or error",
        )
        http_status = raw_entry.get("http_status")
        if http_status is not None:
            _require(
                isinstance(http_status, int) and not isinstance(http_status, bool),
                f"{where}: http_status must be an integer",
            )
        response = raw_entry.get("response")
        detail = raw_entry.get("detail")
        value_source = raw_entry.get("value_source")
        _require(
            value_source in (None, "native", "synthetic"),
            f"{where}: value_source must be native or synthetic",
        )
        downstream = raw_entry.get("downstream_decisions")
        if downstream is not None:
            _require(
                isinstance(downstream, dict),
                f"{where}: downstream_decisions must be an object",
            )
            extras_for_downstream = set(downstream) - set(DOWNSTREAM_PATHS)
            _require(
                not extras_for_downstream,
                f"{where}: unknown downstream paths {sorted(extras_for_downstream)}",
            )
            for path, action in downstream.items():
                _require(
                    action in DOWNSTREAM_ACTIONS,
                    f"{where}: downstream {path!r} has invalid action {action!r}",
                )
        if kind == "native":
            _require("response" in raw_entry, f"{where}: native import requires response")
            _require(
                value_source is not None,
                f"{where}: native import requires value_source='native' or 'synthetic'",
            )
        else:
            _require(
                isinstance(detail, str) and detail.strip(),
                f"{where}: {kind} import requires a readable detail",
            )
        entries.append(
            ResponseEntry(
                experiment_id=experiment_id,
                case_id=case_id,
                raw=response,
                http_status=http_status,
                outcome_hint=kind,
                error_detail=detail,
                value_source=(
                    value_source
                    if value_source is not None
                    else ("native" if kind == "native" else None)
                ),
                downstream_decisions=downstream,
            )
        )
    return entries, span_convention


def _response_envelope(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TypedValuesError("response must be a JSON object")
    forbidden_prefixes = ("source_", "diagnostic", "editorial_oracle", "rate_limit")
    leaked = [
        key
        for key in raw
        if isinstance(key, str) and key.casefold().startswith(forbidden_prefixes)
    ]
    if leaked:
        raise TypedValuesError(
            f"response is not a provider answer; contains local metadata {sorted(leaked)!r}"
        )
    if raw.get("success") is False or raw.get("errors"):
        raise TypedValuesError(f"provider envelope reports failure: {raw.get('errors')!r}")
    if "result" in raw:
        result = raw["result"]
        if not isinstance(result, dict):
            raise TypedValuesError("response.result must be an object")
        leaked = [
            key
            for key in result
            if isinstance(key, str) and key.casefold().startswith(forbidden_prefixes)
        ]
        if leaked:
            raise TypedValuesError(
                f"response.result contains local metadata {sorted(leaked)!r}"
            )
        if result.get("success") is False or result.get("errors"):
            raise TypedValuesError(
                f"response.result reports failure: {result.get('errors')!r}"
            )
        if "answers" in result:
            return result
    return raw

def _validate_native_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    required = {"model", "answers", "truncated", "usage"}
    missing = sorted(required - set(envelope))
    _require(not missing, f"native response is missing top-level field(s): {missing}")
    _require(
        isinstance(envelope["model"], str) and bool(envelope["model"].strip()),
        "native response.model must be a non-empty string",
    )
    _require(
        envelope["model"] == "clairic",
        f"native response.model must be 'clairic', got {envelope['model']!r}",
    )
    _require(
        isinstance(envelope["truncated"], bool),
        "native response.truncated must be a boolean",
    )
    usage = envelope["usage"]
    _require(isinstance(usage, dict), "native response.usage must be an object")
    for name in ("input_tokens", "output_tokens"):
        value = usage.get(name)
        _require(
            isinstance(value, int) and not isinstance(value, bool) and value >= 0,
            f"native response.usage.{name} must be a non-negative integer",
        )
    if "state_text" in envelope:
        _require(
            isinstance(envelope["state_text"], str),
            "native response.state_text must be a string",
        )
    return envelope




def _parse_date(value: Any, *, where: str) -> None:
    _require(
        isinstance(value, str) and bool(_DATE_RE.match(value)),
        f"{where}: date must use YYYY-MM-DD",
    )
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise TypedValuesError(f"{where}: invalid calendar date {value!r}") from exc


def _validate_metadata_shape(answer: dict[str, Any], *, where: str, value_source: str) -> None:
    # The fixed schema permits additional metadata and leaves quantiles' item
    # layout unspecified. Preserve it in raw; score only established fields.
    for name in ("p_null", "confidence", "p_below", "p_above"):
        candidate = answer.get(name, _MISSING)
        if candidate is not _MISSING:
            _require(
                _finite_number(candidate) and 0 <= float(candidate) <= 1,
                f"{where}: {name} must be a finite number in [0,1]",
            )
    for name in ("value", "guess", "mean", "median", "p10", "p90"):
        candidate = answer.get(name, _MISSING)
        if candidate is not _MISSING and candidate is not None:
            _require(
                not isinstance(candidate, bool),
                f"{where}: {name} must not be boolean",
            )
    for name in ("span", "spans", "quantiles", "steps"):
        candidate = answer.get(name, _MISSING)
        if candidate is not _MISSING:
            _require(
                isinstance(candidate, list),
                f"{where}: {name} must be an array",
            )
    for span in ([answer["span"]] if "span" in answer else []) + answer.get("spans", []):
        _require(
            isinstance(span, list) and len(span) == 2
            and all(isinstance(item, int) and not isinstance(item, bool) for item in span),
            f"{where}: spans must contain two-integer arrays [start, end]",
        )
    if value_source == "native":
        for name in ("guess", "mean", "median", "p10", "p90"):
            if name in answer and answer[name] is not None and not isinstance(
                answer[name], (str, int, float)
            ):
                raise TypedValuesError(f"{where}: native {name} has unsupported shape")


def _validate_field_value(
    field_name: str,
    config: dict[str, Any],
    value: Any,
    *,
    source: str,
) -> None:
    if value is None:
        return
    field_type = config["type"]
    where = f"field {field_name!r}"
    if field_type == "text":
        _require(isinstance(value, str), f"{where}: expected text or null")
    elif field_type in {"number", "duration"}:
        _require(_finite_number(value), f"{where}: expected finite number or null")
        decimals = config.get("decimals")
        if source == "native" and decimals is None:
            raise TypedValuesError(f"{where}: native number requests require decimals")
        if decimals is not None:
            _require(
                isinstance(decimals, int) and not isinstance(decimals, bool) and decimals >= 0,
                f"{where}: request decimals must be a non-negative integer",
            )
            exponent = Decimal(str(value)).normalize().as_tuple().exponent
            _require(
                exponent >= -decimals,
                f"{where}: value has more than {decimals} decimal places",
            )
    elif field_type == "date":
        _parse_date(value, where=where)
    elif field_type in {"time", "datetime"}:
        raise TypedValuesError(f"{where}: typed-values CLI does not support {field_type}")
    elif field_type == "estimate":
        _require(_finite_number(value), f"{where}: expected finite estimate value or null")
        if source == "native":
            for key in ("min", "max", "step"):
                if key not in config or not _finite_number(config[key]):
                    raise TypedValuesError(
                        f"{where}: native estimate requires finite {key}"
                    )
            _require(
                config["min"] <= value <= config["max"],
                f"{where}: estimate value is outside requested min/max",
            )
            multiple = (
                Decimal(str(value)) - Decimal(str(config["min"]))
            ) / Decimal(str(config["step"]))
            if multiple != multiple.to_integral_value():
                raise TypedValuesError(
                    f"{where}: estimate value is not on the requested grid"
                )
    else:
        raise TypedValuesError(f"{where}: typed-values CLI does not support {field_type}")


def _parse_answers(
    case: TypedCase,
    raw: Any,
    *,
    value_source: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    envelope = _response_envelope(raw)
    if value_source == "native":
        _validate_native_envelope(envelope)
    answers = envelope.get("answers")
    _require(isinstance(answers, dict), "response has no answers object")
    expected = set(case.fields)
    actual = set(answers)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    _require(not missing, f"response is missing field(s): {missing}")
    _require(not unknown, f"response has unknown field(s): {unknown}")
    parsed: dict[str, dict[str, Any]] = {}
    for name, config in case.fields.items():
        answer = answers[name]
        _require(isinstance(answer, dict), f"field {name!r}: answer must be an object")
        _require("value" in answer, f"field {name!r}: explicit value key is required")
        _require(
            answer.get("type") == config["type"],
            f"field {name!r}: response type {answer.get('type')!r} != "
            f"requested type {config['type']!r}",
        )
        _validate_metadata_shape(
            answer, where=f"field {name!r}", value_source=value_source
        )
        _validate_field_value(
            name, config, answer["value"], source=value_source
        )
        parsed[name] = dict(answer)
    return parsed, envelope


def _text_unit_offsets(text: str, unit: str) -> list[int]:
    offsets = [0]
    if unit == "codepoint":
        offsets.extend(range(1, len(text) + 1))
    elif unit == "utf8":
        for char in text:
            offsets.append(offsets[-1] + len(char.encode("utf-8")))
    elif unit == "utf16":
        for char in text:
            offsets.append(offsets[-1] + len(char.encode("utf-16-le")) // 2)
    else:  # guarded when loading
        raise AssertionError(unit)
    return offsets


def _substring_from_span(
    text: str,
    span: Any,
    convention: dict[str, str],
) -> str:
    _require(
        isinstance(span, list) and len(span) == 2,
        "native span must be a two-integer array [start, end]",
    )
    start, end = span
    _require(
        isinstance(start, int)
        and not isinstance(start, bool)
        and isinstance(end, int)
        and not isinstance(end, bool),
        "span start/end must be integers",
    )
    offsets = _text_unit_offsets(text, convention["unit"])
    total = offsets[-1]
    effective_end = end + 1 if convention["end"] == "inclusive" else end
    _require(
        0 <= start <= effective_end <= total,
        f"span [{start},{end}] is outside input bounds 0..{total}",
    )
    try:
        start_index = offsets.index(start)
        end_index = offsets.index(effective_end)
    except ValueError as exc:
        raise TypedValuesError(
            f"span [{start},{end}] splits a {convention['unit']} encoding unit"
        ) from exc
    return text[start_index:end_index]


def _state_text_relation(case: TypedCase, envelope: dict[str, Any]) -> dict[str, Any]:
    returned = envelope.get("state_text")
    truncated = envelope.get("truncated")
    if returned is None:
        return {
            "state_text_present": False,
            "state_text_matches_request": None,
            "truncated": truncated,
            "span_text_source": "request_state",
        }
    matches = returned == case.state
    return {
        "state_text_present": True,
        "state_text_matches_request": matches,
        "truncated": truncated,
        "span_text_source": "response_state_text",
        "state_text_length": len(returned),
    }


def _span_check(
    case: TypedCase,
    answers: dict[str, dict[str, Any]],
    envelope: dict[str, Any],
    span_convention: dict[str, str] | None,
    value_source: str,
) -> dict[str, dict[str, Any]]:
    relation = _state_text_relation(case, envelope)
    state_text = envelope.get("state_text")
    use_request_state = state_text is None
    location_text = case.state if use_request_state else state_text
    result: dict[str, dict[str, Any]] = {}
    for name, answer in answers.items():
        span = answer.get("span")
        if span is None:
            result[name] = {
                "status": "absent",
                "text_source": relation["span_text_source"],
                "candidate": None,
                "candidate_kind": None,
            }
            continue
        if span_convention is None:
            result[name] = {
                "status": "unverified_no_convention",
                "text_source": relation["span_text_source"],
                "candidate": None,
                "candidate_kind": None,
            }
            continue
        candidate = answer.get("value")
        candidate_kind = "value"
        if candidate is None:
            candidate = answer.get("guess")
            candidate_kind = "guess"
        _require(isinstance(candidate, str), f"field {name!r}: span requires a text candidate")
        if value_source == "native" and use_request_state:
            status = "unverified_no_state_text"
        else:
            substring = _substring_from_span(location_text, span, span_convention)
            matches = substring == candidate
            if not matches:
                status = "invalid"
            elif value_source == "native" and relation["state_text_matches_request"] is not True:
                status = "valid_in_returned_state_text"
            elif relation["truncated"] is True:
                status = "valid_in_truncated_state_text"
            else:
                status = "valid"
        result[name] = {
            "status": status,
            "text_source": relation["span_text_source"],
            "candidate": candidate,
            "candidate_kind": candidate_kind,
        }
    return result


def _target_scope(case: TypedCase) -> str:
    if case.experiment_id == "source-null-identity":
        current = case.state.find("当前订单")
        archived = case.state.find("归档订单")
        if current >= 0 and (archived < 0 or archived > current):
            return case.state[current : archived if archived >= 0 else len(case.state)]
    return case.state


def _same_field_value(left: Any, right: Any, field_type: str) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if field_type in {"number", "duration"}:
        if left is None or right is None:
            return left is right
        try:
            return Decimal(str(left)) == Decimal(str(right))
        except InvalidOperation:
            return False
    numeric_left = isinstance(left, (int, float)) and not isinstance(left, bool)
    numeric_right = isinstance(right, (int, float)) and not isinstance(right, bool)
    if numeric_left and isinstance(right, str):
        try:
            return Decimal(str(left)) == Decimal(right)
        except InvalidOperation:
            return False
    if numeric_right and isinstance(left, str):
        try:
            return Decimal(left) == Decimal(str(right))
        except InvalidOperation:
            return False
    if numeric_left and numeric_right:
        return Decimal(str(left)) == Decimal(str(right))
    return left == right


def _evaluate_source_fields(
    case: TypedCase,
    answers: dict[str, dict[str, Any]],
    envelope: dict[str, Any],
    span_convention: dict[str, str] | None,
    value_source: str,
) -> dict[str, Any]:
    oracle_values = case.editorial_oracle["values"]
    target_scope = _target_scope(case)
    spans = _span_check(
        case, answers, envelope, span_convention, value_source
    )
    fields: dict[str, Any] = {}
    for name, answer in answers.items():
        value = answer["value"]
        expected = oracle_values.get(name, _MISSING)
        exact = (
            expected is not _MISSING
            and _same_field_value(value, expected, case.fields[name]["type"])
        )
        text_in_source: bool | None = None
        in_target_scope: bool | None = None
        if isinstance(value, str) and value:
            text_in_source = value in case.state
            in_target_scope = value in target_scope
        relation_correct: bool | None = None
        if expected is not _MISSING:
            if value is None:
                relation_correct = expected is None
            elif isinstance(value, str) and value in case.state:
                relation_correct = bool(in_target_scope) and exact
            else:
                relation_correct = exact
        span = spans[name]
        fields[name] = {
            "value": value,
            "value_kind": "null" if value is None else case.fields[name]["type"],
            "present": True,
            "guess": answer.get("guess"),
            "confidence": answer.get("confidence"),
            "p_null": answer.get("p_null"),
            "type_format_valid": True,
            "exact_match": exact,
            "expected_null": expected is None,
            "text_match": text_in_source,
            "in_target_scope": in_target_scope,
            "entity_version_correct": relation_correct,
            "span_status": span["status"],
            "span_text_source": span["text_source"],
            "span_candidate": span["candidate"],
            "span_candidate_kind": span["candidate_kind"],
        }
    return {
        "kind": "source_field_evaluation",
        "fields": fields,
        "target_entity": case.editorial_oracle.get("target_entity"),
        "target_version": case.editorial_oracle.get("target_version"),
        **_state_text_relation(case, envelope),
        "span_convention": span_convention,
        "span_note": (
            "Provider offset units/endpoints remain unverified without an explicit "
            "import-time span_convention."
        ),
    }


def _as_decimal(value: Any, *, where: str) -> Decimal:
    _require(_finite_number(value), f"{where}: expected a finite JSON number")
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise TypedValuesError(f"{where}: cannot convert to Decimal") from exc


def _classify_status(text: str) -> str:
    status_clause = (
        text.split("验收状态：", 1)[-1]
        if "验收状态：" in text
        else text
    )
    if "无未解决争议" in status_clause:
        return "suggest_continue"
    if "未解决" in status_clause:
        return "inspect_dispute"
    if "无争议" in status_clause:
        return "suggest_continue"
    return "needs_more_context"

def _path_rule(path: str, path_input: dict[str, Any]) -> dict[str, Any]:
    rule_text = path_input["rules"]
    options = path_input["options"]
    if options != list(DOWNSTREAM_ACTIONS):
        raise TypedValuesError("downstream options do not match the fixed action contract")
    numeric_names = ("quantity", "unit_price", "shipping", "currency", "deterministic_total")
    amount_within_limit: bool | None = None
    threshold_checked = False
    if path == "direct":
        state = path_input.get("source_text")
        if not isinstance(state, str) or not state.strip():
            return {"action": "needs_more_context", "amount_within_limit": None}
        amount_match = re.search(r"数量\s*(\d+)\s*件", state)
        price_match = re.search(r"单价\s*([\d.]+)\s*CNY", state)
        shipping_match = re.search(r"运费\s*([\d.]+)\s*CNY", state)
        if not (amount_match and price_match and shipping_match):
            return {"action": "needs_more_context", "amount_within_limit": None}
        total = (
            Decimal(amount_match.group(1))
            * Decimal(price_match.group(1))
            + Decimal(shipping_match.group(1))
        )
        status = _classify_status(state)
        amount_within_limit = total <= Decimal("1200.00")
        threshold_checked = True
    else:
        if any(
            path_input.get(name) is None or path_input.get(name) == ""
            for name in numeric_names
        ):
            return {"action": "needs_more_context", "amount_within_limit": None}
        try:
            quantity = Decimal(str(path_input["quantity"]))
            unit_price = Decimal(str(path_input["unit_price"]))
            shipping = Decimal(str(path_input["shipping"]))
        except InvalidOperation:
            return {"action": "needs_more_context", "amount_within_limit": None}
        total = quantity * unit_price + shipping
        if str(total) != str(path_input["deterministic_total"]):
            return {"action": "needs_more_context", "amount_within_limit": None}
        amount_within_limit = total <= Decimal("1200.00")
        threshold_checked = True
        if path == "extracted_only":
            return {
                "action": "needs_more_context",
                "amount_within_limit": amount_within_limit,
            }
        evidence = path_input.get("source_passage")
        if evidence != path_input.get("status_evidence"):
            evidence = None
        status = (
            _classify_status(evidence)
            if isinstance(evidence, str)
            else "needs_more_context"
        )
    if "金额不超过 1200.00 CNY" not in rule_text:
        raise TypedValuesError("path rule does not contain the fixed amount threshold")
    if status == "inspect_dispute":
        return {
            "action": "inspect_dispute",
            "amount_within_limit": amount_within_limit,
        }
    if status == "needs_more_context":
        return {
            "action": "needs_more_context",
            "amount_within_limit": amount_within_limit,
        }
    if not amount_within_limit:
        # There is no budget-rejection action in this experiment. An amount
        # over the limit does not establish an unresolved delivery dispute.
        return {"action": "unknown", "amount_within_limit": False}
    if not threshold_checked or amount_within_limit is not True:
        raise AssertionError("amount threshold should be checked for a complete action")
    return {"action": status, "amount_within_limit": amount_within_limit}


def _evaluate_compute_paths(
    case: TypedCase,
    answers: dict[str, dict[str, Any]],
    *,
    downstream_decisions: dict[str, Any] | None,
) -> dict[str, Any]:
    values = {name: answer["value"] for name, answer in answers.items()}
    expected_values = case.editorial_oracle["values"]
    quantity_raw = values.get("quantity", _MISSING)
    price_raw = values.get("unit_price", _MISSING)
    shipping_raw = values.get("shipping", _MISSING)
    operands_available = all(
        value is not _MISSING and value is not None
        for value in (quantity_raw, price_raw, shipping_raw)
    )
    quantity = _as_decimal(quantity_raw, where="quantity") if quantity_raw is not None else None
    unit_price = _as_decimal(price_raw, where="unit_price") if price_raw is not None else None
    shipping = _as_decimal(shipping_raw, where="shipping") if shipping_raw is not None else None
    code_total = quantity * unit_price + shipping if operands_available else None
    expected_quantity = Decimal(str(expected_values["quantity"]))
    expected_price = Decimal(str(expected_values["unit_price"]))
    expected_shipping = Decimal(str(expected_values["shipping"]))
    expected_total = Decimal(str(case.editorial_oracle["deterministic_total_decimal"]))
    model_total = (
        _as_decimal(values["computed_total"], where="computed_total")
        if values.get("computed_total") is not None
        else None
    )
    status_value = values.get("status_evidence")
    status_text = status_value if isinstance(status_value, str) else None
    numbers_valid = (
        operands_available
        and quantity == expected_quantity
        and unit_price == expected_price
        and shipping == expected_shipping
    )
    expected_by_path = case.editorial_oracle["expected_decisions_by_input_path"]
    expected_decision = case.editorial_oracle["expected_decision"]
    status_scope = next(
        (line for line in case.state.splitlines() if line.startswith("版本 v2 的验收状态：")),
        "",
    )
    source_passage = (
        status_text if status_text and status_text in status_scope else None
    )

    base_input = {
        "question": "依照给定任务规则，建议下一步怎样处理采购单 PO-731？",
        "rules": case.state.split("\n", 1)[0],
        "options": [
            "suggest_continue",
            "inspect_dispute",
            "needs_more_context",
            "unknown",
        ],
    }
    extracted_input = {
        **base_input,
        "quantity": None if quantity is None else str(quantity),
        "unit_price": None if unit_price is None else str(unit_price),
        "shipping": None if shipping is None else str(shipping),
        "currency": "CNY",
        "deterministic_total": None if code_total is None else str(code_total),
    }
    path_inputs = {
        "direct": {**base_input, "source_text": case.state},
        "extracted_only": extracted_input,
        "source_linked": {
            **extracted_input,
            "source_group": case.source_group,
            "target_entity": case.editorial_oracle.get("target_entity"),
            "target_version": case.editorial_oracle.get("target_version"),
            "status_evidence": status_text,
            "source_passage": source_passage,
        },
    }

    rules = {
        path: _path_rule(path, path_input)
        for path, path_input in path_inputs.items()
    }
    imported_actions = downstream_decisions or {}

    paths: dict[str, Any] = {}
    for path, rule in rules.items():
        action = rule["action"]
        expected_for_path = rule["action"]
        imported = imported_actions.get(path)
        paths[path] = {
            "input": path_inputs[path],
            "rule_baseline_action": action,
            "imported_action": imported,
            "action": imported if imported is not None else action,
            "action_source": (
                "import" if imported is not None else "deterministic_path_baseline"
            ),
            "expected_under_input_contract": expected_for_path,
            "editorial_action_for_reference_projection": expected_by_path[path],
            "amount_within_limit": rule["amount_within_limit"],
            "honest_under_input": None,
            "baseline_under_input_matches": action == expected_for_path,
            "expected_full_task_action": expected_decision,
            "full_task_completed": None,
            "baseline_completes_full_task": action == expected_decision,
        }
        if imported is None:
            paths[path]["honest_under_input"] = action == expected_for_path
            paths[path]["full_task_completed"] = action == expected_decision
        else:
            paths[path]["honest_under_input"] = imported == expected_for_path
            paths[path]["full_task_completed"] = imported == expected_decision

    return {
        "kind": "decimal_compute_and_path_evaluation",
        "decision_source": (
            "imported_actions_with_separate_rule_baseline"
            if imported_actions else "deterministic_path_rule_not_provider_output"
        ),
        "decimal": {
            "quantity": None if quantity is None else str(quantity),
            "unit_price": None if unit_price is None else str(unit_price),
            "shipping": None if shipping is None else str(shipping),
            "currency": "CNY",
            "code_total": None if code_total is None else str(code_total),
            "expected_total": str(expected_total),
            "code_total_matches_expected": (
                None if code_total is None else code_total == expected_total
            ),
            "model_computed_total": None if model_total is None else str(model_total),
            "model_total_minus_code_total": (
                None
                if model_total is None or code_total is None
                else str(model_total - code_total)
            ),
            "operands_valid": numbers_valid,
            "operands_available": operands_available,
        },
        "status_evidence": {
            "value": status_value,
            "exact_match": status_value == expected_values.get("status_evidence"),
        },
        "paths": paths,
    }


def _extract_estimate(answer: dict[str, Any]) -> dict[str, Any]:
    answer_value = answer.get("value", _MISSING)
    median = answer.get("median", _MISSING)
    p10 = answer.get("p10", _MISSING)
    p90 = answer.get("p90", _MISSING)
    if answer_value is _MISSING or answer_value is None:
        return {
            "status": "null",
            "value": None,
            "median": None,
            "p10": None,
            "p90": None,
            "missing": [],
        }
    _require(_finite_number(answer_value), "estimate native value must be a finite number")
    missing = [
        name
        for name, candidate in (("median", median), ("p10", p10), ("p90", p90))
        if candidate is _MISSING or candidate is None
    ]
    if missing:
        return {
            "status": "insufficient",
            "value": float(answer_value),
            "median": None if median is _MISSING else median,
            "p10": None if p10 is _MISSING else p10,
            "p90": None if p90 is _MISSING else p90,
            "missing": missing,
        }
    for name, candidate in (("median", median), ("p10", p10), ("p90", p90)):
        _require(_finite_number(candidate), f"estimate {name} must be a finite number")
    median_float, lower, upper = float(median), float(p10), float(p90)
    _require(lower <= median_float <= upper, "estimate must satisfy p10 <= median <= p90")
    return {
        "status": "ok",
        "value": float(answer_value),
        "median": median_float,
        "p10": lower,
        "p90": upper,
        "missing": [],
    }


def _median(values: list[float]) -> float:
    _require(bool(values), "historical samples must be non-empty")
    return float(statistics.median(values))


def _nearest_rank(values: list[float], probability: float) -> float:
    _require(0 < probability <= 1, "nearest-rank probability must be in (0,1]")
    ordered = sorted(values)
    index = math.ceil(probability * len(ordered)) - 1
    return float(ordered[max(0, index)])


def _evaluate_interval(
    case: TypedCase,
    answers: dict[str, dict[str, Any]],
    suite: TypedSuite,
) -> dict[str, Any]:
    estimate = _extract_estimate(answers["completion_days"])
    config = case.fields["completion_days"]
    lower_bound = config.get("min")
    upper_bound = config.get("max")
    within_range: bool | None = None
    if estimate["status"] == "ok":
        within_range = all(
            (lower_bound is None or estimate[key] >= float(lower_bound))
            and (upper_bound is None or estimate[key] <= float(upper_bound))
            for key in ("median", "p10", "p90")
        )
        _require(
            within_range,
            "estimate median/p10/p90 violate the requested min/max range",
        )
    experiment = suite.experiment(case.experiment_id)
    history = experiment["deterministic_baseline"]["history_days"]
    _require(
        isinstance(history, list)
        and history
        and all(_finite_number(item) for item in history),
        "historical baseline must contain finite numbers",
    )
    history_values = [float(item) for item in history]
    baseline = {
        "median": _median(history_values),
        "p10": _nearest_rank(history_values, 0.1),
        "p90": _nearest_rank(history_values, 0.9),
    }
    baseline["width"] = baseline["p90"] - baseline["p10"]
    observed = case.editorial_oracle["elapsed_calendar_days"]
    if estimate["status"] == "ok":
        width = estimate["p90"] - estimate["p10"]
        observation = {
            "status": "evaluable",
            "observed_days": observed,
            "interval_hit": estimate["p10"] <= observed <= estimate["p90"],
            "absolute_error_from_median": abs(estimate["median"] - observed),
        }
    elif estimate["status"] == "null":
        width = None
        observation = {
            "status": "not_evaluable",
            "reason": "estimate_value_null",
            "observed_days": observed,
            "interval_hit": None,
            "absolute_error_from_median": None,
        }
    else:
        width = None
        observation = {
            "status": "not_evaluable",
            "reason": "estimate_quantiles_missing",
            "missing": estimate["missing"],
            "observed_days": observed,
            "interval_hit": None,
            "absolute_error_from_median": None,
        }
    baseline_contains_grid = (
        (lower_bound is None or baseline["p10"] >= float(lower_bound))
        and (upper_bound is None or baseline["p90"] <= float(upper_bound))
    )
    return {
        "kind": "interval_evaluation",
        "estimate": {
            **estimate,
            "width": width,
            "within_requested_range": within_range,
        },
        "observation": observation,
        "history_baseline": {
            **baseline,
            "observed_days": observed,
            "interval_hit": baseline["p10"] <= observed <= baseline["p90"],
            "absolute_error_from_median": abs(baseline["median"] - observed),
            "method": "ordinary median + nearest-rank sorted[ceil(p*n)-1]",
            "range_source": "empirical_history_not_native_grid",
            "within_requested_range": baseline_contains_grid,
        },
        "evidence_scope": {
            "source_group": case.source_group,
            "variant_case": case.case_id,
            "independent_sample_claimed": False,
        },
    }


def _evaluate_ok_case(
    suite: TypedSuite,
    case: TypedCase,
    raw: Any,
    span_convention: dict[str, str] | None,
    value_source: str,
    downstream_decisions: dict[str, str] | None,
    provenance_kind: str = "native_values",
) -> dict[str, Any]:
    if provenance_kind == "empirical_history_baseline":
        baseline_values = raw["synthetic_answer"]
        baseline_within_range = (
            case.fields["completion_days"]["min"]
            <= baseline_values["baseline_p10"]
            <= baseline_values["baseline_p90"]
            <= case.fields["completion_days"]["max"]
        )
        return {
            "case_id": case.case_id,
            "experiment_id": case.experiment_id,
            "kind": "empirical_history_baseline",
            "estimate": {
                "status": "empirical_baseline_not_native",
                "value": None,
                "median": baseline_values["baseline_median"],
                "p10": baseline_values["baseline_p10"],
                "p90": baseline_values["baseline_p90"],
                "width": (
                    baseline_values["baseline_p90"]
                    - baseline_values["baseline_p10"]
                ),
                "missing": [],
                "within_requested_range": baseline_within_range,
            },
            "observation": {
                "status": "baseline_evaluable",
                "observed_days": case.editorial_oracle["elapsed_calendar_days"],
                "interval_hit": (
                    baseline_values["baseline_p10"]
                    <= case.editorial_oracle["elapsed_calendar_days"]
                    <= baseline_values["baseline_p90"]
                ),
                "absolute_error_from_median": abs(
                    baseline_values["baseline_median"]
                    - case.editorial_oracle["elapsed_calendar_days"]
                ),
            },
            "history_baseline": {
                "median": baseline_values["baseline_median"],
                "p10": baseline_values["baseline_p10"],
                "p90": baseline_values["baseline_p90"],
                "width": (
                    baseline_values["baseline_p90"]
                    - baseline_values["baseline_p10"]
                ),
                "observed_days": case.editorial_oracle["elapsed_calendar_days"],
                "interval_hit": (
                    baseline_values["baseline_p10"]
                    <= case.editorial_oracle["elapsed_calendar_days"]
                    <= baseline_values["baseline_p90"]
                ),
                "absolute_error_from_median": abs(
                    baseline_values["baseline_median"]
                    - case.editorial_oracle["elapsed_calendar_days"]
                ),
                "method": "ordinary median + nearest-rank sorted[ceil(p*n)-1]",
                "range_source": "empirical_history_not_native_grid",
                "within_requested_range": baseline_within_range,
            },
            "evidence_scope": {
                "source_group": case.source_group,
                "variant_case": case.case_id,
                "independent_sample_claimed": False,
                "scope": baseline_values["baseline_scope"],
            },
        }
    answers, envelope = _parse_answers(case, raw, value_source=value_source)
    if case.experiment_id in {"source-null-identity", "extract-compute-decide"}:
        source_eval = _evaluate_source_fields(
            case,
            answers,
            envelope,
            span_convention,
            value_source,
        )
        if case.experiment_id == "source-null-identity":
            return {
                **source_eval,
                "case_id": case.case_id,
                "experiment_id": case.experiment_id,
                "kind": "source_null_identity",
            }
        compute_eval = _evaluate_compute_paths(
            case, answers, downstream_decisions=downstream_decisions
        )
        return {
            **compute_eval,
            "case_id": case.case_id,
            "experiment_id": case.experiment_id,
            "kind": "extract_compute_decide",
            "source_fields": source_eval,
        }
    return {
        "case_id": case.case_id,
        "experiment_id": case.experiment_id,
        **_evaluate_interval(case, answers, suite),
        "native_envelope": {
            "model": envelope.get("model"),
            "truncated": envelope.get("truncated"),
            "usage": envelope.get("usage"),
            "state_text_present": "state_text" in envelope,
        },
    }


def make_result(
    suite: TypedSuite,
    case: TypedCase,
    entry: ResponseEntry,
    *,
    span_convention: dict[str, str] | None,
) -> dict[str, Any]:
    """Build one untrusted result row; replay recomputes it from the raw input."""

    outcome = OUTCOME_OK
    error_kind: str | None = None
    error_detail: str | None = None
    if entry.outcome_hint == OUTCOME_ERROR:
        outcome = OUTCOME_ERROR
        error_kind = "imported_error"
        error_detail = entry.error_detail
    elif entry.outcome_hint == OUTCOME_REFUSAL:
        outcome = OUTCOME_REFUSAL
        error_detail = entry.error_detail
    elif entry.outcome_hint == OUTCOME_UNKNOWN:
        outcome = OUTCOME_UNKNOWN
        error_detail = entry.error_detail
    elif entry.http_status is not None and entry.http_status != 200:
        outcome = OUTCOME_ERROR
        error_kind = f"http_{entry.http_status}"
        error_detail = f"non-200 HTTP status {entry.http_status}"
    else:
        value_source = entry.resolved_value_source()
        try:
            evaluation = _evaluate_ok_case(
                suite,
                case,
                entry.raw,
                span_convention,
                value_source,
                entry.downstream_decisions,
                entry.provenance_kind,
            )
        except (TypedValuesError, KeyError, TypeError, ValueError) as exc:
            outcome = OUTCOME_ERROR
            error_kind = "response_contract"
            error_detail = str(exc)

    if outcome != OUTCOME_OK:
        recorded_detail = entry.error_detail
        if outcome == OUTCOME_ERROR and recorded_detail is None:
            recorded_detail = error_detail
        evaluation = {
            "case_id": case.case_id,
            "experiment_id": case.experiment_id,
            "kind": "not_evaluable",
            "outcome": outcome,
            "error_kind": error_kind,
            "error_detail": recorded_detail,
        }
    raw_snapshot = entry.raw
    try:
        json.dumps(raw_snapshot, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        if outcome == OUTCOME_OK:
            outcome = OUTCOME_ERROR
            error_kind = "response_contract"
            error_detail = "response contains a value that is not valid strict JSON"
            evaluation = {
                "case_id": case.case_id,
                "experiment_id": case.experiment_id,
                "kind": "not_evaluable",
                "outcome": outcome,
                "error_kind": error_kind,
                "error_detail": error_detail,
            }
        raw_snapshot = {
            "non_json_value_kinds": _describe_non_json(entry.raw),
            "note": "Raw response contained a non-JSON value and was retained as a representation.",
        }
    response_input = {
        "raw": raw_snapshot,
        "http_status": entry.http_status,
        "outcome_hint": entry.outcome_hint,
        "error_detail": entry.error_detail,
        "value_source": entry.resolved_value_source(),
        "downstream_decisions": (
            {} if entry.downstream_decisions is None else entry.downstream_decisions
        ),
        "provenance_kind": entry.provenance_kind,
    }
    return {
        "experiment_id": case.experiment_id,
        "case_id": case.case_id,
        "source_group": case.source_group,
        "case_digest": case_digest(case),
        "request": case.request,
        "request_digest": request_digest(case.request),
        "response_digest": _sha(response_input),
        "http_status": entry.http_status,
        "outcome": outcome,
        "outcome_hint": entry.outcome_hint,
        "error_kind": error_kind,
        "error_detail": error_detail,
        "input_error_detail": entry.error_detail,
        "value_source": entry.resolved_value_source(),
        "downstream_decisions": (
            {} if entry.downstream_decisions is None else entry.downstream_decisions
        ),
        "provenance_kind": entry.provenance_kind,
        "raw": raw_snapshot,
        "evaluation": evaluation,
        "evaluation_digest": _sha(
            {
                "outcome": outcome,
                "error_detail": error_detail,
                "evaluation": evaluation,
            }
        ),
    }


def build_record(
    suite: TypedSuite,
    cases: list[TypedCase],
    entries: list[ResponseEntry],
    *,
    provenance: str,
    span_convention: dict[str, str] | None = None,
    notes: str = "",
) -> dict[str, Any]:
    _require(provenance in PROVENANCES, f"unsupported provenance {provenance!r}")
    _require(bool(cases), "a typed-values run must select at least one case")
    for entry in entries:
        if entry.provenance_kind == "empirical_history_baseline":
            continue
        _require(
            provenance != PROVENANCE_IMPORT
            or entry.value_source is not None
            or entry.provenance_kind == "empirical_history_baseline",
            f"case {entry.case_id!r}: import entries need explicit value_source",
        )
        _require(
            provenance == PROVENANCE_IMPORT
            or (
                entry.value_source == "synthetic"
                or entry.provenance_kind == "empirical_history_baseline"
            ),
            f"case {entry.case_id!r}: baseline/demo entries must be explicitly synthetic",
        )
    if provenance == PROVENANCE_IMPORT:
        for entry in entries:
            if entry.outcome_hint != "native":
                continue
            _require(
                (entry.value_source or "native") in {"native", "synthetic"}
                or entry.provenance_kind == "empirical_history_baseline",
                f"case {entry.case_id!r}: imported native entry needs "
                "value_source='native' or an explicit synthetic fixture",
            )
    selected = {case.case_id for case in cases}
    seen: set[str] = set()
    by_id = {case.case_id: case for case in cases}
    ordered_entries: list[ResponseEntry] = []
    for entry in entries:
        _require(entry.case_id in selected, f"response contains foreign case {entry.case_id!r}")
        _require(entry.case_id not in seen, f"duplicate response for case {entry.case_id!r}")
        seen.add(entry.case_id)
        case = by_id[entry.case_id]
        _require(
            entry.experiment_id == case.experiment_id,
            f"case {entry.case_id!r}: experiment identity differs from suite",
        )
        ordered_entries.append(entry)
    missing = selected - seen
    _require(not missing, f"response file is missing cases {sorted(missing)}")

    results = [
        make_result(
            suite,
            by_id[entry.case_id],
            entry,
            span_convention=span_convention,
        )
        for entry in ordered_entries
    ]
    return {
        "record_version": RECORD_VERSION,
        "created_at": _now(),
        "provenance": provenance,
        "synthetic": provenance in {PROVENANCE_BASELINE, PROVENANCE_DEMO},
        "live_verified": False,
        "evidence_notice": (
            "Imported responses are external inputs. No project live-provider "
            "verification is implied."
            if provenance == PROVENANCE_IMPORT
            else "Synthetic offline demonstration; not provider inference."
        ),
        "value_source": (
            "mixed_import"
            if provenance == PROVENANCE_IMPORT
            and len({entry.resolved_value_source() for entry in entries}) > 1
            else (
                entries[0].resolved_value_source()
            )
        ),
        "suite_path": str(suite.source_path.resolve()),
        "suite_digest": suite.digest(),
        "selected_case_ids": [case.case_id for case in cases],
        "span_convention": span_convention,
        "notes": notes,
        "results": results,
    }


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _validate_run_dir(run_dir: str | Path) -> Path:
    path = Path(run_dir).expanduser()
    resolved = path.resolve()
    root = _repo_root()
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        relative = None
    if relative is not None:
        _require(
            bool(relative.parts) and relative.parts[0] == "runs",
            f"refuse to write typed-values results into the source tree: {path}",
        )
    if path.exists():
        _require(path.is_dir(), f"run destination exists and is not a directory: {path}")
        _require(not any(path.iterdir()), f"run directory {path} is not empty")
    return path


def _write_json_atomic(path: Path, data: Any) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_record(run_dir: str | Path, record: dict[str, Any]) -> Path:
    path = _validate_run_dir(run_dir)
    path.mkdir(parents=True, exist_ok=True)
    output = path / "typed-values-record.json"
    _require(not output.exists(), f"{output} already exists; refuse to overwrite")
    _write_json_atomic(output, record)
    return output


def _load_record_data(path: str | Path) -> tuple[Path, dict[str, Any]]:
    p = Path(path)
    if p.is_dir():
        p = p / "typed-values-record.json"
    data = _strict_json(p)
    _require(isinstance(data, dict), f"{p}: record must be a JSON object")
    _require(
        data.get("record_version") == RECORD_VERSION,
        f"{p}: unsupported record_version {data.get('record_version')!r}",
    )
    return p, data


def _path_matches(left: str, right: str | Path) -> bool:
    return Path(left).resolve() == Path(right).resolve()


def replay_record(
    record_path: str | Path,
    suite_path: str | Path = DEFAULT_SUITE,
) -> dict[str, Any]:
    p, data = _load_record_data(record_path)
    suite = load_suite(suite_path)
    provenance = data.get("provenance")
    _require(provenance in PROVENANCES, f"{p}: unknown provenance {provenance!r}")
    _require(isinstance(data.get("synthetic"), bool), f"{p}: synthetic must be boolean")
    _require(
        data.get("synthetic") is (provenance in {PROVENANCE_BASELINE, PROVENANCE_DEMO}),
        f"{p}: synthetic flag is inconsistent with provenance",
    )
    _require(data.get("live_verified") is False, f"{p}: live_verified must be false")
    _require(
        data.get("value_source") in {"native", "synthetic", "mixed_import"},
        f"{p}: value_source must be native, synthetic or mixed_import",
    )
    _require(
        isinstance(data.get("suite_path"), str)
        and _path_matches(data["suite_path"], suite.source_path),
        f"{p}: replay suite path differs from recorded suite path",
    )
    _require(
        data.get("suite_digest") == suite.digest(),
        f"{p}: suite digest differs; refusing a stale or changed suite",
    )
    selected_ids = data.get("selected_case_ids")
    _require(
        isinstance(selected_ids, list)
        and selected_ids
        and all(isinstance(item, str) for item in selected_ids),
        f"{p}: selected_case_ids must be a non-empty string array",
    )
    _require(
        len(selected_ids) == len(set(selected_ids)),
        f"{p}: duplicate selected case id",
    )
    suite_by_id = suite.by_id()
    missing_selected = [case_id for case_id in selected_ids if case_id not in suite_by_id]
    _require(not missing_selected, f"{p}: foreign selected case ids {missing_selected}")
    span_convention = _validate_span_convention(
        data.get("span_convention"), where=f"{p}: span_convention"
    )
    raw_results = data.get("results")
    _require(isinstance(raw_results, list), f"{p}: results must be an array")
    _require(
        len(raw_results) == len(selected_ids),
        f"{p}: result count does not match selected_case_ids",
    )
    seen: set[str] = set()
    recomputed_results: list[dict[str, Any]] = []
    for index, result in enumerate(raw_results):
        where = f"{p}: results[{index}]"
        _require(isinstance(result, dict), f"{where}: result must be an object")
        case_id = result.get("case_id")
        _require(isinstance(case_id, str), f"{where}: case_id must be a string")
        _require(case_id not in seen, f"{p}: duplicate result for case {case_id!r}")
        seen.add(case_id)
        _require(case_id in selected_ids, f"{where}: case is outside selected_case_ids")
        case = suite_by_id[case_id]
        _require(
            result.get("experiment_id") == case.experiment_id,
            f"{where}: experiment identity differs from suite",
        )
        _require(
            result.get("source_group") == case.source_group,
            f"{where}: source_group differs from suite",
        )
        _require(
            result.get("case_digest") == case_digest(case),
            f"{where}: case digest differs; suite case content changed",
        )
        _require(
            result.get("request") == case.request,
            f"{where}: retained request differs from suite request",
        )
        _require(
            result.get("request_digest") == request_digest(case.request),
            f"{where}: retained request digest differs",
        )
        hint = result.get("outcome_hint")
        _require(
            hint in {"native", OUTCOME_UNKNOWN, OUTCOME_REFUSAL, OUTCOME_ERROR},
            f"{where}: invalid outcome_hint",
        )
        result_value_source = result.get("value_source")
        _require(
            (
                provenance != PROVENANCE_IMPORT
                and result_value_source == "synthetic"
            )
            or (
                provenance == PROVENANCE_IMPORT
                and result_value_source in {"native", "synthetic"}
            ),
            f"{where}: value_source is inconsistent with provenance",
        )
        entry = ResponseEntry(
            experiment_id=case.experiment_id,
            case_id=case_id,
            raw=result.get("raw"),
            http_status=result.get("http_status"),
            outcome_hint=hint,
            error_detail=result.get("input_error_detail"),
            value_source=result_value_source,
            downstream_decisions=result.get("downstream_decisions"),
            provenance_kind=result.get("provenance_kind", "native_values"),
        )
        recomputed = make_result(
            suite,
            case,
            entry,
            span_convention=span_convention,
        )
        for key in ("response_digest", "outcome", "evaluation_digest"):
            _require(
                result.get(key) == recomputed[key],
                f"{where}: recorded {key} disagrees with raw response/replay",
            )
        _require(
            result.get("evaluation") == recomputed["evaluation"],
            f"{where}: recorded evaluation was tampered with",
        )
        recomputed_results.append(recomputed)
    _require(set(seen) == set(selected_ids), f"{p}: results do not match selected_case_ids")
    return {
        "record": str(p),
        "suite": str(suite.source_path.resolve()),
        "provenance": provenance,
        "synthetic": data["synthetic"],
        "value_source": data.get("value_source"),
        "live_verified": False,
        "evidence_notice": data.get("evidence_notice"),
        "evaluation": aggregate_evaluation(recomputed_results),
        "cases": recomputed_results,
    }


def aggregate_evaluation(results: list[dict[str, Any]]) -> dict[str, Any]:
    counters = {
        "total": len(results),
        OUTCOME_OK: 0,
        OUTCOME_UNKNOWN: 0,
        OUTCOME_REFUSAL: 0,
        OUTCOME_ERROR: 0,
    }
    errors: list[dict[str, Any]] = []
    source_metrics: dict[str, Any] = {
        "fields": 0,
        "format_checked": 0,
        "format_valid": 0,
        "exact_match": 0,
        "text_match_checked": 0,
        "text_match": 0,
        "relation_checked": 0,
        "relation_correct": 0,
        "expected_null": 0,
        "spurious_fills": 0,
        "expected_nonnull": 0,
        "missed_present_values": 0,
        "spans": {},
    }
    compute_metrics: dict[str, dict[str, int]] = {}
    interval_rows: list[dict[str, Any]] = []
    for result in results:
        outcome = result["outcome"]
        counters[outcome] += 1
        if outcome == OUTCOME_ERROR:
            errors.append(
                {
                    "case_id": result["case_id"],
                    "error_kind": result["error_kind"],
                    "error_detail": result["error_detail"],
                }
            )
            continue
        if outcome != OUTCOME_OK:
            continue
        evaluation = result["evaluation"]
        if evaluation["kind"] == "source_null_identity":
            field_eval = evaluation["fields"]
        elif evaluation["kind"] == "extract_compute_decide":
            field_eval = evaluation["source_fields"]["fields"]
            for path_name, row in evaluation["paths"].items():
                metric = compute_metrics.setdefault(
                    path_name,
                    {
                        "cases": 0,
                        "honest_under_input": 0,
                        "full_task_completed": 0,
                        "imported_cases": 0,
                        "baseline_cases": 0,
                        "imported_honest_under_input": 0,
                        "imported_full_task_completed": 0,
                        "not_provided": 0,
                    },
                )
                metric["cases"] += 1
                if row["action_source"] == "import":
                    metric["imported_cases"] += 1
                    metric["imported_honest_under_input"] += int(row["honest_under_input"])
                    metric["imported_full_task_completed"] += int(row["full_task_completed"])
                else:
                    metric["baseline_cases"] += 1
                    metric["not_provided"] += 1
                if row["honest_under_input"] is None:
                    metric["not_provided"] = metric.get("not_provided", 0) + 1
                else:
                    metric["honest_under_input"] += int(row["honest_under_input"])
                if row["full_task_completed"] is None:
                    metric["task_completion_not_provided"] = (
                        metric.get("task_completion_not_provided", 0) + 1
                    )
                else:
                    metric["full_task_completed"] += int(row["full_task_completed"])
        elif evaluation["kind"] in {
            "interval_evaluation",
            "empirical_history_baseline",
        }:
            field_eval = {}
            interval_rows.append(
                {
                    "case_id": result["case_id"],
                    "source_group": result["source_group"],
                    "width": evaluation["estimate"]["width"],
                    "hit": evaluation["observation"]["interval_hit"],
                    "absolute_error": evaluation["observation"][
                        "absolute_error_from_median"
                    ],
                    "baseline_width": evaluation["history_baseline"]["width"],
                    "baseline_hit": evaluation["history_baseline"]["interval_hit"],
                    "baseline_absolute_error": evaluation["history_baseline"][
                        "absolute_error_from_median"
                    ],
                    "native_range_matches_history": evaluation["history_baseline"][
                        "within_requested_range"
                    ],
                    "estimate_status": evaluation["estimate"]["status"],
                    "observation_status": evaluation["observation"]["status"],
                }
            )
        else:
            field_eval = {}
        for row in field_eval.values():
            source_metrics["fields"] += 1
            if row["expected_null"]:
                source_metrics["expected_null"] += 1
                source_metrics["spurious_fills"] += int(row["value"] is not None)
            else:
                source_metrics["expected_nonnull"] += 1
                source_metrics["missed_present_values"] += int(row["value"] is None)
            if row["type_format_valid"] is not None:
                source_metrics["format_checked"] += 1
                source_metrics["format_valid"] += int(row["type_format_valid"])
            source_metrics["exact_match"] += int(row["exact_match"])
            if row["text_match"] is not None:
                source_metrics["text_match_checked"] += 1
                source_metrics["text_match"] += int(row["text_match"])
            if row["entity_version_correct"] is not None:
                source_metrics["relation_checked"] += 1
                source_metrics["relation_correct"] += int(
                    row["entity_version_correct"]
                )
            span_status = row["span_status"]
            source_metrics["spans"][span_status] = (
                source_metrics["spans"].get(span_status, 0) + 1
            )

    groups: dict[str, list[dict[str, Any]]] = {}
    for row in interval_rows:
        groups.setdefault(row["source_group"], []).append(row)
    by_source_group = {}
    for group, rows in groups.items():
        evaluable = [row for row in rows if row["hit"] is not None]
        hits = sum(int(row["hit"]) for row in evaluable)
        baseline_evaluable = [
            row for row in rows if row["baseline_hit"] is not None
        ]
        by_source_group[group] = {
            "variant_count": len(rows),
            "evaluable_outcomes": len(evaluable),
            "not_evaluable": len(rows) - len(evaluable),
            "interval_hits": hits,
            "empirical_coverage": hits / len(evaluable) if evaluable else None,
            "mean_width": (
                sum(row["width"] for row in evaluable) / len(evaluable)
                if evaluable
                else None
            ),
            "baseline_evaluable": len(baseline_evaluable),
            "baseline_hits": sum(
                int(row["baseline_hit"]) for row in baseline_evaluable
            ),
            "note": "Variants in one source group are not independent samples.",
        }

    evaluable_intervals = [row for row in interval_rows if row["hit"] is not None]
    source_metrics["spurious_fill_rate"] = (
        source_metrics["spurious_fills"] / source_metrics["expected_null"]
        if source_metrics["expected_null"] else None
    )
    source_metrics["missed_present_rate"] = (
        source_metrics["missed_present_values"] / source_metrics["expected_nonnull"]
        if source_metrics["expected_nonnull"] else None
    )

    return {
        "counts": counters,
        "errors": errors,
        "source_fields": source_metrics,
        "compute_paths": compute_metrics,
        "intervals": {
            "total_predictions": len(interval_rows),
            "evaluable_outcomes": len(evaluable_intervals),
            "not_evaluable": len(interval_rows) - len(evaluable_intervals),
            "interval_hits": sum(int(row["hit"]) for row in evaluable_intervals),
            "empirical_coverage": (
                sum(int(row["hit"]) for row in evaluable_intervals)
                / len(evaluable_intervals)
                if evaluable_intervals
                else None
            ),
            "mean_width": (
                sum(row["width"] for row in evaluable_intervals)
                / len(evaluable_intervals)
                if evaluable_intervals
                else None
            ),
            "baseline_hits": sum(
                int(row["baseline_hit"]) for row in interval_rows
            ),
            "by_source_group": by_source_group,
            "independent_samples_claimed": False,
            "calibration_claimed": False,
            "note": (
                "Small authored variants within shared source groups do not "
                "establish calibration or a seven-sample evaluation."
            ),
        },
    }


def baseline_entries(cases: list[TypedCase]) -> list[ResponseEntry]:
    entries: list[ResponseEntry] = []
    for case in cases:
        if case.experiment_id == "source-null-identity":
            scope = _target_scope(case)
            order_match = re.search(r"PO-\d+", scope)
            recipient_match = re.search(r"收件人为([^；。\s]+)", scope)
            date_match = re.search(r"\d{4}-\d{2}-\d{2}", scope)
            values = {
                "current_order_id": order_match.group(0) if order_match else None,
                "current_recipient": (
                    recipient_match.group(1) if recipient_match else None
                ),
                "current_delivery_date": date_match.group(0) if date_match else None,
                "current_delivery_evidence": date_match.group(0) if date_match else None,
            }
        elif case.experiment_id == "extract-compute-decide":
            quantity_match = re.search(r"数量\s*(\d+)\s*件", case.state)
            price_match = re.search(r"单价\s*([\d.]+)\s*CNY", case.state)
            shipping_match = re.search(r"运费\s*([\d.]+)\s*CNY", case.state)
            status_match = re.search(r"(版本 v2 的验收状态：.*?。)", case.state)
            _require(
                bool(quantity_match and price_match and shipping_match and status_match),
                f"baseline cannot parse case {case.case_id!r}",
            )
            quantity = int(quantity_match.group(1))
            price = Decimal(price_match.group(1))
            shipping = Decimal(shipping_match.group(1))
            values = {
                "quantity": quantity,
                "unit_price": float(price),
                "shipping": float(shipping),
                "computed_total": float(quantity * price + shipping),
                "status_evidence": status_match.group(1),
            }
        else:
            history_match = re.search(
                r"耗时分别为\s*([\d、.]+)\s*天", case.state
            )
            _require(bool(history_match), f"baseline cannot parse case {case.case_id!r}")
            history = [
                float(item) for item in history_match.group(1).split("、") if item
            ]
            median_value = _median(history)
            p10_value = _nearest_rank(history, 0.1)
            p90_value = _nearest_rank(history, 0.9)
            scope = {
                "group": case.source_group,
                "variants": [
                    candidate.case_id
                    for candidate in cases
                    if candidate.source_group == case.source_group
                ],
            }
            entries.append(
                ResponseEntry(
                    experiment_id=case.experiment_id,
                    case_id=case.case_id,
                    raw={
                        "kind": "offline_baseline",
                        "answers": {},
                        "synthetic_answer": {
                            "baseline_median": median_value,
                            "baseline_p10": p10_value,
                            "baseline_p90": p90_value,
                            "baseline_scope": scope,
                        },
                    },
                    value_source="synthetic",
                    provenance_kind="empirical_history_baseline",
                )
            )
            continue
        answers = {
            name: {
                "type": case.fields[name]["type"],
                "value": value,
            }
            for name, value in values.items()
        }
        entries.append(
            ResponseEntry(
                experiment_id=case.experiment_id,
                case_id=case.case_id,
                raw={"kind": "offline_baseline", "answers": answers},
                value_source="synthetic",
            )
        )
    return entries


def _demo_answers(case: TypedCase) -> dict[str, Any]:
    if case.experiment_id in {"source-null-identity", "extract-compute-decide"}:
        answers: dict[str, Any] = {}
        for name, value in case.editorial_oracle["values"].items():
            field_type = case.fields[name]["type"]
            if field_type == "number" and isinstance(value, str):
                value = float(Decimal(value))
            answer: dict[str, Any] = {
                "type": field_type,
                "value": value,
                "confidence": 0.7,
            }
            if name in {"current_delivery_date", "current_delivery_evidence"}:
                answer["guess"] = "2026-10-18"
                answer["p_null"] = 0.9
            answers[name] = answer
        return answers
    upper = float(case.fields["completion_days"]["max"])
    return {
        "completion_days": {
            "type": "estimate",
            "value": 5,
            "median": 5,
            "p10": 3,
            "p90": min(9, upper),
        }
    }


def demo_entries(cases: list[TypedCase]) -> list[ResponseEntry]:
    return [
        ResponseEntry(
            experiment_id=case.experiment_id,
            case_id=case.case_id,
            raw={
                "kind": "constructed_typed_values_demo",
                "synthetic": True,
                "answers": _demo_answers(case),
            },
            value_source="synthetic",
        )
        for case in cases
    ]
