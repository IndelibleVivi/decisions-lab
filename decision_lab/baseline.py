"""Deterministic, conservative rules baseline for the next-action task.

This baseline is intentionally simple and fully offline. It reads ONLY
the model-visible task input (see ``Case.model_input``); it never sees
labels. When signals are insufficient it returns ``needs_more_context``,
mirroring the conservative stance the lab expects from a careful reader.

It is a *synthetic demonstration*, not a model judgement and not a
quality claim. Its accuracy number is only meaningful as a smoke test.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .cases import ALLOWED_ACTIONS, Case

#: A short list of cue words per signal. Order of evaluation matters and
#: is documented so the baseline is reproducible and inspectable.
_MISSING_CUES = (
    "tbd", "todo", "to be determined", "[missing]", "(missing)",
    "not included", "unavailable", "omitted", "placeholder",
    "待补充", "缺失", "未提供", "待定", "省略",
)
_CONTRACT_CUES = (
    "contract", "interface", "signature", "schema", "spec", "protocol",
    "backward compat", "breaking change", "api", "endpoint", "payload",
    "契约", "接口", "签名", "模式", "规范", "协议", "兼容", "破坏性",
)
_CONTEXT_CUES = (
    "context", "background", "related", "prior", "history", "existing",
    "usage", "how it is used", "appears in",
    "上下文", "背景", "相关", "历史", "既有", "用法", "出现于",
)
_SOURCE_CUES = (
    "http://", "https://", "see ", "source", "upstream", "commit",
    "diff", "changelog", "release note", "docs.", "reference",
    "来源", "上游", "提交", "变更", "更新日志", "参考", "文档",
)


@dataclass
class BaselineJudgment:
    """A baseline decision with a compact, human-auditable trace."""

    action: str
    reasons: list[str]
    #: Baseline has no calibrated probabilities; expose a flat trace only.
    confidence: None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reasons": list(self.reasons),
            "confidence": self.confidence,
            "kind": "baseline_rules",
        }


def _hit(text: str, cues: tuple[str, ...]) -> list[str]:
    low = text.lower()
    return [c for c in cues if c in low]


def judge(model_input: dict[str, Any]) -> BaselineJudgment:
    """Deterministically map a model-visible task input to an action.

    Precedence (conservative first):
      1. missing/placeholder evidence -> needs_more_context
      2. contract/interface language  -> compare_contract
      3. explicit source pointer      -> inspect_source
      4. contextual linkage           -> read_in_context
      5. otherwise                    -> needs_more_context
    """
    document = str(model_input.get("document", ""))
    claim = str(model_input.get("claim", ""))
    source_ref = str(model_input.get("source_ref", ""))
    hay = "\n".join([document, claim, source_ref])
    reasons: list[str] = []

    missing = _hit(hay, _MISSING_CUES)
    if missing:
        reasons.append(f"missing-evidence cues: {', '.join(sorted(missing))}")
        return BaselineJudgment("needs_more_context", reasons)

    contract = _hit(hay, _CONTRACT_CUES)
    if contract:
        reasons.append(f"contract cues: {', '.join(sorted(contract))}")
        return BaselineJudgment("compare_contract", reasons)

    source = _hit(hay, _SOURCE_CUES)
    if source or source_ref.strip():
        if source:
            reasons.append(f"source cues: {', '.join(sorted(source))}")
        if source_ref.strip():
            reasons.append("explicit source_ref present")
        return BaselineJudgment("inspect_source", reasons)

    context = _hit(hay, _CONTEXT_CUES)
    if context:
        reasons.append(f"context cues: {', '.join(sorted(context))}")
        return BaselineJudgment("read_in_context", reasons)

    reasons.append("no decisive cue; conservative default")
    return BaselineJudgment("needs_more_context", reasons)


def judge_case(case: Case) -> BaselineJudgment:
    return judge(case.model_input())


def assert_contract() -> None:
    """Guard against the baseline emitting an out-of-contract action."""
    j = judge({"document": "", "claim": "", "question": "", "source_ref": ""})
    assert j.action in ALLOWED_ACTIONS, j.action
