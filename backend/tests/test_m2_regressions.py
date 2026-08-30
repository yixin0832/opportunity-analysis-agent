from __future__ import annotations

import asyncio

from backend.app.input_builder import build_revision_input
from backend.app.pipeline import run_mock_pipeline
from backend.app.rules import build_validated_opportunity
from backend.app.schemas import (
    AnalyzeRequest,
    Attribution,
    CandidateFact,
    CandidateNextAction,
    CandidatePerson,
    ClarifyAnswer,
    CurrentValidity,
    DecisionStatus,
    EvidenceCandidate,
    Explicitness,
    FieldStatus,
    Polarity,
    PossibleConflict,
    RawExtraction,
    StageCode,
    StageSignal,
)


def sig(signal_type: str, evidence_id: str) -> StageSignal:
    return StageSignal(signal_type=signal_type, explicitness=Explicitness.EXPLICIT, polarity=Polarity.POSITIVE, attribution=Attribution.CUSTOMER, current_validity=CurrentValidity.ACTIVE, evidence_id=evidence_id)  # type: ignore[arg-type]


def fact(value: str, evidence_id: str) -> CandidateFact:
    return CandidateFact(value=value, evidence_id=evidence_id, attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT, polarity=Polarity.POSITIVE, current_validity=CurrentValidity.ACTIVE)


def test_single_keyword_approval_cannot_produce_s4():
    result = asyncio.run(run_mock_pipeline(AnalyzeRequest(input_text="客户……预算……审批……")))
    assert result.status == DecisionStatus.UNABLE_TO_JUDGE
    assert result.stage is None


def test_single_budget_word_cannot_produce_s3():
    raw = RawExtraction(evidence_candidates=[EvidenceCandidate(id="E01", quote="预算", field="budget")], stage_signals=[sig("budget_discussed", "E01")])
    result = build_validated_opportunity("客户提到预算。", raw)
    assert result.stage is None or result.stage.code != StageCode.S3
    assert result.evidence[0].sufficient is False


def test_person_name_alone_cannot_confirm_decision_maker():
    result = asyncio.run(run_mock_pipeline(AnalyzeRequest(input_text="王总说下周四可以安排一次产品 Demo。")))
    assert result.crm_fields.decision_maker.name is None
    assert result.crm_fields.decision_maker.status == FieldStatus.UNKNOWN
    assert result.crm_fields.influencers == []


def test_budget_conflict_propagates_to_crm_budget():
    result = asyncio.run(run_mock_pipeline(AnalyzeRequest(input_text="客户先说今年预算 50 万，可以评估客服自动化方案。会议后半段又说今年没有预算，可能要等明年再看。")))
    assert result.crm_fields.budget.status == FieldStatus.CONFLICT
    assert result.crm_fields.budget.value is None
    assert set(result.crm_fields.budget.evidence_ids) >= {"E02", "E03"}
    assert result.crm_fields.budget.conflicting_values == ["50 万", "今年没有预算"]


def test_uncertain_demand_validity_blocks_mechanical_s3_but_keeps_reliable_s2():
    result = asyncio.run(run_mock_pipeline(AnalyzeRequest(input_text="客户先说今年预算 50 万，可以评估客服自动化方案。会议后半段又说今年没有预算，可能要等明年再看。")))
    assert result.status == DecisionStatus.NEED_CONFIRMATION
    assert result.stage is not None
    assert result.stage.code == StageCode.S2
    assert result.stage.code != StageCode.S3
    signal_types = {signal["signal_type"] for signal in result.developer_details["stage_signals"]}
    assert "solution_evaluation" in signal_types


def test_formal_procurement_solution_evaluation_is_s2_when_budget_conflict_blocks_s3():
    text = "客户确认招生咨询和学员售后答疑两个场景仍然要继续推进，也希望评估正式采购方案。赵经理说项目预算大约 50 万，采购刘经理说立项预算是 70 万左右。"
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="两个场景仍然要继续推进", field="customer_needs"),
            EvidenceCandidate(id="E02", quote="项目预算大约 50 万", field="budget"),
            EvidenceCandidate(id="E03", quote="立项预算是 70 万左右", field="budget"),
        ],
        candidate_needs=[fact("招生咨询和学员售后答疑两个场景继续推进", "E01")],
        candidate_budget=[fact("大约 50 万", "E02"), fact("70 万左右", "E03")],
        stage_signals=[sig("need_identified", "E01"), sig("budget_discussed", "E02"), sig("budget_discussed", "E03")],
        possible_conflicts=[PossibleConflict(field="budget", description="预算金额口径冲突", evidence_ids=["E02", "E03"])],
    )
    result = build_validated_opportunity(text, raw)
    assert result.stage is not None
    assert result.stage.code == StageCode.S2
    signal_types = {signal["signal_type"] for signal in result.developer_details["stage_signals"]}
    assert "solution_evaluation" in signal_types
    assert result.crm_fields.budget.status == FieldStatus.CONFLICT


def test_confirmed_next_action_time_can_share_original_timeline_when_extracted():
    result = asyncio.run(run_mock_pipeline(AnalyzeRequest(input_text="王总说下周四可以安排一次产品 Demo。")))
    assert result.confirmed_next_action.time == "下周四"
    assert result.crm_fields.timeline.value == "下周四安排产品 Demo"
    assert result.crm_fields.timeline.status == FieldStatus.CONFIRMED


def test_unable_to_judge_does_not_force_s0_to_s5():
    result = asyncio.run(run_mock_pipeline(AnalyzeRequest(input_text="客户……预算……审批……")))
    assert result.status == DecisionStatus.UNABLE_TO_JUDGE
    assert result.stage is None


def test_real_customer_contact_without_higher_signal_falls_back_to_s0():
    result = build_validated_opportunity(
        "今天和客户沟通后，我感觉客户挺感兴趣，应该很快会进入内部审批。",
        RawExtraction(),
    )
    assert result.status == DecisionStatus.COMPLETE
    assert result.stage is not None
    assert result.stage.code == StageCode.S0


def test_fragmented_customer_keywords_do_not_fall_back_to_s0():
    result = build_validated_opportunity("客户……预算……审批……", RawExtraction())
    assert result.status == DecisionStatus.UNABLE_TO_JUDGE
    assert result.stage is None


def test_existing_but_insufficient_evidence_cannot_confirm_key_field():
    raw = RawExtraction(evidence_candidates=[EvidenceCandidate(id="E01", quote="审批", field="stage")], stage_signals=[sig("internal_project_approval", "E01")])
    result = build_validated_opportunity("客户提到审批。", raw)
    assert result.evidence[0].valid is True
    assert result.evidence[0].sufficient is False
    assert result.stage is None or result.stage.code != StageCode.S4


def test_summary_is_business_contract_not_raw_input_replay():
    text = "今天拜访了某连锁零售客户。客户说门店客服工单处理慢，希望用智能问答先覆盖售后知识库场景。王总说下周四可以安排一次产品 Demo。"
    result = asyncio.run(run_mock_pipeline(AnalyzeRequest(input_text=text)))
    assert result.summary != f"当前商机阶段判断为 S2（方案验证）。输入摘要：{text}"
    assert "S2" in result.summary
    assert "门店客服工单处理慢" in result.summary
    assert "安排产品 Demo" in result.summary


def test_blocker_does_not_generate_template_next_action_for_budget_conflict():
    result = asyncio.run(run_mock_pipeline(AnalyzeRequest(input_text="客户先说今年预算 50 万，可以评估客服自动化方案。会议后半段又说今年没有预算，可能要等明年再看。")))
    assert result.recommended_next_actions == []
    assert result.confirmed_next_action is None
    assert any(item.value == "下一步行动未确认" for item in result.unconfirmed_info)


def test_insufficient_input_goes_to_analysis_warnings_not_opportunity_risks():
    result = asyncio.run(run_mock_pipeline(AnalyzeRequest(input_text="客户……预算……审批……")))
    assert result.opportunity_risks == []
    assert result.analysis_warnings
    assert result.analysis_warnings[0].type == "insufficient_input"


def test_unknown_decision_authority_stays_unconfirmed_info_for_s2_demo():
    result = asyncio.run(run_mock_pipeline(AnalyzeRequest(input_text="王总说下周四可以安排一次产品 Demo。")))
    risk_types = {risk.type for risk in result.opportunity_risks}
    assert "unknown_decision_authority" not in risk_types
    assert any(item.value == "决策人或决策权限未确认" for item in result.unconfirmed_info)

def test_next_action_missing_owner_and_time_becomes_pending_in_final_result():
    raw = RawExtraction(
        evidence_candidates=[EvidenceCandidate(id="E01", quote="下次安排一次产品 Demo", field="next_action")],
        candidate_next_actions=[
            CandidateNextAction(
                action="安排产品 Demo",
                evidence_id="E01",
                attribution=Attribution.CUSTOMER,
                explicitness=Explicitness.EXPLICIT,
            )
        ],
        stage_signals=[sig("demo_agreed", "E01")],
    )
    result = build_validated_opportunity("客户说下次安排一次产品 Demo。", raw)
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.owner == "待确认"
    assert result.confirmed_next_action.time == "待确认"


