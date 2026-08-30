from __future__ import annotations

import asyncio
from typing import Any

from backend.app.errors import LLMProviderError
from backend.app.rules import build_validated_opportunity
from backend.app.schemas import (
    Attribution,
    CandidateFact,
    CandidateNextAction,
    CandidatePerson,
    CurrentValidity,
    EvidenceCandidate,
    Explicitness,
    FieldStatus,
    Polarity,
    PossibleConflict,
    RawExtraction,
    StageSignal,
)
from backend.app.summary import build_summary_context, generate_grounded_summary, validate_grounded_summary


class FakeSummaryProvider:
    provider_name = "fake"
    model_name = "fake-summary-v1"

    def __init__(self, summary: str | None = None, error: Exception | None = None) -> None:
        self.summary = summary
        self.error = error

    async def invoke_grounded_summary(self, context: dict[str, Any], deterministic_draft: str) -> str:
        if self.error:
            raise self.error
        return self.summary if self.summary is not None else deterministic_draft


def sig(signal_type: str, evidence_id: str, *, current_validity: CurrentValidity = CurrentValidity.ACTIVE, polarity: Polarity = Polarity.POSITIVE) -> StageSignal:
    return StageSignal(
        signal_type=signal_type,  # type: ignore[arg-type]
        explicitness=Explicitness.EXPLICIT,
        polarity=polarity,
        attribution=Attribution.CUSTOMER,
        current_validity=current_validity,
        evidence_id=evidence_id,
    )


def fact(value: str, evidence_id: str, *, current_validity: CurrentValidity = CurrentValidity.ACTIVE, polarity: Polarity = Polarity.POSITIVE) -> CandidateFact:
    return CandidateFact(
        value=value,
        evidence_id=evidence_id,
        attribution=Attribution.CUSTOMER,
        explicitness=Explicitness.EXPLICIT,
        polarity=polarity,
        current_validity=current_validity,
    )


def test_summary_context_excludes_raw_visit_note() -> None:
    text = "客户说客服工单处理慢。内部备注：这句话不能作为 summary LLM 的自由上下文。"
    raw = RawExtraction(
        evidence_candidates=[EvidenceCandidate(id="E01", quote="客服工单处理慢", field="customer_needs")],
        candidate_needs=[fact("客服工单处理慢", "E01")],
        stage_signals=[sig("need_identified", "E01")],
    )
    result = build_validated_opportunity(text, raw)
    context_text = str(build_summary_context(result))
    assert "内部备注" not in context_text
    assert "自由上下文" not in context_text


