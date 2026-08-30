from __future__ import annotations

import re
from uuid import uuid4

from .evidence import summarize_input, validate_evidence
from .input_builder import has_correction_intent
from .schemas import (
    AnalysisWarning,
    Attribution,
    CandidateFact,
    CandidateNextAction,
    CandidatePerson,
    Clarification,
    ClarificationQuestion,
    ConfirmedNextAction,
    CrmFields,
    CurrentValidity,
    DecisionStatus,
    EvidenceCandidate,
    Explicitness,
    FieldStatus,
    Polarity,
    PossibleConflict,
    RawExtraction,
    RecommendedNextAction,
    StageCode,
    STAGE_LABELS,
    StageResult,
    StageSignal,
    ValidatedField,
    ValidatedOpportunity,
    ValidatedPerson,
    OpportunityRisk,
)

S2_SIGNALS = {"demo_agreed", "trial_agreed", "technical_exchange_agreed", "solution_evaluation"}
S3_SIGNALS = {"budget_discussed", "quote_discussed", "procurement_discussed", "contract_terms_discussed"}
S4_SIGNALS = {"internal_project_approval", "vendor_decision"}
S5_SIGNALS = {"contract_signed", "order_confirmed"}

STAGE_DECISION_REASON_DESCRIPTIONS = {
    "insufficient_input": "输入文本本身过于残缺，无法正常解析销售拜访信息。",
    "insufficient_business_facts": "当前记录可以解析，但缺少客户需求、使用场景或推进动作等关键业务事实。",
    "insufficient_stage_signal": "当前记录已有部分业务事实，但不足以确认 S0-S5 销售阶段。",
    "stage_blocked_or_conflicting": "当前记录存在历史状态、项目暂停、预算受阻或关键信息冲突，暂时无法可靠判定当前阶段。",
}

STAGE_DECISION_REASON_ACTIONS = {
    "insufficient_input": "请补充完整的客户沟通内容、需求背景或推进状态。",
    "insufficient_business_facts": "请补充客户当前需求、核心场景或双方已经确认的下一步动作。",
    "insufficient_stage_signal": "请补充能够证明需求、方案验证、商务评估、审批或签约进展的事实。",
    "stage_blocked_or_conflicting": "请优先澄清项目当前是否仍有效推进，并确认冲突信息的真实状态。",
}

NO_STAGE_CONTEXT_SIGNALS = {"demand_invalidated", "demand_delayed", "budget_unavailable"}

SIMPLE_STAGE_PATTERNS: dict[str, tuple[str, ...]] = {
    "need_identified": (r"客户.*(问题|需求|希望|想|场景)", r"(处理慢|减少人工|智能问答|客服自动化需求|客服自动化方案|售后知识库)", r"有客服问题", r"客服问题"),
    "demo_agreed": (r"(客户|王总|李总|.*说).*(安排|约|同意|可以).*(Demo|演示)", r"(安排|约|同意|可以).*(Demo|演示)", r"已约.*Demo"),
    "trial_agreed": (r"(客户|.*说).*(同意|可以|安排|先).*(试用)", r"(同意|可以|安排|先).*试用"),
    "technical_exchange_agreed": (r"(客户|.*希望|.*同意|.*可以).*(技术交流|方案交流|技术同学)", r"做一次方案交流"),
    "solution_evaluation": (
        r"(客户|.*说).*(方案评估|评估方案|可以评估).*(方案|产品)",
        r"(客户|.*说|.*确认|.*希望|.*同意|.*可以).*(评估).*(方案|产品)",
        r"(方案评估|评估方案|可以评估|评估.*方案|评估.*产品).*(方案|产品)?",
    ),
    "budget_discussed": (r"预算.*\d+\s*万", r"\d+\s*万.*预算", r"讨论过预算", r"有.*预算"),
    "quote_discussed": (r"(问了|讨论|确认|需要).*报价",),
    "procurement_discussed": (r"(走|进入|确认|讨论).*采购流程",),
    "contract_terms_discussed": (r"(看|讨论|确认|评审).*合同条款",),
    "internal_project_approval": (r"进入.*(内部立项|内部审批|审批流程)", r"项目.*(内部立项|内部审批)", r"老板审批后就能定"),
    "vendor_decision": (r"进入.*供应商(评审|决策)", r"供应商(评审|决策)"),
    "contract_signed": (r"合同(已签|已经签完|签完)",),
    "order_confirmed": (r"(正式订单|订单).*(确认|已确认)",),
    "demand_invalidated": (r"项目暂停", r"需求失效", r"项目取消"),
    "budget_unavailable": (r"没有预算", r"暂无预算"),
    "demand_delayed": (r"等明年", r"延期到明年", r"明年再看"),
}


def build_validated_opportunity(
    original_text: str,
    raw: RawExtraction,
    *,
    analysis_id: str | None = None,
    revision: int = 1,
) -> ValidatedOpportunity:
    raw = _with_deterministic_user_confirmations(original_text, raw)
    raw = _with_deterministic_stage_and_people_hints(original_text, raw)
    raw = _with_deterministic_original_next_action_hints(original_text, raw)
    raw = _with_deterministic_original_timeline_hints(original_text, raw)
    evidence = validate_evidence(original_text, raw.evidence_candidates)
    for item in evidence:
        item.sufficient, item.insufficiency_reason = evaluate_evidence_sufficiency(item.field, item.quote)

    evidence_by_id = {item.id: item for item in evidence}
    valid_evidence_ids = {item.id for item in evidence if item.valid}
    sufficient_evidence_ids = {item.id for item in evidence if item.valid and item.sufficient}
    evidence_origins, evidence_positions = _evidence_context(original_text, evidence)
    raw_for_rules = _apply_user_fact_overrides(original_text, raw, evidence_origins, evidence_positions)
    raw_for_rules = _with_normalized_next_actions(raw_for_rules)
    raw_for_rules = _with_inferred_next_action_conflicts(raw_for_rules, sufficient_evidence_ids)

    confirmed_next_action = build_confirmed_next_action(raw_for_rules.candidate_next_actions, sufficient_evidence_ids, raw_for_rules.possible_conflicts)
    raw_for_rules = _without_timeline_next_action_pseudo_conflicts(raw_for_rules)
    conflict_fields = {_normalize_field_name(conflict.field) for conflict in raw_for_rules.possible_conflicts}
    crm_fields = build_crm_fields(raw_for_rules, sufficient_evidence_ids, conflict_fields, confirmed_next_action, evidence_by_id)
    stage = determine_stage(original_text, raw_for_rules.stage_signals, evidence_by_id, raw_for_rules.possible_conflicts)
    risks = build_opportunity_risks(raw_for_rules, valid_evidence_ids, sufficient_evidence_ids, stage)
    stage_decision_reason = determine_stage_decision_reason(original_text, raw_for_rules, valid_evidence_ids, sufficient_evidence_ids, stage)
    analysis_warnings = build_analysis_warnings(raw_for_rules, valid_evidence_ids, sufficient_evidence_ids, stage, stage_decision_reason)
    unconfirmed_info = build_unconfirmed_info(crm_fields, confirmed_next_action)
    recommended_next_actions: list[RecommendedNextAction] = []
    status = determine_status(original_text, stage, risks)
    clarification = build_clarification(status, risks, stage, crm_fields, unconfirmed_info, stage_decision_reason)

    return ValidatedOpportunity(
        analysis_id=analysis_id or str(uuid4()),
        revision=revision,
        status=status,
        summary=build_summary(stage, crm_fields, confirmed_next_action, risks, unconfirmed_info, analysis_warnings, stage_decision_reason),
        stage=stage,
        crm_fields=crm_fields,
        opportunity_risks=risks,
        analysis_warnings=analysis_warnings,
        confirmed_next_action=confirmed_next_action,
        recommended_next_actions=recommended_next_actions,
        unconfirmed_info=unconfirmed_info,
        evidence=evidence,
        clarification=clarification,
        developer_details={
            "stage_signals": [signal.model_dump() for signal in raw_for_rules.stage_signals],
            "valid_evidence_ids": sorted(valid_evidence_ids),
            "sufficient_evidence_ids": sorted(sufficient_evidence_ids),
            "stage_decision_reason": stage_decision_reason,
        },
    )


def _line_at(text: str, position: int) -> str:
    start = text.rfind("\n", 0, position) + 1
    end = text.find("\n", position)
    if end < 0:
        end = len(text)
    return text[start:end].strip()


def _next_evidence_id(raw: RawExtraction, prefix: str = "U") -> str:
    existing = {item.id for item in raw.evidence_candidates}
    index = 1
    while f"{prefix}{index:03d}" in existing:
        index += 1
    return f"{prefix}{index:03d}"


def _append_user_evidence(raw: RawExtraction, text: str, line: str, field: str) -> str:
    evidence_id = _next_evidence_id(raw)
    quote = line.strip()
    start_char = text.rfind(quote)
    raw.evidence_candidates.append(
        EvidenceCandidate(
            id=evidence_id,
            quote=quote,
            field=field,
            start_char=start_char if start_char >= 0 else None,
            end_char=start_char + len(quote) if start_char >= 0 else None,
        )
    )
    return evidence_id


def _append_evidence_once(raw: RawExtraction, quote: str, field: str) -> str:
    cleaned = quote.strip(" ：:，。；;\n")
    for item in raw.evidence_candidates:
        if item.quote == cleaned:
            return item.id
    evidence_id = _next_evidence_id(raw)
    raw.evidence_candidates.append(EvidenceCandidate(id=evidence_id, quote=cleaned, field=field))
    return evidence_id


def _append_evidence_once_for_field(raw: RawExtraction, quote: str, field: str) -> str:
    cleaned = quote.strip(" ：:，。；;\n")
    for item in raw.evidence_candidates:
        if item.quote == cleaned and item.field == field:
            return item.id
    evidence_id = _next_evidence_id(raw)
    raw.evidence_candidates.append(EvidenceCandidate(id=evidence_id, quote=cleaned, field=field))
    return evidence_id


def _extract_after_patterns(text: str, patterns: tuple[str, ...]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text.strip())
        if not match:
            continue
        value = match.group(1).strip(" ：:，。；;")
        if value:
            return value
    return None


def _looks_like_person_name(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text.strip(" ：:，。；;"))
    return (
        bool(normalized)
        and len(normalized) <= 12
        and not _looks_like_time_value(normalized)
        and not re.search(r"(时间|预算|行动|场景|需求|确认|确定|未定|未确定|待确认|待确定|未约定|约定)", normalized)
    )


def _looks_like_time_value(text: str | None) -> bool:
    normalized = re.sub(r"\s+", "", str(text or "").strip(" ：:，。；;"))
    if not normalized:
        return False
    return bool(
        re.search(
            r"(今天|明天|后天|昨天|本周|下周|上周|本月|下月|月底|月初|季度|周[一二三四五六日天]|星期[一二三四五六日天]|[0-9０-９]{1,2}\s*月\s*[0-9０-９]{1,2}\s*[日号]?|[0-9０-９]{1,2}\s*[日号]|上午|下午|中午|晚上|早上|[0-9０-９]{1,2}\s*点|[0-9０-９]{1,2}:[0-9０-９]{2})",
            normalized,
        )
    )


def _strip_correction_intro(text: str) -> str:
    parts = re.split(r"(?:写错了|记错了|录错了|填错了|有误|错误|不对)[，,]?", text, maxsplit=1)
    return parts[-1].strip() if len(parts) > 1 else text.strip()


def _clean_person_confirmation_value(value: str) -> str:
    normalized = _strip_correction_intro(value).strip(" ：:，。；;")
    patterns = (
        r"不是\s*([^，。；;]+)[，,]?(?:而是|是|应为|应该是|改为)\s*([^，。；;]+)",
        r"(?:最终|实际|真实|当前|本次)?(?:采购)?(?:决策人|审批人|拍板人|影响人|参与人|评估人)?(?:应该)?(?:是|为|应为|改为|确认为|确认是)\s*([^，。；;]+)",
        r"([^，。；;]{1,12})(?:是|为).{0,10}(?:最终采购决策人|最终审批人|拍板人|决策人|影响人|参与人|评估人)",
    )
    for index, pattern in enumerate(patterns):
        match = re.search(pattern, normalized)
        if not match:
            continue
        candidate = match.group(2 if index == 0 else 1).strip(" ：:，。；;")
        if _looks_like_person_name(candidate):
            return candidate
    return normalized


def _deterministic_signal_exists(raw: RawExtraction, signal_type: str, evidence_id: str) -> bool:
    return any(signal.signal_type == signal_type and signal.evidence_id == evidence_id for signal in raw.stage_signals)


def _append_stage_signal(raw: RawExtraction, signal_type: str, evidence_id: str) -> None:
    if _deterministic_signal_exists(raw, signal_type, evidence_id):
        return
    raw.stage_signals.append(
        StageSignal(
            signal_type=signal_type,  # type: ignore[arg-type]
            explicitness=Explicitness.EXPLICIT,
            polarity=Polarity.POSITIVE,
            attribution=Attribution.CUSTOMER,
            current_validity=CurrentValidity.ACTIVE,
            evidence_id=evidence_id,
        )
    )


