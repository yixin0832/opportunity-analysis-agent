from __future__ import annotations

from .schemas import ExampleInput


EXAMPLES: list[ExampleInput] = [
    ExampleInput(
        id="demo_s2",
        title="决策审批",
        description="客户已试用方案，进入内部立项审批并明确下一步报价动作。",
        input_text="今天和远川零售集团数字化负责人陈总、采购刘经理开了方案评审会。客户确认门店售后咨询和会员活动问答是今年重点改造场景，已经试用过我们的智能客服方案，客服团队反馈效果可以继续推进。陈总表示今年预算约 80 万，采购刘经理询问了正式报价、付款方式和采购流程，项目需要进入内部立项审批，并计划本月底完成供应商选择。最终由陈总负责审批。客户确认下一步行动是由销售负责人张晨在本周五前发送正式报价和实施计划给采购刘经理。",
    ),
    ExampleInput(
        id="budget_conflict",
        title="预算冲突",
        description="客户预算表达前后冲突，需要确认当前真实状态。",
        input_text="客户先说今年预算 50 万，可以评估客服自动化方案。会议后半段又说今年没有预算，可能要等明年再看。",
    ),
    ExampleInput(
        id="insufficient_text",
        title="信息不足",
        description="文本严重残缺，不能凭模型常识补全。",
        input_text="客户……预算……审批……",
    ),
]