def test_explicit_final_approval_confirms_decision_maker():
    raw = RawExtraction(
        evidence_candidates=[EvidenceCandidate(id="E01", quote="李总负责最终审批", field="decision_maker")],
        candidate_people=[CandidatePerson(name="李总", role="最终审批", kind="decision_maker", authority_confirmed=True, evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
    )
    result = build_validated_opportunity("李总负责最终审批。", raw)
    assert result.crm_fields.decision_maker.name == "李总"
    assert result.crm_fields.decision_maker.status == FieldStatus.CONFIRMED
    assert result.crm_fields.decision_maker.authority_confirmed is True


def test_decision_maker_candidate_without_authority_is_partial_not_confirmed():
    raw = RawExtraction(
        evidence_candidates=[EvidenceCandidate(id="E01", quote="王总", field="person")],
        candidate_people=[CandidatePerson(name="王总", kind="decision_maker", authority_confirmed=False, evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
    )
    result = build_validated_opportunity("王总参加了会议。", raw)
    assert result.crm_fields.decision_maker.name == "王总"
    assert result.crm_fields.decision_maker.status == FieldStatus.PARTIAL
    assert result.crm_fields.decision_maker.status != FieldStatus.CONFIRMED
    assert any(item.value == "决策人或决策权限未确认" for item in result.unconfirmed_info)


def test_technical_solution_evaluator_maps_to_influencer():
    raw = RawExtraction(
        evidence_candidates=[EvidenceCandidate(id="E01", quote="IT 王工负责技术方案评估", field="people")],
        candidate_people=[CandidatePerson(name="IT 王工", role="技术方案评估", kind="influencer", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
    )
    result = build_validated_opportunity("IT 王工负责技术方案评估。", raw)
    assert len(result.crm_fields.influencers) == 1
    assert result.crm_fields.influencers[0].name == "IT 王工"
    assert result.crm_fields.decision_maker.status == FieldStatus.UNKNOWN


def test_influencer_name_only_evidence_is_not_confirmed():
    raw = RawExtraction(
        evidence_candidates=[EvidenceCandidate(id="E01", quote="IT 王工", field="person")],
        candidate_people=[CandidatePerson(name="IT 王工", role="IT", kind="influencer", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
    )
    result = build_validated_opportunity("参会人包括客服负责人王总和 IT 王工。", raw)
    assert result.crm_fields.influencers == []
    assert any(item.value == "影响人未确认" for item in result.unconfirmed_info)


def test_influencer_requires_business_evaluation_context_not_just_attendance():
    raw = RawExtraction(
        evidence_candidates=[EvidenceCandidate(id="E01", quote="让客服主管和 IT 王工一起看效果", field="person")],
        candidate_people=[CandidatePerson(name="IT 王工", role="IT", kind="influencer", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
    )
    result = build_validated_opportunity("王总说下周四可以安排一次产品 Demo，让客服主管和 IT 王工一起看效果。", raw)
    assert len(result.crm_fields.influencers) == 1
    assert result.crm_fields.influencers[0].name == "IT 王工"
    assert result.crm_fields.influencers[0].evidence_ids == ["E01"]


def test_meeting_or_demo_coordinator_unknown_person_does_not_map_to_influencer():
    raw = RawExtraction(
        evidence_candidates=[EvidenceCandidate(id="E01", quote="王总负责协调下周 Demo", field="person")],
        candidate_people=[CandidatePerson(name="王总", role="协调下周 Demo", kind="unknown", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
    )
    result = build_validated_opportunity("王总负责协调下周 Demo。", raw)
    assert result.crm_fields.influencers == []
    assert result.crm_fields.decision_maker.status == FieldStatus.UNKNOWN


def test_deterministic_customer_roles_keep_influencers_stable_when_llm_omits_people():
    text = "今天和云澜教育集团教务运营负责人赵经理、信息化负责人孙工复盘了智能客服试点。下午采购刘经理补充说财务系统里的立项预算是 70 万左右。客户希望评估正式采购方案。"
    raw = RawExtraction(
        evidence_candidates=[EvidenceCandidate(id="E01", quote="客户希望评估正式采购方案", field="stage")],
        stage_signals=[sig("solution_evaluation", "E01")],
    )
    result = build_validated_opportunity(text, raw)
    names = {person.name for person in result.crm_fields.influencers}
    assert {"赵经理", "孙工", "刘经理"} <= names


def test_influencer_does_not_merge_unrelated_need_evidence_into_confirmed_person():
    text = "今天和云澜教育集团教务运营负责人赵经理、信息化负责人孙工复盘了智能客服试点。客户确认招生咨询和学员售后答疑两个场景仍然要继续推进，也希望评估正式采购方案。"
    raw = RawExtraction(
        evidence_candidates=[EvidenceCandidate(id="E01", quote="客户确认招生咨询和学员售后答疑两个场景仍然要继续推进，也希望评估正式采购方案", field="customer_needs")],
        candidate_people=[CandidatePerson(name="赵经理", role="教务运营负责人", kind="influencer", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
        stage_signals=[sig("solution_evaluation", "E01")],
    )
    result = build_validated_opportunity(text, raw)
    zhao = next(person for person in result.crm_fields.influencers if person.name == "赵经理")
    quotes = {item.id: item.quote for item in result.evidence}
    assert all("赵经理" in quotes[evidence_id] for evidence_id in zhao.evidence_ids)
    assert all("复盘" in quotes[evidence_id] for evidence_id in zhao.evidence_ids)


def test_duplicate_influencer_candidates_are_merged_for_crm_display():
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="王工负责技术评估", field="people"),
            EvidenceCandidate(id="E02", quote="王工还会参与 PoC 结果评价", field="people"),
        ],
        candidate_people=[
            CandidatePerson(name="王工", role="技术评估", kind="influencer", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
            CandidatePerson(name="王工", role="PoC 结果评价", kind="influencer", evidence_id="E02", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
        ],
    )
    result = build_validated_opportunity("王工负责技术评估。王工还会参与 PoC 结果评价。", raw)
    assert len(raw.candidate_people) == 2
    assert len(result.evidence) == 2
    assert len(result.crm_fields.influencers) == 1
    influencer = result.crm_fields.influencers[0]
    assert influencer.name == "王工"
    assert influencer.role == "技术评估、PoC 结果评价"
    assert influencer.evidence_ids == ["E01", "E02"]



def test_s0_does_not_generate_template_next_action():
    raw = RawExtraction()
    result = build_validated_opportunity("今天第一次和客户简单认识了一下。", raw)
    assert result.stage is not None
    assert result.stage.code == StageCode.S0
    assert result.recommended_next_actions == []
    assert result.confirmed_next_action is None
    assert any(item.value == "下一步行动未确认" for item in result.unconfirmed_info)


def test_unknown_and_conflict_fields_include_business_reasons():
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="预算 50 万", field="budget"),
            EvidenceCandidate(id="E02", quote="今年没有预算", field="budget"),
        ],
        candidate_budget=[fact("50 万", "E01"), CandidateFact(value="今年没有预算", evidence_id="E02", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT, polarity=Polarity.NEGATIVE, current_validity=CurrentValidity.ACTIVE)],
        possible_conflicts=[PossibleConflict(field="budget", description="预算前后冲突", evidence_ids=["E01", "E02"])],
    )
    result = build_validated_opportunity("客户先说预算 50 万，后来又说今年没有预算。", raw)
    assert result.crm_fields.budget.status == FieldStatus.CONFLICT
    assert result.crm_fields.budget.reason
    assert "不能自动选择" in result.crm_fields.budget.reason
    assert result.crm_fields.decision_maker.reason
    assert any(item.reason for item in result.unconfirmed_info if item.value == "预算存在冲突")


def test_budget_conflict_clarification_uses_current_conflicting_values():
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="今年项目预算大约 60 万", field="budget"),
            EvidenceCandidate(id="E02", quote="今年预算目前已经被冻结", field="budget"),
        ],
        candidate_budget=[
            fact("大约 60 万", "E01"),
            CandidateFact(value="今年预算目前已经被冻结", evidence_id="E02", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT, polarity=Polarity.NEGATIVE, current_validity=CurrentValidity.ACTIVE),
        ],
        possible_conflicts=[PossibleConflict(field="budget", description="预算前后冲突", evidence_ids=["E01", "E02"])],
    )
    result = build_validated_opportunity("客户上午表示今年项目预算大约 60 万。下午客户又表示今年预算目前已经被冻结。", raw)
    questions = [question.question for question in result.clarification.questions]
    assert any("大约 60 万" in question and "今年预算目前已经被冻结" in question for question in questions)
    assert all("50" not in question for question in questions)
    assert all("明年" not in question for question in questions)


def test_budget_conflict_clarification_uses_different_current_amounts():
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="预算约 30 万", field="budget"),
            EvidenceCandidate(id="E02", quote="预算已经被冻结", field="budget"),
        ],
        candidate_budget=[
            fact("约 30 万", "E01"),
            CandidateFact(value="预算已经被冻结", evidence_id="E02", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT, polarity=Polarity.NEGATIVE, current_validity=CurrentValidity.ACTIVE),
        ],
        possible_conflicts=[PossibleConflict(field="budget", description="预算金额与冻结状态冲突", evidence_ids=["E01", "E02"])],
    )
    result = build_validated_opportunity("客户说预算约 30 万，后来又说预算已经被冻结。", raw)
    questions = [question.question for question in result.clarification.questions]
    assert any("约 30 万" in question and "预算已经被冻结" in question for question in questions)
    assert all("50" not in question and "60" not in question for question in questions)


def test_budget_conflict_clarification_handles_three_conflicting_values():
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="预算先按 25 万看", field="budget"),
            EvidenceCandidate(id="E02", quote="采购后来提出最多只能批 18 万", field="budget"),
            EvidenceCandidate(id="E03", quote="财务暂时不放预算", field="budget"),
        ],
        candidate_budget=[
            fact("25 万", "E01"),
            fact("最多 18 万", "E02"),
            CandidateFact(value="财务暂时不放预算", evidence_id="E03", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT, polarity=Polarity.NEGATIVE, current_validity=CurrentValidity.ACTIVE),
        ],
        possible_conflicts=[PossibleConflict(field="budget", description="预算存在多个不一致表述", evidence_ids=["E01", "E02", "E03"])],
    )
    result = build_validated_opportunity("客户说预算先按 25 万看，采购后来提出最多只能批 18 万，但财务暂时不放预算。", raw)
    questions = [question.question for question in result.clarification.questions]
    assert any("25 万" in question and "最多 18 万" in question and "财务暂时不放预算" in question for question in questions)


def test_budget_conflict_clarification_suppresses_generic_budget_question():
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="项目预算大约 50 万", field="budget"),
            EvidenceCandidate(id="E02", quote="立项预算是 70 万左右", field="budget"),
        ],
        candidate_budget=[fact("大约 50 万", "E01"), fact("70 万左右", "E02")],
        stage_signals=[sig("budget_discussed", "E01"), sig("budget_discussed", "E02")],
        possible_conflicts=[PossibleConflict(field="budget", description="预算金额口径冲突", evidence_ids=["E01", "E02"])],
    )
    result = build_validated_opportunity("赵经理说项目预算大约 50 万。采购刘经理说立项预算是 70 万左右。", raw)
    questions = [question for question in result.clarification.questions if question.field == "budget"]
    assert len(questions) == 1
    assert "大约 50 万" in questions[0].question
    assert "70 万左右" in questions[0].question


def test_equivalent_user_budget_values_do_not_create_new_conflict():
    text = """【原始销售拜访记录】
客户表示预算大约 50 万，同时询问正式报价。

【第 2 次分析补充确认信息】
预算确认：客户确定 预算最终为70万"""
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="预算大约 50 万", field="budget", start_char=text.index("预算大约 50 万")),
            EvidenceCandidate(id="E02", quote="正式报价", field="stage", start_char=text.index("正式报价")),
            EvidenceCandidate(id="E03", quote="70万", field="budget", start_char=text.index("70万")),
        ],
        candidate_budget=[fact("大约 50 万", "E01"), fact("70万", "E03")],
        stage_signals=[sig("quote_discussed", "E02"), sig("budget_discussed", "E03")],
    )
    result = build_validated_opportunity(text, raw)
    assert result.crm_fields.budget.status == FieldStatus.CONFIRMED
    assert result.crm_fields.budget.value == "70万"
    assert not any(item.value == "预算存在冲突" for item in result.unconfirmed_info)


def test_historical_budget_value_does_not_use_missing_budget_reason():
    raw = RawExtraction(
        evidence_candidates=[EvidenceCandidate(id="E01", quote="上个月已经讨论过 40 万预算", field="budget")],
        candidate_budget=[CandidateFact(value="40 万", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT, polarity=Polarity.POSITIVE, current_validity=CurrentValidity.HISTORICAL)],
    )
    result = build_validated_opportunity("客户上个月已经讨论过 40 万预算，但今天没有确认当前预算是否仍有效。", raw)
    assert result.crm_fields.budget.value == "40 万"
    assert result.crm_fields.budget.status == FieldStatus.UNKNOWN
    assert "历史状态" in result.crm_fields.budget.reason
    assert "未提供预算金额" not in result.crm_fields.budget.reason
    reasons = {item.value: item.reason for item in result.unconfirmed_info}
    assert "历史状态" in reasons["预算未确认"]
    assert "未提供预算金额" not in reasons["预算未确认"]


