from __future__ import annotations

import pytest

from backend.app.input_builder import build_revision_input, validate_correction_answers
from backend.app.schemas import ClarifyAnswer


def test_revision_one_input_contains_only_original_visit_when_no_clarifications():
    text = build_revision_input("客户有客服问题。", [])
    assert text == "【原始销售拜访记录】\n客户有客服问题。"


def test_builder_uses_original_visit_plus_all_clarification_records():
    text = build_revision_input(
        "客户有客服问题。",
        [
            [ClarifyAnswer(question_id="stage", answer="已约下周 Demo。")],
            [ClarifyAnswer(question_id="budget", answer="预算约 30 万。"), ClarifyAnswer(question_id=None, answer="李总拍板。")],
        ],
    )
    assert "【原始销售拜访记录】\n客户有客服问题。" in text
    assert "【第 2 次分析补充确认信息】" in text
    assert "商机阶段确认：已约下周 Demo。" in text
    assert "【第 3 次分析补充确认信息】" in text
    assert "预算确认：预算约 30 万。" in text
    assert "补充信息确认：李总拍板。" in text
    assert text.count("【原始销售拜访记录】") == 1
    assert "Revision" not in text


def test_builder_separates_correction_facts_from_missing_info_supplements():
    text = build_revision_input(
        "王总说下周四可以安排一次产品 Demo。",
        [
            [
                ClarifyAnswer(question_id="修正识别：决策人", answer="王总只是技术负责人，李总才是最终采购决策人。"),
                ClarifyAnswer(question_id="预算", answer="客户确认今年预算为 80 万。"),
            ],
        ],
    )
    assert "【第 2 次分析补充确认信息】" in text
    assert "预算确认：客户确认今年预算为 80 万。" in text
    assert "【第 2 次分析修正识别事实】" in text
    assert "决策人修正：王总只是技术负责人，李总才是最终采购决策人。" in text
    assert "当前分析应以修正后的事实为准" in text
    assert "Revision" not in text


def test_builder_treats_structured_correction_prefix_as_correction_fact():
    text = build_revision_input(
        "客户确认下周四技术交流。",
        [[ClarifyAnswer(question_id="correction:timeline", answer="不是下周四，客户确认安排在下下周一。")]],
    )
    assert "【第 2 次分析修正识别事实】" in text
    assert "时间计划修正：不是下周四，客户确认安排在下下周一。" in text
    assert "【第 2 次分析补充确认信息】" not in text
    assert "Revision" not in text


def test_builder_does_not_duplicate_action_words_in_field_labels():
    text = build_revision_input(
        "客户说预算 30 万。",
        [
            [
                ClarifyAnswer(question_id="修正识别：预算修正", answer="我原文写错了，客户实际预算是 80 万。"),
                ClarifyAnswer(question_id="其他补充信息确认", answer="客户已确认下一步行动。"),
            ]
        ],
    )
    assert "预算修正修正" not in text
    assert "补充信息确认确认" not in text
    assert "预算修正：我原文写错了，客户实际预算是 80 万。" in text
    assert "补充信息确认：客户已确认下一步行动。" in text
    assert "Revision" not in text


def test_invalid_correction_without_error_intent_is_rejected():
    with pytest.raises(ValueError, match="修正识别只用于"):
        validate_correction_answers([ClarifyAnswer(question_id="修正识别：时间计划", answer="下个周完成商务评估")])