def _clean_person_role(role: str | None) -> str | None:
    if not role:
        return None
    parts = [part.strip(" ：:，。；;、") for part in re.split(r"[、,，/]+", role) if part.strip(" ：:，。；;、")]
    normalized: list[str] = []
    for part in parts:
        if part == "采购" and any(existing in {"采购经理", "采购负责人"} for existing in normalized):
            continue
        if part in {"采购经理", "采购负责人"}:
            normalized = [existing for existing in normalized if existing != "采购"]
        if part not in normalized:
            normalized.append(part)
    return "、".join(normalized) or None


def _role_already_in_name(name: str, role: str) -> bool:
    compact_name = re.sub(r"\s+", "", name)
    compact_role = re.sub(r"\s+", "", role)
    if not compact_name or not compact_role:
        return False
    if compact_role == "IT" and compact_name.upper().startswith("IT"):
        return True
    return compact_name.startswith(compact_role)


def _normalize_person_name_role(name: str | None, role: str | None) -> tuple[str | None, str | None]:
    cleaned_name = (name or "").strip(" ：:，。；;、")
    cleaned_role = _clean_person_role(role)
    procurement_match = re.fullmatch(r"采购(?P<name>[\u4e00-\u9fa5]{1,3}经理)", cleaned_name)
    if procurement_match:
        cleaned_name = procurement_match.group("name")
        cleaned_role = _clean_person_role(cleaned_role or "采购")
    noisy_role_suffix = re.match(r"(?P<name>[\u4e00-\u9fa5A-Za-z\s]{1,12}(?:经理|总|工|主管))(?P<roles>(?:[、,，/](?:采购经理|采购|技术|IT|信息化|业务|客服|方案评估参与人))+)$", cleaned_name)
    if noisy_role_suffix:
        cleaned_name = noisy_role_suffix.group("name").strip()
        suffix_role = noisy_role_suffix.group("roles").strip("、,，/")
        cleaned_role = _clean_person_role("、".join([item for item in (cleaned_role, suffix_role) if item]))
    if cleaned_role:
        role_parts = [part for part in cleaned_role.split("、") if not _role_already_in_name(cleaned_name, part)]
        cleaned_role = "、".join(role_parts) or None
    return cleaned_name or None, cleaned_role


def _append_influencer_hint(raw: RawExtraction, quote: str, name: str, role: str) -> None:
    cleaned_name, cleaned_role = _normalize_person_name_role(name, role)
    if cleaned_name == "王工" and re.search(r"IT\s*王工", quote):
        cleaned_name = "IT 王工"
    if not cleaned_name:
        return
    evidence_id = _append_evidence_once(raw, quote, "influencers")
    raw.candidate_people.append(
        CandidatePerson(
            name=cleaned_name,
            role=cleaned_role,
            kind="influencer",
            authority_confirmed=False,
            evidence_id=evidence_id,
            attribution=Attribution.CUSTOMER,
            explicitness=Explicitness.EXPLICIT,
        )
    )


def _sentence_like_segments(text: str) -> list[str]:
    return [segment.strip(" ：:，。；;\n") for segment in re.split(r"[。！？\n]", text) if segment.strip(" ：:，。；;\n")]


def _segment_has_influencer_action(segment: str) -> bool:
    return bool(re.search(r"(复盘|方案评审|技术方案评估|方案评估|评估|试点|试用|验证|看效果|看方案|技术交流|方案交流|采购流程|采购申请|采购评审|采购决策|供应商选择|选型|比选|正式报价|付款方式|预算确认|立项预算|补充说|确认会)", segment))


def _person_role_mentions(segment: str) -> list[tuple[str, str]]:
    mentions: list[tuple[str, str]] = []
    patterns = (
        r"(?P<role>(?:教务运营|信息化|数字化|技术|IT|客服|业务|售前|产品)[^，。；、\n]{0,8}负责人)(?P<name>(?:[\u4e00-\u9fa5]{1,3}(?:经理|总|工|主管)|[A-Za-z]+\s*[\u4e00-\u9fa5]{1,3}工))",
        r"(?P<role>采购)(?P<name>[\u4e00-\u9fa5]{1,3}经理)",
        r"(?P<role>采购经理)(?P<name>[\u4e00-\u9fa5]{1,3}经理)",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, segment):
            mentions.append((match.group("name"), match.group("role")))
    return mentions


def _with_deterministic_stage_and_people_hints(original_text: str, raw: RawExtraction) -> RawExtraction:
    resolved = raw.model_copy(deep=True)
    for match in re.finditer(r"客户[^。！？\n]{0,80}(?:确认|希望|同意|可以)[^。！？\n]{0,40}评估[^。！？\n]{0,30}(?:正式采购方案|采购方案|技术方案|方案|产品)", original_text):
        evidence_id = _append_evidence_once(resolved, match.group(0), "stage")
        _append_stage_signal(resolved, "solution_evaluation", evidence_id)

    for segment in _sentence_like_segments(original_text):
        if not _segment_has_influencer_action(segment):
            continue
        for name, role in _person_role_mentions(segment):
            _append_influencer_hint(resolved, segment, name, role)

    for match in re.finditer(r"(?P<quote>让[^。！？；\n]{0,30}(?P<name>IT\s*[\u4e00-\u9fa5]{1,3}工|[\u4e00-\u9fa5]{1,3}工)[^。！？；\n]{0,18}(?:看效果|评估|试用|验证|看方案))", original_text):
        _append_influencer_hint(resolved, match.group("quote"), match.group("name"), "方案评估参与人")

    return resolved


def _with_deterministic_original_next_action_hints(original_text: str, raw: RawExtraction) -> RawExtraction:
    original_section = _original_visit_section(original_text)
    if not original_section:
        return raw
    resolved = raw.model_copy(deep=True)
    existing_event_keys = {_event_key(action.action) for action in resolved.candidate_next_actions if _event_key(action.action)}
    for segment in _sentence_like_segments(original_section):
        if "下一步" not in segment or not re.search(r"(确认|确定|约定|安排)", segment):
            continue
        action = _timeline_action_from_segment(segment)
        time = _extract_timeline_time(segment)
        owner = _extract_after_patterns(
            segment,
            (
                r"下一步[^，。；;]{0,20}由\s*([^，。；;]{1,20}?)(?=本周|下周|本月|下月|[0-9０-９]{1,2}\s*月|[0-9０-９]{1,2}\s*[日号])",
                r"下一步[^，。；;]{0,20}(?:负责人|责任人)(?:是|为)?\s*([^，。；;]+)",
            ),
        )
        if not action or not owner or not time:
            continue
        event_key = _event_key(action)
        if event_key and event_key in existing_event_keys:
            continue
        evidence_id = _append_evidence_once_for_field(resolved, segment, "next_action")
        resolved.candidate_next_actions = [
            candidate
            for candidate in resolved.candidate_next_actions
            if not (candidate.evidence_id == evidence_id and not _next_action_same_event(candidate.action, action))
        ]
        resolved.candidate_next_actions.append(
            CandidateNextAction(
                action=action,
                owner=_normalize_next_action_owner(owner),
                time=_normalize_next_action_time(time),
                evidence_id=evidence_id,
                attribution=Attribution.CUSTOMER,
                explicitness=Explicitness.EXPLICIT,
            )
        )
        if event_key:
            existing_event_keys.add(event_key)
    return resolved


def _original_visit_section(text: str) -> str:
    before_revisions = re.split(r"\n?【第\s*\d+\s*次分析", text, maxsplit=1)[0]
    return before_revisions.replace("【原始销售拜访记录】", "").strip()


def _extract_timeline_time(segment: str) -> str | None:
    match = re.search(
        r"(本周五前|本周[一二三四五六日天](?:上午|下午|晚上)?|下周[一二三四五六日天](?:上午|下午|晚上)?|本月底|月底|下月底|本月内|下月内|[0-9０-９]{1,2}\s*月\s*[0-9０-９]{1,2}\s*[日号]?(?:上午|下午|晚上)?|[0-9０-９]{1,2}\s*[日号](?:上午|下午|晚上)?|下季度|本季度)",
        segment,
    )
    return match.group(1).strip() if match else None


def _event_key(text: str | None) -> str | None:
    compact = re.sub(r"\s+", "", str(text or "").strip()).lower()
    if not compact or _unknown_next_action_value(compact):
        return None
    if "demo" in compact or "演示" in compact:
        return "demo"
    if "预算确认会" in compact or ("预算" in compact and "确认" in compact and "会" in compact):
        return "budget_confirmation_meeting"
    if "商务评估" in compact:
        return "business_evaluation"
    if "供应商选择" in compact or "供应商选型" in compact:
        return "vendor_selection"
    if "正式报价" in compact and "实施计划" in compact:
        return "quote_and_implementation_plan"
    if "正式报价" in compact:
        return "quote"
    return None


def _timeline_action_from_segment(segment: str) -> str | None:
    compact = re.sub(r"\s+", "", segment)
    if "Demo" in segment or "demo" in compact.lower() or "演示" in compact:
        return "安排产品 Demo"
    if "预算确认会" in compact:
        return "开预算确认会"
    if "供应商选择" in compact or "供应商选型" in compact:
        return "完成供应商选择"
    if "正式报价" in compact and "实施计划" in compact:
        return "发送正式报价和实施计划"
    if "商务评估" in compact:
        return "进行商务评估"
    return None


def _timeline_value_from_time_action(time: str, action: str) -> str:
    cleaned_time = time.strip(" ：:，。；;")
    cleaned_action = action.strip(" ：:，。；;")
    return f"{cleaned_time}{cleaned_action}"


def _timeline_matches_next_action(timeline_value: str | None, action: str | None) -> bool:
    timeline_key = _event_key(timeline_value)
    action_key = _event_key(action)
    return bool(timeline_key and action_key and timeline_key == action_key)


def _timeline_synced_to_next_action_time(timeline: ValidatedField, confirmed_next_action: ConfirmedNextAction | None) -> ValidatedField:
    if (
        timeline.status != FieldStatus.CONFIRMED
        or not timeline.value
        or not confirmed_next_action
        or confirmed_next_action.action == "待确认"
        or confirmed_next_action.time == "待确认"
        or not _timeline_matches_next_action(str(timeline.value), confirmed_next_action.action)
    ):
        return timeline
    synced_value = _timeline_value_from_time_action(confirmed_next_action.time, confirmed_next_action.action)
    if synced_value == timeline.value:
        return timeline
    return timeline.model_copy(update={"value": synced_value, "evidence_ids": _unique_ids(timeline.evidence_ids + confirmed_next_action.evidence_ids)})


def _with_deterministic_original_timeline_hints(original_text: str, raw: RawExtraction) -> RawExtraction:
    original_section = _original_visit_section(original_text)
    if not original_section:
        return raw
    resolved = raw.model_copy(deep=True)
    next_action_evidence_ids = _candidate_next_action_evidence_ids(resolved)
    if any(item.evidence_id not in next_action_evidence_ids for item in resolved.candidate_timeline):
        return resolved
    existing_values = {re.sub(r"\s+", "", item.value) for item in resolved.candidate_timeline}
    existing_event_keys = {_event_key(item.value) for item in resolved.candidate_timeline if _event_key(item.value)}
    for segment in _sentence_like_segments(original_section):
        time = _extract_timeline_time(segment)
        action = _timeline_action_from_segment(segment)
        if not time or not action:
            continue
        if _event_key(action) in existing_event_keys:
            continue
        value = _timeline_value_from_time_action(time, action)
        if re.sub(r"\s+", "", value) in existing_values:
            continue
        evidence_id = _append_evidence_once_for_field(resolved, segment, "timeline")
        resolved.candidate_timeline.append(
            CandidateFact(
                value=value,
                evidence_id=evidence_id,
                attribution=Attribution.CUSTOMER,
                explicitness=Explicitness.EXPLICIT,
                polarity=Polarity.POSITIVE,
                current_validity=CurrentValidity.ACTIVE,
            )
        )
        existing_values.add(re.sub(r"\s+", "", value))
        if event_key := _event_key(value):
            existing_event_keys.add(event_key)
    return resolved


