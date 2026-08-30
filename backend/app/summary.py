from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from .schemas import (
    AnalysisWarning,
    ConfirmedNextAction,
    CrmFields,
    FieldStatus,
    OpportunityRisk,
    STAGE_LABELS,
    StageCode,
    StageResult,
    ValidatedField,
    ValidatedOpportunity,
    ValidatedPerson,
)


class GroundedSummaryProvider(Protocol):
    @property
    def provider_name(self) -> str:
        ...

    @property
    def model_name(self) -> str:
        ...

    async def invoke_grounded_summary(self, context: dict[str, Any], deterministic_draft: str) -> str:
        ...


@dataclass(frozen=True)
class SummaryGenerationResult:
    summary: str
    mode: str
    fallback_reason: str | None = None
    validation_errors: list[str] | None = None


class SummaryValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def build_deterministic_grounded_summary(result: ValidatedOpportunity) -> str:
    stage = result.stage
    crm_fields = result.crm_fields
    risk = result.opportunity_risks[0] if result.opportunity_risks else None

    if stage is None:
        return _build_stage_null_summary(result, risk)

    first_sentence = f"当前商机处于 {stage.code}（{stage.label}），{stage.reason.rstrip('。')}。"
    key_facts = _confirmed_fact_phrases(crm_fields)
    second_sentence = "；".join(key_facts[:2]) + "。" if key_facts else "当前已确认的需求、场景或商务事实仍有限。"

    attention = _attention_phrase(result, risk)
    action = _next_action_phrase(result.confirmed_next_action)
    if action and attention:
        third_sentence = f"{attention}，{action}。"
    elif action:
        third_sentence = f"{action}。"
    else:
        third_sentence = f"{attention}。" if attention else "后续应优先补齐仍待确认的关键信息。"
    return _compact_summary([first_sentence, second_sentence, third_sentence])


def build_summary_context(result: ValidatedOpportunity) -> dict[str, Any]:
    return {
        "status": result.status.value,
        "stage": result.stage.model_dump(mode="json") if result.stage else None,
        "stage_decision_reason": result.developer_details.get("stage_decision_reason"),
        "crm_fields": {
            "customer_needs": [_field_context(item) for item in result.crm_fields.customer_needs],
            "core_scenarios": [_field_context(item) for item in result.crm_fields.core_scenarios],
            "budget": _field_context(result.crm_fields.budget),
            "decision_maker": _person_context(result.crm_fields.decision_maker),
            "influencers": [_person_context(item) for item in result.crm_fields.influencers],
            "timeline": _field_context(result.crm_fields.timeline),
        },
        "opportunity_risks": [risk.model_dump(mode="json") for risk in result.opportunity_risks],
        "confirmed_next_action": result.confirmed_next_action.model_dump(mode="json") if result.confirmed_next_action else None,
        "unconfirmed_info": [_field_context(item) for item in result.unconfirmed_info],
        "analysis_warnings": [warning.model_dump(mode="json") for warning in result.analysis_warnings],
        "evidence": [
            {"id": item.id, "field": item.field, "quote": item.quote}
            for item in result.evidence
            if item.valid and item.sufficient
        ],
    }