def test_different_historical_budget_value_uses_historical_reason_when_project_paused():
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="去年预留过 80 万预算", field="budget"),
            EvidenceCandidate(id="E02", quote="当前项目已经暂停", field="stage"),
        ],
        candidate_budget=[CandidateFact(value="80 万", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT, polarity=Polarity.POSITIVE, current_validity=CurrentValidity.HISTORICAL)],
        stage_signals=[StageSignal(signal_type="demand_invalidated", explicitness=Explicitness.EXPLICIT, polarity=Polarity.NEGATIVE, attribution=Attribution.CUSTOMER, current_validity=CurrentValidity.ACTIVE, evidence_id="E02")],
    )
    result = build_validated_opportunity("客户去年预留过 80 万预算，但当前项目已经暂停。", raw)
    assert result.crm_fields.budget.value == "80 万"
    assert result.crm_fields.budget.status == FieldStatus.UNKNOWN
    assert "历史状态" in result.crm_fields.budget.reason
    assert "未提供预算金额" not in result.crm_fields.budget.reason
    assert result.developer_details["stage_decision_reason"] == "stage_blocked_or_conflicting"


def test_negative_timeline_value_does_not_use_missing_timeline_reason():
    raw = RawExtraction(
        evidence_candidates=[EvidenceCandidate(id="E01", quote="上线时间已经推迟到下季度", field="timeline")],
        candidate_timeline=[CandidateFact(value="推迟到下季度", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT, polarity=Polarity.NEGATIVE, current_validity=CurrentValidity.ACTIVE)],
    )
    result = build_validated_opportunity("客户说上线时间已经推迟到下季度。", raw)
    assert result.crm_fields.timeline.value == "推迟到下季度"
    assert result.crm_fields.timeline.status == FieldStatus.UNKNOWN
    assert "不可用、否定或失效状态" in result.crm_fields.timeline.reason
    assert "未提供明确推进时间" not in result.crm_fields.timeline.reason
    reasons = {item.value: item.reason for item in result.unconfirmed_info}
    assert "不可用、否定或失效状态" in reasons["时间计划未确认"]


def test_timeline_conflict_preserves_current_time_expressions_without_budget_template():
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="本月底启动上线", field="timeline"),
            EvidenceCandidate(id="E02", quote="推迟到下季度再启动", field="timeline"),
        ],
        candidate_timeline=[
            fact("本月底启动上线", "E01"),
            CandidateFact(value="推迟到下季度再启动", evidence_id="E02", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT, polarity=Polarity.NEGATIVE, current_validity=CurrentValidity.ACTIVE),
        ],
        possible_conflicts=[PossibleConflict(field="timeline", description="启动时间存在冲突", evidence_ids=["E01", "E02"])],
    )
    result = build_validated_opportunity("客户先说本月底启动上线，后来又说推迟到下季度再启动。", raw)
    assert result.crm_fields.timeline.status == FieldStatus.CONFLICT
    assert result.crm_fields.timeline.conflicting_values == ["本月底启动上线", "推迟到下季度再启动"]
    questions = [question.question for question in result.clarification.questions] if result.clarification else []
    assert all("50" not in question and "60" not in question for question in questions)


def test_missing_budget_timeline_and_decision_maker_have_reasons():
    result = build_validated_opportunity("今天第一次和客户简单认识了一下。", RawExtraction())
    assert result.crm_fields.budget.reason == "本次记录未提供预算金额、预算范围或明确预算安排。"
    assert result.crm_fields.timeline.reason == "本次记录未提供明确推进时间或上线计划。"
    assert result.crm_fields.decision_maker.reason == "当前记录未明确最终审批、拍板或购买决策权限。"
    reasons = {item.value: item.reason for item in result.unconfirmed_info}
    assert reasons["预算未确认"]
    assert reasons["决策人或决策权限未确认"]
    assert reasons["时间计划未确认"]


def test_stage_null_fragmented_input_uses_insufficient_input_reason():
    result = build_validated_opportunity("客户……预算……审批……", RawExtraction())
    assert result.stage is None
    assert result.status == DecisionStatus.UNABLE_TO_JUDGE
    assert result.developer_details["stage_decision_reason"] == "insufficient_input"
    assert result.analysis_warnings[0].description == "输入文本本身过于残缺，无法正常解析销售拜访信息。"
    assert "输入信息过于残缺" not in result.analysis_warnings[0].description


def test_stage_null_historical_or_blocked_context_uses_blocked_reason():
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="之前讨论过 50 万预算", field="stage"),
            EvidenceCandidate(id="E02", quote="客户今天确认项目暂停", field="stage"),
        ],
        stage_signals=[
            StageSignal(
                signal_type="budget_discussed",
                explicitness=Explicitness.EXPLICIT,
                polarity=Polarity.POSITIVE,
                attribution=Attribution.CUSTOMER,
                current_validity=CurrentValidity.HISTORICAL,
                evidence_id="E01",
            ),
            StageSignal(
                signal_type="demand_invalidated",
                explicitness=Explicitness.EXPLICIT,
                polarity=Polarity.NEGATIVE,
                attribution=Attribution.CUSTOMER,
                current_validity=CurrentValidity.ACTIVE,
                evidence_id="E02",
            ),
        ],
    )
    result = build_validated_opportunity("之前讨论过 50 万预算，但客户今天确认项目暂停，不再推进。", raw)
    assert result.stage is None
    assert result.status == DecisionStatus.NEED_CONFIRMATION
    assert result.developer_details["stage_decision_reason"] == "stage_blocked_or_conflicting"
    assert "项目暂停" in result.analysis_warnings[0].description
    assert "输入信息过于残缺" not in result.summary
    assert "输入信息过于残缺" not in result.analysis_warnings[0].description


def test_stage_null_complete_text_without_stage_signal_uses_stage_signal_reason():
    raw = RawExtraction(
        evidence_candidates=[EvidenceCandidate(id="E01", quote="客户表示后续可以再看看", field="ambiguity")],
        ambiguities=["客户态度积极，但没有明确需求、方案验证或商务推进事实"],
    )
    result = build_validated_opportunity("客户表示后续可以再看看，目前还没有明确需求或推进安排。", raw)
    assert result.stage is None
    assert result.status == DecisionStatus.UNABLE_TO_JUDGE
    assert result.developer_details["stage_decision_reason"] == "insufficient_stage_signal"
    assert result.analysis_warnings[0].description == "当前记录已有部分业务事实，但不足以确认 S0-S5 销售阶段。"
    assert "输入信息过于残缺" not in result.summary
    assert "输入信息过于残缺" not in result.analysis_warnings[0].description


def test_stage_null_without_extracted_business_facts_uses_business_fact_reason():
    result = build_validated_opportunity("客户表示后续再联系，目前没有展开具体业务内容。", RawExtraction())
    assert result.stage is None
    assert result.status == DecisionStatus.UNABLE_TO_JUDGE
    assert result.developer_details["stage_decision_reason"] == "insufficient_business_facts"
    assert "缺少客户需求、使用场景或推进动作" in result.analysis_warnings[0].description
    assert "输入信息过于残缺" not in result.summary


def test_blocking_risk_evidence_ids_are_deduped_within_same_risk():
    raw = RawExtraction(
        evidence_candidates=[EvidenceCandidate(id="E01", quote="项目已经暂停，今年不再推进，最快明年再重新评估", field="demand_status")],
        stage_signals=[
            StageSignal(
                signal_type="demand_invalidated",
                explicitness=Explicitness.EXPLICIT,
                polarity=Polarity.NEGATIVE,
                attribution=Attribution.CUSTOMER,
                current_validity=CurrentValidity.ACTIVE,
                evidence_id="E01",
            ),
            StageSignal(
                signal_type="demand_delayed",
                explicitness=Explicitness.EXPLICIT,
                polarity=Polarity.NEGATIVE,
                attribution=Attribution.CUSTOMER,
                current_validity=CurrentValidity.ACTIVE,
                evidence_id="E01",
            ),
        ],
    )
    result = build_validated_opportunity("客户说项目已经暂停，今年不再推进，最快明年再重新评估。", raw)
    blocking_risks = [risk for risk in result.opportunity_risks if risk.type == "demand_invalidated"]
    assert blocking_risks
    assert blocking_risks[0].evidence_ids == ["E01"]


def test_user_budget_correction_supersedes_original_budget_without_customer_conflict():
    text = """【原始销售拜访记录】
客户表示预算 30 万，同时询问正式报价和采购流程。

【第 2 次分析修正识别事实】
以下内容是用户对已识别信息的明确修正；当前分析应以修正后的事实为准，修正前内容仅作为历史记录保留，不视为客户前后表达矛盾。
预算修正：原文写错了，预算改为 80 万。"""
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="预算 30 万", field="budget", start_char=text.index("预算 30 万")),
            EvidenceCandidate(id="E02", quote="正式报价", field="stage"),
            EvidenceCandidate(id="E03", quote="预算改为 80 万", field="budget", start_char=text.index("预算改为 80 万")),
        ],
        candidate_budget=[fact("30 万", "E01"), fact("80 万", "E03")],
        stage_signals=[sig("quote_discussed", "E02"), sig("budget_discussed", "E03")],
        possible_conflicts=[PossibleConflict(field="budget", description="预算金额存在冲突", evidence_ids=["E01", "E03"])],
    )
    result = build_validated_opportunity(text, raw)
    assert result.crm_fields.budget.status == FieldStatus.CONFIRMED
    assert result.crm_fields.budget.value == "80 万"
    assert result.stage is not None
    assert result.stage.code == StageCode.S3
    assert not any(risk.type == "conflict" for risk in result.opportunity_risks)
    assert not any(item.value == "预算存在冲突" for item in result.unconfirmed_info)


def test_later_clarification_keeps_prior_user_correction_as_current_fact():
    text = """【原始销售拜访记录】
客户表示预算 35 万，同时询问正式报价和采购流程。最终审批人目前还没有确认。

【第 2 次分析修正识别事实】
以下内容是用户对已识别信息的明确修正；当前分析应以修正后的事实为准，修正前内容仅作为历史记录保留，不视为客户前后表达矛盾。
预算修正：原文写错了，预算实际为 90 万。

【第 3 次分析补充确认信息】
决策人确认：张总是最终采购决策人。"""
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="预算 35 万", field="budget", start_char=text.index("预算 35 万")),
            EvidenceCandidate(id="E02", quote="正式报价", field="stage"),
            EvidenceCandidate(id="E03", quote="预算实际为 90 万", field="budget", start_char=text.index("预算实际为 90 万")),
            EvidenceCandidate(id="E04", quote="张总是最终采购决策人", field="decision_maker", start_char=text.index("张总是最终采购决策人")),
        ],
        candidate_budget=[fact("35 万", "E01"), fact("90 万", "E03")],
        candidate_people=[
            CandidatePerson(
                name="张总",
                role="最终采购决策人",
                kind="decision_maker",
                authority_confirmed=True,
                evidence_id="E04",
                attribution=Attribution.CUSTOMER,
                explicitness=Explicitness.EXPLICIT,
            )
        ],
        stage_signals=[sig("quote_discussed", "E02"), sig("budget_discussed", "E03")],
        possible_conflicts=[PossibleConflict(field="budget", description="预算金额存在冲突", evidence_ids=["E01", "E03"])],
    )
    result = build_validated_opportunity(text, raw)
    assert result.crm_fields.budget.status == FieldStatus.CONFIRMED
    assert result.crm_fields.budget.value == "90 万"
    assert result.crm_fields.decision_maker.name == "张总"
    assert result.crm_fields.decision_maker.status == FieldStatus.CONFIRMED
    assert result.stage is not None
    assert result.stage.code == StageCode.S3
    assert not any(risk.type == "conflict" for risk in result.opportunity_risks)
    questions = [question.question for question in result.clarification.questions] if result.clarification else []
    assert not any("35 万" in question and "90 万" in question for question in questions)