def _parse_next_action_from_user_text(text: str, field_hint: str | None = None) -> tuple[str | None, str | None, str | None]:
    normalized = text.strip()
    compact = re.sub(r"\s+", "", normalized)
    if _unknown_next_action_value(compact) and not re.search(r"(进行|安排|推进|行动|负责人|责任人)", compact):
        if field_hint == "owner":
            return None, "待确认", None
        if field_hint == "time" or "时间" in compact or "约定" in compact:
            return None, None, "待确认"
        return None, None, None
    action = _extract_after_patterns(
        normalized,
        (
            r"客户已确认下一步(?:行动)?(?:是|为|进行|做|安排|推进)?\s*([^，。；;]+)",
            r"下一步(?:行动)?(?:是|为|进行|做|安排|推进|确认[:：为是]*)\s*([^，。；;]+)",
        ),
    )
    if action is None and field_hint in {"action", "next_action"}:
        bare_action = re.split(r"[，。；;]", normalized, maxsplit=1)[0].strip(" ：:，。；;")
        if bare_action and (field_hint == "action" or re.search(r"(安排|进行|推进|发送|提交|开|沟通|确认|评估|Demo|演示|试用|会议|报价)", bare_action, flags=re.IGNORECASE)):
            action = bare_action
    if action and ("负责人" in action or "责任人" in action or "时间" in action or re.search(r"(为|是)$", action)):
        action = None
    owner = _extract_after_patterns(
        normalized,
        (
            r"(?:建议)?负责人(?:是|为|确认为|确认是)\s*([^，。；;]+)",
            r"(?:建议)?负责人\s*(待确认|待确定|未确认|未确定|不确定|还没定|没确定)",
            r"责任人(?:是|为|确认为|确认是)\s*([^，。；;]+)",
            r"责任人\s*(待确认|待确定|未确认|未确定|不确定|还没定|没确定)",
            r"下一步行动负责人(?:是|为|确认为|确认是)\s*([^，。；;]+)",
        ),
    )
    time = _extract_after_patterns(
        normalized,
        (
            r"时间(?:是|为|确认为|确认是)\s*([^，。；;]+)",
            r"时间\s*(未确定|不确定|待确认|待确定|未确认|还没定|没确定|[^，。；;]+)",
        ),
    )
    if field_hint == "time" and time is None:
        bare_time = re.split(r"[，。；;]", normalized, maxsplit=1)[0].strip(" ：:，。；;")
        if bare_time and (_looks_like_time_value(bare_time) or _unknown_next_action_value(bare_time)):
            time = "待确认" if _unknown_next_action_value(bare_time) else bare_time
    if owner is not None and _looks_like_time_value(owner):
        owner = None
    if field_hint == "owner" and owner is None and action is None and time is None and _looks_like_person_name(normalized):
        owner = normalized.strip(" ：:，。；;")
    elif field_hint is None and owner is None and action is None and time is None and _looks_like_person_name(normalized):
        owner = normalized.strip(" ：:，。；;")
    if field_hint == "time" and time is None and _unknown_next_action_value(normalized):
        time = "待确认"
    return _normalize_next_action_action(action), _normalize_next_action_owner(owner), _normalize_next_action_time(time)


def _has_complete_next_action_values(action: CandidateNextAction) -> bool:
    return bool(
        action.action
        and not _unknown_next_action_value(action.action)
        and action.owner
        and not _unknown_next_action_value(action.owner)
        and action.time
        and not _unknown_next_action_value(action.time)
    )


def _complete_next_action_confirmation(action: CandidateNextAction, line: str) -> bool:
    if not _has_complete_next_action_values(action):
        return False
    normalized = re.sub(r"\s+", "", line.strip())
    directed_confirmation = normalized.startswith(("下一步行动确认", "下一步行动负责人确认", "下一步行动时间确认"))
    explicit_resolution = bool(re.search(r"(当前|真实|现在|本次|最终|最新|以.+为准)", normalized))
    return bool(
        (directed_confirmation or explicit_resolution)
        and re.search(r"(客户|对方|已|最终|当前|本次).{0,8}(确认|确定)", normalized)
        and "下一步" in normalized
        and re.search(r"(负责人|责任人)", normalized)
        and "时间" in normalized
    )


def _with_deterministic_user_confirmations(original_text: str, raw: RawExtraction) -> RawExtraction:
    if "【第 " not in original_text:
        return raw
    resolved = raw.model_copy(deep=True)
    for line in original_text.splitlines():
        stripped = line.strip()
        if "：" not in stripped and ":" not in stripped:
            continue
        label, value = re.split(r"[：:]", stripped, maxsplit=1)
        label = label.strip()
        value = value.strip()
        if not value or not re.search(r"(确认|修正)", label):
            continue
        is_correction = "修正" in label
        if is_correction and not has_correction_intent(value):
            continue

        if "决策人" in label:
            name = _extract_after_patterns(value, (r"(?:决策人|审批人|拍板人)(?:是|为)\s*([^，。；;]+)",)) or _clean_person_confirmation_value(value)
            evidence_id = _append_user_evidence(resolved, original_text, stripped, "decision_maker")
            resolved.candidate_people.append(CandidatePerson(name=name.strip(" ：:，。；;"), kind="decision_maker", authority_confirmed=True, evidence_id=evidence_id, attribution=Attribution.THIRD_PARTY, explicitness=Explicitness.EXPLICIT))
        elif "影响人" in label:
            name = _extract_after_patterns(value, (r"(?:影响人|参与人|评估人)(?:是|为)\s*([^，。；;]+)",)) or _clean_person_confirmation_value(value)
            evidence_id = _append_user_evidence(resolved, original_text, stripped, "influencers")
            resolved.candidate_people.append(CandidatePerson(name=name.strip(" ：:，。；;"), kind="influencer", authority_confirmed=False, evidence_id=evidence_id, attribution=Attribution.THIRD_PARTY, explicitness=Explicitness.EXPLICIT))
        elif "核心场景" in label:
            scenario = _extract_after_patterns(value, (r"(?:场景|核心场景)(?:是|为)\s*([^，。；;]+)",)) or value
            evidence_id = _append_user_evidence(resolved, original_text, stripped, "core_scenarios")
            resolved.candidate_scenarios.append(CandidateFact(value=scenario.strip(" ：:，。；;"), evidence_id=evidence_id, attribution=Attribution.THIRD_PARTY, explicitness=Explicitness.EXPLICIT, polarity=Polarity.POSITIVE, current_validity=CurrentValidity.ACTIVE))
        elif "客户需求" in label:
            need = _extract_after_patterns(value, (r"(?:需求|客户需求)(?:是|为)\s*([^，。；;]+)",)) or value
            evidence_id = _append_user_evidence(resolved, original_text, stripped, "customer_needs")
            resolved.candidate_needs.append(CandidateFact(value=need.strip(" ：:，。；;"), evidence_id=evidence_id, attribution=Attribution.THIRD_PARTY, explicitness=Explicitness.EXPLICIT, polarity=Polarity.POSITIVE, current_validity=CurrentValidity.ACTIVE))
        elif "预算" in label:
            budget = _extract_after_patterns(value, (r"预算(?:是|为)?\s*([^，。；;]+)",)) or value
            evidence_id = _append_user_evidence(resolved, original_text, stripped, "budget")
            resolved.candidate_budget.append(CandidateFact(value=budget.strip(" ：:，。；;"), evidence_id=evidence_id, attribution=Attribution.THIRD_PARTY, explicitness=Explicitness.EXPLICIT, polarity=Polarity.POSITIVE, current_validity=CurrentValidity.ACTIVE))
        elif "时间计划" in label:
            timeline = _strip_correction_intro(value) if is_correction else value
            evidence_id = _append_user_evidence(resolved, original_text, stripped, "timeline")
            resolved.candidate_timeline.append(CandidateFact(value=timeline.strip(" ：:，。；;"), evidence_id=evidence_id, attribution=Attribution.THIRD_PARTY, explicitness=Explicitness.EXPLICIT, polarity=Polarity.POSITIVE, current_validity=CurrentValidity.ACTIVE))
        elif "下一步行动负责人" in label:
            action, owner, time = _parse_next_action_from_user_text(value, "owner")
            owner = owner or _extract_after_patterns(value, (r"(?:下一步行动)?(?:建议)?负责人(?:是|为|确认为|确认是)\s*([^，。；;]+)", r"责任人(?:是|为|确认为|确认是)\s*([^，。；;]+)"))
            if owner is None and _looks_like_person_name(value):
                owner = value
            owner = _normalize_next_action_owner(owner) or "待确认"
            evidence_id = _append_user_evidence(resolved, original_text, stripped, "next_action")
            resolved.candidate_next_actions.append(CandidateNextAction(action=action or "待确认", owner=owner, time=time, evidence_id=evidence_id, attribution=Attribution.THIRD_PARTY, explicitness=Explicitness.EXPLICIT))
        elif "下一步行动时间" in label:
            action, owner, time = _parse_next_action_from_user_text(value, "time")
            time = time or _extract_after_patterns(value, (r"(?:下一步行动)?时间(?:是|为|确认为|确认是)\s*([^，。；;]+)", r"时间\s*(未确定|不确定|待确认|待确定|未确认|还没定|没确定|未约定|尚未约定|未定)")) or value
            time = "待确认" if _unknown_next_action_value(time) else time.strip(" ：:，。；;")
            evidence_id = _append_user_evidence(resolved, original_text, stripped, "next_action")
            resolved.candidate_next_actions.append(CandidateNextAction(action=action or "待确认", owner=owner, time=time, evidence_id=evidence_id, attribution=Attribution.THIRD_PARTY, explicitness=Explicitness.EXPLICIT))
        elif "下一步行动" in label or "补充信息" in label:
            if "补充信息" in label and not re.search(r"(已确认|已确定|确认|确定|下一步|负责人|责任人|时间)", value):
                continue
            hint = "owner" if "负责人" in label or "责任人" in label else "time" if "时间" in label else "next_action" if "下一步行动" in label else None
            action, owner, time = _parse_next_action_from_user_text(value, hint)
            if action or owner or time:
                evidence_id = _append_user_evidence(resolved, original_text, stripped, "next_action")
                resolved.candidate_next_actions.append(CandidateNextAction(action=action or "待确认", owner=owner, time=time, evidence_id=evidence_id, attribution=Attribution.THIRD_PARTY, explicitness=Explicitness.EXPLICIT))
    return resolved


def _qualified_correction_text(text: str) -> bool:
    return has_correction_intent(text)


def _evidence_context(original_text: str, evidence: list[object]) -> tuple[dict[str, str], dict[str, int]]:
    markers = [(match.start(), match.group(1)) for match in re.finditer(r"【([^】]+)】", original_text)]
    origins: dict[str, str] = {}
    positions: dict[str, int] = {}
    for item in evidence:
        evidence_id = getattr(item, "id", None)
        start_char = getattr(item, "start_char", None)
        if not evidence_id:
            continue
        if isinstance(start_char, int):
            positions[evidence_id] = start_char
        origin = "original"
        if isinstance(start_char, int):
            previous_markers = [label for position, label in markers if position <= start_char]
            label = previous_markers[-1] if previous_markers else ""
            if "修正识别" in label or "用户修正识别" in label:
                origin = "user_correction" if _qualified_correction_text(_line_at(original_text, start_char)) else "user_supplement"
            elif "补充确认" in label or "后续补充" in label:
                line = _line_at(original_text, start_char)
                origin = "user_supplement" if line.startswith(("补充信息", "其他补充信息")) and not _qualified_correction_text(line) else "user_confirmation"
        origins[evidence_id] = origin
    return origins, positions


def _user_origin(evidence_id: str | None, evidence_origins: dict[str, str]) -> bool:
    return evidence_origins.get(evidence_id or "") in {"user_correction", "user_confirmation"}


def _normalize_field_name(field: str | None) -> str:
    normalized = (field or "").strip().lower()
    aliases = {
        "candidate_budget": "budget",
        "customer_budget": "budget",
        "candidate_timeline": "timeline",
        "customer_timeline": "timeline",
        "candidate_next_actions": "next_action",
        "confirmed_next_action": "next_action",
        "next_actions": "next_action",
        "customer_needs": "customer_needs",
        "candidate_needs": "customer_needs",
        "candidate_scenarios": "core_scenarios",
        "core_scenario": "core_scenarios",
        "candidate_people": "decision_maker",
        "person": "decision_maker",
    }
    return aliases.get(normalized, normalized)


def _evidence_field_map(raw: RawExtraction) -> dict[str, str]:
    return {item.id: _normalize_field_name(item.field) for item in raw.evidence_candidates}


def _conflict_mentions_resolved_field(conflict: PossibleConflict, resolved_field: str, evidence_fields: dict[str, str]) -> bool:
    field = _normalize_field_name(conflict.field)
    evidence_scoped_fields = {_normalize_field_name(evidence_fields.get(evidence_id)) for evidence_id in conflict.evidence_ids}
    text = f"{conflict.field} {conflict.description}"
    keywords = {
        "budget": ("预算", "金额"),
        "timeline": ("时间", "计划", "商务评估"),
        "decision_maker": ("决策", "审批", "拍板"),
        "customer_needs": ("需求",),
        "core_scenarios": ("场景",),
    }
    if field == resolved_field or resolved_field in evidence_scoped_fields:
        return True
    if field in {"", "risk", "stage", "conflict", "unknown"}:
        return any(keyword in text for keyword in keywords.get(resolved_field, ()))
    return False