async def generate_grounded_summary(provider: GroundedSummaryProvider, result: ValidatedOpportunity) -> SummaryGenerationResult:
    deterministic = result.summary or build_deterministic_grounded_summary(result)
    result.summary = deterministic
    context = build_summary_context(result)

    if provider.provider_name == "mock":
        result.developer_details["summary_generation"] = {
            "mode": "deterministic_fallback",
            "fallback_reason": "mock_provider",
            "validation_errors": [],
        }
        return SummaryGenerationResult(summary=deterministic, mode="deterministic_fallback", fallback_reason="mock_provider", validation_errors=[])

    try:
        candidate = (await provider.invoke_grounded_summary(context, deterministic)).strip()
        if not candidate:
            raise SummaryValidationError(["empty_summary"])
        validation_errors = validate_grounded_summary(candidate, result, context)
        if validation_errors:
            raise SummaryValidationError(validation_errors)
        result.summary = candidate
        result.developer_details["summary_generation"] = {
            "mode": "llm",
            "fallback_reason": None,
            "validation_errors": [],
            "provider": provider.provider_name,
            "model": provider.model_name,
        }
        return SummaryGenerationResult(summary=candidate, mode="llm")
    except SummaryValidationError as exc:
        result.developer_details["summary_generation"] = {
            "mode": "deterministic_fallback",
            "fallback_reason": "grounding_validation_failed",
            "validation_errors": exc.errors,
            "provider": provider.provider_name,
            "model": provider.model_name,
        }
        return SummaryGenerationResult(summary=deterministic, mode="deterministic_fallback", fallback_reason="grounding_validation_failed", validation_errors=exc.errors)
    except Exception as exc:
        result.developer_details["summary_generation"] = {
            "mode": "deterministic_fallback",
            "fallback_reason": exc.__class__.__name__,
            "validation_errors": [],
            "provider": provider.provider_name,
            "model": provider.model_name,
        }
        return SummaryGenerationResult(summary=deterministic, mode="deterministic_fallback", fallback_reason=exc.__class__.__name__, validation_errors=[])