def test_customer_budget_conflict_without_user_correction_remains_a_conflict():
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="预算 30 万", field="budget"),
            EvidenceCandidate(id="E02", quote="预算改为 80 万", field="budget"),
        ],
        candidate_budget=[fact("30 万", "E01"), fact("80 万", "E02")],
        stage_signals=[sig("budget_discussed", "E01"), sig("budget_discussed", "E02")],
        possible_conflicts=[PossibleConflict(field="budget", description="客户预算表述前后冲突", evidence_ids=["E01", "E02"])],
    )
    result = build_validated_opportunity("客户上午说预算 30 万，下午又说预算改为 80 万。", raw)
    assert result.crm_fields.budget.status == FieldStatus.CONFLICT
    assert result.crm_fields.budget.conflicting_values == ["30 万", "80 万"]
    assert any(risk.type == "conflict" for risk in result.opportunity_risks)
    assert result.stage is None


def test_blocked_commercial_signal_does_not_fallback_to_s0_without_need_signal():
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="预算 70 万", field="budget"),
            EvidenceCandidate(id="E02", quote="预算已经冻结", field="budget"),
        ],
        candidate_budget=[
            fact("70 万", "E01"),
            CandidateFact(value="预算已经冻结", evidence_id="E02", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT, polarity=Polarity.NEGATIVE, current_validity=CurrentValidity.ACTIVE),
        ],
        stage_signals=[sig("budget_discussed", "E01")],
        possible_conflicts=[PossibleConflict(field="budget", description="预算金额与冻结状态冲突", evidence_ids=["E01", "E02"])],
    )
    result = build_validated_opportunity("客户表示预算 70 万，但随后确认预算已经冻结。", raw)
    assert result.stage is None
    assert result.status == DecisionStatus.NEED_CONFIRMATION
    assert result.developer_details["stage_decision_reason"] == "stage_blocked_or_conflicting"


def test_unqualified_user_correction_does_not_override_customer_budget_conflict():
    text = """【原始销售拜访记录】
客户表示预算 30 万，同时询问正式报价和采购流程。

【第 2 次分析修正识别事实】
以下内容是用户对已识别信息的明确修正；当前分析应以修正后的事实为准，修正前内容仅作为历史记录保留，不视为客户前后表达矛盾。
预算修正：客户又说预算 80 万。"""
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="预算 30 万", field="budget", start_char=text.index("预算 30 万")),
            EvidenceCandidate(id="E02", quote="正式报价", field="stage"),
            EvidenceCandidate(id="E03", quote="预算 80 万", field="budget", start_char=text.index("预算 80 万")),
        ],
        candidate_budget=[fact("30 万", "E01"), fact("80 万", "E03")],
        stage_signals=[sig("quote_discussed", "E02"), sig("budget_discussed", "E03")],
        possible_conflicts=[PossibleConflict(field="budget", description="预算金额存在冲突", evidence_ids=["E01", "E03"])],
    )
    result = build_validated_opportunity(text, raw)
    assert result.crm_fields.budget.status == FieldStatus.CONFLICT
    assert result.crm_fields.budget.conflicting_values == ["30 万", "80 万"]
    assert any("30 万" in question.question and "80 万" in question.question for question in result.clarification.questions)


def test_next_action_owner_conflict_does_not_pick_latest_without_qualified_confirmation():
    text = """【原始销售拜访记录】
客户已确认下一步进行商务评估，建议负责人为张1，时间在9月2日下午三点。

【第 2 次分析补充确认信息】
补充信息确认：客户说下一步行动建议负责人改为张3。

【第 3 次分析补充确认信息】
补充信息确认：客户说下一步行动建议负责人为张4。"""
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="客户已确认下一步进行商务评估，建议负责人为张1，时间在9月2日下午三点", field="next_action", start_char=text.index("客户已确认下一步进行商务评估")),
            EvidenceCandidate(id="E02", quote="客户说下一步行动建议负责人改为张3", field="next_action", start_char=text.index("客户说下一步行动建议负责人改为张3")),
            EvidenceCandidate(id="E03", quote="客户说下一步行动建议负责人为张4", field="next_action", start_char=text.index("客户说下一步行动建议负责人为张4")),
        ],
        candidate_next_actions=[
            CandidateNextAction(action="进行商务评估", owner="张1", time="9月2日下午三点", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
            CandidateNextAction(action="进行商务评估", owner="张3", time=None, evidence_id="E02", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
            CandidateNextAction(action="进行商务评估", owner="张4", time=None, evidence_id="E03", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
        ],
        stage_signals=[sig("solution_evaluation", "E01")],
        possible_conflicts=[PossibleConflict(field="next_action.owner", description="建议负责人从张1改为张3，再改为张4，最终以张4为准", evidence_ids=["E01", "E02", "E03"])],
    )
    result = build_validated_opportunity(text, raw)
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "进行商务评估"
    assert result.confirmed_next_action.owner == "待确认"
    assert result.confirmed_next_action.time == "9月2日下午三点"
    assert result.recommended_next_actions == []
    risk_descriptions = [risk.description for risk in result.opportunity_risks]
    assert any("张1、张3、张4" in description for description in risk_descriptions)
    assert not any("最终以" in description or "为准" in description for description in risk_descriptions)
    assert any(question.field == "next_action.owner" and "负责人" in question.question for question in result.clarification.questions)


def test_qualified_next_action_confirmation_can_supersede_prior_owner_values():
    text = """【原始销售拜访记录】
客户已确认下一步进行商务评估，建议负责人为张1，时间在9月2日下午三点。

【第 2 次分析补充确认信息】
补充信息确认：张1负责人安排作废，客户最终确认下一步行动负责人为张4。"""
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="客户已确认下一步进行商务评估，建议负责人为张1，时间在9月2日下午三点", field="next_action", start_char=text.index("客户已确认下一步进行商务评估")),
            EvidenceCandidate(id="E02", quote="张1负责人安排作废，客户最终确认下一步行动负责人为张4", field="next_action", start_char=text.index("张1负责人安排作废")),
        ],
        candidate_next_actions=[
            CandidateNextAction(action="进行商务评估", owner="张1", time="9月2日下午三点", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
            CandidateNextAction(action="进行商务评估", owner="张4", time="9月2日下午三点", evidence_id="E02", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
        ],
        stage_signals=[sig("solution_evaluation", "E01")],
        possible_conflicts=[PossibleConflict(field="next_action.owner", description="下一步行动负责人前后不一致", evidence_ids=["E01", "E02"])],
    )
    result = build_validated_opportunity(text, raw)
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.owner == "张4"
    assert result.confirmed_next_action.time == "9月2日下午三点"
    assert not any(risk.type == "conflict" for risk in result.opportunity_risks)


def test_full_next_action_confirmation_supersedes_prior_conflicting_action_owner_and_time():
    text = """【原始销售拜访记录】
王总说下周四可以安排一次产品 Demo。

【第 2 次分析补充确认信息】
补充信息确认：客户已确认下一步进行商务评估，建议负责人为张三，时间为 9 月 2 日下午三点。

【第 3 次分析补充确认信息】
下一步行动负责人确认：客户已确认下一步行动是安排产品 Demo，建议负责人为销售顾问林敏，时间为下周四下午。"""
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="下周四可以安排一次产品 Demo", field="next_action", start_char=text.index("下周四可以安排一次产品 Demo")),
            EvidenceCandidate(id="E02", quote="客户已确认下一步进行商务评估，建议负责人为张三，时间为 9 月 2 日下午三点", field="next_action", start_char=text.index("客户已确认下一步进行商务评估")),
            EvidenceCandidate(id="E03", quote="客户已确认下一步行动是安排产品 Demo，建议负责人为销售顾问林敏，时间为下周四下午", field="next_action", start_char=text.index("客户已确认下一步行动是安排产品 Demo")),
        ],
        candidate_next_actions=[
            CandidateNextAction(action="安排产品 Demo", owner=None, time="下周四", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
            CandidateNextAction(action="进行商务评估", owner="张三", time="9 月 2 日下午三点", evidence_id="E02", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
            CandidateNextAction(action="安排产品 Demo", owner="销售顾问林敏", time="下周四下午", evidence_id="E03", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
        ],
        stage_signals=[sig("demo_agreed", "E01")],
        possible_conflicts=[
            PossibleConflict(field="next_action.action", description="下一步行动存在多个不一致表述", evidence_ids=["E01", "E02", "E03"]),
            PossibleConflict(field="next_action.owner", description="下一步行动负责人存在多个不一致表述", evidence_ids=["E02", "E03"]),
            PossibleConflict(field="next_action.time", description="下一步行动时间存在多个不一致表述", evidence_ids=["E01", "E02", "E03"]),
        ],
    )
    result = build_validated_opportunity(text, raw)
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "安排产品 Demo"
    assert result.confirmed_next_action.owner == "林敏"
    assert result.confirmed_next_action.time == "下周四下午"
    assert not any(risk.type == "conflict" and "下一步行动" in risk.description for risk in result.opportunity_risks)
    assert not any(question.field.startswith("next_action") for question in (result.clarification.questions if result.clarification else []))


def test_owner_question_full_triple_is_parsed_as_complete_next_action_confirmation():
    original = "王总说下周四可以安排一次产品 Demo。"
    text = build_revision_input(
        original,
        [
            [ClarifyAnswer(question_id="其他补充信息", answer="客户已确认下一步进行商务评估，建议负责人为张三，时间为 9 月 2 日下午三点。")],
            [ClarifyAnswer(question_id="next_action.owner", answer="客户已确认下一步行动是安排产品 Demo，建议负责人为销售顾问林敏，时间为下周四下午。")],
        ],
    )
    result = build_validated_opportunity(
        text,
        RawExtraction(
            evidence_candidates=[EvidenceCandidate(id="E01", quote="下周四可以安排一次产品 Demo", field="next_action", start_char=text.index("下周四可以安排一次产品 Demo"))],
            candidate_next_actions=[CandidateNextAction(action="安排产品 Demo", time="下周四", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
            stage_signals=[sig("demo_agreed", "E01")],
        ),
    )
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "安排产品 Demo"
    assert result.confirmed_next_action.owner == "林敏"
    assert result.confirmed_next_action.time == "下周四下午"
    assert not any("张三" in risk.description for risk in result.opportunity_risks)


def test_timeline_confirmation_does_not_become_confirmed_next_action_by_itself():
    raw = RawExtraction(
        evidence_candidates=[EvidenceCandidate(id="E01", quote="计划本月底完成商务评估", field="timeline")],
        candidate_timeline=[fact("本月底完成商务评估", "E01")],
        stage_signals=[sig("solution_evaluation", "E01")],
    )
    result = build_validated_opportunity("客户计划本月底完成商务评估。", raw)
    assert result.crm_fields.timeline.status == FieldStatus.CONFIRMED
    assert result.confirmed_next_action is None
    assert any(item.value == "下一步行动未确认" for item in result.unconfirmed_info)


def test_full_next_action_confirmation_updates_action_owner_and_time():
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="客户已确认下一步进行商务评估，建议负责人为张7，时间在下季度第一周", field="next_action")
        ],
        candidate_next_actions=[
            CandidateNextAction(action="进行商务评估", owner="张7", time="下季度第一周", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)
        ],
        stage_signals=[sig("solution_evaluation", "E01")],
    )
    result = build_validated_opportunity("客户已确认下一步进行商务评估，建议负责人为张7，时间在下季度第一周。", raw)
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "进行商务评估"
    assert result.confirmed_next_action.owner == "张7"
    assert result.confirmed_next_action.time == "下季度第一周"


def test_candidate_budget_alias_conflict_is_removed_after_qualified_correction_and_later_supplement():
    text = """【原始销售拜访记录】
客户表示今年有约 50 万预算，同时询问了正式报价和付款方式。

【第 2 次分析修正识别事实】
以下内容是用户对已识别信息的明确修正；当前分析应以修正后的事实为准，修正前内容仅作为历史记录保留，不视为客户前后表达矛盾。
预算修正：原文写错了，预算应该是 60 万。

【第 3 次分析补充确认信息】
决策人确认：决策人是王1。"""
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="约 50 万预算", field="candidate_budget", start_char=text.index("约 50 万预算")),
            EvidenceCandidate(id="E02", quote="正式报价", field="stage", start_char=text.index("正式报价")),
            EvidenceCandidate(id="E03", quote="预算应该是 60 万", field="candidate_budget", start_char=text.index("预算应该是 60 万")),
            EvidenceCandidate(id="E04", quote="决策人是王1", field="candidate_people", start_char=text.index("决策人是王1")),
        ],
        candidate_budget=[
            CandidateFact(value="约 50 万", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT, current_validity=CurrentValidity.HISTORICAL),
            fact("60 万", "E03"),
        ],
        candidate_people=[
            CandidatePerson(name="王1", kind="decision_maker", authority_confirmed=True, evidence_id="E04", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)
        ],
        stage_signals=[sig("budget_discussed", "E03"), sig("quote_discussed", "E02")],
        possible_conflicts=[PossibleConflict(field="candidate_budget", description="预算金额冲突：原文约50万，修正为60万", evidence_ids=["E01", "E03"])],
    )
    result = build_validated_opportunity(text, raw)
    assert result.crm_fields.budget.status == FieldStatus.CONFIRMED
    assert result.crm_fields.budget.value == "60 万"
    assert result.crm_fields.decision_maker.name == "王1"
    assert not any(risk.type == "conflict" and "预算" in risk.description for risk in result.opportunity_risks)
    assert result.stage is not None
    assert result.stage.code == StageCode.S3