def _latest_user_facts(items: list[CandidateFact], evidence_origins: dict[str, str], evidence_positions: dict[str, int]) -> list[CandidateFact]:
    user_items = [item for item in items if _user_origin(item.evidence_id, evidence_origins)]
    if not user_items:
        return []
    latest_position = max(evidence_positions.get(item.evidence_id or "", -1) for item in user_items)
    return [item for item in user_items if evidence_positions.get(item.evidence_id or "", -1) == latest_position]


def _latest_user_actions(items: list[CandidateNextAction], evidence_origins: dict[str, str], evidence_positions: dict[str, int]) -> list[CandidateNextAction]:
    user_items = [item for item in items if evidence_origins.get(item.evidence_id or "").startswith("user_")]
    if not user_items:
        return []
    latest_position = max(evidence_positions.get(item.evidence_id or "", -1) for item in user_items)
    return [item for item in user_items if evidence_positions.get(item.evidence_id or "", -1) == latest_position]


def _qualified_user_origin(evidence_id: str | None, evidence_origins: dict[str, str]) -> bool:
    return evidence_origins.get(evidence_id or "") in {"user_correction", "user_confirmation"}


def _next_action_resolution_intent(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text.strip())
    if has_correction_intent(normalized):
        return True
    patterns = (
        r"(当前|真实|现在|本次).{0,16}(负责人|责任人|行动|时间).{0,8}(是|为|确认|确定)",
        r"(最终|最新).{0,16}(确认|确定)",
        r"(之前|前面|原来|上一版|前述).{0,18}(作废|无效|不算|取消)",
        r"(负责人|责任人|行动|时间).{0,8}(改为|调整为|更正为|确认为)",
        r"以.{1,30}为准",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def _next_action_field_confirmation(line: str, field: str) -> bool:
    normalized = re.sub(r"\s+", "", line.strip())
    if normalized.startswith("下一步行动负责人确认"):
        return field == "owner"
    if normalized.startswith("下一步行动时间确认"):
        return field == "time"
    if not normalized.startswith("下一步行动确认"):
        return False
    if field == "owner":
        return bool(re.search(r"(负责人|责任人|^[^：:]+[：:].{1,12}$)", normalized))
    if field == "time":
        return "时间" in normalized
    if field == "action":
        return "行动" in normalized and not re.search(r"(负责人|责任人|时间)", normalized)
    return False


def _next_action_field_supersedes_prior(line: str, field: str) -> bool:
    normalized = re.sub(r"\s+", "", line.strip())
    if _next_action_field_confirmation(line, field):
        return True
    if not re.search(r"(当前|真实|现在|本次|最终|最新|以.+为准|作废|无效|不算|取消)", normalized):
        return False
    if field == "owner":
        return "负责人" in normalized or "责任人" in normalized
    if field == "time":
        return "时间" in normalized
    if field == "action":
        return "行动" in normalized
    return False


def _is_next_action_conflict(conflict: PossibleConflict) -> bool:
    field = _normalize_field_name(conflict.field)
    text = f"{conflict.field} {conflict.description}"
    return field.startswith("next_action") or "下一步" in text or ("负责人" in text and ("行动" in text or "商务评估" in text))


def _timeline_item_from_next_action_user_line(
    item: CandidateFact,
    original_text: str,
    evidence_origins: dict[str, str],
    evidence_positions: dict[str, int],
) -> bool:
    evidence_id = item.evidence_id or ""
    if not evidence_origins.get(evidence_id, "").startswith("user_"):
        return False
    line = _line_at(original_text, evidence_positions.get(evidence_id, -1))
    compact = re.sub(r"\s+", "", line)
    return "下一步行动" in compact and "时间计划" not in compact


def _apply_user_fact_overrides(original_text: str, raw: RawExtraction, evidence_origins: dict[str, str], evidence_positions: dict[str, int]) -> RawExtraction:
    resolved = raw.model_copy(deep=True)
    resolved_fields: set[str] = set()
    evidence_fields = _evidence_field_map(resolved)
    resolved.candidate_timeline = [
        item
        for item in resolved.candidate_timeline
        if not _timeline_item_from_next_action_user_line(item, original_text, evidence_origins, evidence_positions)
    ]
    for field_name, attr in (
        ("customer_needs", "candidate_needs"),
        ("core_scenarios", "candidate_scenarios"),
        ("budget", "candidate_budget"),
        ("timeline", "candidate_timeline"),
    ):
        latest = _latest_user_facts(getattr(resolved, attr), evidence_origins, evidence_positions)
        if latest:
            for item in latest:
                item.attribution = Attribution.THIRD_PARTY
                item.current_validity = CurrentValidity.ACTIVE
            setattr(resolved, attr, latest)
            resolved_fields.add(field_name)
    user_decision_people = [
        person
        for person in resolved.candidate_people
        if person.kind == "decision_maker" and _user_origin(person.evidence_id, evidence_origins)
    ]
    if user_decision_people:
        latest_position = max(evidence_positions.get(person.evidence_id or "", -1) for person in user_decision_people)
        latest_people = [
            person
            for person in user_decision_people
            if evidence_positions.get(person.evidence_id or "", -1) == latest_position
        ]
        for person in latest_people:
            person.attribution = Attribution.THIRD_PARTY
        resolved.candidate_people = latest_people + [
            person
            for person in resolved.candidate_people
            if person.kind == "influencer"
        ]
        resolved_fields.add("decision_maker")
    latest_actions = _latest_user_actions(resolved.candidate_next_actions, evidence_origins, evidence_positions)
    latest_action_lines = [_line_at(original_text, evidence_positions.get(action.evidence_id or "", -1)) for action in latest_actions]
    latest_actions_resolve_previous = bool(latest_actions) and all(
        evidence_origins.get(action.evidence_id or "") == "user_correction"
        or _next_action_resolution_intent(line)
        or _complete_next_action_confirmation(action, line)
        for action, line in zip(latest_actions, latest_action_lines)
    )
    if latest_actions_resolve_previous:
        for action in latest_actions:
            action.attribution = Attribution.THIRD_PARTY
        resolved.candidate_next_actions = latest_actions
        resolved_fields.add("next_action")
    else:
        for action in resolved.candidate_next_actions:
            origin = evidence_origins.get(action.evidence_id or "")
            if origin.startswith("user_"):
                action.attribution = Attribution.THIRD_PARTY
    latest_field_values: dict[str, tuple[str, int]] = {}
    for action in resolved.candidate_next_actions:
        evidence_id = action.evidence_id or ""
        if not evidence_origins.get(evidence_id, "").startswith("user_"):
            continue
        line = _line_at(original_text, evidence_positions.get(evidence_id, -1))
        position = evidence_positions.get(evidence_id, -1)
        for field, value in (("action", action.action), ("owner", action.owner), ("time", action.time)):
            if value is None or (field == "action" and _unknown_next_action_value(value)):
                continue
            if _next_action_field_supersedes_prior(line, field):
                current = latest_field_values.get(field)
                if current is None or position > current[1]:
                    latest_field_values[field] = (str(value), position)
    if latest_field_values:
        resolving_fields = {field for field, (value, _) in latest_field_values.items() if not _unknown_next_action_value(value)}
        for action in resolved.candidate_next_actions:
            position = evidence_positions.get(action.evidence_id or "", -1)
            if "owner" in resolving_fields and position < latest_field_values["owner"][1]:
                action.owner = None
            if "action" in resolving_fields and position < latest_field_values["action"][1]:
                action.action = "待确认"
            if "time" in resolving_fields and position < latest_field_values["time"][1]:
                action.time = None
        resolved.candidate_next_actions = [
            action
            for action in resolved.candidate_next_actions
            if not _empty_next_action_field_placeholder(action, original_text, evidence_positions)
        ]
        resolved.possible_conflicts = [
            conflict
            for conflict in resolved.possible_conflicts
            if not (
                _is_next_action_conflict(conflict)
                and (fields := _next_action_conflict_fields([conflict]))
                and fields <= resolving_fields
            )
        ]
    if resolved_fields:
        resolved.possible_conflicts = [
            conflict
            for conflict in resolved.possible_conflicts
            if not any(_conflict_mentions_resolved_field(conflict, field, evidence_fields) for field in resolved_fields)
            and not ("next_action" in resolved_fields and _is_next_action_conflict(conflict))
        ]
    return resolved


def _empty_next_action_field_placeholder(action: CandidateNextAction, original_text: str, evidence_positions: dict[str, int]) -> bool:
    if not _unknown_next_action_value(action.action) or action.owner is not None or action.time is not None:
        return False
    line = _line_at(original_text, evidence_positions.get(action.evidence_id or "", -1))
    compact = re.sub(r"\s+", "", line)
    return "下一步行动负责人" in compact or "下一步行动时间" in compact


def _candidate_action_confirmed(action: CandidateNextAction, sufficient_evidence_ids: set[str]) -> bool:
    return (
        action.evidence_id in sufficient_evidence_ids
        and action.attribution in {Attribution.CUSTOMER, Attribution.THIRD_PARTY}
        and action.explicitness == Explicitness.EXPLICIT
    )


def _confirmed_actions(actions: list[CandidateNextAction], sufficient_evidence_ids: set[str]) -> list[CandidateNextAction]:
    return [action for action in actions if _candidate_action_confirmed(action, sufficient_evidence_ids)]


def _unique_non_empty(values: list[str | None]) -> list[str]:
    return list(dict.fromkeys(str(value).strip() for value in values if value and str(value).strip()))


def _unknown_next_action_value(value: str | None) -> bool:
    if value is None:
        return True
    normalized = re.sub(r"\s+", "", str(value).strip())
    if not normalized:
        return True
    return bool(re.search(r"(待确认|待确定|未确认|不确定|未确定|未定|没确定|没有确定|还没定|尚未确定|未约定|尚未约定|没约定|暂无|暂未)", normalized))


def _normalize_next_action_action(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip(" ：:，。；;")
    if not cleaned:
        return None
    if _unknown_next_action_value(cleaned):
        return "待确认"
    compact = re.sub(r"\s+", "", cleaned)
    if "商务评估" in compact:
        return "进行商务评估"
    if re.search(r"产品?demo", compact, flags=re.IGNORECASE) and re.search(r"(安排|约|看|演示)", compact):
        return "安排产品 Demo"
    return cleaned


def _normalize_next_action_owner(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip(" ：:，。；;")
    if not cleaned:
        return None
    if _unknown_next_action_value(cleaned):
        return "待确认"
    if _looks_like_time_value(cleaned):
        return None
    cleaned = re.sub(r"^(?:建议)?(?:负责人|责任人)(?:是|为)?", "", cleaned).strip(" ：:，。；;")
    cleaned = re.sub(r"^(?:销售顾问|销售负责人|客户经理|项目负责人|商务负责人|售前负责人|实施负责人|负责人|责任人)", "", cleaned).strip(" ：:，。；;")
    return cleaned or None


def _normalize_next_action_time(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip(" ：:，。；;")
    if not cleaned:
        return None
    return "待确认" if _unknown_next_action_value(cleaned) else cleaned


def _normalize_next_action_candidate(action: CandidateNextAction) -> CandidateNextAction:
    action.action = _normalize_next_action_action(action.action) or "待确认"
    action.owner = _normalize_next_action_owner(action.owner)
    action.time = _normalize_next_action_time(action.time)
    return action


def _with_normalized_next_actions(raw: RawExtraction) -> RawExtraction:
    resolved = raw.model_copy(deep=True)
    for action in resolved.candidate_next_actions:
        _normalize_next_action_candidate(action)
    return resolved


def _explicit_next_action_values(values: list[str | None], field: str | None = None) -> list[str]:
    normalized_values: list[str | None] = []
    for value in values:
        if field == "action":
            normalized_values.append(_normalize_next_action_action(value))
        elif field == "owner":
            normalized_values.append(_normalize_next_action_owner(value))
        elif field == "time":
            normalized_values.append(_normalize_next_action_time(value))
        else:
            normalized_values.append(value)
    return _unique_non_empty([value for value in normalized_values if not _unknown_next_action_value(value)])


def _explicit_unknown_next_action_values(values: list[str | None], field: str | None = None) -> list[str]:
    normalized_values: list[str | None] = []
    for value in values:
        if field == "action":
            normalized_values.append(_normalize_next_action_action(value))
        elif field == "owner":
            normalized_values.append(_normalize_next_action_owner(value))
        elif field == "time":
            normalized_values.append(_normalize_next_action_time(value))
        else:
            normalized_values.append(value)
    return _unique_non_empty([value for value in normalized_values if value is not None and _unknown_next_action_value(value)])


def _next_action_field_sequence(actions: list[CandidateNextAction], field: str) -> list[str]:
    values: list[str] = []
    for action in actions:
        if field == "action":
            value = _normalize_next_action_action(action.action)
            if value is not None and _unknown_next_action_value(value) and (action.owner is not None or action.time is not None):
                continue
        elif field == "owner":
            value = _normalize_next_action_owner(action.owner)
        elif field == "time":
            value = _normalize_next_action_time(action.time)
        else:
            value = None
        if value is not None:
            values.append(value)
    return values


def _latest_unknown_after_concrete(values: list[str]) -> bool:
    concrete_seen = any(not _unknown_next_action_value(value) for value in values[:-1])
    return bool(values and concrete_seen and _unknown_next_action_value(values[-1]))


def _field_has_material_next_action_conflict(actions: list[CandidateNextAction], field: str) -> bool:
    values = _next_action_field_sequence(actions, field)
    concrete_values = _unique_non_empty([value for value in values if not _unknown_next_action_value(value)])
    return len(concrete_values) > 1 or _latest_unknown_after_concrete(values)


def _infer_next_action_conflict_fields(actions: list[CandidateNextAction], sufficient_evidence_ids: set[str]) -> set[str]:
    confirmed = _confirmed_actions(actions, sufficient_evidence_ids)
    fields: set[str] = set()
    if _field_has_material_next_action_conflict(confirmed, "action"):
        fields.add("action")
    if _field_has_material_next_action_conflict(confirmed, "owner"):
        fields.add("owner")
    if _field_has_material_next_action_conflict(confirmed, "time"):
        fields.add("time")
    return fields


def _with_inferred_next_action_conflicts(raw: RawExtraction, sufficient_evidence_ids: set[str]) -> RawExtraction:
    inferred_fields = _infer_next_action_conflict_fields(raw.candidate_next_actions, sufficient_evidence_ids)
    if not inferred_fields:
        return raw
    existing_fields = _material_next_action_conflict_fields(raw.candidate_next_actions, sufficient_evidence_ids, raw.possible_conflicts)
    missing_fields = inferred_fields - existing_fields
    if not missing_fields:
        return raw
    resolved = raw.model_copy(deep=True)
    evidence_ids = _unique_ids([action.evidence_id for action in _confirmed_actions(resolved.candidate_next_actions, sufficient_evidence_ids) if action.evidence_id])
    descriptions = {
        "action": "下一步行动存在多个不一致表述",
        "owner": "下一步行动负责人存在多个不一致表述",
        "time": "下一步行动时间存在多个不一致表述",
    }
    for field in sorted(missing_fields):
        resolved.possible_conflicts.append(PossibleConflict(field=f"next_action.{field}", description=descriptions[field], evidence_ids=evidence_ids))
    return resolved


def _candidate_next_action_evidence_ids(raw: RawExtraction) -> set[str]:
    return {action.evidence_id for action in raw.candidate_next_actions if action.evidence_id}


def _without_timeline_next_action_pseudo_conflicts(raw: RawExtraction) -> RawExtraction:
    next_action_ids = _candidate_next_action_evidence_ids(raw)
    if not next_action_ids:
        return raw
    timeline_ids = {item.evidence_id for item in raw.candidate_timeline if item.evidence_id}
    independent_timeline_ids = timeline_ids - next_action_ids
    if not independent_timeline_ids:
        return raw
    kept = [
        conflict
        for conflict in raw.possible_conflicts
        if not (
            _normalize_field_name(conflict.field) == "timeline"
            and any(evidence_id in next_action_ids for evidence_id in conflict.evidence_ids)
        )
    ]
    if len(kept) == len(raw.possible_conflicts):
        return raw
    resolved = raw.model_copy(deep=True)
    resolved.possible_conflicts = kept
    return resolved


def _next_action_conflict_fields(conflicts: list[PossibleConflict]) -> set[str]:
    fields: set[str] = set()
    for conflict in conflicts:
        field = _normalize_field_name(conflict.field)
        description = conflict.description
        if _is_next_action_conflict(conflict):
            if "owner" in field or "负责人" in conflict.field or "负责人" in description:
                fields.add("owner")
            elif "time" in field or "时间" in conflict.field or "时间" in description:
                fields.add("time")
            elif "action" in field or "行动" in conflict.field or "行动" in description:
                fields.add("action")
            else:
                fields.update({"action", "owner", "time"})
    return fields


def _material_next_action_conflict_fields(
    actions: list[CandidateNextAction],
    sufficient_evidence_ids: set[str],
    conflicts: list[PossibleConflict],
) -> set[str]:
    fields: set[str] = set()
    for conflict in conflicts:
        if not _is_next_action_conflict(conflict):
            continue
        scoped_actions = _confirmed_actions(actions, set(conflict.evidence_ids) & sufficient_evidence_ids) if conflict.evidence_ids else _confirmed_actions(actions, sufficient_evidence_ids)
        if not scoped_actions:
            scoped_actions = _confirmed_actions(actions, sufficient_evidence_ids)
        field = _normalize_field_name(conflict.field)
        description = conflict.description
        if ("owner" in field or "负责人" in conflict.field or "负责人" in description) and _field_has_material_next_action_conflict(scoped_actions, "owner"):
            fields.add("owner")
        if ("time" in field or "时间" in conflict.field or "时间" in description) and _field_has_material_next_action_conflict(scoped_actions, "time"):
            fields.add("time")
        if ("action" in field or "行动" in conflict.field or "行动" in description) and _field_has_material_next_action_conflict(scoped_actions, "action"):
            fields.add("action")
        if field == "next_action":
            if _field_has_material_next_action_conflict(scoped_actions, "owner"):
                fields.add("owner")
            if _field_has_material_next_action_conflict(scoped_actions, "time"):
                fields.add("time")
            if _field_has_material_next_action_conflict(scoped_actions, "action"):
                fields.add("action")
    return fields


def _next_action_conflict_fields_from_context(raw: RawExtraction, conflict: PossibleConflict) -> set[str]:
    fields = _next_action_conflict_fields([conflict])
    if fields:
        return fields
    next_action_ids = _candidate_next_action_evidence_ids(raw)
    if conflict.evidence_ids and not any(evidence_id in next_action_ids for evidence_id in conflict.evidence_ids):
        return set()
    if not conflict.evidence_ids:
        return set()
    text = f"{conflict.field} {conflict.description}"
    scoped_actions = _confirmed_actions(raw.candidate_next_actions, set(conflict.evidence_ids))
    if not scoped_actions:
        return set()
    fields = set()
    if re.search(r"(负责人|责任人|owner)", text, re.IGNORECASE):
        fields.add("owner")
    if re.search(r"(时间|日期|time)", text, re.IGNORECASE):
        fields.add("time")
    if re.search(r"(下一步|行动|动作|action)", text, re.IGNORECASE):
        fields.add("action")
    if not fields:
        if _field_has_material_next_action_conflict(scoped_actions, "owner"):
            fields.add("owner")
        if _field_has_material_next_action_conflict(scoped_actions, "time"):
            fields.add("time")
        if _field_has_material_next_action_conflict(scoped_actions, "action"):
            fields.add("action")
    return fields


def _next_action_conflict_for_fields(conflict: PossibleConflict, fields: set[str]) -> PossibleConflict:
    if len(fields) == 1:
        field = f"next_action.{next(iter(fields))}"
    else:
        field = "next_action"
    return PossibleConflict(field=field, description=conflict.description, evidence_ids=conflict.evidence_ids)


def _risk_specificity_score(risk: OpportunityRisk) -> int:
    score = 0
    if "下一步行动" in risk.description:
        score += 4
    if "存在多个不一致表述" in risk.description:
        score += 2
    if "需确认当前真实" in risk.description:
        score += 1
    score += min(len(risk.evidence_ids), 3)
    return score


def evaluate_evidence_sufficiency(field: str, quote: str) -> tuple[bool, str | None]:
    stripped = quote.strip()
    if field == "person" and len(stripped) >= 2:
        return True, None
    if len(stripped) < 3:
        return False, "证据片段过短，无法支撑业务结论。"
    if field in {"stage", "budget"} and stripped in {"预算", "审批", "报价", "Demo", "演示", "试用"}:
        return False, "单个关键词不足以支撑阶段或预算结论。"
    if field == "decision_maker" and stripped in {"王总", "李总", "老板"}:
        return False, "仅出现人物称呼不能证明决策权限。"
    return True, None


def _is_confirmed_fact(item: CandidateFact, sufficient_evidence_ids: set[str]) -> bool:
    return (
        item.evidence_id in sufficient_evidence_ids
        and item.attribution in {Attribution.CUSTOMER, Attribution.THIRD_PARTY}
        and item.explicitness == Explicitness.EXPLICIT
        and item.polarity == Polarity.POSITIVE
        and item.current_validity in {CurrentValidity.ACTIVE, CurrentValidity.UNKNOWN}
    )


def _signal_has_sufficient_evidence(signal: StageSignal, evidence_by_id: dict[str, object]) -> bool:
    if not signal.evidence_id or signal.evidence_id not in evidence_by_id:
        return False
    evidence = evidence_by_id[signal.evidence_id]
    if not getattr(evidence, "valid", False):
        return False
    quote = getattr(evidence, "quote", "")
    patterns = SIMPLE_STAGE_PATTERNS.get(signal.signal_type, ())
    if not patterns:
        return getattr(evidence, "sufficient", False)
    return any(re.search(pattern, quote) for pattern in patterns)


def _valid_positive_stage_signal(signal: StageSignal, evidence_by_id: dict[str, object]) -> bool:
    return (
        _signal_has_sufficient_evidence(signal, evidence_by_id)
        and signal.explicitness == Explicitness.EXPLICIT
        and signal.polarity == Polarity.POSITIVE
        and signal.attribution in {Attribution.CUSTOMER, Attribution.THIRD_PARTY}
        and signal.current_validity == CurrentValidity.ACTIVE
    )


def _has_blocking_signal(signals: list[StageSignal], evidence_by_id: dict[str, object]) -> bool:
    return any(
        signal.signal_type in {"demand_invalidated", "budget_unavailable", "demand_delayed"}
        and _signal_has_sufficient_evidence(signal, evidence_by_id)
        and signal.attribution in {Attribution.CUSTOMER, Attribution.THIRD_PARTY}
        for signal in signals
    )


def _minimum_analyzable(original_text: str, valid_signals: list[StageSignal]) -> bool:
    text = original_text.strip()
    normal_chars = re.sub(r"[\s。！？,.，、…]", "", text)
    if "……" in text and len(normal_chars) <= 8:
        return False
    if valid_signals:
        return True
    if len(text) < 8:
        return False
    contact_patterns = (
        r"(和|与).{0,20}客户.{0,12}(沟通|交流|会面|通话|电话沟通|微信沟通|当面交流)",
        r"客户.{0,12}(沟通|交流|会面|通话|电话沟通|微信沟通|当面交流)",
        r"(拜访|介绍|加了微信|初步接触|认识|接触)",
    )
    return any(re.search(pattern, text) for pattern in contact_patterns)


def determine_stage(
    original_text: str,
    signals: list[StageSignal],
    evidence_by_id: dict[str, object],
    conflicts: list[PossibleConflict],
) -> StageResult | None:
    valid_signals = [signal for signal in signals if _valid_positive_stage_signal(signal, evidence_by_id)]
    if not _minimum_analyzable(original_text, valid_signals):
        return None

    by_type = {signal.signal_type: signal for signal in valid_signals}
    conflict_fields = {_normalize_field_name(conflict.field) for conflict in conflicts}

    for signal_type in S5_SIGNALS:
        if signal_type in by_type:
            return _stage(StageCode.S5, "合同或正式订单已确认。", [by_type[signal_type].evidence_id])

    for signal_type in S4_SIGNALS:
        if signal_type in by_type:
            return _stage(StageCode.S4, "已进入内部立项、审批或供应商决策。", [by_type[signal_type].evidence_id])

    s3_blocked = _has_blocking_signal(signals, evidence_by_id) or "budget" in conflict_fields
    if not s3_blocked:
        for signal_type in S3_SIGNALS:
            if signal_type in by_type:
                return _stage(StageCode.S3, "已讨论预算、报价、采购流程或合同条款之一，且需求仍有效。", [by_type[signal_type].evidence_id])

    for signal_type in S2_SIGNALS:
        if signal_type in by_type:
            return _stage(StageCode.S2, "客户明确同意演示、试用、技术交流或方案评估。", [by_type[signal_type].evidence_id])

    if "need_identified" in by_type:
        status = "conflicting" if s3_blocked else "sufficient"
        return _stage(StageCode.S1, "明确至少一个业务问题或使用场景。", [by_type["need_identified"].evidence_id], status)

    if s3_blocked and any(signal_type in by_type for signal_type in S3_SIGNALS):
        return None

    return _stage(StageCode.S0, "只有初步接触，无明确需求。", [])


def _stage(code: StageCode, reason: str, evidence_ids: list[str | None], evidence_status: str = "sufficient") -> StageResult:
    return StageResult(
        code=code,
        label=STAGE_LABELS[code],
        evidence_status=evidence_status,  # type: ignore[arg-type]
        reason=reason,
        evidence_ids=[evidence_id for evidence_id in evidence_ids if evidence_id],
    )


def _unique_ids(evidence_ids: list[str]) -> list[str]:
    return list(dict.fromkeys(evidence_ids))


def build_crm_fields(
    raw: RawExtraction,
    sufficient_evidence_ids: set[str],
    conflict_fields: set[str],
    confirmed_next_action: ConfirmedNextAction | None,
    evidence_by_id: dict[str, object],
) -> CrmFields:
    budget = _single_field(raw.candidate_budget, sufficient_evidence_ids, "budget", conflict_fields)
    next_action_evidence_ids = _candidate_next_action_evidence_ids(raw)
    independent_timeline_items = [item for item in raw.candidate_timeline if item.evidence_id not in next_action_evidence_ids]
    timeline_items = independent_timeline_items or raw.candidate_timeline
    timeline_conflict_fields = conflict_fields if independent_timeline_items else conflict_fields - {"timeline"}
    timeline = _single_field(timeline_items, sufficient_evidence_ids, "timeline", timeline_conflict_fields)
    timeline = _timeline_synced_to_next_action_time(timeline, confirmed_next_action)
    decision_maker = _decision_maker(raw.candidate_people, sufficient_evidence_ids)
    influencer_candidates = [_influencer_person(person, sufficient_evidence_ids, evidence_by_id) for person in raw.candidate_people if person.kind == "influencer"]
    influencers = _dedupe_people([person for person in influencer_candidates if person.status == FieldStatus.CONFIRMED])
    return CrmFields(
        customer_needs=_dedupe_fields([_field(item, sufficient_evidence_ids) for item in raw.candidate_needs]),
        core_scenarios=_dedupe_fields([_field(item, sufficient_evidence_ids) for item in raw.candidate_scenarios]),
        budget=budget,
        decision_maker=decision_maker,
        influencers=influencers,
        timeline=timeline,
    )


def _field(item: CandidateFact, sufficient_evidence_ids: set[str]) -> ValidatedField:
    evidence_ids = [item.evidence_id] if item.evidence_id in sufficient_evidence_ids else []
    if _is_confirmed_fact(item, sufficient_evidence_ids):
        return ValidatedField(value=item.value, status=FieldStatus.CONFIRMED, evidence_ids=evidence_ids, reason="该信息来自客户或第三方明确表达，并且原文依据有效。")
    if item.explicitness == Explicitness.AMBIGUOUS or item.attribution == Attribution.SALES:
        return ValidatedField(value=item.value, status=FieldStatus.INFERRED, evidence_ids=evidence_ids, reason="该信息不是客户明确确认事实，需进一步核实。")
    if item.current_validity in {CurrentValidity.HISTORICAL, CurrentValidity.INVALIDATED}:
        return ValidatedField(value=item.value, status=FieldStatus.UNKNOWN, evidence_ids=evidence_ids, reason="记录中提到该信息，但属于历史状态或当前有效性无法确认。")
    if item.polarity == Polarity.NEGATIVE:
        return ValidatedField(value=item.value, status=FieldStatus.UNKNOWN, evidence_ids=evidence_ids, reason="记录中提到该信息，但表达的是不可用、否定或失效状态，不能确认为当前有效事实。")
    return ValidatedField(value=item.value, status=FieldStatus.UNKNOWN, evidence_ids=evidence_ids, reason="当前原文依据不足，无法确认该字段。")


def _budget_value_key(value: object) -> str:
    normalized = re.sub(r"\s+", "", str(value or ""))
    normalized = re.sub(r"^(客户)?(确定|确认|最终|当前|有效|预算|为|是|约)+", "", normalized)
    normalized = re.sub(r"(预算|最终|当前|有效|为准)$", "", normalized)
    return normalized


def _single_field(items: list[CandidateFact], sufficient_evidence_ids: set[str], field_name: str, conflict_fields: set[str]) -> ValidatedField:
    fields = [_field(item, sufficient_evidence_ids) for item in items]
    confirmed = [field for field in fields if field.status == FieldStatus.CONFIRMED]
    if field_name in conflict_fields:
        return ValidatedField(value=None, status=FieldStatus.CONFLICT, evidence_ids=sum((field.evidence_ids for field in fields), []), conflicting_values=[field.value for field in fields if field.value is not None], reason="记录中存在互相冲突的信息，不能自动选择其中一条作为最终事实。")
    if not fields:
        return ValidatedField(reason=_missing_reason(field_name))
    if field_name == "budget" and len({_budget_value_key(field.value) for field in confirmed}) == 1 and confirmed:
        preferred = min(confirmed, key=lambda field: len(str(field.value or "")))
        preferred.evidence_ids = list(dict.fromkeys(sum((field.evidence_ids for field in confirmed), [])))
        return preferred
    if len({str(field.value) for field in confirmed}) > 1:
        return ValidatedField(value=None, status=FieldStatus.CONFLICT, evidence_ids=sum((field.evidence_ids for field in confirmed), []), conflicting_values=[field.value for field in confirmed], reason="记录中出现多个不同的确认值，需要人工确认当前真实状态。")
    return confirmed[0] if confirmed else fields[0]


def _decision_maker(people: list[CandidatePerson], sufficient_evidence_ids: set[str]) -> ValidatedPerson:
    makers = [person for person in people if person.kind == "decision_maker"]
    if not makers:
        return ValidatedPerson(reason="当前记录未明确最终审批、拍板或购买决策权限。")
    confirmed = [person for person in makers if person.authority_confirmed and person.explicitness == Explicitness.EXPLICIT and person.evidence_id in sufficient_evidence_ids]
    return _decision_person(confirmed[-1] if confirmed else makers[-1], sufficient_evidence_ids)


def _dedupe_people(people: list[ValidatedPerson]) -> list[ValidatedPerson]:
    by_name: dict[str, ValidatedPerson] = {}
    deduped: list[ValidatedPerson] = []
    for person in people:
        person.name, person.role = _normalize_person_name_role(person.name, person.role)
        if not person.name:
            deduped.append(person)
            continue
        key = re.sub(r"\s+", "", person.name)
        existing = by_name.get(key)
        if existing is None:
            by_name[key] = person
            deduped.append(person)
            continue
        roles = [role for role in (existing.role, person.role) if role]
        if roles:
            existing.role = _clean_person_role("、".join(dict.fromkeys(roles)))
        existing.evidence_ids = list(dict.fromkeys(existing.evidence_ids + person.evidence_ids))
        if existing.status != FieldStatus.CONFIRMED and person.status == FieldStatus.CONFIRMED:
            existing.status = person.status
        existing.authority_confirmed = existing.authority_confirmed or person.authority_confirmed
    return deduped


def _dedupe_fields(fields: list[ValidatedField]) -> list[ValidatedField]:
    deduped: list[ValidatedField] = []
    by_key: dict[tuple[str, str], ValidatedField] = {}
    for field in fields:
        key = (str(field.value or "").strip(), field.status.value if hasattr(field.status, "value") else str(field.status))
        if not key[0]:
            deduped.append(field)
            continue
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = field
            deduped.append(field)
            continue
        existing.evidence_ids = list(dict.fromkeys(existing.evidence_ids + field.evidence_ids))
        if not existing.reason and field.reason:
            existing.reason = field.reason
    return deduped


def _decision_person(person: CandidatePerson, sufficient_evidence_ids: set[str]) -> ValidatedPerson:
    evidence_ids = [person.evidence_id] if person.evidence_id in sufficient_evidence_ids else []
    name, role = _normalize_person_name_role(person.name, person.role)
    if evidence_ids and person.authority_confirmed and person.explicitness == Explicitness.EXPLICIT:
        status = FieldStatus.CONFIRMED if name else FieldStatus.PARTIAL
        reason = "该人物的最终审批、拍板或购买决策权限已有明确原文依据。" if name else "记录提到决策权限，但姓名仍未确认。"
    elif name:
        status = FieldStatus.PARTIAL
        reason = "记录中存在候选人物信息，但最终审批、拍板或购买决策权限尚未被明确确认。"
    else:
        status = FieldStatus.UNKNOWN
        reason = "当前记录未明确最终审批、拍板或购买决策权限。"
    return ValidatedPerson(name=name, role=role, status=status, authority_confirmed=person.authority_confirmed, evidence_ids=evidence_ids, reason=reason)


def _influencer_evidence_supports_confirmation(person: CandidatePerson, evidence_by_id: dict[str, object]) -> bool:
    if not person.evidence_id or person.evidence_id not in evidence_by_id:
        return False
    evidence = evidence_by_id[person.evidence_id]
    quote = str(getattr(evidence, "quote", "") or "")
    compact_quote = re.sub(r"\s+", "", quote)
    compact_name = re.sub(r"\s+", "", person.name or "")
    if not compact_name or compact_quote == compact_name or compact_name not in compact_quote:
        return False
    if re.search(r"(参会|参加|拜访|沟通对象|包括|一起沟通|开会)", compact_quote) and not re.search(r"(评估|采购|选型|比选|试用|PoC|POC|看效果|看方案|负责|负责人)", compact_quote):
        return False
    return bool(
        re.search(
            r"(复盘|方案评审|技术方案评估|方案评估|评估|采购流程|采购申请|采购评审|采购决策|供应商选择|选型|比选|正式报价|付款方式|试用|PoC|POC|看效果|看方案|影响人|参与人|预算确认|立项预算|补充说|确认会)",
            quote,
        )
    )


def _influencer_person(person: CandidatePerson, sufficient_evidence_ids: set[str], evidence_by_id: dict[str, object]) -> ValidatedPerson:
    evidence_ids = [person.evidence_id] if person.evidence_id in sufficient_evidence_ids else []
    name, role = _normalize_person_name_role(person.name, person.role)
    if evidence_ids and name and person.explicitness == Explicitness.EXPLICIT and _influencer_evidence_supports_confirmation(person, evidence_by_id):
        return ValidatedPerson(name=name, role=role, status=FieldStatus.CONFIRMED, authority_confirmed=False, evidence_ids=evidence_ids, reason="该人物被明确记录为影响方案、评估、采购或购买判断的参与人。")
    if name:
        return ValidatedPerson(name=name, role=role, status=FieldStatus.PARTIAL, authority_confirmed=False, evidence_ids=evidence_ids, reason="记录中存在候选参与人，但其对方案、采购或购买判断的影响仍需确认。")
    return ValidatedPerson(status=FieldStatus.UNKNOWN, authority_confirmed=False, evidence_ids=evidence_ids, reason="当前记录未明确能影响方案、采购或购买判断的参与人。")


def _format_next_action_conflict(raw: RawExtraction, conflict: PossibleConflict) -> str:
    actions = _confirmed_actions(raw.candidate_next_actions, set(conflict.evidence_ids))
    owners = _explicit_next_action_values([action.owner for action in actions], "owner")
    unknown_owners = _explicit_unknown_next_action_values([action.owner for action in actions], "owner")
    times = _explicit_next_action_values([action.time for action in actions], "time")
    unknown_times = _explicit_unknown_next_action_values([action.time for action in actions], "time")
    action_values = _explicit_next_action_values([action.action for action in actions], "action")
    unknown_actions = _explicit_unknown_next_action_values([action.action for action in actions], "action")
    field = conflict.field.lower()
    owner_became_unknown = _latest_unknown_after_concrete(_next_action_field_sequence(actions, "owner"))
    time_became_unknown = _latest_unknown_after_concrete(_next_action_field_sequence(actions, "time"))
    action_became_unknown = _latest_unknown_after_concrete(_next_action_field_sequence(actions, "action"))
    if ("owner" in field or "负责人" in conflict.field) and len(owners) >= 2:
        return f"下一步行动负责人存在多个不一致表述：{'、'.join(owners)}，需确认当前真实负责人。"
    if ("owner" in field or "负责人" in conflict.field) and owner_became_unknown:
        return f"下一步行动负责人从明确负责人变为待确认：{'、'.join(owners)}、{'、'.join(unknown_owners)}，需确认当前真实负责人。"
    if ("time" in field or "时间" in conflict.field) and time_became_unknown:
        return f"下一步行动时间从明确时间变为未确定：{'、'.join(times)}、{'、'.join(unknown_times)}，需确认当前真实时间。"
    if ("time" in field or "时间" in conflict.field) and len(times) >= 2:
        return f"下一步行动时间存在多个不一致表述：{'、'.join(times)}，需确认当前真实时间。"
    if ("action" in field or "行动" in conflict.field) and len(action_values) >= 2:
        return f"下一步行动存在多个不一致表述：{'、'.join(action_values)}，需确认当前真实行动。"
    if ("action" in field or "行动" in conflict.field) and action_became_unknown:
        return f"下一步行动从明确行动变为待确认：{'、'.join(action_values)}、{'、'.join(unknown_actions)}，需确认当前真实行动。"
    if len(owners) >= 2:
        return f"下一步行动负责人存在多个不一致表述：{'、'.join(owners)}，需确认当前真实负责人。"
    if owner_became_unknown:
        return f"下一步行动负责人从明确负责人变为待确认：{'、'.join(owners)}、{'、'.join(unknown_owners)}，需确认当前真实负责人。"
    if len(times) >= 2:
        return f"下一步行动时间存在多个不一致表述：{'、'.join(times)}，需确认当前真实时间。"
    if time_became_unknown:
        return f"下一步行动时间从明确时间变为未确定：{'、'.join(times)}、{'、'.join(unknown_times)}，需确认当前真实时间。"
    if action_became_unknown:
        return f"下一步行动从明确行动变为待确认：{'、'.join(action_values)}、{'、'.join(unknown_actions)}，需确认当前真实行动。"
    return "下一步行动存在不一致表述，需确认当前真实行动、负责人或时间。"


def _formalize_conflict_text(description: str) -> str:
    text = re.sub(r"\s+vs\s+", " 与 ", description.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\bvs\b", "与", text, flags=re.IGNORECASE)
    if re.search(r"(冲突|不一致)[：:][^。]*与[^。]*$", text) and "需确认" not in text:
        text = f"{text}，需确认当前真实状态。"
    return text


def _normalize_conflict_description(raw: RawExtraction, conflict: PossibleConflict) -> str:
    field = _normalize_field_name(conflict.field)
    if field.startswith("next_action") or _is_next_action_conflict(conflict):
        return _formalize_conflict_text(_format_next_action_conflict(raw, conflict))
    description = _formalize_conflict_text(conflict.description.strip().rstrip("。"))
    over_decided = re.search(r"(最终以.+为准|已确认以.+为准|以.+为准|最终(选择|采纳)|选择其中|采纳其中)", description)
    if over_decided:
        return "记录中存在互相冲突的信息，需确认当前真实状态。"
    return description or "记录中存在互相冲突的信息，需确认当前真实状态。"


def build_opportunity_risks(raw: RawExtraction, valid_evidence_ids: set[str], sufficient_evidence_ids: set[str], stage: StageResult | None) -> list[OpportunityRisk]:
    risks: list[OpportunityRisk] = []
    deduped_conflict_risks: dict[tuple[str, str], OpportunityRisk] = {}
    for conflict in raw.possible_conflicts:
        next_action_fields = _next_action_conflict_fields_from_context(raw, conflict)
        normalized_conflict = _next_action_conflict_for_fields(conflict, next_action_fields) if next_action_fields else conflict
        if next_action_fields and not _material_next_action_conflict_fields(raw.candidate_next_actions, sufficient_evidence_ids, [normalized_conflict]):
            continue
        valid_ids = _unique_ids([evidence_id for evidence_id in conflict.evidence_ids if evidence_id in valid_evidence_ids])
        risk = OpportunityRisk(type="conflict", severity="high", description=_normalize_conflict_description(raw, normalized_conflict), evidence_ids=valid_ids)
        if next_action_fields:
            key = ("next_action", ",".join(sorted(next_action_fields)))
        else:
            key = (_normalize_field_name(conflict.field), risk.description)
        existing = deduped_conflict_risks.get(key)
        if existing is None or _risk_specificity_score(risk) > _risk_specificity_score(existing):
            deduped_conflict_risks[key] = risk
    risks.extend(deduped_conflict_risks.values())

    blocking_by_type: dict[str, list[str]] = {"demand_invalidated": [], "demand_delayed": [], "budget_unavailable": []}
    for signal in raw.stage_signals:
        if signal.signal_type in {"demand_invalidated", "demand_delayed", "budget_unavailable"} and signal.evidence_id in valid_evidence_ids:
            blocking_by_type[signal.signal_type].append(signal.evidence_id)
    if blocking_by_type["demand_invalidated"]:
        risks.append(OpportunityRisk(type="demand_invalidated", severity="high", description="客户表达项目暂停、取消或需求失效，当前需求有效性需要确认。", evidence_ids=_unique_ids(blocking_by_type["demand_invalidated"])))
    if blocking_by_type["budget_unavailable"]:
        risks.append(OpportunityRisk(type="budget_unavailable", severity="high", description="客户明确表达预算不可用、预算不足或预算审批受阻，可能影响商务推进。", evidence_ids=_unique_ids(blocking_by_type["budget_unavailable"])))
    if blocking_by_type["demand_delayed"]:
        risks.append(OpportunityRisk(type="demand_delayed", severity="medium", description="客户表达项目延期或后续再看，当前推进节奏需要确认。", evidence_ids=_unique_ids(blocking_by_type["demand_delayed"])))

    procurement_risk_ids: list[str] = []
    for signal in raw.stage_signals:
        if signal.signal_type != "procurement_discussed" or signal.evidence_id not in valid_evidence_ids:
            continue
        quote = next((item.quote for item in raw.evidence_candidates if item.id == signal.evidence_id), "")
        if signal.polarity == Polarity.NEGATIVE or re.search(r"(还没|未|没有|卡住|受阻|拖慢|未启动|未提交)", quote):
            procurement_risk_ids.append(signal.evidence_id)
    if procurement_risk_ids:
        risks.append(OpportunityRisk(type="unknown_procurement_process", severity="medium", description="采购或审批流程存在未启动、未提交或受阻信息，可能影响后续推进。", evidence_ids=_unique_ids(procurement_risk_ids)))

    # Unknowns stay in unconfirmed_info by default. They become OpportunityRisk only
    # when they can materially block a later-stage commercial decision.
    if stage and stage.code in {StageCode.S3, StageCode.S4} and any(person.kind == "decision_maker" and not person.authority_confirmed for person in raw.candidate_people):
        risks.append(OpportunityRisk(type="unknown_decision_authority", severity="medium", description="当前已进入商务/审批阶段，但决策权限尚未被明确证据确认。", evidence_ids=[]))

    return risks


def determine_stage_decision_reason(
    original_text: str,
    raw: RawExtraction,
    valid_evidence_ids: set[str],
    sufficient_evidence_ids: set[str],
    stage: StageResult | None,
) -> str | None:
    if stage is not None:
        return None

    text = original_text.strip()
    normal_chars = re.sub(r"[\s。！？,.，、…]", "", text)
    if not text or len(text) < 8 or ("……" in text and len(normal_chars) <= 8):
        return "insufficient_input"

    contextual_signals = [
        signal
        for signal in raw.stage_signals
        if signal.evidence_id in valid_evidence_ids
        and (
            signal.signal_type in NO_STAGE_CONTEXT_SIGNALS
            or signal.current_validity in {CurrentValidity.HISTORICAL, CurrentValidity.INVALIDATED}
        )
    ]
    if contextual_signals or raw.possible_conflicts:
        return "stage_blocked_or_conflicting"

    extracted_content_exists = any(
        (
            raw.evidence_candidates,
            raw.candidate_needs,
            raw.candidate_scenarios,
            raw.candidate_budget,
            raw.candidate_people,
            raw.candidate_timeline,
            raw.candidate_next_actions,
            raw.stage_signals,
            raw.ambiguities,
            raw.possible_conflicts,
        )
    )
    if extracted_content_exists or sufficient_evidence_ids:
        return "insufficient_stage_signal"

    return "insufficient_business_facts"


def build_analysis_warnings(
    raw: RawExtraction,
    valid_evidence_ids: set[str],
    sufficient_evidence_ids: set[str],
    stage: StageResult | None,
    stage_decision_reason: str | None = None,
) -> list[AnalysisWarning]:
    warnings: list[AnalysisWarning] = []
    if stage is None:
        reason = stage_decision_reason or "insufficient_input"
        warnings.append(
            AnalysisWarning(
                type="insufficient_input",
                severity="high" if reason == "insufficient_input" else "medium",
                description=STAGE_DECISION_REASON_DESCRIPTIONS[reason],
                evidence_ids=[],
            )
        )

    weak_ids: list[str] = []
    for signal in raw.stage_signals:
        if signal.evidence_id in valid_evidence_ids and signal.evidence_id not in sufficient_evidence_ids and signal.signal_type in S2_SIGNALS | S3_SIGNALS | S4_SIGNALS | S5_SIGNALS:
            weak_ids.append(signal.evidence_id)
    if weak_ids:
        warnings.append(AnalysisWarning(type="weak_evidence", severity="medium", description="存在证据文本但语义不足，关键阶段信号未被采纳。", evidence_ids=_unique_ids(weak_ids)))
    return warnings


def build_confirmed_next_action(actions: list[CandidateNextAction], sufficient_evidence_ids: set[str], conflicts: list[PossibleConflict] | None = None) -> ConfirmedNextAction | None:
    confirmed = _confirmed_actions(actions, sufficient_evidence_ids)
    if not confirmed:
        return None
    conflict_fields = _material_next_action_conflict_fields(actions, sufficient_evidence_ids, conflicts or [])
    action_values = _explicit_next_action_values([action.action for action in confirmed], "action")
    action_value = action_values[0] if len(action_values) == 1 and "action" not in conflict_fields else "待确认"
    scoped_actions = _actions_scoped_to_selected_next_action(confirmed, action_value)
    owners = _explicit_next_action_values([action.owner for action in scoped_actions], "owner")
    times = _explicit_next_action_values([action.time for action in scoped_actions], "time")
    latest = scoped_actions[-1] if scoped_actions else confirmed[-1]
    owner_value = owners[0] if len(owners) == 1 and "owner" not in conflict_fields else "待确认"
    latest_time_explicitly_unknown = latest.time is not None and _unknown_next_action_value(latest.time)
    time_value = times[0] if len(times) == 1 and "time" not in conflict_fields and not latest_time_explicitly_unknown else "待确认"
    return ConfirmedNextAction(
        action=action_value,
        owner=owner_value,
        time=time_value,
        evidence_ids=_unique_ids([action.evidence_id for action in confirmed if action.evidence_id]),
    )


def _actions_scoped_to_selected_next_action(actions: list[CandidateNextAction], action_value: str) -> list[CandidateNextAction]:
    if _unknown_next_action_value(action_value):
        return actions
    selected_indices = [index for index, action in enumerate(actions) if _next_action_same_event(action.action, action_value)]
    if not selected_indices:
        return actions
    latest_selected_index = max(selected_indices)
    scoped: list[CandidateNextAction] = []
    for index, action in enumerate(actions):
        if _next_action_same_event(action.action, action_value):
            scoped.append(action)
        elif index > latest_selected_index and _unknown_next_action_value(action.action):
            scoped.append(action)
    return scoped


def _next_action_same_event(candidate_action: str | None, selected_action: str | None) -> bool:
    candidate = _normalize_next_action_action(candidate_action)
    selected = _normalize_next_action_action(selected_action)
    if not candidate or not selected or _unknown_next_action_value(candidate) or _unknown_next_action_value(selected):
        return False
    candidate_key = _event_key(candidate)
    selected_key = _event_key(selected)
    if candidate_key and selected_key:
        return candidate_key == selected_key
    return re.sub(r"\s+", "", candidate) == re.sub(r"\s+", "", selected)


def build_unconfirmed_info(crm_fields: CrmFields, confirmed_next_action: ConfirmedNextAction | None) -> list[ValidatedField]:
    items: list[ValidatedField] = []
    if not any(field.status == FieldStatus.CONFIRMED for field in crm_fields.customer_needs):
        items.append(ValidatedField(value="客户需求未确认", status=FieldStatus.UNKNOWN, reason="当前记录未形成可确认的客户业务问题、需求表达或改进目标。"))
    if not any(field.status == FieldStatus.CONFIRMED for field in crm_fields.core_scenarios):
        items.append(ValidatedField(value="核心场景未确认", status=FieldStatus.UNKNOWN, reason="当前记录未明确该商机对应的落地场景、使用场景或业务流程。"))
    if crm_fields.budget.status == FieldStatus.UNKNOWN:
        items.append(ValidatedField(value="预算未确认", status=FieldStatus.UNKNOWN, reason=crm_fields.budget.reason or "本次记录未提供预算金额、预算范围或明确预算安排。"))
    if crm_fields.budget.status == FieldStatus.CONFLICT:
        items.append(ValidatedField(value="预算存在冲突", status=FieldStatus.CONFLICT, evidence_ids=crm_fields.budget.evidence_ids, conflicting_values=crm_fields.budget.conflicting_values, reason=crm_fields.budget.reason))
    if crm_fields.decision_maker.status in {FieldStatus.UNKNOWN, FieldStatus.PARTIAL}:
        items.append(ValidatedField(value="决策人或决策权限未确认", status=FieldStatus.UNKNOWN, reason=crm_fields.decision_maker.reason or "当前记录未明确最终审批、拍板或购买决策权限。"))
    if not any(person.status == FieldStatus.CONFIRMED for person in crm_fields.influencers):
        items.append(ValidatedField(value="影响人未确认", status=FieldStatus.UNKNOWN, reason="当前记录未明确存在能实质影响方案或购买判断的参与人。"))
    if crm_fields.timeline.status == FieldStatus.UNKNOWN:
        items.append(ValidatedField(value="时间计划未确认", status=FieldStatus.UNKNOWN, reason=crm_fields.timeline.reason or "本次记录未提供明确推进时间或上线计划。"))
    if crm_fields.timeline.status == FieldStatus.CONFLICT:
        items.append(ValidatedField(value="时间计划存在冲突", status=FieldStatus.CONFLICT, evidence_ids=crm_fields.timeline.evidence_ids, conflicting_values=crm_fields.timeline.conflicting_values, reason=crm_fields.timeline.reason))
    if confirmed_next_action is None:
        items.append(ValidatedField(value="下一步行动未确认", status=FieldStatus.UNKNOWN, reason="当前记录尚未明确客户已确认的下一步动作、负责人或时间。"))
    else:
        if confirmed_next_action.action == "待确认":
            items.append(ValidatedField(value="下一步具体行动仍需确认", status=FieldStatus.UNKNOWN, reason="记录提到了下一步行动相关信息，但行动本身缺失或存在冲突。"))
        if confirmed_next_action.owner == "待确认":
            items.append(ValidatedField(value="下一步行动负责人仍需确认", status=FieldStatus.UNKNOWN, reason="客户已确认下一步行动，但负责人缺失或存在冲突。"))
        if confirmed_next_action.time == "待确认":
            items.append(ValidatedField(value="下一步行动时间仍需确认", status=FieldStatus.UNKNOWN, reason="客户已确认下一步行动，但时间缺失或尚未约定。"))
    return items


def _missing_reason(field_name: str) -> str:
    reasons = {
        "budget": "本次记录未提供预算金额、预算范围或明确预算安排。",
        "timeline": "本次记录未提供明确推进时间或上线计划。",
    }
    return reasons.get(field_name, "本次记录未提供足够信息确认该字段。")


def determine_status(original_text: str, stage: StageResult | None, risks: list[OpportunityRisk]) -> DecisionStatus:
    if any(risk.severity == "high" and risk.type in {"conflict", "demand_invalidated", "budget_unavailable"} for risk in risks):
        return DecisionStatus.NEED_CONFIRMATION
    if stage is None:
        return DecisionStatus.UNABLE_TO_JUDGE
    return DecisionStatus.COMPLETE


def _format_budget_conflict_question(budget: ValidatedField) -> str:
    values = [str(value) for value in budget.conflicting_values if value not in (None, "")]
    unique_values = list(dict.fromkeys(values))
    if len(unique_values) >= 2:
        if len(unique_values) == 2:
            alternatives = f"{unique_values[0]}，还是{unique_values[1]}"
        else:
            alternatives = "、".join(unique_values[:-1]) + f"，还是{unique_values[-1]}"
        return f"请确认客户当前预算状态：{alternatives}？"
    if unique_values:
        return f"请确认客户当前预算状态是否仍为：{unique_values[0]}？"
    return "请确认客户当前真实预算状态，以解除预算相关冲突。"


def _format_conflict_question(risk: OpportunityRisk, crm_fields: CrmFields) -> ClarificationQuestion:
    if crm_fields.budget.status == FieldStatus.CONFLICT and "预算" in risk.description:
        return ClarificationQuestion(field="budget", question=_format_budget_conflict_question(crm_fields.budget), priority="high", reason="该问题可直接解除预算冲突并影响 S3 判断。")
    if crm_fields.timeline.status == FieldStatus.CONFLICT and "时间" in risk.description:
        return ClarificationQuestion(field="timeline", question="请确认客户当前真实的时间计划是什么？", priority="high", reason="该问题可解除时间计划冲突。")
    if "下一步行动负责人" in risk.description:
        return ClarificationQuestion(field="next_action.owner", question="请确认客户当前已确认的下一步行动负责人是谁？", priority="high", reason="该问题可解除下一步行动负责人冲突。")
    if "下一步行动时间" in risk.description:
        return ClarificationQuestion(field="next_action.time", question="请确认客户当前已确认的下一步行动时间是什么？", priority="high", reason="该问题可解除下一步行动时间冲突。")
    if "下一步行动" in risk.description:
        return ClarificationQuestion(field="next_action.action", question="请确认客户当前已确认的下一步具体行动是什么？", priority="high", reason="该问题可解除下一步行动冲突。")
    if "预算" in risk.description:
        return ClarificationQuestion(field="budget", question="请确认客户当前真实预算状态。", priority="high", reason="该问题可解除预算相关冲突。")
    if "决策" in risk.description or "审批" in risk.description:
        return ClarificationQuestion(field="decision_maker", question="请确认最终审批人、拍板人或采购决策权限。", priority="high", reason="该问题可解除决策权限相关冲突。")
    return ClarificationQuestion(field="source_text", question=f"请确认以下冲突信息的当前真实状态：{risk.description}", priority="high", reason="该问题可解除关键信息冲突。")


def _question_from_unconfirmed(item: ValidatedField) -> ClarificationQuestion:
    value = str(item.value or "")
    field = "source_text"
    question = "请补充当前缺失的商机信息。"
    if "客户需求" in value:
        field = "customer_needs"
        question = "客户当前是否明确提出了业务需求、业务问题或改进目标？"
    elif "核心场景" in value:
        field = "core_scenarios"
        question = "该商机对应的核心使用场景或业务流程是什么？"
    elif "预算" in value:
        field = "budget"
        question = "请确认客户当前有效的预算金额、预算范围或预算状态。"
    elif "决策人" in value or "决策权限" in value:
        field = "decision_maker"
        question = "请确认最终审批人、拍板人或采购决策权限。"
    elif "影响人" in value:
        field = "influencers"
        question = "请确认是否存在能影响方案或购买判断的参与人。"
    elif "时间计划" in value:
        field = "timeline"
        question = "请确认客户当前真实的时间计划是什么？"
    elif "下一步具体行动" in value:
        field = "next_action.action"
        question = "请确认客户当前已确认的下一步具体行动是什么？"
    elif "下一步行动负责人" in value:
        field = "next_action.owner"
        question = "请确认客户当前已确认的下一步行动负责人是谁？"
    elif "下一步行动时间" in value:
        field = "next_action.time"
        question = "请确认客户当前已确认的下一步行动时间是什么？"
    elif "下一步行动" in value:
        field = "next_action"
        question = "请确认客户当前已确认的下一步行动、负责人和时间。"
    return ClarificationQuestion(field=field, question=question, priority="medium", reason=item.reason or "该信息当前仍需补充确认。")


def build_clarification(
    status: DecisionStatus,
    risks: list[OpportunityRisk],
    stage: StageResult | None,
    crm_fields: CrmFields,
    unconfirmed_info: list[ValidatedField],
    stage_decision_reason: str | None = None,
) -> Clarification | None:
    questions: list[ClarificationQuestion] = []
    if status == DecisionStatus.UNABLE_TO_JUDGE:
        if stage_decision_reason == "insufficient_input":
            questions.append(ClarificationQuestion(field="source_text", question="请补充一段完整的客户沟通记录，包括客户需求、场景或推进状态。", priority="high", reason=STAGE_DECISION_REASON_DESCRIPTIONS["insufficient_input"]))
        elif stage_decision_reason == "insufficient_business_facts":
            questions.append(ClarificationQuestion(field="customer_needs", question="客户当前是否明确提出了业务需求、使用场景或改进目标？", priority="high", reason=STAGE_DECISION_REASON_DESCRIPTIONS["insufficient_business_facts"]))
        else:
            questions.append(ClarificationQuestion(field="customer_needs", question="客户当前具体有什么业务需求或使用场景？", priority="high", reason=STAGE_DECISION_REASON_DESCRIPTIONS.get(stage_decision_reason or "insufficient_stage_signal", STAGE_DECISION_REASON_DESCRIPTIONS["insufficient_stage_signal"])))
            questions.append(ClarificationQuestion(field="stage", question="当前是否已有客户确认的方案验证、商务评估、审批或签约进展？", priority="high", reason=STAGE_DECISION_REASON_ACTIONS["insufficient_stage_signal"]))
    for risk in risks:
        if risk.type == "conflict":
            questions.append(_format_conflict_question(risk, crm_fields))
        if risk.type == "demand_invalidated":
            questions.append(ClarificationQuestion(field="stage", question="请确认该项目当前是否仍有效推进，以及阻塞推进的因素是否已经解除？", priority="high", reason="需求有效性会影响 S3 阶段判断。"))
        if risk.type == "budget_unavailable":
            questions.append(ClarificationQuestion(field="budget", question="请确认当前预算冻结、预算不足或预算审批受阻是否已经解除。", priority="high", reason="预算可用性会影响商务推进判断。"))
        if risk.type == "unknown_procurement_process":
            questions.append(ClarificationQuestion(field="stage", question="请确认采购或审批流程当前是否已启动，以及是否存在阻塞。", priority="medium", reason="采购流程状态会影响后续推进判断。"))
    questions.extend(_question_from_unconfirmed(item) for item in unconfirmed_info)
    deduped: list[ClarificationQuestion] = []
    seen: set[tuple[str, str]] = set()
    conflict_resolution_fields = {
        question.field
        for question in questions
        if question.priority == "high" and ("解除" in question.reason or "冲突" in question.question)
    }
    for question in questions:
        if question.priority == "medium" and question.field in conflict_resolution_fields:
            continue
        key = (question.field, question.question)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(question)
    if not deduped:
        return None
    return Clarification(needed=True, questions=deduped, max_questions=len(deduped))


def _field_values(fields: list[ValidatedField]) -> list[str]:
    return [str(field.value) for field in fields if field.value and field.status == FieldStatus.CONFIRMED]


def build_summary(
    stage: StageResult | None,
    crm_fields: CrmFields,
    confirmed_next_action: ConfirmedNextAction | None,
    risks: list[OpportunityRisk],
    unconfirmed_info: list[ValidatedField],
    analysis_warnings: list[AnalysisWarning],
    stage_decision_reason: str | None = None,
) -> str:
    if stage is None:
        if risks:
            risk_description = risks[0].description.rstrip("。")
            return f"当前记录存在关键阻塞，暂不能可靠确认销售阶段：{risk_description}。已验证的信息应先用于澄清项目有效性或冲突状态。"
        if stage_decision_reason == "insufficient_business_facts":
            return "当前记录可以解析，但客户需求、使用场景或推进动作仍不足，暂不能形成可靠销售阶段判断。需要先补齐可验证的业务事实。"
        if stage_decision_reason == "insufficient_stage_signal":
            return "当前记录已有部分业务信息，但尚未形成可采纳的 S0-S5 阶段信号，暂不能确认销售阶段。需要补充客户需求、方案验证或商务进展等明确事实。"
        if analysis_warnings:
            return f"当前尚未获得可用于商机分析的完整拜访记录，暂不能形成可靠销售阶段判断。{analysis_warnings[0].description}"
        return "当前销售记录信息不足，暂不能形成可靠商机概览。需要补充完整客户沟通内容后再分析。"
    need_or_scene = _field_values(crm_fields.customer_needs) or _field_values(crm_fields.core_scenarios)
    first_sentence = f"当前商机处于 {stage.code}（{stage.label}），{stage.reason.rstrip('。')}。"
    facts: list[str] = []
    if need_or_scene:
        facts.append("已确认的核心需求或场景为" + "、".join(need_or_scene[:2]))
    if crm_fields.budget.status == FieldStatus.CONFIRMED and crm_fields.budget.value:
        facts.append(f"预算为{crm_fields.budget.value}")
    if crm_fields.timeline.status == FieldStatus.CONFIRMED and crm_fields.timeline.value:
        facts.append(f"时间计划为{crm_fields.timeline.value}")
    if crm_fields.decision_maker.status == FieldStatus.CONFIRMED and crm_fields.decision_maker.name:
        role = f"（{crm_fields.decision_maker.role}）" if crm_fields.decision_maker.role else ""
        facts.append(f"决策人已确认为{crm_fields.decision_maker.name}{role}")
    fact_sentence = "；".join(facts[:2]) + "。" if facts else "当前已确认的需求、场景或商务事实仍有限。"
    if confirmed_next_action and confirmed_next_action.action != "待确认":
        action_parts = [f"下一步已确认{confirmed_next_action.action}"]
        action_parts.append(f"负责人为{confirmed_next_action.owner}" if confirmed_next_action.owner != "待确认" else "负责人待确认")
        action_parts.append(f"时间为{confirmed_next_action.time}" if confirmed_next_action.time != "待确认" else "时间待确认")
        action_part = "，".join(action_parts)
    elif confirmed_next_action:
        action_part = "下一步行动存在冲突，需确认具体动作、负责人或时间"
    else:
        action_part = ""
    if risks:
        risk_description = risks[0].description.rstrip("。")
        attention = "当前最需要关注的是" + risk_description
    elif unconfirmed_info:
        values = [str(item.value) for item in unconfirmed_info[:2] if item.value]
        attention = "当前仍需补齐" + "、".join(values)
    else:
        attention = ""
    if action_part and attention:
        closing = f"{attention}，{action_part}。"
    elif action_part:
        closing = f"{action_part}。"
    else:
        closing = f"{attention}。" if attention else "后续应优先补齐仍待确认的关键信息。"
    return first_sentence + fact_sentence + closing
