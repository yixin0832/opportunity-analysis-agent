from __future__ import annotations

import unittest

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
    StageCode,
    StageSignal,
    DecisionStatus,
)


def e(id_: str, quote: str, field: str = "stage") -> EvidenceCandidate:
    return EvidenceCandidate(id=id_, quote=quote, field=field)


def sig(signal_type: str, evidence_id: str, *, attribution: Attribution = Attribution.CUSTOMER, explicitness: Explicitness = Explicitness.EXPLICIT) -> StageSignal:
    return StageSignal(
        signal_type=signal_type,  # type: ignore[arg-type]
        explicitness=explicitness,
        polarity=Polarity.POSITIVE,
        attribution=attribution,
        current_validity=CurrentValidity.ACTIVE,
        evidence_id=evidence_id,
    )


def fact(value: str, evidence_id: str, *, attribution: Attribution = Attribution.CUSTOMER, explicitness: Explicitness = Explicitness.EXPLICIT) -> CandidateFact:
    return CandidateFact(
        value=value,
        evidence_id=evidence_id,
        attribution=attribution,
        explicitness=explicitness,
        polarity=Polarity.POSITIVE,
        current_validity=CurrentValidity.ACTIVE,
    )


class GoldenCasesTest(unittest.TestCase):
    def analyze(self, text: str, raw: RawExtraction):
        return build_validated_opportunity(text, raw, analysis_id="test", revision=1)

    def test_g01_initial_contact_is_s0(self):
        text = "今天拜访了客户，只是简单介绍了一下产品，加了微信。"
        result = self.analyze(text, RawExtraction())
        self.assertEqual(result.stage.code, StageCode.S0)
        self.assertEqual(result.status, DecisionStatus.COMPLETE)

    def test_g02_need_identified_is_s1(self):
        text = "客户说客服工单处理慢，希望减少人工分单。"
        raw = RawExtraction(
            evidence_candidates=[e("E01", "客服工单处理慢", "customer_needs")],
            candidate_needs=[fact("客服工单处理慢", "E01")],
            stage_signals=[sig("need_identified", "E01")],
        )
        result = self.analyze(text, raw)
        self.assertEqual(result.stage.code, StageCode.S1)
        self.assertEqual(result.crm_fields.customer_needs[0].status, FieldStatus.CONFIRMED)

    def test_g03_core_scenario_is_s1(self):
        text = "客户想在售后知识库场景做智能问答。"
        raw = RawExtraction(
            evidence_candidates=[e("E01", "售后知识库场景做智能问答", "core_scenarios")],
            candidate_scenarios=[fact("售后知识库智能问答", "E01")],
            stage_signals=[sig("need_identified", "E01")],
        )
        result = self.analyze(text, raw)
        self.assertEqual(result.stage.code, StageCode.S1)
        self.assertEqual(result.crm_fields.core_scenarios[0].status, FieldStatus.CONFIRMED)

    def test_g04_demo_agreed_is_s2_and_confirmed_next_action(self):
        text = "王总说下周四可以安排一次产品 Demo。"
        raw = RawExtraction(
            evidence_candidates=[e("E01", "下周四可以安排一次产品 Demo", "next_action")],
            candidate_next_actions=[CandidateNextAction(action="安排产品 Demo", time="下周四", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
            stage_signals=[sig("demo_agreed", "E01")],
        )
        result = self.analyze(text, raw)
        self.assertEqual(result.stage.code, StageCode.S2)
        self.assertIsNotNone(result.confirmed_next_action)
        self.assertEqual(result.confirmed_next_action.time, "下周四")
        self.assertEqual(result.confirmed_next_action.owner, "待确认")

    def test_g05_trial_agreed_is_s2(self):
        text = "客户同意先试用两周。"
        raw = RawExtraction(evidence_candidates=[e("E01", "同意先试用两周")], stage_signals=[sig("trial_agreed", "E01")])
        self.assertEqual(self.analyze(text, raw).stage.code, StageCode.S2)

    def test_g06_technical_exchange_is_s2(self):
        text = "客户希望我们拉技术同学做一次方案交流。"
        raw = RawExtraction(evidence_candidates=[e("E01", "做一次方案交流")], stage_signals=[sig("technical_exchange_agreed", "E01")])
        self.assertEqual(self.analyze(text, raw).stage.code, StageCode.S2)

    def test_g07_quote_discussed_is_s3(self):
        text = "客户问了报价，需求仍然明确。"
        raw = RawExtraction(evidence_candidates=[e("E01", "问了报价")], stage_signals=[sig("quote_discussed", "E01")])
        self.assertEqual(self.analyze(text, raw).stage.code, StageCode.S3)

    def test_g08_budget_discussed_is_s3_with_budget_evidence(self):
        text = "客户说今年预算大概 30 万。"
        raw = RawExtraction(
            evidence_candidates=[e("E01", "预算大概 30 万", "budget")],
            candidate_budget=[fact("30 万", "E01")],
            stage_signals=[sig("budget_discussed", "E01")],
        )
        result = self.analyze(text, raw)
        self.assertEqual(result.stage.code, StageCode.S3)
        self.assertEqual(result.crm_fields.budget.status, FieldStatus.CONFIRMED)

    def test_g09_procurement_discussed_is_s3(self):
        text = "客户说需要走采购流程。"
        raw = RawExtraction(evidence_candidates=[e("E01", "走采购流程")], stage_signals=[sig("procurement_discussed", "E01")])
        self.assertEqual(self.analyze(text, raw).stage.code, StageCode.S3)

    def test_g10_contract_terms_discussed_is_s3(self):
        text = "法务正在看合同条款。"
        raw = RawExtraction(evidence_candidates=[e("E01", "看合同条款")], stage_signals=[sig("contract_terms_discussed", "E01", attribution=Attribution.THIRD_PARTY)])
        self.assertEqual(self.analyze(text, raw).stage.code, StageCode.S3)

    def test_g11_internal_approval_is_s4(self):
        text = "项目已经进入内部立项流程。"
        raw = RawExtraction(evidence_candidates=[e("E01", "进入内部立项流程")], stage_signals=[sig("internal_project_approval", "E01")])
        self.assertEqual(self.analyze(text, raw).stage.code, StageCode.S4)

    def test_g12_vendor_decision_is_s4(self):
        text = "客户说下周进入供应商评审。"
        raw = RawExtraction(evidence_candidates=[e("E01", "进入供应商评审")], stage_signals=[sig("vendor_decision", "E01")])
        self.assertEqual(self.analyze(text, raw).stage.code, StageCode.S4)

    def test_g13_approval_is_s4_but_decision_maker_partial(self):
        text = "老板审批后就能定。"
        raw = RawExtraction(evidence_candidates=[e("E01", "老板审批后就能定", "decision_maker")], candidate_people=[CandidatePerson(role="老板", kind="decision_maker", authority_confirmed=True, evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)], stage_signals=[sig("internal_project_approval", "E01")])
        result = self.analyze(text, raw)
        self.assertEqual(result.stage.code, StageCode.S4)
        self.assertEqual(result.crm_fields.decision_maker.status, FieldStatus.PARTIAL)

    def test_g14_contract_signed_is_s5(self):
        text = "合同已经签完。"
        raw = RawExtraction(evidence_candidates=[e("E01", "合同已经签完")], stage_signals=[sig("contract_signed", "E01")])
        self.assertEqual(self.analyze(text, raw).stage.code, StageCode.S5)

    def test_g15_order_confirmed_is_s5(self):
        text = "正式订单已经确认。"
        raw = RawExtraction(evidence_candidates=[e("E01", "正式订单已经确认")], stage_signals=[sig("order_confirmed", "E01")])
        self.assertEqual(self.analyze(text, raw).stage.code, StageCode.S5)

    def test_g16_sales_guess_does_not_confirm_budget_or_s2(self):
        text = "我感觉客户挺感兴趣，应该会有预算。"
        raw = RawExtraction(
            evidence_candidates=[e("E01", "应该会有预算", "budget")],
            candidate_budget=[fact("有预算", "E01", attribution=Attribution.SALES, explicitness=Explicitness.AMBIGUOUS)],
            stage_signals=[sig("budget_discussed", "E01", attribution=Attribution.SALES, explicitness=Explicitness.AMBIGUOUS)],
        )
        result = self.analyze(text, raw)
        self.assertTrue(result.stage is None or result.stage.code not in {StageCode.S2, StageCode.S3})
        self.assertNotEqual(result.crm_fields.budget.status, FieldStatus.CONFIRMED)

    def test_g17_budget_conflict_needs_confirmation(self):
        text = "客户先说预算 50 万，后来又说今年没有预算。"
        raw = RawExtraction(
            evidence_candidates=[e("E01", "预算 50 万", "budget"), e("E02", "今年没有预算", "budget")],
            possible_conflicts=[PossibleConflict(field="budget", description="客户预算表述前后冲突。", evidence_ids=["E01", "E02"])],
            stage_signals=[sig("budget_discussed", "E01")],
        )
        result = self.analyze(text, raw)
        self.assertEqual(result.status, DecisionStatus.NEED_CONFIRMATION)
        self.assertTrue(any(risk.type == "conflict" for risk in result.opportunity_risks))
        self.assertEqual(result.crm_fields.budget.status, FieldStatus.CONFLICT)

    def test_g18_partial_decision_maker_does_not_fill_name(self):
        text = "李总拍板，但没说李总全名。"
        raw = RawExtraction(evidence_candidates=[e("E01", "李总拍板", "decision_maker")], candidate_people=[CandidatePerson(name="李总", role="拍板人", kind="decision_maker", authority_confirmed=True, evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)])
        result = self.analyze(text, raw)
        self.assertEqual(result.crm_fields.decision_maker.name, "李总")
        self.assertEqual(result.crm_fields.decision_maker.status, FieldStatus.CONFIRMED)

    def test_g19_timeline_keeps_original_precision(self):
        text = "计划下季度上线。"
        raw = RawExtraction(evidence_candidates=[e("E01", "下季度上线", "timeline")], candidate_timeline=[fact("下季度上线", "E01")])
        result = self.analyze(text, raw)
        self.assertEqual(result.crm_fields.timeline.value, "下季度上线")

    def test_g20_unowned_next_action_marks_owner_pending(self):
        text = "客户说下周跟进。"
        raw = RawExtraction(evidence_candidates=[e("E01", "下周跟进", "next_action")], candidate_next_actions=[CandidateNextAction(action="跟进", time="下周", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)])
        result = self.analyze(text, raw)
        self.assertEqual(result.confirmed_next_action.owner, "待确认")

    def test_g21_budget_discussed_but_demand_invalidated_is_not_s3(self):
        text = "之前讨论过预算，但客户说项目暂停。"
        raw = RawExtraction(
            evidence_candidates=[e("E01", "讨论过预算"), e("E02", "项目暂停")],
            stage_signals=[sig("budget_discussed", "E01"), sig("demand_invalidated", "E02")],
        )
        result = self.analyze(text, raw)
        self.assertTrue(result.stage is None or result.stage.code != StageCode.S3)
        self.assertTrue(any(risk.type == "demand_invalidated" for risk in result.opportunity_risks))

    def test_g22_vague_text_is_unable_to_judge(self):
        text = "客户不错"
        result = self.analyze(text, RawExtraction())
        self.assertEqual(result.status, DecisionStatus.UNABLE_TO_JUDGE)

    def test_g23_decision_maker_vs_influencers(self):
        text = "业务负责人张经理提需求，IT 王工评估，采购刘经理负责流程。"
        raw = RawExtraction(
            evidence_candidates=[e("E01", "张经理提需求", "people"), e("E02", "王工评估", "people"), e("E03", "刘经理负责流程", "people")],
            candidate_people=[
                CandidatePerson(name="张经理", role="业务负责人", kind="influencer", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
                CandidatePerson(name="王工", role="IT 评估人", kind="influencer", evidence_id="E02", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
                CandidatePerson(name="刘经理", role="采购", kind="influencer", evidence_id="E03", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT),
            ],
        )
        result = self.analyze(text, raw)
        self.assertEqual(result.crm_fields.decision_maker.status, FieldStatus.UNKNOWN)
        self.assertEqual(len(result.crm_fields.influencers), 3)

    def test_g24_revision_stage_can_move_from_s1_to_s2(self):
        v1_text = "客户有客服问题。"
        v1 = self.analyze(v1_text, RawExtraction(evidence_candidates=[e("E01", "客服问题")], stage_signals=[sig("need_identified", "E01")]))
        v2_text = "客户有客服问题。补充：已约下周 Demo。"
        v2 = build_validated_opportunity(v2_text, RawExtraction(evidence_candidates=[e("E01", "客服问题"), e("E02", "已约下周 Demo")], stage_signals=[sig("need_identified", "E01"), sig("demo_agreed", "E02")]), analysis_id="test", revision=2)
        self.assertEqual(v1.stage.code, StageCode.S1)
        self.assertEqual(v2.stage.code, StageCode.S2)
        self.assertEqual(v2.revision, 2)

    def test_g25_broken_text_record_does_not_get_filled(self):
        text = "客户……预算……审批……"
        result = self.analyze(text, RawExtraction())
        self.assertEqual(result.status, DecisionStatus.UNABLE_TO_JUDGE)
        self.assertIsNone(result.stage)
        self.assertEqual(result.crm_fields.budget.status, FieldStatus.UNKNOWN)
        self.assertEqual(result.crm_fields.decision_maker.status, FieldStatus.UNKNOWN)
        self.assertEqual(result.opportunity_risks, [])
        self.assertTrue(any(warning.type == "insufficient_input" for warning in result.analysis_warnings))

    def test_g26_no_confirmed_next_action_stays_unconfirmed_without_ai_recommendation(self):
        text = "客户明确有客服自动化需求。"
        raw = RawExtraction(evidence_candidates=[e("E01", "客服自动化需求")], stage_signals=[sig("need_identified", "E01")])
        result = self.analyze(text, raw)
        self.assertIsNone(result.confirmed_next_action)
        self.assertEqual(result.recommended_next_actions, [])
        self.assertTrue(any(item.value == "下一步行动未确认" for item in result.unconfirmed_info))

    def test_g27_sales_attribution_budget_is_not_confirmed(self):
        text = "销售判断客户预算至少百万。"
        raw = RawExtraction(evidence_candidates=[e("E01", "预算至少百万", "budget")], candidate_budget=[fact("至少百万", "E01", attribution=Attribution.SALES)])
        result = self.analyze(text, raw)
        self.assertNotEqual(result.crm_fields.budget.status, FieldStatus.CONFIRMED)

    def test_g28_timeline_conflict_needs_confirmation(self):
        text = "客户先说 9 月上线，后说今年不上线。"
        raw = RawExtraction(evidence_candidates=[e("E01", "9 月上线", "timeline"), e("E02", "今年不上线", "timeline")], possible_conflicts=[PossibleConflict(field="timeline", description="上线时间前后冲突。", evidence_ids=["E01", "E02"])])
        result = self.analyze(text, raw)
        self.assertEqual(result.status, DecisionStatus.NEED_CONFIRMATION)

    def test_g29_forged_evidence_invalidates_confirmed_field(self):
        text = "客户说想看 Demo。"
        raw = RawExtraction(
            evidence_candidates=[e("E01", "客户预算 80 万", "budget")],
            candidate_budget=[fact("80 万", "E01")],
            stage_signals=[sig("budget_discussed", "E01")],
        )
        result = self.analyze(text, raw)
        self.assertFalse(result.evidence[0].valid)
        self.assertNotEqual(result.crm_fields.budget.status, FieldStatus.CONFIRMED)
        self.assertTrue(result.stage is None or result.stage.code != StageCode.S3)

    def test_g30_higher_stage_dominates_lower_signals(self):
        text = "合同已签，之前也做过 Demo，预算 80 万。"
        raw = RawExtraction(
            evidence_candidates=[e("E01", "合同已签"), e("E02", "做过 Demo"), e("E03", "预算 80 万")],
            stage_signals=[sig("contract_signed", "E01"), sig("demo_agreed", "E02"), sig("budget_discussed", "E03")],
        )
        result = self.analyze(text, raw)
        self.assertEqual(result.stage.code, StageCode.S5)

    def test_g31_solution_evaluation_is_s2(self):
        text = "客户说可以评估客服自动化方案。"
        raw = RawExtraction(
            evidence_candidates=[e("E01", "可以评估客服自动化方案", "core_scenarios")],
            candidate_scenarios=[fact("客服自动化方案评估", "E01")],
            stage_signals=[sig("need_identified", "E01"), sig("solution_evaluation", "E01")],
        )
        result = self.analyze(text, raw)
        self.assertEqual(result.stage.code, StageCode.S2)

    def test_g32_unknown_does_not_automatically_become_opportunity_risk(self):
        text = "王总说下周四可以安排一次产品 Demo。"
        raw = RawExtraction(
            evidence_candidates=[e("E01", "下周四可以安排一次产品 Demo", "next_action"), e("E02", "王总", "person")],
            candidate_next_actions=[CandidateNextAction(action="安排产品 Demo", time="下周四", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
            candidate_people=[CandidatePerson(name="王总", kind="decision_maker", authority_confirmed=False, evidence_id="E02", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
            stage_signals=[sig("demo_agreed", "E01")],
        )
        result = self.analyze(text, raw)
        self.assertEqual(result.stage.code, StageCode.S2)
        self.assertFalse(any(risk.type == "unknown_decision_authority" for risk in result.opportunity_risks))
        self.assertTrue(any(item.value == "决策人或决策权限未确认" for item in result.unconfirmed_info))

    def test_g33_analysis_warning_is_not_opportunity_risk(self):
        text = "客户……预算……审批……"
        result = self.analyze(text, RawExtraction())
        self.assertEqual(result.opportunity_risks, [])
        self.assertTrue(any(warning.type == "insufficient_input" for warning in result.analysis_warnings))


if __name__ == "__main__":
    unittest.main()