def test_normal_s2_llm_summary_can_naturalize_without_new_facts() -> None:
    text = "客户说客服工单处理慢，希望用智能问答覆盖售后知识库场景。王总说下周四可以安排一次产品 Demo。"
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="客服工单处理慢", field="customer_needs"),
            EvidenceCandidate(id="E02", quote="售后知识库场景", field="core_scenarios"),
            EvidenceCandidate(id="E03", quote="下周四可以安排一次产品 Demo", field="next_action"),
        ],
        candidate_needs=[fact("客服工单处理慢", "E01")],
        candidate_scenarios=[fact("售后知识库场景", "E02")],
        candidate_next_actions=[CandidateNextAction(action="安排产品 Demo", time="下周四", evidence_id="E03", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
        stage_signals=[sig("need_identified", "E01"), sig("demo_agreed", "E03")],
    )
    result = build_validated_opportunity(text, raw)
    candidate = "当前商机处于 S2（方案验证），客户已确认客服工单处理慢，并同意安排产品 Demo。核心场景是售后知识库场景，下一步 Demo 时间为下周四，负责人仍待确认。"
    output = asyncio.run(generate_grounded_summary(FakeSummaryProvider(candidate), result))
    assert output.mode == "llm"
    assert result.summary == candidate
    assert "50 万" not in result.summary


def test_normal_s4_summary_keeps_rule_engine_stage() -> None:
    text = "客户确认项目已经进入内部审批流程，预算 80 万，李总负责最终审批。"
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="进入内部审批流程", field="stage"),
            EvidenceCandidate(id="E02", quote="预算 80 万", field="budget"),
            EvidenceCandidate(id="E03", quote="李总负责最终审批", field="decision_maker"),
        ],
        candidate_budget=[fact("80 万", "E02")],
        candidate_people=[CandidatePerson(name="李总", role="最终审批", kind="decision_maker", authority_confirmed=True, evidence_id="E03", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
        stage_signals=[sig("internal_project_approval", "E01"), sig("budget_discussed", "E02")],
    )
    result = build_validated_opportunity(text, raw)
    candidate = "当前商机处于 S4（决策审批），项目已进入内部审批流程。预算为 80 万，决策人已确认为李总，后续仍需补齐下一步行动。"
    asyncio.run(generate_grounded_summary(FakeSummaryProvider(candidate), result))
    assert result.stage.code == "S4"
    assert result.summary == candidate


def test_normal_s5_summary_does_not_add_procurement_status() -> None:
    text = "客户确认合同已经签完，正式订单已经确认。"
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="合同已经签完", field="stage"),
            EvidenceCandidate(id="E02", quote="正式订单已经确认", field="stage"),
        ],
        stage_signals=[sig("contract_signed", "E01"), sig("order_confirmed", "E02")],
    )
    result = build_validated_opportunity(text, raw)
    candidate = "当前商机处于 S5（赢单签约），合同或正式订单已确认。当前需求、预算和下一步行动仍需补齐，但签约状态不应被重新改写。"
    asyncio.run(generate_grounded_summary(FakeSummaryProvider(candidate), result))
    assert result.stage.code == "S5"
    assert "采购流程" not in result.summary


def test_stage_null_rejects_llm_stage_guess_and_falls_back() -> None:
    result = build_validated_opportunity("客户……预算……审批……", RawExtraction())
    fallback = result.summary
    candidate = "当前商机处于 S3（商务评估），预算和审批信息正在推进。"
    output = asyncio.run(generate_grounded_summary(FakeSummaryProvider(candidate), result))
    assert output.mode == "deterministic_fallback"
    assert "stage_invented_when_stage_null" in output.validation_errors
    assert result.summary == fallback
    assert "S3" not in result.summary


def test_fragmented_input_deterministic_summary_stays_uncertain() -> None:
    result = build_validated_opportunity("客户……预算……审批……", RawExtraction())
    assert result.stage is None
    assert "暂不能" in result.summary
    assert "预算为" not in result.summary


def test_budget_conflict_summary_must_not_pick_one_value() -> None:
    text = "客户先说预算 50 万，后来又说今年没有预算。"
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="预算 50 万", field="budget"),
            EvidenceCandidate(id="E02", quote="今年没有预算", field="budget"),
        ],
        candidate_budget=[fact("50 万", "E01"), fact("今年没有预算", "E02", polarity=Polarity.NEGATIVE)],
        stage_signals=[sig("budget_discussed", "E01")],
        possible_conflicts=[PossibleConflict(field="budget", description="客户预算表述前后冲突。", evidence_ids=["E01", "E02"])],
    )
    result = build_validated_opportunity(text, raw)
    candidate = "当前商机预算为 50 万，建议继续推进商务评估。"
    output = asyncio.run(generate_grounded_summary(FakeSummaryProvider(candidate), result))
    assert output.mode == "deterministic_fallback"
    assert any(error in output.validation_errors for error in ("conflict_resolved_or_hidden", "budget_upgraded"))
    assert "冲突" in result.summary or "阻塞" in result.summary


def test_historical_or_invalidated_facts_cannot_be_written_as_current_facts() -> None:
    text = "客户上个月讨论过 40 万预算，但今天明确说项目暂停。"
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="上个月讨论过 40 万预算", field="budget"),
            EvidenceCandidate(id="E02", quote="项目暂停", field="stage"),
        ],
        candidate_budget=[fact("40 万", "E01", current_validity=CurrentValidity.HISTORICAL)],
        stage_signals=[sig("budget_discussed", "E01", current_validity=CurrentValidity.HISTORICAL), sig("demand_invalidated", "E02", polarity=Polarity.NEGATIVE)],
    )
    result = build_validated_opportunity(text, raw)
    candidate = "当前商机预算为 40 万，项目正在继续推进。"
    output = asyncio.run(generate_grounded_summary(FakeSummaryProvider(candidate), result))
    assert output.mode == "deterministic_fallback"
    assert "budget_upgraded" in output.validation_errors
    assert "项目暂停" in result.summary or "阻塞" in result.summary