def test_decision_maker_correction_displays_clean_person_name():
    text = """【原始销售拜访记录】
客户表示预算 50 万，同时询问正式报价。

【第 2 次分析修正识别事实】
以下内容是用户对已识别信息的明确修正；当前分析应以修正后的事实为准，修正前内容仅作为历史记录保留，不视为客户前后表达矛盾。
决策人修正：原文写错了，是赵2。"""
    raw = RawExtraction(
        evidence_candidates=[EvidenceCandidate(id="E01", quote="正式报价", field="stage", start_char=text.index("正式报价"))],
        stage_signals=[sig("quote_discussed", "E01")],
    )
    result = build_validated_opportunity(text, raw)
    assert result.crm_fields.decision_maker.name == "赵2"
    assert result.crm_fields.decision_maker.status == FieldStatus.CONFIRMED
    assert result.crm_fields.decision_maker.evidence_ids == ["U001"]
    assert all("原文写错" not in str(result.crm_fields.decision_maker.name) for _ in [0])


def test_decision_maker_correction_uses_latter_person_for_not_a_but_b():
    text = """【原始销售拜访记录】
客户表示预算 50 万，同时询问正式报价。

【第 2 次分析修正识别事实】
以下内容是用户对已识别信息的明确修正；当前分析应以修正后的事实为准，修正前内容仅作为历史记录保留，不视为客户前后表达矛盾。
决策人修正：不是赵1，是赵2。"""
    raw = RawExtraction(
        evidence_candidates=[EvidenceCandidate(id="E01", quote="正式报价", field="stage", start_char=text.index("正式报价"))],
        stage_signals=[sig("quote_discussed", "E01")],
    )
    result = build_validated_opportunity(text, raw)
    assert result.crm_fields.decision_maker.name == "赵2"


def test_user_revision_sequence_resolves_owner_but_keeps_explicit_unknown_time_conflict():
    original = "客户已经完成产品 Demo，并确认客服自动化需求会继续推进。客户表示今年有约 50 万预算，同时询问了正式报价和付款方式。采购同事提到后续需要走采购申请流程。最终审批人目前还没有确认，计划下个月完成商务评估"
    records = [
        [ClarifyAnswer(question_id="修正识别：预算", answer="原文写错了，预算是60万")],
        [ClarifyAnswer(question_id="修正识别：时间计划", answer="原文写错了，下个周完成商务评估")],
        [ClarifyAnswer(question_id="其他补充信息", answer="客户已确认下一步进行商务评估，建议负责人为张1，时间为9月2日下午三点")],
        [ClarifyAnswer(question_id="其他补充信息", answer="客户已确认下一步进行商务评估，建议负责人为张2，时间为9月2日下午三点")],
        [ClarifyAnswer(question_id="next_action", answer="张2")],
        [ClarifyAnswer(question_id="next_action", answer="客户已确定 下一步行动负责人是张2")],
        [ClarifyAnswer(question_id="其他补充信息", answer="客户已确认下一步进行商务评估，建议负责人为张2，时间未确定")],
    ]
    text = build_revision_input(original, records)
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="客服自动化需求会继续推进", field="customer_needs", start_char=text.index("客服自动化需求会继续推进")),
            EvidenceCandidate(id="E02", quote="正式报价", field="stage", start_char=text.index("正式报价")),
        ],
        candidate_needs=[fact("客服自动化需求", "E01")],
        stage_signals=[sig("quote_discussed", "E02")],
    )
    result = build_validated_opportunity(text, raw)
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "进行商务评估"
    assert result.confirmed_next_action.owner == "张2"
    assert result.confirmed_next_action.time == "待确认"
    assert any("下一步行动时间" in risk.description and "未确定" in risk.description for risk in result.opportunity_risks)
    assert not any("下一步行动负责人" in risk.description for risk in result.opportunity_risks)
    assert any(question.field == "next_action.time" for question in result.clarification.questions)


def test_specific_next_action_time_confirmation_clears_time_conflict_without_losing_owner():
    original = "客户已经完成产品 Demo，并确认客服自动化需求会继续推进。客户表示今年有约 50 万预算，同时询问了正式报价和付款方式。采购同事提到后续需要走采购申请流程。最终审批人目前还没有确认，计划下个月完成商务评估"
    records = [
        [ClarifyAnswer(question_id="修正识别：预算", answer="原文写错了，预算是60万")],
        [ClarifyAnswer(question_id="修正识别：时间计划", answer="原文写错了，下个周完成商务评估")],
        [ClarifyAnswer(question_id="其他补充信息", answer="客户已确认下一步进行商务评估，建议负责人为张1，时间为9月2日下午三点")],
        [ClarifyAnswer(question_id="其他补充信息", answer="客户已确认下一步进行商务评估，建议负责人为张2，时间为9月2日下午三点")],
        [ClarifyAnswer(question_id="next_action.owner", answer="确定 下一步行动负责人为张2")],
        [ClarifyAnswer(question_id="其他补充信息", answer="客户已确认下一步进行商务评估，建议负责人为张2，时间未确定")],
        [ClarifyAnswer(question_id="next_action.time", answer="客户已确定 下一步行动时间未确定")],
    ]
    text = build_revision_input(original, records)
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="客服自动化需求会继续推进", field="customer_needs"),
            EvidenceCandidate(id="E02", quote="正式报价", field="stage"),
        ],
        candidate_needs=[fact("客服自动化需求", "E01")],
        stage_signals=[sig("quote_discussed", "E02")],
    )
    result = build_validated_opportunity(text, raw)
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "进行商务评估"
    assert result.confirmed_next_action.owner == "张2"
    assert result.confirmed_next_action.time == "待确认"
    assert not any("下一步行动负责人" in risk.description for risk in result.opportunity_risks)
    assert not any("下一步行动时间" in risk.description for risk in result.opportunity_risks)
    assert any(item.value == "下一步行动时间仍需确认" for item in result.unconfirmed_info)


def test_user_field_confirmations_apply_in_same_revision_and_keep_person_roles_separate():
    original = "客户已经完成产品 Demo，并确认客服自动化需求会继续推进。客户表示今年有约 50 万预算，同时询问了正式报价和付款方式。计划下个月完成商务评估"
    records = [
        [ClarifyAnswer(question_id="修正识别：预算", answer="原文写错了，预算是60万")],
        [ClarifyAnswer(question_id="decision_maker", answer="决策人是王1")],
        [ClarifyAnswer(question_id="core_scenarios", answer="场景是电商智能客服系统")],
        [ClarifyAnswer(question_id="influencers", answer="李1")],
    ]
    rev3_text = build_revision_input(original, records[:2])
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="客服自动化需求会继续推进", field="customer_needs", start_char=rev3_text.index("客服自动化需求会继续推进")),
            EvidenceCandidate(id="E02", quote="正式报价", field="stage", start_char=rev3_text.index("正式报价")),
        ],
        candidate_needs=[fact("客服自动化需求", "E01")],
        stage_signals=[sig("quote_discussed", "E02")],
    )
    rev3 = build_validated_opportunity(rev3_text, raw)
    assert rev3.crm_fields.decision_maker.name == "王1"
    assert rev3.crm_fields.decision_maker.status == FieldStatus.CONFIRMED

    rev5_text = build_revision_input(original, records)
    rev5_raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="客服自动化需求会继续推进", field="customer_needs"),
            EvidenceCandidate(id="E02", quote="正式报价", field="stage"),
        ],
        candidate_needs=[fact("客服自动化需求", "E01")],
        stage_signals=[sig("quote_discussed", "E02")],
    )
    rev5 = build_validated_opportunity(rev5_text, rev5_raw)
    assert rev5.crm_fields.decision_maker.name == "王1"
    assert rev5.crm_fields.influencers
    assert rev5.crm_fields.influencers[0].name == "李1"
    assert rev5.crm_fields.influencers[0].status == FieldStatus.CONFIRMED
    assert not any(item.value == "影响人未确认" for item in rev5.unconfirmed_info)
    assert rev5.confirmed_next_action is None