def validate_grounded_summary(summary: str, result: ValidatedOpportunity, context: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    errors.extend(_validate_stage(summary, result.stage))
    errors.extend(_validate_unknown_boundaries(summary, result))
    errors.extend(_validate_conflict_boundaries(summary, result))
    errors.extend(_validate_protected_tokens(summary, context))
    errors.extend(_validate_next_action(summary, result.confirmed_next_action))
    if len(_sentences(summary)) > 4:
        errors.append("too_many_sentences")
    if re.search(r"(^|\n)\s*[-*]\s+", summary):
        errors.append("markdown_list_not_allowed")
    return errors


def _field_context(field: ValidatedField) -> dict[str, Any]:
    return {
        "value": field.value,
        "status": field.status.value,
        "evidence_ids": field.evidence_ids,
        "conflicting_values": field.conflicting_values,
        "reason": field.reason,
    }


def _person_context(person: ValidatedPerson) -> dict[str, Any]:
    return {
        "name": person.name,
        "role": person.role,
        "status": person.status.value,
        "authority_confirmed": person.authority_confirmed,
        "evidence_ids": person.evidence_ids,
        "reason": person.reason,
    }


def _build_stage_null_summary(result: ValidatedOpportunity, risk: OpportunityRisk | None) -> str:
    reason = result.developer_details.get("stage_decision_reason")
    if risk:
        return _compact_summary(
            [
                f"当前记录存在关键阻塞，暂不能可靠确认销售阶段：{risk.description.rstrip('。')}。",
                "已验证的信息应先用于澄清项目有效性或冲突状态，系统不会选择其中一个冲突事实作为当前结论。",
            ]
        )
    if reason == "insufficient_business_facts":
        return "当前记录可以解析，但客户需求、使用场景或推进动作仍不足，暂不能形成可靠销售阶段判断。需要先补齐可验证的业务事实。"
    if reason == "insufficient_stage_signal":
        return "当前记录已有部分业务信息，但尚未形成可采纳的 S0-S5 阶段信号，暂不能确认销售阶段。需要补充客户需求、方案验证或商务进展等明确事实。"
    if result.analysis_warnings:
        return f"当前尚未获得可用于商机分析的完整拜访记录，暂不能形成可靠销售阶段判断。{result.analysis_warnings[0].description}"
    return "当前销售记录信息不足，暂不能形成可靠商机概览。需要补充完整客户沟通内容后再分析。"


def _confirmed_fact_phrases(crm_fields: CrmFields) -> list[str]:
    phrases: list[str] = []
    needs = _confirmed_values(crm_fields.customer_needs)
    scenarios = _confirmed_values(crm_fields.core_scenarios)
    if needs:
        phrases.append("已确认客户需求为" + "、".join(needs[:2]))
    if scenarios:
        phrases.append("核心场景为" + "、".join(scenarios[:2]))
    if crm_fields.budget.status == FieldStatus.CONFIRMED and crm_fields.budget.value:
        phrases.append(f"预算为{crm_fields.budget.value}")
    if crm_fields.timeline.status == FieldStatus.CONFIRMED and crm_fields.timeline.value:
        phrases.append(f"时间计划为{crm_fields.timeline.value}")
    if crm_fields.decision_maker.status == FieldStatus.CONFIRMED and crm_fields.decision_maker.name:
        role = f"（{crm_fields.decision_maker.role}）" if crm_fields.decision_maker.role else ""
        phrases.append(f"决策人已确认为{crm_fields.decision_maker.name}{role}")
    return phrases


def _confirmed_values(fields: list[ValidatedField]) -> list[str]:
    return [str(field.value) for field in fields if field.status == FieldStatus.CONFIRMED and field.value]


def _attention_phrase(result: ValidatedOpportunity, risk: OpportunityRisk | None) -> str:
    if risk:
        return "当前最需要关注的是" + risk.description.rstrip("。")
    if result.unconfirmed_info:
        values = [str(item.value) for item in result.unconfirmed_info[:2] if item.value]
        if values:
            return "当前仍需补齐" + "、".join(values)
    return ""


def _next_action_phrase(next_action: ConfirmedNextAction | None) -> str:
    if next_action is None:
        return ""
    parts = [f"下一步已确认{next_action.action}" if next_action.action != "待确认" else "下一步具体行动仍待确认"]
    if next_action.owner != "待确认":
        parts.append(f"负责人为{next_action.owner}")
    else:
        parts.append("负责人待确认")
    if next_action.time != "待确认":
        parts.append(f"时间为{next_action.time}")
    else:
        parts.append("时间待确认")
    return "，".join(parts)


def _compact_summary(sentences: list[str]) -> str:
    return "".join(sentence for sentence in sentences if sentence and sentence.strip())


def _sentences(summary: str) -> list[str]:
    return [part for part in re.split(r"[。！？!?]+", summary) if part.strip()]


def _validate_stage(summary: str, stage: StageResult | None) -> list[str]:
    errors: list[str] = []
    labels = {code.value: label for code, label in STAGE_LABELS.items()}
    if stage is None:
        for code, label in labels.items():
            if code in summary or label in summary:
                errors.append("stage_invented_when_stage_null")
                break
        return errors

    current_code = stage.code.value if stage.code else None
    current_label = stage.label
    for code, label in labels.items():
        if code != current_code and (code in summary or label in summary):
            errors.append("stage_changed")
            break
    if re.search(r"当前商机.*阶段", summary) and current_code and current_code not in summary and (current_label not in summary if current_label else True):
        errors.append("stage_omitted_after_stage_claim")
    return errors


def _validate_unknown_boundaries(summary: str, result: ValidatedOpportunity) -> list[str]:
    errors: list[str] = []
    decision = result.crm_fields.decision_maker
    if decision.status in {FieldStatus.UNKNOWN, FieldStatus.PARTIAL} and re.search(r"决策人(已确认|确认为|是|为)|最终(审批人|拍板人).*(是|为)", summary):
        errors.append("decision_maker_upgraded")
    if result.crm_fields.budget.status != FieldStatus.CONFIRMED and re.search(r"预算(为|是|约|大约|已落实|已确认)|\d+\s*(万|w|元)", summary, re.IGNORECASE):
        if result.crm_fields.budget.status != FieldStatus.CONFLICT:
            errors.append("budget_upgraded")
    if result.crm_fields.timeline.status != FieldStatus.CONFIRMED and re.search(r"(下周|本周|月底|月初|季度|上线|启动|完成|时间为|计划为)", summary):
        if result.crm_fields.timeline.status != FieldStatus.CONFLICT and not (result.confirmed_next_action and result.confirmed_next_action.time != "待确认"):
            errors.append("timeline_upgraded")
    for field in result.crm_fields.customer_needs + result.crm_fields.core_scenarios:
        if field.status in {FieldStatus.INFERRED, FieldStatus.UNKNOWN, FieldStatus.PARTIAL} and field.value and str(field.value) in summary and not re.search(r"(待确认|需确认|尚未确认|未确认|可能|推断)", summary):
            errors.append("unconfirmed_fact_upgraded")
            break
    return errors


def _validate_conflict_boundaries(summary: str, result: ValidatedOpportunity) -> list[str]:
    errors: list[str] = []
    conflict_fields = [result.crm_fields.budget, result.crm_fields.timeline]
    conflict_fields.extend(item for item in result.unconfirmed_info if item.status == FieldStatus.CONFLICT)
    has_conflict = any(field.status == FieldStatus.CONFLICT for field in conflict_fields) or any(risk.type == "conflict" for risk in result.opportunity_risks)
    if has_conflict and not re.search(r"(冲突|不一致|矛盾|需确认|待确认|不能.*选择|无法.*确认)", summary):
        errors.append("conflict_resolved_or_hidden")
    return errors


def _validate_protected_tokens(summary: str, context: dict[str, Any]) -> list[str]:
    allowed_text = _flatten_context_text(context)
    allowed_people_text = _allowed_people_text(context)
    errors: list[str] = []
    for token in _protected_number_tokens(summary):
        if token not in allowed_text and token.replace(" ", "") not in allowed_text.replace(" ", ""):
            errors.append(f"unauthorized_number:{token}")
    for token in _protected_person_tokens(summary):
        if token not in allowed_people_text:
            errors.append(f"unauthorized_person:{token}")
    return errors


def _flatten_context_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(_flatten_context_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_context_text(item) for item in value)
    return str(value)


def _allowed_people_text(context: dict[str, Any]) -> str:
    people: list[str] = []
    crm_fields = context.get("crm_fields", {})
    if isinstance(crm_fields, dict):
        decision_maker = crm_fields.get("decision_maker", {})
        if isinstance(decision_maker, dict):
            people.extend(str(decision_maker.get(key) or "") for key in ("name", "role"))
        influencers = crm_fields.get("influencers", [])
        if isinstance(influencers, list):
            for person in influencers:
                if isinstance(person, dict):
                    people.extend(str(person.get(key) or "") for key in ("name", "role"))
    next_action = context.get("confirmed_next_action")
    if isinstance(next_action, dict) and next_action.get("owner") != "待确认":
        people.append(str(next_action.get("owner") or ""))
    return " ".join(people)


def _protected_number_tokens(text: str) -> list[str]:
    pattern = r"\d+(?:\.\d+)?\s*(?:万|w|元|块|%|个月|周|天|月|号|日|季度|年|点|时|分钟)"
    return list(dict.fromkeys(match.group(0).strip() for match in re.finditer(pattern, text, re.IGNORECASE)))


def _protected_person_tokens(text: str) -> list[str]:
    tokens = re.findall(r"(?:IT\s*)?[王李张刘陈赵周吴郑孙][\u4e00-\u9fa5A-Za-z0-9]{0,2}(?:总|经理|工)", text)
    generic = {"客户", "销售", "负责人", "业务负责人", "技术负责人"}
    return [token for token in dict.fromkeys(tokens) if token not in generic and not token.startswith("当前")]


def _validate_next_action(summary: str, next_action: ConfirmedNextAction | None) -> list[str]:
    errors: list[str] = []
    if next_action is None and re.search(r"下一步(已|将|建议|应|需要|可).*?(安排|推进|确认|跟进|完成)", summary):
        errors.append("next_action_invented")
    if next_action is not None:
        if next_action.owner == "待确认" and re.search(r"负责人(为|是|由)[^，。；;]*(总|经理|工|负责人|审批人|拍板人|销售)", summary):
            errors.append("next_action_owner_invented")
        if next_action.time == "待确认" and re.search(r"(下周|本周|月底|月初|季度|明天|后天|\d+\s*(月|号|日|点))", summary):
            errors.append("next_action_time_invented")
    return errors
