from __future__ import annotations

from backend.app.history_title import build_opportunity_title
from backend.app.rules import build_validated_opportunity
from backend.app.schemas import (
    Attribution,
    CandidateFact,
    CandidateNextAction,
    CurrentValidity,
    EvidenceCandidate,
    Explicitness,
    Polarity,
    RawExtraction,
    StageSignal,
)


def sig(signal_type: str, evidence_id: str) -> StageSignal:
    return StageSignal(
        signal_type=signal_type,  # type: ignore[arg-type]
        explicitness=Explicitness.EXPLICIT,
        polarity=Polarity.POSITIVE,
        attribution=Attribution.CUSTOMER,
        current_validity=CurrentValidity.ACTIVE,
        evidence_id=evidence_id,
    )


def fact(value: str, evidence_id: str) -> CandidateFact:
    return CandidateFact(
        value=value,
        evidence_id=evidence_id,
        attribution=Attribution.CUSTOMER,
        explicitness=Explicitness.EXPLICIT,
        polarity=Polarity.POSITIVE,
        current_validity=CurrentValidity.ACTIVE,
    )


def test_title_uses_explicit_customer_and_validated_topic() -> None:
    text = "今天拜访了远川科技客户。客户说客服工单处理慢。"
    result = build_validated_opportunity(
        text,
        RawExtraction(
            evidence_candidates=[EvidenceCandidate(id="E01", quote="客服工单处理慢", field="customer_needs")],
            candidate_needs=[fact("客服工单处理慢", "E01")],
            stage_signals=[sig("need_identified", "E01")],
        ),
    )
    assert build_opportunity_title(text, result) == "远川科技 · 客服自动化项目"


def test_title_without_customer_does_not_invent_name() -> None:
    text = "客户说希望用智能问答覆盖售后知识库场景。"
    result = build_validated_opportunity(
        text,
        RawExtraction(
            evidence_candidates=[EvidenceCandidate(id="E01", quote="售后知识库场景", field="core_scenarios")],
            candidate_scenarios=[fact("售后知识库智能问答", "E01")],
            stage_signals=[sig("need_identified", "E01")],
        ),
    )
    title = build_opportunity_title(text, result)
    assert title == "智能问答场景"
    assert "客户 ·" not in title
    assert "远川" not in title


def test_title_uses_business_event_without_stage_or_status() -> None:
    text = "王总说下周四可以安排一次产品 Demo。"
    result = build_validated_opportunity(
        text,
        RawExtraction(
            evidence_candidates=[EvidenceCandidate(id="E01", quote="下周四可以安排一次产品 Demo", field="next_action")],
            candidate_next_actions=[CandidateNextAction(action="安排产品 Demo", time="下周四", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
            stage_signals=[sig("demo_agreed", "E01")],
        ),
    )
    title = build_opportunity_title(text, result)
    assert title == "产品 Demo 与方案验证"
    assert "S2" not in title
    assert "方案验证" in title


def test_title_for_insufficient_input_is_stable_fallback() -> None:
    result = build_validated_opportunity("客户……预算……审批……", RawExtraction())
    assert build_opportunity_title("客户……预算……审批……", result) == "商机信息待补充"


def test_title_filters_weak_or_business_terms_as_customer_name() -> None:
    text = "今天拜访了某连锁零售客户。客户说客服工单处理慢。"
    result = build_validated_opportunity(
        text,
        RawExtraction(
            evidence_candidates=[EvidenceCandidate(id="E01", quote="客服工单处理慢", field="customer_needs")],
            candidate_needs=[fact("客服工单处理慢", "E01")],
            stage_signals=[sig("need_identified", "E01")],
        ),
    )
    assert build_opportunity_title(text, result) == "客服自动化项目"


def test_title_uses_explicit_project_theme_from_raw_context() -> None:
    text = "客户提到星河智能客服系统，需要先看报价和采购流程。"
    result = build_validated_opportunity(
        text,
        RawExtraction(
            evidence_candidates=[EvidenceCandidate(id="E01", quote="看报价", field="stage")],
            stage_signals=[sig("quote_discussed", "E01")],
        ),
    )
    assert build_opportunity_title(text, result) == "星河智能客服系统"


def test_title_does_not_use_stage_or_status_as_fallback() -> None:
    text = "今天第一次和客户简单认识了一下。"
    result = build_validated_opportunity(text, RawExtraction())
    assert result.stage is not None
    title = build_opportunity_title(text, result)
    assert title == "商机信息待补充"
    assert "S0" not in title
    assert "线索" not in title


def test_title_stays_stable_across_revisions_for_same_opportunity() -> None:
    original = "今天拜访了星河科技客户。客户希望建设客服自动化项目。"
    v1 = build_validated_opportunity(
        original,
        RawExtraction(
            evidence_candidates=[EvidenceCandidate(id="E01", quote="客服自动化项目", field="core_scenarios")],
            candidate_scenarios=[fact("客服自动化项目", "E01")],
            stage_signals=[sig("need_identified", "E01")],
        ),
    )
    v2_text = original + "\n补充：客户确认下周安排产品 Demo。"
    v2 = build_validated_opportunity(
        v2_text,
        RawExtraction(
            evidence_candidates=[
                EvidenceCandidate(id="E01", quote="客服自动化项目", field="core_scenarios"),
                EvidenceCandidate(id="E02", quote="下周安排产品 Demo", field="next_action"),
            ],
            candidate_scenarios=[fact("客服自动化项目", "E01")],
            candidate_next_actions=[CandidateNextAction(action="安排产品 Demo", time="下周", evidence_id="E02", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
            stage_signals=[sig("need_identified", "E01"), sig("demo_agreed", "E02")],
        ),
        revision=2,
    )
    assert build_opportunity_title(original, v1) == "星河科技 · 客服自动化项目"
    assert build_opportunity_title(original, v2) == "星河科技 · 客服自动化项目"