def test_candidate_next_actions_alias_conflict_keeps_confirmed_action_and_marks_owner_pending():
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="客户已确定下一步是商务评估，建议负责人是张1，时间在8月2号", field="candidate_next_actions"),
            EvidenceCandidate(id="E02", quote="客户已确定 建议负责人是张2", field="candidate_next_actions"),
            EvidenceCandidate(id="E03", quote="正式报价", field="stage"),
        ],
        candidate_next_actions=[
            CandidateNextAction(action="商务评估", owner="张1", time="8月2号", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
            CandidateNextAction(action="商务评估", owner="张2", time=None, evidence_id="E02", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
        ],
        stage_signals=[sig("quote_discussed", "E03")],
        possible_conflicts=[PossibleConflict(field="candidate_next_actions", description="商务评估负责人冲突：张1和张2", evidence_ids=["E01", "E02"])],
    )
    result = build_validated_opportunity("客户已确定下一步是商务评估，建议负责人是张1，时间在8月2号。客户已确定 建议负责人是张2。", raw)
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "进行商务评估"
    assert result.confirmed_next_action.owner == "待确认"
    assert result.confirmed_next_action.time == "8月2号"
    assert result.recommended_next_actions == []
    assert any("下一步行动负责人" in risk.description and "张1、张2" in risk.description for risk in result.opportunity_risks)
    assert any(question.field == "next_action.owner" and "负责人" in question.question for question in result.clarification.questions)


def test_next_action_conflict_is_inferred_when_provider_omits_possible_conflict():
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="客户已确认下一步进行商务评估，负责人为刘1，时间为本周五", field="next_action"),
            EvidenceCandidate(id="E02", quote="客户又说负责人为刘2", field="next_action"),
        ],
        candidate_next_actions=[
            CandidateNextAction(action="进行商务评估", owner="刘1", time="本周五", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
            CandidateNextAction(action="进行商务评估", owner="刘2", time=None, evidence_id="E02", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
        ],
        stage_signals=[sig("solution_evaluation", "E01")],
    )
    result = build_validated_opportunity("客户已确认下一步进行商务评估，负责人为刘1，时间为本周五。客户又说负责人为刘2。", raw)
    assert result.status == DecisionStatus.NEED_CONFIRMATION
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.owner == "待确认"
    assert any("刘1、刘2" in risk.description for risk in result.opportunity_risks)


def test_next_action_time_syncs_crm_timeline_when_it_is_the_same_event():
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="计划下个月完成商务评估", field="candidate_timeline"),
            EvidenceCandidate(id="E02", quote="客户已确认下一步是商务评估，建议负责人是张1，时间在8月2号", field="candidate_next_actions"),
            EvidenceCandidate(id="E03", quote="正式报价", field="stage"),
        ],
        candidate_timeline=[fact("下个月完成商务评估", "E01"), fact("8月2号", "E02")],
        candidate_next_actions=[
            CandidateNextAction(action="商务评估", owner="张1", time="8月2号", evidence_id="E02", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)
        ],
        stage_signals=[sig("quote_discussed", "E03")],
        possible_conflicts=[PossibleConflict(field="candidate_timeline", description="时间计划前后不一致：下个月和8月2号", evidence_ids=["E01", "E02"])],
    )
    result = build_validated_opportunity("计划下个月完成商务评估。客户已确认下一步是商务评估，建议负责人是张1，时间在8月2号。", raw)
    assert result.crm_fields.timeline.status == FieldStatus.CONFIRMED
    assert result.crm_fields.timeline.value == "8月2号进行商务评估"
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.time == "8月2号"
    assert not any("时间计划前后不一致" in risk.description for risk in result.opportunity_risks)


def test_duplicate_generic_conflict_clarification_questions_are_deduped():
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="客户信息 A", field="stage"),
            EvidenceCandidate(id="E02", quote="客户信息 B", field="stage"),
            EvidenceCandidate(id="E03", quote="客户信息 C", field="stage"),
        ],
        possible_conflicts=[
            PossibleConflict(field="stage", description="客户信息存在冲突", evidence_ids=["E01", "E02"]),
            PossibleConflict(field="stage", description="客户信息存在冲突", evidence_ids=["E02", "E03"]),
        ],
    )
    result = build_validated_opportunity("客户信息 A。客户信息 B。客户信息 C。", raw)
    questions = result.clarification.questions if result.clarification else []
    assert len([question for question in questions if question.question == "请确认以下冲突信息的当前真实状态：客户信息存在冲突"]) == 1


def test_mock_provider_accepts_next_step_is_phrase_without_full_template():
    result = asyncio.run(
        run_mock_pipeline(
            AnalyzeRequest(
                input_text="客户已经完成产品 Demo，并询问正式报价。客户已确定  下一步是商务评估，建议负责人是张1。"
            )
        )
    )
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "进行商务评估"
    assert result.confirmed_next_action.owner == "张1"
    assert result.confirmed_next_action.time == "待确认"
    assert result.recommended_next_actions == []


def test_next_action_owner_conflict_keeps_action_and_marks_owner_only_pending():
    result = asyncio.run(
        run_mock_pipeline(
            AnalyzeRequest(
                input_text="客户已经完成产品 Demo，并询问正式报价。客户已确认下一步进行商务评估，建议负责人为张1，时间为9月2日下午三点。客户已确认下一步进行商务评估，建议负责人为张3。"
            )
        )
    )
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "进行商务评估"
    assert result.confirmed_next_action.owner == "待确认"
    assert result.confirmed_next_action.time == "9月2日下午三点"
    assert result.recommended_next_actions == []
    assert any("下一步行动负责人" in risk.description and "张1、张3" in risk.description for risk in result.opportunity_risks)
    questions = result.clarification.questions if result.clarification else []
    assert any(question.field == "next_action.owner" and "负责人" in question.question for question in questions)


def test_budget_correction_does_not_resurface_after_next_action_supplement_conflict():
    text = """【原始销售拜访记录】
客户已经完成产品 Demo，并确认客服自动化需求会继续推进。客户表示今年有约 50 万预算，同时询问了正式报价。

【第 2 次分析修正识别事实】
以下内容是用户对已识别信息的明确修正；当前分析应以修正后的事实为准，修正前内容仅作为历史记录保留，不视为客户前后表达矛盾。
预算修正：原文写错了，预算是60万。

【第 3 次分析补充确认信息】
补充信息确认：客户已确认下一步进行商务评估，建议负责人为张1，时间为9月2日下午三点。

【第 4 次分析补充确认信息】
补充信息确认：客户已确认下一步进行商务评估，建议负责人为张3。"""
    result = asyncio.run(run_mock_pipeline(AnalyzeRequest(input_text=text)))
    assert result.crm_fields.budget.status == FieldStatus.CONFIRMED
    assert result.crm_fields.budget.value in {"60万", "60 万"}
    assert not any("预算" in risk.description for risk in result.opportunity_risks)
    assert any("下一步行动负责人" in risk.description for risk in result.opportunity_risks)


