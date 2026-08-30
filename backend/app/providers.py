from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx
from pydantic import ValidationError

from .config import AppSettings, get_settings
from .errors import (
    LLMSchemaInvalidError,
    LLMProviderError,
    LLMTimeoutError,
    ProviderNotConfiguredError,
    UnsupportedProviderError,
)
from .prompts import (
    GROUNDED_SUMMARY_SYSTEM_PROMPT,
    RAW_EXTRACTION_SYSTEM_PROMPT,
    build_grounded_summary_user_prompt,
    build_raw_extraction_user_prompt,
)
from .schemas import (
    Attribution,
    CandidateFact,
    CandidateNextAction,
    CandidatePerson,
    CurrentValidity,
    EvidenceCandidate,
    Explicitness,
    Polarity,
    PossibleConflict,
    RawExtraction,
    StageSignal,
)


class LLMProvider(ABC):
    @abstractmethod
    async def invoke_structured(self, input_text: str) -> RawExtraction:
        """Return model-style semantic extraction without final business decisions."""

    async def invoke_grounded_summary(self, context: dict[str, Any], deterministic_draft: str) -> str:
        """Rewrite a validated deterministic summary without changing business facts."""
        raise LLMProviderError()

    @property
    def provider_name(self) -> str:
        return self.__class__.__name__.replace("Provider", "").lower()

    @property
    def model_name(self) -> str:
        return "unknown"


def _candidate_fact(
    value: str,
    evidence_id: str,
    *,
    attribution: Attribution = Attribution.CUSTOMER,
    explicitness: Explicitness = Explicitness.EXPLICIT,
    polarity: Polarity = Polarity.POSITIVE,
) -> CandidateFact:
    return CandidateFact(
        value=value,
        evidence_id=evidence_id,
        attribution=attribution,
        explicitness=explicitness,
        polarity=polarity,
        current_validity=CurrentValidity.ACTIVE,
    )


def _signal(
    signal_type: str,
    evidence_id: str,
    *,
    attribution: Attribution = Attribution.CUSTOMER,
    explicitness: Explicitness = Explicitness.EXPLICIT,
    polarity: Polarity = Polarity.POSITIVE,
) -> StageSignal:
    return StageSignal(
        signal_type=signal_type,  # type: ignore[arg-type]
        explicitness=explicitness,
        polarity=polarity,
        attribution=attribution,
        current_validity=CurrentValidity.ACTIVE,
        evidence_id=evidence_id,
    )


