from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.prompts import RAW_EXTRACTION_SYSTEM_PROMPT
from backend.app.schemas import RawExtraction


def test_task_contract_keeps_llm_out_of_final_business_decisions():
    prompt = RAW_EXTRACTION_SYSTEM_PROMPT
    assert "可供 Evidence Validator 和 Rule Engine 使用" in prompt
    assert "记录里实际表达了什么" in prompt
    assert "不要输出最终 S0-S5、status、OpportunityRisk 或 ValidatedOpportunity" in prompt
    assert "S0 不需要新增 Stage Signal" in prompt
    assert "S0 由 Rule Engine" in prompt


def test_output_schema_matches_raw_extraction_models():
    prompt = RAW_EXTRACTION_SYSTEM_PROMPT
    assert "candidate_needs / candidate_scenarios / candidate_budget / candidate_timeline 的每个对象只能使用：value, evidence_id, attribution, explicitness, polarity, current_validity" in prompt
    assert "candidate_people 的每个对象只能使用：name, role, kind, authority_confirmed, evidence_id, attribution, explicitness" in prompt
    assert "candidate_next_actions 的每个对象只能使用：action, owner, time, evidence_id, attribution, explicitness" in prompt
    assert "stage_signals 的每个对象只能使用：signal_type, explicitness, polarity, attribution, current_validity, evidence_id" in prompt
    assert "possible_conflicts 的每个对象只能使用：field, description, evidence_ids" in prompt
    assert "candidate 字段必须是单数 evidence_id" in prompt


def test_ambiguities_are_list_of_strings_in_prompt_and_schema():
    prompt = RAW_EXTRACTION_SYSTEM_PROMPT
    assert "ambiguities 必须是字符串数组 list[str]" in prompt
    assert "不要使用对象" in prompt
    assert "budget: 客户确认有预算，但金额未确认" in prompt
    with pytest.raises(ValidationError):
        RawExtraction.model_validate({
            "candidate_needs": [],
            "candidate_scenarios": [],
            "candidate_budget": [],
            "candidate_people": [],
            "candidate_timeline": [],
            "candidate_next_actions": [],
            "stage_signals": [],
            "ambiguities": [{"field": "budget", "reason": "金额未确认"}],
            "possible_conflicts": [],
            "evidence_candidates": [],
        })


def test_need_and_scenario_boundaries_are_explicit():
    prompt = RAW_EXTRACTION_SYSTEM_PROMPT
    assert "Need 回答“客户想解决什么问题 / 达成什么目标”" in prompt
    assert "Scenario 回答“能力具体用在哪里”" in prompt
    assert "一句话确实同时包含 Need 和 Scenario 时允许分别抽取" in prompt
    assert "不要为了填字段而强行把 Need 推断成 Scenario" in prompt


def test_budget_raw_value_boundary_is_not_normalization():
    prompt = RAW_EXTRACTION_SYSTEM_PROMPT
    assert "candidate_budget.value 保留预算金额、预算范围或预算存在性本身及必要限定词" in prompt
    assert "不要包含“客户表示”“今年有”“预算为”“预算已经落实为”等叙述性外壳" in prompt
    assert "不要自行标准化金额、换算单位或取区间中位数" in prompt
    assert "value 可以比 evidence quote 更短" in prompt
    assert "如果没有金额，不得补金额" in prompt


def test_people_classification_boundary_is_role_evidence_based():
    prompt = RAW_EXTRACTION_SYSTEM_PROMPT
    assert "candidate_people.kind 必须基于原文角色证据" in prompt
    assert '"kind":"unknown"' in prompt
    assert "最终由王总拍板" in prompt
    assert "王总负责最终审批" in prompt
    assert "王总是这个项目的决策人" in prompt
    assert "不得标为 confirmed decision maker" in prompt
    assert "业务负责人最终审批" in prompt
    assert "决策人姓名未确认" in prompt


def test_next_action_boundary_keeps_recommendations_out_of_raw_extraction():
    prompt = RAW_EXTRACTION_SYSTEM_PROMPT
    assert "candidate_next_actions 只能来自客户明确约定或拜访记录明确记载的已确认动作" in prompt
    assert "AI 自己认为“下一步应该做什么”不是 candidate_next_actions" in prompt
    assert "owner/time 使用 null" in prompt
    assert "不得凭空补 owner 或 time" in prompt


def test_stage_signal_semantics_cover_high_ambiguity_boundaries():
    prompt = RAW_EXTRACTION_SYSTEM_PROMPT
    assert "客户表示可以评估一下客服自动化方案" in prompt
    assert "客户希望 AI 用在客服场景" in prompt
    assert "客户确认今年有预算" in prompt
    assert "销售准备下次和客户聊预算" in prompt
    assert "客户问了报价" in prompt
    assert "销售准备下次发报价" in prompt
    assert "王总负责该项目最终审批" in prompt
    assert "王总参加了产品 Demo" in prompt
    assert "客户说下周进入供应商评审" in prompt
    assert "客户还在了解市场上的几家产品" in prompt


def test_demand_delayed_boundary_separates_unknown_timeline():
    prompt = RAW_EXTRACTION_SYSTEM_PROMPT
    assert "Timeline unknown 不等于 demand_delayed" in prompt
    assert "具体时间还没定" in prompt or "具体上线时间还没有确定" in prompt
    assert "上线时间暂时不确定" in prompt or "上线时间暂时待确认" in prompt
    assert "后面再约时间" in prompt
    assert "上线日期待确认" in prompt
    assert "项目或计划延期" in prompt
    assert "demand_delayed 和 demand_invalidated 必须严格区分" in prompt


def test_evidence_rules_require_unique_ids_and_existing_references():
    prompt = RAW_EXTRACTION_SYSTEM_PROMPT
    assert "id 在一次 RawExtraction 中必须唯一" in prompt
    assert "E01, E02, E03" in prompt
    assert "quote 必须逐字来自输入原文" in prompt
    assert "最短但语义完整" in prompt
    assert "不要仅因为不同字段引用同一句话，就重复生成内容完全相同的 Evidence" in prompt
    assert "evidence_id 必须能在 evidence_candidates.id 中找到" in prompt


def test_conflict_and_current_validity_boundaries_do_not_let_llm_adjudicate():
    prompt = RAW_EXTRACTION_SYSTEM_PROMPT
    assert "possible_conflicts 只记录候选冲突事实" in prompt
    assert "不直接输出最终 Risk" in prompt
    assert "不自行选择某一条作为真相" in prompt
    assert "明确历史事实用 historical" in prompt
    assert "两个当前陈述互相冲突时保留双方 Evidence 和 possible_conflicts" in prompt
    assert "不要在没有规则依据时随意决定谁是真相" in prompt


def test_prompt_v1_freeze_keeps_keyword_safety_and_stage_scan():
    prompt = RAW_EXTRACTION_SYSTEM_PROMPT
    assert "孤立关键词触发" in prompt
    assert "完整业务主谓含义" in prompt
    assert "Stage Signal Scan" in prompt
    assert "销售自己的猜测" in prompt
