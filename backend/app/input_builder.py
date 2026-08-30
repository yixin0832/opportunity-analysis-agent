from __future__ import annotations

import re

from .schemas import ClarifyAnswer


CORRECTION_PREFIX = "修正识别"
FIELD_LABELS = {
    "customer_needs": "客户需求",
    "core_scenarios": "核心场景",
    "budget": "预算",
    "decision_maker": "决策人",
    "influencers": "影响人",
    "timeline": "时间计划",
    "stage": "商机阶段",
    "source_text": "销售拜访记录",
    "next_action": "下一步行动",
    "next_action.action": "下一步行动",
    "next_action.owner": "下一步行动负责人",
    "next_action.time": "下一步行动时间",
    "confirmed_next_action": "下一步行动",
    "其他补充信息": "补充信息",
    "补充信息": "补充信息",
}


def has_correction_intent(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text.strip())
    if not normalized:
        return False
    original_error_patterns = (
        r"(我|用户|销售|记录人)?(原文|原始记录|记录|录入|输入|纪要|拜访记录).{0,12}(写错|写反|记错|录错|填错|有误|错误|不对)",
        r"(我|用户|销售|记录人).{0,8}(写错|写反|记错|录错|填错)",
        r"(手误|笔误|录入有误|记录有误|原文有误)",
    )
    recognition_error_patterns = (
        r"(系统|模型|AI|agent|助手).{0,12}(识别错|识别有误|识别不对|判断错|判断有误|判断不对|抽取错|抽取有误|理解错|理解有误)",
        r"(不是|并非).{1,40}(而是|是|应该是|实际是|实际为|才是)",
        r"(不是|并非).{1,40}(确认|安排|改为|调整为|更正为)",
        r".{1,40}只是.{1,40}(才是|不是)",
        r".{1,40}只是.{1,40}(拍板|决策|审批|负责人|责任人)",
    )
    return any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in original_error_patterns + recognition_error_patterns)


def validate_correction_answers(answers: list[ClarifyAnswer]) -> None:
    invalid = [answer for answer in answers if is_correction_answer(answer) and not has_correction_intent(answer.answer)]
    if invalid:
        raise ValueError("修正识别只用于原始记录手误或系统识别错误。请写明“原文/录入写错了”或“系统识别错了”，并给出正确事实；客户前后说法不一致请在待确认事项中补充。")


def is_correction_answer(answer: ClarifyAnswer) -> bool:
    question_id = (answer.question_id or "").strip()
    return question_id.startswith(CORRECTION_PREFIX) or question_id.startswith("correction:")


def _field_label(question_id: str | None) -> str:
    raw = (question_id or "补充信息").strip()
    if raw.startswith(CORRECTION_PREFIX):
        raw = raw.removeprefix(CORRECTION_PREFIX).lstrip("：: ")
    if raw.startswith("correction:"):
        raw = raw.split(":", 1)[1]
    raw = raw.removesuffix("修正").removesuffix("确认").strip()
    return FIELD_LABELS.get(raw, raw)


def _append_answers(parts: list[str], answers: list[ClarifyAnswer], *, correction: bool = False) -> None:
    for answer in answers:
        label = _field_label(answer.question_id)
        action = "修正" if correction else "确认"
        parts.append(f"{label}{action}：{answer.answer.strip()}")


def build_revision_input(original_input: str, clarification_records: list[list[ClarifyAnswer]]) -> str:
    parts = ["【原始销售拜访记录】", original_input.strip()]
    for index, answers in enumerate(clarification_records, start=2):
        if not answers:
            continue
        validate_correction_answers(answers)
        clarification_answers = [answer for answer in answers if not is_correction_answer(answer)]
        correction_answers = [answer for answer in answers if is_correction_answer(answer)]
        if clarification_answers:
            parts.extend(["", f"【第 {index} 次分析补充确认信息】"])
            _append_answers(parts, clarification_answers)
        if correction_answers:
            parts.extend(
                [
                    "",
                    f"【第 {index} 次分析修正识别事实】",
                    "以下内容是用户对已识别信息的明确修正；当前分析应以修正后的事实为准，修正前内容仅作为历史记录保留，不视为客户前后表达矛盾。",
                ]
            )
            _append_answers(parts, correction_answers, correction=True)
    return "\n".join(parts).strip()