class MockProvider(LLMProvider):
    @property
    def model_name(self) -> str:
        return "mock-v1"

    async def invoke_structured(self, input_text: str) -> RawExtraction:
        return self.extract(input_text)

    async def invoke_grounded_summary(self, context: dict[str, Any], deterministic_draft: str) -> str:
        return deterministic_draft

    def extract(self, input_text: str) -> RawExtraction:
        raw = RawExtraction()

        def add_evidence(quote: str, field: str) -> str:
            evidence_id = f"E{len(raw.evidence_candidates) + 1:02d}"
            position = input_text.find(quote)
            raw.evidence_candidates.append(EvidenceCandidate(id=evidence_id, quote=quote, field=field, start_char=position if position >= 0 else None))
            return evidence_id

        if "门店售后咨询和会员活动问答" in input_text:
            evidence_id = add_evidence("门店售后咨询和会员活动问答是今年重点改造场景", "customer_needs")
            raw.candidate_needs.append(_candidate_fact("门店售后咨询和会员活动问答", evidence_id))
            raw.candidate_scenarios.append(_candidate_fact("门店售后咨询", evidence_id))
            raw.candidate_scenarios.append(_candidate_fact("会员活动问答", evidence_id))
            raw.stage_signals.append(_signal("need_identified", evidence_id))
        elif "门店客服工单处理慢" in input_text:
            evidence_id = add_evidence("客户说门店客服工单处理慢", "customer_needs")
            raw.candidate_needs.append(_candidate_fact("门店客服工单处理慢", evidence_id))
            raw.stage_signals.append(_signal("need_identified", evidence_id))
        elif "客服工单处理慢" in input_text:
            evidence_id = add_evidence("客户说客服工单处理慢" if "客户说客服工单处理慢" in input_text else "客服工单处理慢", "customer_needs")
            raw.candidate_needs.append(_candidate_fact("客服工单处理慢", evidence_id))
            raw.stage_signals.append(_signal("need_identified", evidence_id))
        elif "客服自动化需求" in input_text:
            evidence_id = add_evidence("客服自动化需求", "customer_needs")
            raw.candidate_needs.append(_candidate_fact("客服自动化需求", evidence_id))
            raw.stage_signals.append(_signal("need_identified", evidence_id))
        elif "客服自动化方案" in input_text:
            quote = "可以评估客服自动化方案" if "可以评估客服自动化方案" in input_text else "评估客服自动化方案"
            evidence_id = add_evidence(quote, "core_scenarios")
            raw.candidate_scenarios.append(_candidate_fact("客服自动化方案评估", evidence_id))
            raw.stage_signals.append(_signal("need_identified", evidence_id))
            if any(phrase in input_text for phrase in ("可以评估客服自动化方案", "方案评估", "评估方案")):
                raw.stage_signals.append(_signal("solution_evaluation", evidence_id))
        elif "已通过方案评估" in input_text or "产品方案本身客户仍表示认可" in input_text:
            quote = "已通过方案评估" if "已通过方案评估" in input_text else "产品方案本身客户仍表示认可"
            evidence_id = add_evidence(quote, "core_scenarios")
            raw.candidate_scenarios.append(_candidate_fact("产品方案获得客户认可", evidence_id, attribution=Attribution.THIRD_PARTY))
            raw.stage_signals.append(_signal("solution_evaluation", evidence_id, attribution=Attribution.THIRD_PARTY))

        if "售后知识库场景" in input_text:
            evidence_id = add_evidence("希望用智能问答先覆盖售后知识库场景", "core_scenarios")
            raw.candidate_scenarios.append(_candidate_fact("售后知识库智能问答", evidence_id))
            if not any(signal.signal_type == "need_identified" for signal in raw.stage_signals):
                raw.stage_signals.append(_signal("need_identified", evidence_id))
        elif "智能问答" in input_text:
            evidence_id = add_evidence("智能问答", "core_scenarios")
            raw.candidate_scenarios.append(_candidate_fact("智能问答", evidence_id))
            if not any(signal.signal_type == "need_identified" for signal in raw.stage_signals):
                raw.stage_signals.append(_signal("need_identified", evidence_id))

        if "下周四可以安排一次产品 Demo" in input_text:
            evidence_id = add_evidence("王总说下周四可以安排一次产品 Demo", "next_action")
            raw.stage_signals.append(_signal("demo_agreed", evidence_id))
            raw.candidate_next_actions.append(CandidateNextAction(action="安排产品 Demo", time="下周四", evidence_id=evidence_id, attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT))
            raw.candidate_timeline.append(_candidate_fact("下周四", evidence_id))
        elif "已约下周 Demo" in input_text:
            evidence_id = add_evidence("已约下周 Demo", "next_action")
            raw.stage_signals.append(_signal("demo_agreed", evidence_id))
            raw.candidate_next_actions.append(CandidateNextAction(action="安排产品 Demo", time="下周", evidence_id=evidence_id, attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT))
            raw.candidate_timeline.append(_candidate_fact("下周", evidence_id))
        elif "客户说可以安排 Demo" in input_text:
            evidence_id = add_evidence("客户说可以安排 Demo", "next_action")
            raw.stage_signals.append(_signal("demo_agreed", evidence_id))
            raw.candidate_next_actions.append(CandidateNextAction(action="安排产品 Demo", evidence_id=evidence_id, attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT))

        if "客户同意先试用两周" in input_text:
            evidence_id = add_evidence("客户同意先试用两周", "stage")
            raw.stage_signals.append(_signal("trial_agreed", evidence_id))
        if "方案交流" in input_text or "技术交流" in input_text:
            quote = "客户希望我们拉技术同学做一次方案交流" if "客户希望我们拉技术同学做一次方案交流" in input_text else "技术交流"
            evidence_id = add_evidence(quote, "stage")
            raw.stage_signals.append(_signal("technical_exchange_agreed", evidence_id))

        if "预算 50 万" in input_text:
            evidence_id = add_evidence("预算 50 万", "budget")
            raw.candidate_budget.append(_candidate_fact("50 万", evidence_id))
            raw.stage_signals.append(_signal("budget_discussed", evidence_id))
        if "预算大概 30 万" in input_text:
            evidence_id = add_evidence("预算大概 30 万", "budget")
            raw.candidate_budget.append(_candidate_fact("30 万", evidence_id))
            raw.stage_signals.append(_signal("budget_discussed", evidence_id))
        elif "30 万" in input_text and "预算" in input_text:
            evidence_id = add_evidence("30 万", "budget")
            raw.candidate_budget.append(_candidate_fact("30 万", evidence_id))
            raw.stage_signals.append(_signal("budget_discussed", evidence_id))
        if "预算 80 万" in input_text:
            evidence_id = add_evidence("预算 80 万", "budget")
            raw.candidate_budget.append(_candidate_fact("80 万", evidence_id))
            raw.stage_signals.append(_signal("budget_discussed", evidence_id))
        def budget_key(value: str) -> str:
            return value.lower().replace(" ", "").replace("w", "万")

        seen_budget_values = {budget_key(item.value) for item in raw.candidate_budget}
        for match in re.finditer(r"预算(?:实际)?(?:金额)?(?:是|为|约|大概|大约)?\s*(\d+\s*万|\d+\s*w)", input_text, re.IGNORECASE):
            value = match.group(1).replace(" ", "")
            if value.lower().endswith("w"):
                value = value[:-1] + "w"
            else:
                value = re.sub(r"^(\d+)万$", r"\1 万", value)
            key = budget_key(value)
            if key not in seen_budget_values:
                evidence_id = add_evidence(match.group(0), "budget")
                raw.candidate_budget.append(_candidate_fact(value, evidence_id))
                raw.stage_signals.append(_signal("budget_discussed", evidence_id))
                seen_budget_values.add(key)
        if "今年没有预算" in input_text:
            evidence_id = add_evidence("今年没有预算", "budget")
            raw.candidate_budget.append(_candidate_fact("今年没有预算", evidence_id, polarity=Polarity.NEGATIVE))
            raw.stage_signals.append(_signal("budget_unavailable", evidence_id, polarity=Polarity.NEGATIVE))
            raw.possible_conflicts.append(PossibleConflict(field="budget", description="客户预算表述前后冲突：先出现预算金额，后又表示今年没有预算。", evidence_ids=[item.evidence_id for item in raw.candidate_budget if item.evidence_id]))
        if any(phrase in input_text for phrase in ("预算目前已经被冻结", "预算不足", "预算被冻结", "预算冻结", "预算未批", "预算批不下来")):
            quote = next(phrase for phrase in ("预算目前已经被冻结", "预算不足", "预算被冻结", "预算冻结", "预算未批", "预算批不下来") if phrase in input_text)
            evidence_id = add_evidence(quote, "budget")
            raw.candidate_budget.append(_candidate_fact(quote, evidence_id, polarity=Polarity.NEGATIVE))
            raw.stage_signals.append(_signal("budget_unavailable", evidence_id, polarity=Polarity.NEGATIVE))
        if "等明年再看" in input_text:
            evidence_id = add_evidence("可能要等明年再看", "stage")
            raw.stage_signals.append(_signal("demand_delayed", evidence_id, explicitness=Explicitness.AMBIGUOUS, polarity=Polarity.NEGATIVE))

        if "问了报价" in input_text or "在讨论报价" in input_text or "正式报价" in input_text:
            quote = "问了报价" if "问了报价" in input_text else ("在讨论报价" if "在讨论报价" in input_text else "正式报价")
            evidence_id = add_evidence(quote, "stage")
            raw.stage_signals.append(_signal("quote_discussed", evidence_id))
        if "走采购流程" in input_text or "采购流程" in input_text:
            evidence_id = add_evidence("走采购流程" if "走采购流程" in input_text else "采购流程", "stage")
            raw.stage_signals.append(_signal("procurement_discussed", evidence_id))
        if any(phrase in input_text for phrase in ("采购申请还没提交", "采购流程卡住", "采购流程未启动", "审批还没启动")):
            quote = next(phrase for phrase in ("采购申请还没提交", "采购流程卡住", "采购流程未启动", "审批还没启动") if phrase in input_text)
            evidence_id = add_evidence(quote, "stage")
            raw.stage_signals.append(_signal("procurement_discussed", evidence_id, polarity=Polarity.NEGATIVE))
        if "看合同条款" in input_text:
            evidence_id = add_evidence("看合同条款", "stage")
            raw.stage_signals.append(_signal("contract_terms_discussed", evidence_id, attribution=Attribution.THIRD_PARTY))
        if "进入内部立项流程" in input_text or "进入内部立项审批" in input_text:
            evidence_id = add_evidence("进入内部立项流程" if "进入内部立项流程" in input_text else "进入内部立项审批", "stage")
            raw.stage_signals.append(_signal("internal_project_approval", evidence_id))
        elif "进入内部审批" in input_text or "进入内部审批流程" in input_text:
            evidence_id = add_evidence("进入内部审批流程" if "进入内部审批流程" in input_text else "进入内部审批", "stage")
            raw.stage_signals.append(_signal("internal_project_approval", evidence_id))
        if "老板审批后就能定" in input_text:
            evidence_id = add_evidence("老板审批后就能定", "decision_maker")
            raw.stage_signals.append(_signal("internal_project_approval", evidence_id))
        if "进入供应商评审" in input_text:
            evidence_id = add_evidence("进入供应商评审", "stage")
            raw.stage_signals.append(_signal("vendor_decision", evidence_id))
        if "合同已签" in input_text or "合同已经签完" in input_text:
            quote = "合同已签" if "合同已签" in input_text else "合同已经签完"
            evidence_id = add_evidence(quote, "stage")
            raw.stage_signals.append(_signal("contract_signed", evidence_id))
        if "正式订单已经确认" in input_text:
            evidence_id = add_evidence("正式订单已经确认", "stage")
            raw.stage_signals.append(_signal("order_confirmed", evidence_id))
        if "项目暂停" in input_text:
            evidence_id = add_evidence("项目暂停", "stage")
            raw.stage_signals.append(_signal("demand_invalidated", evidence_id))

        if "王总" in input_text:
            evidence_id = add_evidence("王总", "person")
            raw.candidate_people.append(CandidatePerson(name="王总", role=None, kind="unknown", authority_confirmed=False, evidence_id=evidence_id, attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT))
        if "陈总负责审批" in input_text:
            evidence_id = add_evidence("最终由陈总负责审批", "decision_maker")
            raw.candidate_people.append(CandidatePerson(name="陈总", role="审批负责人", kind="decision_maker", authority_confirmed=True, evidence_id=evidence_id, attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT))
        elif "陈总" in input_text:
            evidence_id = add_evidence("陈总", "person")
            raw.candidate_people.append(CandidatePerson(name="陈总", role="数字化负责人" if "数字化负责人陈总" in input_text else None, kind="unknown", authority_confirmed=False, evidence_id=evidence_id, attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT))
        if "采购刘经理" in input_text:
            evidence_id = add_evidence("采购刘经理", "person")
            raw.candidate_people.append(CandidatePerson(name="刘经理", role="采购", kind="influencer", authority_confirmed=False, evidence_id=evidence_id, attribution=Attribution.THIRD_PARTY, explicitness=Explicitness.EXPLICIT))
        if "李总拍板" in input_text:
            evidence_id = add_evidence("李总拍板", "decision_maker")
            raw.candidate_people.append(CandidatePerson(name="李总", role="拍板人", kind="decision_maker", authority_confirmed=True, evidence_id=evidence_id, attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT))
        if "下季度上线" in input_text:
            evidence_id = add_evidence("下季度上线", "timeline")
            raw.candidate_timeline.append(_candidate_fact("下季度上线", evidence_id))
        if "计划本月底完成供应商选择" in input_text:
            evidence_id = add_evidence("计划本月底完成供应商选择", "timeline")
            raw.candidate_timeline.append(_candidate_fact("本月底完成供应商选择", evidence_id))
        if "客户确认下一步行动是由销售负责人张晨在本周五前发送正式报价和实施计划给采购刘经理" in input_text:
            evidence_id = add_evidence("客户确认下一步行动是由销售负责人张晨在本周五前发送正式报价和实施计划给采购刘经理", "next_action")
            raw.candidate_next_actions.append(
                CandidateNextAction(action="发送正式报价和实施计划", owner="张晨", time="本周五前", evidence_id=evidence_id, attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)
            )

        seen_next_action_quotes = {candidate.quote for candidate in raw.evidence_candidates if candidate.field in {"next_action", "candidate_next_actions"}}
        last_next_action = raw.candidate_next_actions[-1].action if raw.candidate_next_actions else None
        for sentence in re.split(r"[。；;\n]+", input_text):
            text = re.sub(r"\s+", " ", sentence).strip()
            if not text or text in seen_next_action_quotes:
                continue
            if "客户" not in text or not re.search(r"(已确认|已确定|确认|确定)", text):
                continue
            if "下一步" not in text and not (last_next_action and "负责人" in text):
                continue

            action: str | None = None
            action_match = re.search(r"下一步(?:行动)?\s*(?:是|为|进行|安排|推进)?\s*([^，,；;\n]+)", text)
            if action_match:
                action = re.split(r"(?:建议负责人|负责人|时间|定在|安排在|在)", action_match.group(1).strip())[0].strip()
                action = re.sub(r"^(是|为|进行|安排|推进)\s*", "", action).strip()
                if not action or action.startswith(("建议负责人", "负责人", "时间")):
                    action = None
            if not action:
                action = last_next_action
            if not action:
                continue

            owner_match = re.search(r"(?:建议负责人|负责人)\s*(?:是|为|改为|调整为)?\s*([^，,；;\n]+)", text)
            time_match = re.search(r"(?:时间|时间为|时间在|定在|安排在)\s*(?:是|为|在)?\s*([^，,；;\n]+)", text)
            owner = owner_match.group(1).strip() if owner_match else None
            time = time_match.group(1).strip() if time_match else None
            if time and re.search(r"(待确认|待确定|未确认|不确定|未确定|未定|没确定|没有确定|还没定|尚未确定|未约定|尚未约定|没约定|暂无|暂未)", time):
                time = "待确认"
            evidence_id = add_evidence(text, "next_action")
            raw.candidate_next_actions.append(
                CandidateNextAction(action=action, owner=owner, time=time, evidence_id=evidence_id, attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)
            )
            last_next_action = action
            seen_next_action_quotes.add(text)
        return raw