def test_missing_decision_maker_rejects_invented_person_or_role() -> None:
    text = "王总说下周四可以安排一次产品 Demo。"
    raw = RawExtraction(
        evidence_candidates=[EvidenceCandidate(id="E01", quote="下周四可以安排一次产品 Demo", field="next_action")],
        candidate_next_actions=[CandidateNextAction(action="安排产品 Demo", time="下周四", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
        stage_signals=[sig("demo_agreed", "E01")],
    )
    result = build_validated_opportunity(text, raw)
    candidate = "当前商机处于 S2（方案验证），建议与王总确认最终采购方案。"
    output = asyncio.run(generate_grounded_summary(FakeSummaryProvider(candidate), result))
    assert output.mode == "deterministic_fallback"
    assert any(error.startswith("unauthorized_person") for error in output.validation_errors)
    assert "王总确认最终采购方案" not in result.summary


def test_missing_timeline_rejects_invented_time() -> None:
    text = "客户说可以安排一次产品 Demo。"
    raw = RawExtraction(
        evidence_candidates=[EvidenceCandidate(id="E01", quote="可以安排一次产品 Demo", field="next_action")],
        candidate_next_actions=[CandidateNextAction(action="安排产品 Demo", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
        stage_signals=[sig("demo_agreed", "E01")],
    )
    result = build_validated_opportunity(text, raw)
    candidate = "当前商机处于 S2（方案验证），建议下周完成 Demo。"
    output = asyncio.run(generate_grounded_summary(FakeSummaryProvider(candidate), result))
    assert output.mode == "deterministic_fallback"
    assert "next_action_time_invented" in output.validation_errors or "timeline_upgraded" in output.validation_errors
    assert "下周完成" not in result.summary


def test_provider_failure_keeps_deterministic_fallback() -> None:
    text = "客户说客服工单处理慢。"
    raw = RawExtraction(
        evidence_candidates=[EvidenceCandidate(id="E01", quote="客服工单处理慢", field="customer_needs")],
        candidate_needs=[fact("客服工单处理慢", "E01")],
        stage_signals=[sig("need_identified", "E01")],
    )
    result = build_validated_opportunity(text, raw)
    fallback = result.summary
    output = asyncio.run(generate_grounded_summary(FakeSummaryProvider(error=LLMProviderError()), result))
    assert output.mode == "deterministic_fallback"
    assert output.fallback_reason == "LLMProviderError"
    assert result.summary == fallback


def test_malformed_llm_output_keeps_deterministic_fallback() -> None:
    result = build_validated_opportunity("客户说客服工单处理慢。", RawExtraction())
    fallback = result.summary
    output = asyncio.run(generate_grounded_summary(FakeSummaryProvider(""), result))
    assert output.mode == "deterministic_fallback"
    assert output.fallback_reason == "grounding_validation_failed"
    assert result.summary == fallback


def test_grounding_violation_rejects_new_amount_person_and_time() -> None:
    text = "客户说客服工单处理慢。"
    raw = RawExtraction(
        evidence_candidates=[EvidenceCandidate(id="E01", quote="客服工单处理慢", field="customer_needs")],
        candidate_needs=[fact("客服工单处理慢", "E01")],
        stage_signals=[sig("need_identified", "E01")],
    )
    result = build_validated_opportunity(text, raw)
    candidate = "当前商机处于 S1（需求初探），预算为 99 万，李总将在下周推进审批。"
    errors = validate_grounded_summary(candidate, result, build_summary_context(result))
    assert "budget_upgraded" in errors
    assert "unauthorized_number:99 万" in errors
    assert any(error.startswith("unauthorized_person") for error in errors)
