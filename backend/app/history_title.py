from __future__ import annotations

import re

from .schemas import FieldStatus, ValidatedOpportunity


TITLE_MAX_LEN = 20


def build_opportunity_title(original_input: str, result: ValidatedOpportunity) -> str:
    subject = _extract_named_subject(original_input)
    topic = _topic_from_result(result) or _topic_from_text(original_input, result)
    if subject and topic:
        return _trim_title(f"{subject} · {topic}")
    if topic:
        return _trim_title(topic)
    return "商机信息待补充"


def _topic_from_result(result: ValidatedOpportunity) -> str | None:
    needs = [str(item.value) for item in result.crm_fields.customer_needs if item.status == FieldStatus.CONFIRMED and item.value]
    scenarios = [str(item.value) for item in result.crm_fields.core_scenarios if item.status == FieldStatus.CONFIRMED and item.value]
    if scenarios:
        return _normalize_topic(scenarios[0])
    if needs:
        return _normalize_topic(needs[0])
    if result.confirmed_next_action and result.confirmed_next_action.action != "待确认":
        return _normalize_topic(result.confirmed_next_action.action)
    return None


def _normalize_topic(value: str) -> str:
    text = re.sub(r"^(客户|用户|门店|当前)?(希望|想要|想|需要|计划|确认|明确)?", "", value.strip())
    replacements = {
        "客服工单处理慢": "客服自动化项目",
        "门店客服工单处理慢": "客服自动化项目",
        "减少人工回复压力": "客服自动化项目",
        "提升客服响应效率": "客服自动化项目",
        "售后知识库智能问答": "智能问答场景",
        "售后知识库场景": "智能问答场景",
        "客服自动化方案评估": "客服自动化方案",
        "安排产品 Demo": "产品 Demo 与方案验证",
        "安排产品Demo": "产品 Demo 与方案验证",
        "技术交流": "技术交流推进",
        "方案交流": "方案交流推进",
        "进行商务评估": "商务评估推进",
        "商务评估": "商务评估推进",
    }
    compact = re.sub(r"\s+", "", text)
    for source, target in replacements.items():
        if source in compact:
            return target
    if any(keyword in compact for keyword in ("客服", "工单", "知识库", "智能问答")):
        if any(keyword in compact for keyword in ("自动", "AI", "智能", "知识库")):
            return "客服自动化项目"
        return "客服问题跟进"
    if "Demo" in text or "演示" in compact:
        return "产品 Demo 推进"
    if "预算" in compact or "报价" in compact:
        return "商务评估推进"
    if "审批" in compact or "立项" in compact:
        return "审批流程推进"
    return text[:TITLE_MAX_LEN].strip() or "商机信息待补充"


def _extract_named_subject(text: str) -> str | None:
    patterns = (
        r"(?:拜访了|拜访|走访了|走访|会见了|会见|今天和|与|和)([^。；，,\n]{2,20}?)(?:客户|公司|集团|企业)",
        r"(?:客户|公司|集团)[：: ]([^。；，,\n]{2,20})",
        r"([^。；，,\n]{2,20}(?:公司|集团))(?:表示|确认|说|提到|目前|已经|计划)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        candidate = _clean_subject(match.group(1))
        if candidate:
            return candidate
    return None


def _topic_from_text(text: str, result: ValidatedOpportunity) -> str | None:
    if result.developer_details.get("stage_decision_reason") == "insufficient_input":
        return None
    project_patterns = (
        r"([^。；，,\n]{2,18}(?:项目|系统|平台|方案|场景))(?:，|。|；|,|;|$)",
        r"(?:围绕|关于|推进|评估|建设)([^。；，,\n]{2,18}(?:项目|系统|平台|方案|场景))",
    )
    for pattern in project_patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        topic = _clean_topic(match.group(1))
        if topic:
            return topic[:TITLE_MAX_LEN]
    event_parts: list[str] = []
    if re.search(r"(Demo|演示)", text):
        event_parts.append("产品 Demo")
    if re.search(r"(商务评估|报价|预算|采购流程|合同条款)", text):
        event_parts.append("商务评估")
    if re.search(r"(技术交流|方案交流)", text):
        event_parts.append("技术交流")
    if re.search(r"(内部审批|内部立项|供应商评审|供应商选择)", text):
        event_parts.append("审批推进")
    if len(event_parts) >= 2:
        return "与".join(event_parts[:2])
    if event_parts:
        return f"{event_parts[0]}推进"
    return None


def _clean_topic(value: str) -> str | None:
    text = re.sub(r"^(客户|用户|目前|当前|这个|该|希望|想要|需要|计划|确认|明确|提到|表示|用|在)+", "", value.strip())
    text = re.sub(r"\s+", "", text)
    weak = {"项目", "系统", "平台", "方案", "场景", "这个项目", "该项目", "当前项目"}
    if not text or text in weak:
        return None
    if re.search(r"(预算|审批|报价|合同|今年|下周|本月|下月)", text) and not re.search(r"(系统|平台|方案|场景|项目)$", text):
        return None
    return text


def _clean_subject(value: str) -> str | None:
    text = re.sub(r"^(某|这个|该|当前|今天|客户|项目|公司|集团|和|与)", "", value.strip())
    text = re.sub(r"(的)?$", "", text).strip()
    text = re.sub(r"\s+", "", text)
    if not text or len(text) < 2:
        return None
    weak = {"客户", "某客户", "公司", "集团", "项目", "连锁零售客户", "连锁零售"}
    if text in weak:
        return None
    if re.search(r"(预算|审批|报价|合同|需求|方案|Demo|演示|客服|工单|智能问答)", text):
        return None
    return text[:12]


def _trim_title(title: str) -> str:
    text = re.sub(r"\s+", " ", title).strip()
    if len(text) <= TITLE_MAX_LEN:
        return text
    if " · " in text:
        subject, topic = text.split(" · ", 1)
        available = max(6, TITLE_MAX_LEN - len(subject) - 3)
        return f"{subject} · {topic[:available]}".rstrip()
    return text[:TITLE_MAX_LEN].rstrip()