class DeepSeekProvider(LLMProvider):
    base_url = "https://api.deepseek.com"

    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or get_settings()
        if not self.settings.llm_api_key or not self.settings.llm_model:
            raise ProviderNotConfiguredError()

    @property
    def provider_name(self) -> str:
        return "deepseek"

    @property
    def model_name(self) -> str:
        return self.settings.llm_model

    async def invoke_structured(self, input_text: str) -> RawExtraction:
        attempts = max(self.settings.llm_schema_retry, 0) + 1
        last_schema_error: Exception | None = None
        for _ in range(attempts):
            try:
                payload = await self._call_chat_json_output(input_text)
                return self._validate_payload(payload)
            except (json.JSONDecodeError, ValidationError, LLMSchemaInvalidError) as exc:
                last_schema_error = exc
        raise LLMSchemaInvalidError() from last_schema_error

    async def invoke_grounded_summary(self, context: dict[str, Any], deterministic_draft: str) -> str:
        payload = await self._call_summary_json_output(context, deterministic_draft)
        summary = payload.get("summary")
        if not isinstance(summary, str):
            raise LLMSchemaInvalidError()
        return summary

    async def check_connection(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=min(self.settings.llm_timeout_seconds, 10.0)) as client:
                response = await client.get(f"{self.base_url}/models", headers=self._headers())
            return response.status_code < 500
        except Exception:
            return False

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.llm_api_key}", "Content-Type": "application/json"}

    async def _call_responses_json_schema(self, input_text: str) -> dict[str, Any]:
        body = {
            "model": self.settings.llm_model,
            "input": [
                {"role": "system", "content": RAW_EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": build_raw_extraction_user_prompt(input_text)},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "RawExtraction",
                    "schema": RawExtraction.model_json_schema(),
                }
            },
            "thinking": {"type": "disabled"},
            "temperature": 0,
            "max_output_tokens": 2048,
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
                response = await client.post(f"{self.base_url}/responses", headers=self._headers(), json=body)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError() from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError() from exc
        if response.status_code in {400, 404}:
            raise _StructuredOutputUnsupported()
        if response.status_code >= 500 or response.status_code == 429:
            raise LLMProviderError()
        if response.status_code >= 400:
            raise _StructuredOutputUnsupported()
        data = response.json()
        if data.get("status") in {"failed", "incomplete"}:
            raise LLMProviderError(retryable=True)
        text = self._extract_responses_text(data)
        return json.loads(text)

    async def _call_chat_json_output(self, input_text: str) -> dict[str, Any]:
        body = {
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": RAW_EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": build_raw_extraction_user_prompt(input_text)},
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "temperature": 0,
            "max_tokens": 2048,
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
                response = await client.post(f"{self.base_url}/chat/completions", headers=self._headers(), json=body)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError() from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError() from exc
        if response.status_code >= 500 or response.status_code == 429:
            raise LLMProviderError()
        if response.status_code >= 400:
            raise LLMProviderError(retryable=False)
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        if not content:
            raise LLMSchemaInvalidError()
        return json.loads(content)

    async def _call_summary_json_output(self, context: dict[str, Any], deterministic_draft: str) -> dict[str, Any]:
        context_json = json.dumps(context, ensure_ascii=False, sort_keys=True)
        body = {
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": GROUNDED_SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": build_grounded_summary_user_prompt(context_json, deterministic_draft)},
            ],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "temperature": 0,
            "max_tokens": 512,
        }
        try:
            async with httpx.AsyncClient(timeout=min(self.settings.llm_timeout_seconds, 12.0)) as client:
                response = await client.post(f"{self.base_url}/chat/completions", headers=self._headers(), json=body)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError() from exc
        except httpx.HTTPError as exc:
            raise LLMProviderError() from exc
        if response.status_code >= 500 or response.status_code == 429:
            raise LLMProviderError()
        if response.status_code >= 400:
            raise LLMProviderError(retryable=False)
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        if not content:
            raise LLMSchemaInvalidError()
        return json.loads(content)

    def _extract_responses_text(self, data: dict[str, Any]) -> str:
        chunks: list[str] = []
        for item in data.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    chunks.append(content["text"])
        if not chunks:
            raise LLMSchemaInvalidError()
        return "".join(chunks)

    def _validate_payload(self, payload: dict[str, Any]) -> RawExtraction:
        return RawExtraction.model_validate(payload)


class _StructuredOutputUnsupported(Exception):
    pass

def get_provider(name: str | None = None, settings: AppSettings | None = None) -> LLMProvider:
    resolved_settings = settings or get_settings()
    provider_name = (name or resolved_settings.llm_provider or "mock").lower()
    if provider_name in {"default", ""}:
        provider_name = resolved_settings.llm_provider
    if provider_name == "mock":
        return MockProvider()
    if provider_name == "deepseek":
        return DeepSeekProvider(resolved_settings)
    raise UnsupportedProviderError(provider_name)