def test_generic_budget_and_timeline_conflicts_are_removed_after_valid_corrections():
    text = """【原始销售拜访记录】
客户表示今年有约 50 万预算，计划下个月完成商务评估，同时询问了正式报价。

【第 2 次分析修正识别事实】
以下内容是用户对已识别信息的明确修正；当前分析应以修正后的事实为准，修正前内容仅作为历史记录保留，不视为客户前后表达矛盾。
预算修正：原文写错了，预算是60万。

【第 3 次分析修正识别事实】
以下内容是用户对已识别信息的明确修正；当前分析应以修正后的事实为准，修正前内容仅作为历史记录保留，不视为客户前后表达矛盾。
时间计划修正：我原文写错了，下个周完成商务评估。

【第 4 次分析补充确认信息】
补充信息确认：客户已确认下一步进行商务评估，建议负责人为张1，时间为9月2日下午三点。

【第 5 次分析补充确认信息】
补充信息确认：客户已确认下一步进行商务评估，建议负责人为张2，时间为9月2日下午三点。"""
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="约 50 万预算", field="budget", start_char=text.index("约 50 万预算")),
            EvidenceCandidate(id="E02", quote="计划下个月完成商务评估", field="timeline", start_char=text.index("计划下个月完成商务评估")),
            EvidenceCandidate(id="E03", quote="正式报价", field="stage", start_char=text.index("正式报价")),
            EvidenceCandidate(id="E04", quote="预算是60万", field="budget", start_char=text.index("预算是60万")),
            EvidenceCandidate(id="E05", quote="下个周完成商务评估", field="timeline", start_char=text.index("下个周完成商务评估")),
            EvidenceCandidate(id="E06", quote="客户已确认下一步进行商务评估，建议负责人为张1，时间为9月2日下午三点", field="next_action", start_char=text.index("客户已确认下一步进行商务评估，建议负责人为张1")),
            EvidenceCandidate(id="E07", quote="客户已确认下一步进行商务评估，建议负责人为张2，时间为9月2日下午三点", field="next_action", start_char=text.index("客户已确认下一步进行商务评估，建议负责人为张2")),
        ],
        candidate_budget=[fact("约50万", "E01"), fact("60万", "E04")],
        candidate_timeline=[fact("下个月完成商务评估", "E02"), fact("下个周完成商务评估", "E05")],
        candidate_next_actions=[
            CandidateNextAction(action="进行商务评估", owner="张1", time="9月2日下午三点", evidence_id="E06", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
            CandidateNextAction(action="进行商务评估", owner="张2", time="9月2日下午三点", evidence_id="E07", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
        ],
        stage_signals=[sig("budget_discussed", "E04"), sig("quote_discussed", "E03")],
        possible_conflicts=[
            PossibleConflict(field="risk", description="预算金额冲突：约50万 vs 60万", evidence_ids=["E01", "E04"]),
            PossibleConflict(field="stage", description="商务评估时间冲突：下个月 vs 下个周", evidence_ids=["E02", "E05"]),
            PossibleConflict(field="next_action.owner", description="下一步行动负责人存在多个不一致表述", evidence_ids=["E06", "E07"]),
        ],
    )
    result = build_validated_opportunity(text, raw)
    assert result.crm_fields.budget.status == FieldStatus.CONFIRMED
    assert result.crm_fields.timeline.status == FieldStatus.CONFIRMED
    assert not any("预算" in risk.description for risk in result.opportunity_risks)
    assert not any("商务评估时间" in risk.description or "时间冲突" in risk.description for risk in result.opportunity_risks)
    assert any("下一步行动负责人" in risk.description for risk in result.opportunity_risks)


def test_next_action_unknown_time_after_explicit_time_marks_time_pending_not_conflict():
    result = asyncio.run(
        run_mock_pipeline(
            AnalyzeRequest(
                input_text="客户已经完成产品 Demo，并询问正式报价。客户已确认下一步进行商务评估，建议负责人为张2，时间为9月2日下午三点。客户已确认下一步进行商务评估，建议负责人为张2，时间未确定。"
            )
        )
    )
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "进行商务评估"
    assert result.confirmed_next_action.owner == "张2"
    assert result.confirmed_next_action.time == "待确认"
    assert not any("下一步行动时间存在多个不一致" in risk.description for risk in result.opportunity_risks)
    assert any(str(item.value) == "下一步行动时间仍需确认" for item in result.unconfirmed_info)


def test_next_action_owner_conflict_is_not_overridden_by_later_plain_confirmation():
    result = asyncio.run(
        run_mock_pipeline(
            AnalyzeRequest(
                input_text="客户已经完成产品 Demo，并询问正式报价。客户已确认下一步进行商务评估，建议负责人为张1，时间为9月2日下午三点。客户已确认下一步进行商务评估，建议负责人为张2，时间为9月2日下午三点。"
            )
        )
    )
    assert result.status == DecisionStatus.NEED_CONFIRMATION
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "进行商务评估"
    assert result.confirmed_next_action.owner == "待确认"
    assert result.confirmed_next_action.time == "9月2日下午三点"
    assert result.recommended_next_actions == []
    assert any("下一步行动负责人存在多个不一致表述" in risk.description for risk in result.opportunity_risks)


def test_generic_and_specific_next_action_owner_conflicts_are_deduped():
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="客户已确认下一步进行商务评估，建议负责人为张1，时间为9月2日下午三点", field="next_action"),
            EvidenceCandidate(id="E02", quote="客户已确认下一步进行商务评估，建议负责人为张2，时间为9月2日下午三点", field="next_action"),
            EvidenceCandidate(id="E03", quote="正式报价", field="stage"),
        ],
        candidate_next_actions=[
            CandidateNextAction(action="进行商务评估", owner="张1", time="9月2日下午三点", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
            CandidateNextAction(action="进行商务评估", owner="张2", time="9月2日下午三点", evidence_id="E02", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
        ],
        stage_signals=[sig("quote_discussed", "E03")],
        possible_conflicts=[
            PossibleConflict(field="risk", description="负责人冲突：张1 vs 张2", evidence_ids=["E01", "E02"]),
            PossibleConflict(field="next_action.owner", description="下一步行动负责人存在多个不一致表述", evidence_ids=["E01", "E02"]),
        ],
    )
    result = build_validated_opportunity(
        "客户已确认下一步进行商务评估，建议负责人为张1，时间为9月2日下午三点。客户已确认下一步进行商务评估，建议负责人为张2，时间为9月2日下午三点。正式报价。",
        raw,
    )
    owner_risks = [risk for risk in result.opportunity_risks if "负责人" in risk.description]
    assert len(owner_risks) == 1
    assert owner_risks[0].description == "下一步行动负责人存在多个不一致表述：张1、张2，需确认当前真实负责人。"
    assert "vs" not in owner_risks[0].description
    owner_questions = [question for question in result.clarification.questions if question.field == "next_action.owner"]
    assert len(owner_questions) == 1


def test_specific_next_action_action_question_accepts_bare_answer():
    text = build_revision_input(
        "客户还没有确认下一步动作。",
        [[ClarifyAnswer(question_id="next_action.action", answer="安排产品 Demo")]],
    )
    result = build_validated_opportunity(text, RawExtraction())
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "安排产品 Demo"
    assert result.confirmed_next_action.owner == "待确认"
    assert result.confirmed_next_action.time == "待确认"


def test_specific_next_action_owner_and_time_questions_accept_bare_answers():
    text = build_revision_input(
        "王总说下周四可以安排一次产品 Demo。",
        [
            [
                ClarifyAnswer(question_id="next_action.owner", answer="销售顾问林敏"),
                ClarifyAnswer(question_id="next_action.time", answer="待确认"),
            ]
        ],
    )
    result = build_validated_opportunity(
        text,
        RawExtraction(
            evidence_candidates=[EvidenceCandidate(id="E01", quote="下周四可以安排一次产品 Demo", field="next_action", start_char=text.index("下周四可以安排一次产品 Demo"))],
            candidate_next_actions=[CandidateNextAction(action="安排产品 Demo", time="下周四", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
            stage_signals=[sig("demo_agreed", "E01")],
        ),
    )
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "安排产品 Demo"
    assert result.confirmed_next_action.owner == "林敏"
    assert result.confirmed_next_action.time == "待确认"
    assert not any("下一步行动时间存在多个不一致" in risk.description for risk in result.opportunity_risks)


def test_overall_next_action_question_accepts_action_owner_time_without_confirmed_prefix():
    text = build_revision_input(
        "客户还没有确认下一步动作。",
        [[ClarifyAnswer(question_id="next_action", answer="安排产品 Demo，负责人待确认，时间下周四下午")]],
    )
    result = build_validated_opportunity(text, RawExtraction())
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "安排产品 Demo"
    assert result.confirmed_next_action.owner == "待确认"
    assert result.confirmed_next_action.time == "下周四下午"


def test_influencer_role_repetition_is_cleaned_and_deduped():
    text = "今天和远川零售集团数字化负责人陈总、采购刘经理开了方案评审会。陈总表示今年预算约 80 万，采购刘经理询问了正式报价、付款方式和采购流程。"
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="今天和远川零售集团数字化负责人陈总、采购刘经理开了方案评审会", field="influencers", start_char=text.index("今天和远川")),
            EvidenceCandidate(id="E02", quote="采购刘经理询问了正式报价、付款方式和采购流程", field="influencers", start_char=text.index("采购刘经理询问")),
        ],
        candidate_people=[
            CandidatePerson(name="采购刘经理", role="采购经理、采购、采购、采购", kind="influencer", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
            CandidatePerson(name="刘经理", role="采购、采购", kind="influencer", evidence_id="E02", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
        ],
    )
    result = build_validated_opportunity(text, raw)
    assert len(result.crm_fields.influencers) == 2
    liu = next(person for person in result.crm_fields.influencers if person.name == "刘经理")
    assert liu.role == "采购经理"
    assert "采购、采购" not in f"{liu.name} · {liu.role}"


def test_influencer_name_and_role_only_evidence_is_not_confirmed_for_procurement_person():
    text = "今天和远川零售集团数字化负责人陈总、采购刘经理开会。陈总表示今年预算约 80 万。"
    raw = RawExtraction(
        evidence_candidates=[EvidenceCandidate(id="E01", quote="采购刘经理", field="influencers", start_char=text.index("采购刘经理"))],
        candidate_people=[CandidatePerson(name="采购刘经理", role="采购经理、采购", kind="influencer", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
    )
    result = build_validated_opportunity(text, raw)
    assert all(person.name != "刘经理" for person in result.crm_fields.influencers)


def test_influencer_role_already_in_name_is_removed():
    text = "王总说下周四可以安排一次产品 Demo，让IT 王工一起看效果。"
    raw = RawExtraction(
        evidence_candidates=[EvidenceCandidate(id="E01", quote="让IT 王工一起看效果", field="influencers", start_char=text.index("让IT 王工一起看效果"))],
        candidate_people=[CandidatePerson(name="IT 王工", role="IT、方案评估参与人", kind="influencer", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
    )
    result = build_validated_opportunity(text, raw)
    assert len(result.crm_fields.influencers) == 1
    assert result.crm_fields.influencers[0].name == "IT 王工"
    assert result.crm_fields.influencers[0].role == "方案评估参与人"


def test_decision_maker_confirmation_does_not_create_influencer():
    original = "今天拜访了星河科技客户服务部，参会人包括客服负责人王总和 IT 王工。王总说下周四可以安排一次产品 Demo，让IT 王工一起看效果。"
    text = build_revision_input(
        original,
        [[ClarifyAnswer(question_id="decision_maker", answer="最终采购决策人是客服负责人王总")]],
    )
    decision_quote = "决策人确认：最终采购决策人是客服负责人王总"
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote=decision_quote, field="people", start_char=text.index(decision_quote)),
        ],
        candidate_people=[
            CandidatePerson(name="王总", role="客服负责人", kind="influencer", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
        ],
    )
    result = build_validated_opportunity(text, raw)
    assert result.crm_fields.decision_maker.name == "王总"
    assert result.crm_fields.decision_maker.status == FieldStatus.CONFIRMED
    assert all(person.name != "王总" for person in result.crm_fields.influencers)


def test_next_action_time_answer_does_not_become_owner():
    text = build_revision_input(
        "王总说下周四可以安排一次产品 Demo。",
        [
            [ClarifyAnswer(question_id="next_action.owner", answer="张1")],
            [ClarifyAnswer(question_id="next_action.time", answer="9月2号")],
        ],
    )
    result = build_validated_opportunity(
        text,
        RawExtraction(
            evidence_candidates=[EvidenceCandidate(id="E01", quote="下周四可以安排一次产品 Demo", field="next_action", start_char=text.index("下周四可以安排一次产品 Demo"))],
            candidate_next_actions=[CandidateNextAction(action="安排产品 Demo", time="下周四", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
            stage_signals=[sig("demo_agreed", "E01")],
        ),
    )
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.owner == "张1"
    assert result.confirmed_next_action.time == "9月2号"
    assert not any("9月2号" in risk.description and "负责人" in risk.description for risk in result.opportunity_risks)


def test_next_action_time_update_does_not_overwrite_independent_timeline():
    original = "王总说下周四可以安排一次产品 Demo，客户计划本月底完成供应商选择。"
    text = build_revision_input(original, [[ClarifyAnswer(question_id="next_action.time", answer="9月2号")]])
    result = build_validated_opportunity(
        text,
        RawExtraction(
            evidence_candidates=[
                EvidenceCandidate(id="E01", quote="下周四可以安排一次产品 Demo", field="next_action", start_char=text.index("下周四可以安排一次产品 Demo")),
                EvidenceCandidate(id="E02", quote="计划本月底完成供应商选择", field="timeline", start_char=text.index("计划本月底完成供应商选择")),
            ],
            candidate_next_actions=[CandidateNextAction(action="安排产品 Demo", time="下周四", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
            candidate_timeline=[fact("本月底完成供应商选择", "E02")],
            stage_signals=[sig("demo_agreed", "E01")],
        ),
    )
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.time == "9月2号"
    assert result.crm_fields.timeline.status == FieldStatus.CONFIRMED
    assert result.crm_fields.timeline.value == "本月底完成供应商选择"


def test_next_action_business_evaluation_alias_does_not_create_conflict():
    text = "客户已确认下一步行动是商务评估，负责人是张1，时间不确定。随后补充下一步行动确认：商务评估。"
    raw = RawExtraction(
        evidence_candidates=[
            EvidenceCandidate(id="E01", quote="客户已确认下一步行动是商务评估，负责人是张1，时间不确定", field="next_action", start_char=text.index("客户已确认下一步行动是商务评估")),
            EvidenceCandidate(id="E02", quote="下一步行动确认：商务评估", field="next_action", start_char=text.index("下一步行动确认")),
        ],
        candidate_next_actions=[
            CandidateNextAction(action="商务评估", owner="张1", time="待确认", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
            CandidateNextAction(action="进行商务评估", owner=None, time=None, evidence_id="E02", attribution=Attribution.THIRD_PARTY, explicitness=Explicitness.EXPLICIT),
        ],
    )
    result = build_validated_opportunity(text, raw)
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "进行商务评估"
    assert not any("下一步行动存在多个不一致" in risk.description for risk in result.opportunity_risks)


def test_later_next_action_time_confirmation_does_not_resurface_resolved_action_owner_conflicts():
    original = "王总说下周四可以安排一次产品 Demo。"
    text = build_revision_input(
        original,
        [
            [ClarifyAnswer(question_id="其他补充信息", answer="下一步行动是商务评估，负责人是张1，时间不确定")],
            [
                ClarifyAnswer(question_id="next_action.action", answer="商务评估"),
                ClarifyAnswer(question_id="next_action.owner", answer="张1"),
                ClarifyAnswer(question_id="next_action.time", answer="待确定"),
            ],
            [ClarifyAnswer(question_id="next_action.time", answer="9月2号")],
        ],
    )
    result = build_validated_opportunity(
        text,
        RawExtraction(
            evidence_candidates=[EvidenceCandidate(id="E01", quote="下周四可以安排一次产品 Demo", field="next_action", start_char=text.index("下周四可以安排一次产品 Demo"))],
            candidate_next_actions=[CandidateNextAction(action="安排产品 Demo", time="下周四", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
            stage_signals=[sig("demo_agreed", "E01")],
        ),
    )
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "进行商务评估"
    assert result.confirmed_next_action.owner == "张1"
    assert result.confirmed_next_action.time == "9月2号"
    assert result.crm_fields.timeline.status == FieldStatus.CONFIRMED
    assert result.crm_fields.timeline.value == "下周四安排产品 Demo"
    assert not any(risk.type == "conflict" and "下一步行动" in risk.description for risk in result.opportunity_risks)


def test_same_event_next_action_time_update_syncs_timeline_event_time():
    original = "王总说下周四可以安排一次产品 Demo。"
    text = build_revision_input(
        original,
        [
            [ClarifyAnswer(question_id="next_action.owner", answer="林敏")],
            [ClarifyAnswer(question_id="next_action.time", answer="9月2号")],
        ],
    )
    result = build_validated_opportunity(
        text,
        RawExtraction(
            evidence_candidates=[EvidenceCandidate(id="E01", quote="下周四可以安排一次产品 Demo", field="next_action", start_char=text.index("下周四可以安排一次产品 Demo"))],
            candidate_next_actions=[CandidateNextAction(action="安排产品 Demo", time="下周四", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
            stage_signals=[sig("demo_agreed", "E01")],
        ),
    )
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "安排产品 Demo"
    assert result.confirmed_next_action.owner == "林敏"
    assert result.confirmed_next_action.time == "9月2号"
    assert result.crm_fields.timeline.status == FieldStatus.CONFIRMED
    assert result.crm_fields.timeline.value == "9月2号安排产品 Demo"


def test_next_action_unknown_owner_is_not_conflict_with_later_confirmed_owner():
    original = "王总说下周四可以安排一次产品 Demo。"
    text = build_revision_input(
        original,
        [
            [ClarifyAnswer(question_id="next_action.owner", answer="待确认")],
            [ClarifyAnswer(question_id="next_action.owner", answer="销售顾问林敏")],
        ],
    )
    result = build_validated_opportunity(
        text,
        RawExtraction(
            evidence_candidates=[EvidenceCandidate(id="E01", quote="下周四可以安排一次产品 Demo", field="next_action", start_char=text.index("下周四可以安排一次产品 Demo"))],
            candidate_next_actions=[CandidateNextAction(action="安排产品 Demo", time="下周四", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
            possible_conflicts=[PossibleConflict(field="next_action.owner", description="下一步行动负责人存在多个不一致表述：待确认、林敏、销售顾问林敏", evidence_ids=["E01"])],
            stage_signals=[sig("demo_agreed", "E01")],
        ),
    )
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "安排产品 Demo"
    assert result.confirmed_next_action.owner == "林敏"
    assert result.confirmed_next_action.time == "下周四"
    assert not any(risk.type == "conflict" and "下一步行动负责人" in risk.description for risk in result.opportunity_risks)


def test_confirming_new_action_and_owner_does_not_inherit_old_action_time():
    original = "王总说下周四可以安排一次产品 Demo。"
    text = build_revision_input(
        original,
        [
            [ClarifyAnswer(question_id="next_action.owner", answer="销售顾问林敏")],
            [ClarifyAnswer(question_id="其他补充信息", answer="下一步行动是商务评估，负责人是张1，时间不确定")],
            [
                ClarifyAnswer(question_id="next_action.action", answer="商务评估"),
                ClarifyAnswer(question_id="next_action.owner", answer="张1"),
            ],
        ],
    )
    result = build_validated_opportunity(
        text,
        RawExtraction(
            evidence_candidates=[EvidenceCandidate(id="E01", quote="下周四可以安排一次产品 Demo", field="next_action", start_char=text.index("下周四可以安排一次产品 Demo"))],
            candidate_next_actions=[CandidateNextAction(action="安排产品 Demo", time="下周四", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
            stage_signals=[sig("demo_agreed", "E01")],
        ),
    )
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "进行商务评估"
    assert result.confirmed_next_action.owner == "张1"
    assert result.confirmed_next_action.time == "待确认"
    assert not any("下一步行动存在多个不一致" in risk.description for risk in result.opportunity_risks)
    assert not any("下一步行动负责人存在多个不一致" in risk.description for risk in result.opportunity_risks)
    assert any("下一步行动时间" in risk.description and "未确定" in risk.description for risk in result.opportunity_risks)


def test_confirming_new_action_time_resolves_prior_unknown_time_conflict():
    original = "王总说下周四可以安排一次产品 Demo。"
    text = build_revision_input(
        original,
        [
            [ClarifyAnswer(question_id="next_action.owner", answer="销售顾问林敏")],
            [ClarifyAnswer(question_id="其他补充信息", answer="下一步行动是商务评估，负责人是张1，时间不确定")],
            [
                ClarifyAnswer(question_id="next_action.action", answer="商务评估"),
                ClarifyAnswer(question_id="next_action.owner", answer="张1"),
            ],
            [ClarifyAnswer(question_id="next_action.time", answer="9月2号")],
        ],
    )
    result = build_validated_opportunity(
        text,
        RawExtraction(
            evidence_candidates=[EvidenceCandidate(id="E01", quote="下周四可以安排一次产品 Demo", field="next_action", start_char=text.index("下周四可以安排一次产品 Demo"))],
            candidate_next_actions=[CandidateNextAction(action="安排产品 Demo", time="下周四", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
            stage_signals=[sig("demo_agreed", "E01")],
        ),
    )
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "进行商务评估"
    assert result.confirmed_next_action.owner == "张1"
    assert result.confirmed_next_action.time == "9月2号"
    assert not any(risk.type == "conflict" and "下一步行动" in risk.description for risk in result.opportunity_risks)


def test_next_action_time_conflict_can_resolve_to_unknown_time():
    original = "王总说下周四可以安排一次产品 Demo。"
    text = build_revision_input(
        original,
        [
            [ClarifyAnswer(question_id="next_action.owner", answer="销售顾问林敏")],
            [ClarifyAnswer(question_id="其他补充信息", answer="下一步行动是商务评估，负责人是张1，时间不确定")],
            [
                ClarifyAnswer(question_id="next_action.action", answer="商务评估"),
                ClarifyAnswer(question_id="next_action.owner", answer="张1"),
                ClarifyAnswer(question_id="next_action.time", answer="待确定"),
            ],
        ],
    )
    result = build_validated_opportunity(
        text,
        RawExtraction(
            evidence_candidates=[EvidenceCandidate(id="E01", quote="下周四可以安排一次产品 Demo", field="next_action", start_char=text.index("下周四可以安排一次产品 Demo"))],
            candidate_next_actions=[CandidateNextAction(action="安排产品 Demo", time="下周四", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
            stage_signals=[sig("demo_agreed", "E01")],
        ),
    )
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "进行商务评估"
    assert result.confirmed_next_action.owner == "张1"
    assert result.confirmed_next_action.time == "待确认"
    assert not any(risk.type == "conflict" and "下一步行动" in risk.description for risk in result.opportunity_risks)
    assert any(item.value == "下一步行动时间仍需确认" for item in result.unconfirmed_info)


def test_repeated_unknown_next_action_time_confirmation_stays_resolved():
    original = "王总说下周四可以安排一次产品 Demo。"
    text = build_revision_input(
        original,
        [
            [ClarifyAnswer(question_id="next_action.owner", answer="销售顾问林敏")],
            [ClarifyAnswer(question_id="其他补充信息", answer="下一步行动是商务评估，负责人是张1，时间不确定")],
            [
                ClarifyAnswer(question_id="next_action.action", answer="商务评估"),
                ClarifyAnswer(question_id="next_action.owner", answer="张1"),
                ClarifyAnswer(question_id="next_action.time", answer="待确定"),
            ],
            [ClarifyAnswer(question_id="next_action.time", answer="待确定")],
        ],
    )
    result = build_validated_opportunity(
        text,
        RawExtraction(
            evidence_candidates=[EvidenceCandidate(id="E01", quote="下周四可以安排一次产品 Demo", field="next_action", start_char=text.index("下周四可以安排一次产品 Demo"))],
            candidate_next_actions=[CandidateNextAction(action="安排产品 Demo", time="下周四", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
            stage_signals=[sig("demo_agreed", "E01")],
        ),
    )
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "进行商务评估"
    assert result.confirmed_next_action.owner == "张1"
    assert result.confirmed_next_action.time == "待确认"
    assert not any(risk.type == "conflict" and "下一步行动" in risk.description for risk in result.opportunity_risks)


def test_original_next_action_fallback_overrides_sales_attribution_for_confirmed_meeting_sentence():
    text = "今天和云澜教育集团教务运营负责人赵经理、信息化负责人孙工复盘了智能客服试点。客户确认招生咨询和学员售后答疑两个场景仍然要继续推进，试点效果总体认可，也希望评估正式采购方案。赵经理上午说今年项目预算大约 50 万，可以继续走采购申请；下午采购刘经理补充说财务系统里的立项预算是 70 万左右，两个金额还需要他们内部确认。客户没有取消需求，下一步确认由销售负责人李娜下周二和赵经理、采购刘经理开一次预算确认会。"
    quote = "下一步确认由销售负责人李娜下周二和赵经理、采购刘经理开一次预算确认会"
    result = build_validated_opportunity(
        text,
        RawExtraction(
            evidence_candidates=[EvidenceCandidate(id="E04", quote=quote, field="next_action", start_char=text.index(quote))],
            candidate_next_actions=[CandidateNextAction(action="开预算确认会", owner="李娜", time="下周二", evidence_id="E04", attribution=Attribution.SALES, explicitness=Explicitness.EXPLICIT)],
        ),
    )
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "开预算确认会"
    assert result.confirmed_next_action.owner == "李娜"
    assert result.confirmed_next_action.time == "下周二"
    assert not any(item.value == "下一步行动未确认" for item in result.unconfirmed_info)


def test_original_next_action_confirmed_by_owner_time_meeting_sentence_is_extracted():
    text = "客户没有取消需求，下一步确认由销售负责人李娜下周二和赵经理、采购刘经理开一次预算确认会。"
    result = build_validated_opportunity(text, RawExtraction())
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "开预算确认会"
    assert result.confirmed_next_action.owner == "李娜"
    assert result.confirmed_next_action.time == "下周二"


def test_yunlan_original_record_extracts_next_action_in_mock_pipeline():
    text = "今天和云澜教育集团教务运营负责人赵经理、信息化负责人孙工复盘了智能客服试点。客户确认招生咨询和学员售后答疑两个场景仍然要继续推进，试点效果总体认可，也希望评估正式采购方案。赵经理上午说今年项目预算大约 50 万，可以继续走采购申请；下午采购刘经理补充说财务系统里的立项预算是 70 万左右，两个金额还需要他们内部确认。客户没有取消需求，下一步确认由销售负责人李娜下周二和赵经理、采购刘经理开一次预算确认会。"
    result = asyncio.run(run_mock_pipeline(AnalyzeRequest(input_text=text)))
    assert result.confirmed_next_action is not None
    assert result.confirmed_next_action.action == "开预算确认会"
    assert result.confirmed_next_action.owner == "李娜"
    assert result.confirmed_next_action.time == "下周二"


def test_non_conflict_budget_blocker_is_recorded_as_risk():
    result = asyncio.run(
        run_mock_pipeline(
            AnalyzeRequest(
                input_text="客户说客服自动化需求明确，也问了报价，但客户表示预算被冻结，担心会影响项目推进。"
            )
        )
    )
    assert any(risk.type == "budget_unavailable" for risk in result.opportunity_risks)
    assert result.status == DecisionStatus.NEED_CONFIRMATION
    assert result.confirmed_next_action is None
    assert result.recommended_next_actions == []
    assert any(item.value == "下一步行动未确认" for item in result.unconfirmed_info)


def test_budget_frozen_with_solution_approval_records_risk_without_template_action():
    result = asyncio.run(
        run_mock_pipeline(
            AnalyzeRequest(
                input_text="和字节跳动的项目已通过方案评估，在讨论报价。但是客户表示今年预算目前已经被冻结，暂时无法确认是否还能继续采购。产品方案本身客户仍表示认可。"
            )
        )
    )
    assert result.stage is not None
    assert result.stage.code == StageCode.S3
    assert any(field.status == FieldStatus.CONFIRMED for field in result.crm_fields.core_scenarios)
    assert any(risk.type == "budget_unavailable" for risk in result.opportunity_risks)
    assert result.confirmed_next_action is None
    assert result.recommended_next_actions == []
    assert any(item.value == "下一步行动未确认" for item in result.unconfirmed_info)


def test_non_conflict_procurement_blocker_is_recorded_as_risk():
    result = asyncio.run(
        run_mock_pipeline(
            AnalyzeRequest(
                input_text="客户说客服自动化需求明确，也问了报价。采购申请还没提交，客户担心流程会拖慢。"
            )
        )
    )
    assert any(risk.type == "unknown_procurement_process" for risk in result.opportunity_risks)
