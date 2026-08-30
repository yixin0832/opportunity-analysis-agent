from __future__ import annotations

import asyncio
import unittest

from backend.app.examples import EXAMPLES
from backend.app.pipeline import list_examples, run_mock_pipeline, run_pipeline
from backend.app.schemas import AnalyzeRequest, DecisionStatus, StageCode


class MockPipelineTest(unittest.TestCase):
    def run_pipeline(self, input_text: str, provider: str | None = None):
        return asyncio.run(run_mock_pipeline(AnalyzeRequest(input_text=input_text, provider=provider)))

    def test_examples_are_available_in_chinese(self):
        examples = list_examples()
        self.assertGreaterEqual(len(examples), 3)
        self.assertTrue(all(example.title for example in examples))
        self.assertTrue(any(example.id == "demo_s2" for example in examples))

    def test_demo_s2_pipeline_returns_validated_opportunity(self):
        example = next(item for item in EXAMPLES if item.id == "demo_s2")
        result = self.run_pipeline(example.input_text)
        self.assertEqual(result.stage.code, StageCode.S4)
        self.assertEqual(result.status, DecisionStatus.COMPLETE)
        self.assertIsNotNone(result.confirmed_next_action)
        self.assertEqual(result.confirmed_next_action.action, "发送正式报价和实施计划")
        self.assertEqual(result.confirmed_next_action.owner, "张晨")
        self.assertEqual(result.confirmed_next_action.time, "本周五前")
        self.assertEqual(result.crm_fields.timeline.value, "本月底完成供应商选择")
        self.assertTrue(result.evidence)
        self.assertTrue(all(item.valid for item in result.evidence))
        self.assertEqual(result.developer_details["provider"], "mock")

    def test_budget_conflict_pipeline_needs_confirmation(self):
        example = next(item for item in EXAMPLES if item.id == "budget_conflict")
        result = self.run_pipeline(example.input_text)
        self.assertEqual(result.status, DecisionStatus.NEED_CONFIRMATION)
        self.assertTrue(any(risk.type == "conflict" for risk in result.opportunity_risks))
        self.assertIsNotNone(result.clarification)
        question_text = " ".join(question.question for question in result.clarification.questions)
        self.assertIn("预算", question_text)
        self.assertIn("下一步", question_text)

    def test_insufficient_text_does_not_invent_fields(self):
        example = next(item for item in EXAMPLES if item.id == "insufficient_text")
        result = self.run_pipeline(example.input_text)
        self.assertIsNone(result.confirmed_next_action)
        self.assertEqual(result.crm_fields.budget.status, "unknown")
        self.assertEqual(result.crm_fields.decision_maker.status, "unknown")

    def test_empty_input_is_rejected_before_provider(self):
        with self.assertRaisesRegex(ValueError, "请输入销售拜访记录"):
            self.run_pipeline("   ")

    def test_unsupported_provider_is_rejected_by_general_pipeline(self):
        with self.assertRaisesRegex(Exception, "暂不支持 Provider"):
            asyncio.run(run_pipeline(AnalyzeRequest(input_text="客户说可以安排 Demo。", provider="openai")))

    def test_api_response_shape_is_json_serializable(self):
        result = self.run_pipeline("王总说下周四可以安排一次产品 Demo。")
        payload = result.model_dump(mode="json")
        self.assertEqual(payload["stage"]["code"], "S2")
        self.assertEqual(payload["confirmed_next_action"]["type"], "customer_confirmed")
        self.assertIn("developer_details", payload)


if __name__ == "__main__":
    unittest.main()
