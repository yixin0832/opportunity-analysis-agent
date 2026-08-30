# Stage Decision Explanation Layer Fix Regression

Created at: 2026-08-28T01:05:16

## Summary

| Case | Stage | Status | Stage Decision Reason | Result |
| --- | --- | --- | --- | --- |
| Case9 | None | need_confirmation | historical_context_only | PASS |
| Case11 | None | unable_to_judge | insufficient_stage_signal | PASS |
| Case12 | S0 | complete | None | PASS |
| Case1 | S0 | complete | None | PASS |
| Case5 | S4 | complete | None | PASS |
| Case8 | None | need_confirmation | historical_context_only | PASS |

## Key Explanations

- Case9: 当前记录主要描述历史状态、暂停、延期或预算受阻情况，暂时无法确认当前销售阶段。
- Case11: 当前信息不足以确认销售阶段，请补充客户需求、方案推进或商务进展。

## Full Records

### Case9

Input: 客户上个月已经讨论过 40 万预算，也评估过我们的客服自动化方案。但客户今天明确表示，由于业务调整，这个项目已经暂停，今年不再推进，最快明年再重新评估。

RawExtraction stage_signals: `[{'signal_type': 'budget_discussed', 'explicitness': 'explicit', 'polarity': 'positive', 'attribution': 'customer', 'current_validity': 'historical', 'evidence_id': 'E01'}, {'signal_type': 'solution_evaluation', 'explicitness': 'explicit', 'polarity': 'positive', 'attribution': 'customer', 'current_validity': 'historical', 'evidence_id': 'E02'}, {'signal_type': 'demand_invalidated', 'explicitness': 'explicit', 'polarity': 'negative', 'attribution': 'customer', 'current_validity': 'active', 'evidence_id': 'E03'}, {'signal_type': 'demand_delayed', 'explicitness': 'explicit', 'polarity': 'negative', 'attribution': 'customer', 'current_validity': 'active', 'evidence_id': 'E03'}]`

Rule Engine: `{'stage': None, 'status': 'need_confirmation', 'stage_reason': None, 'stage_decision_reason': 'historical_context_only', 'analysis_warning_descriptions': ['当前记录主要描述历史状态、暂停、延期或预算受阻情况，暂时无法确认当前销售阶段。'], 'opportunity_risk_types': ['demand_invalidated']}`

### Case11

Input: 客户确认项目继续推进，也认可当前方案。客户表示具体上线时间还没有最终确定，后面再根据内部资源安排确认日期。目前没有说项目延期或暂停。

RawExtraction stage_signals: `[]`

Rule Engine: `{'stage': None, 'status': 'unable_to_judge', 'stage_reason': None, 'stage_decision_reason': 'insufficient_stage_signal', 'analysis_warning_descriptions': ['当前信息不足以确认销售阶段，请补充客户需求、方案推进或商务进展。'], 'opportunity_risk_types': []}`

### Case12

Input: 今天客户交流情况不错，后面再看。

RawExtraction stage_signals: `[]`

Rule Engine: `{'stage': 'S0', 'status': 'complete', 'stage_reason': '只有初步接触，无明确需求。', 'stage_decision_reason': None, 'analysis_warning_descriptions': [], 'opportunity_risk_types': []}`

### Case1

Input: 今天第一次和远川科技采购经理简单认识了一下，主要介绍了我们公司的产品和服务。客户表示可以后续再保持联系，目前暂时没有明确项目，也没有提出具体业务问题或使用场景。

RawExtraction stage_signals: `[]`

Rule Engine: `{'stage': 'S0', 'status': 'complete', 'stage_reason': '只有初步接触，无明确需求。', 'stage_decision_reason': None, 'analysis_warning_descriptions': [], 'opportunity_risk_types': []}`

### Case5

Input: 客户确认需求继续推进，预算已经落实为 80 万。项目目前已经进入内部审批流程，同时正在进行三家供应商比选。最终由李总负责审批，采购团队计划本月底完成供应商选择。

RawExtraction stage_signals: `[{'signal_type': 'budget_discussed', 'explicitness': 'explicit', 'polarity': 'positive', 'attribution': 'customer', 'current_validity': 'active', 'evidence_id': 'E01'}, {'signal_type': 'internal_project_approval', 'explicitness': 'explicit', 'polarity': 'positive', 'attribution': 'third_party', 'current_validity': 'active', 'evidence_id': 'E02'}, {'signal_type': 'vendor_decision', 'explicitness': 'explicit', 'polarity': 'positive', 'attribution': 'third_party', 'current_validity': 'active', 'evidence_id': 'E02'}]`

Rule Engine: `{'stage': 'S4', 'status': 'complete', 'stage_reason': '已进入内部立项、审批或供应商决策。', 'stage_decision_reason': None, 'analysis_warning_descriptions': [], 'opportunity_risk_types': []}`

### Case8

Input: 客户上午表示今年项目预算大约 60 万，可以继续推进。下午再次沟通时，客户又表示今年预算目前已经被冻结，暂时无法确认是否还能继续采购。产品方案本身客户仍表示认可。

RawExtraction stage_signals: `[{'signal_type': 'budget_discussed', 'explicitness': 'explicit', 'polarity': 'positive', 'attribution': 'customer', 'current_validity': 'historical', 'evidence_id': 'E01'}, {'signal_type': 'budget_unavailable', 'explicitness': 'explicit', 'polarity': 'negative', 'attribution': 'customer', 'current_validity': 'active', 'evidence_id': 'E02'}, {'signal_type': 'solution_evaluation', 'explicitness': 'explicit', 'polarity': 'positive', 'attribution': 'customer', 'current_validity': 'active', 'evidence_id': 'E03'}]`

Rule Engine: `{'stage': None, 'status': 'need_confirmation', 'stage_reason': None, 'stage_decision_reason': 'historical_context_only', 'analysis_warning_descriptions': ['当前记录主要描述历史状态、暂停、延期或预算受阻情况，暂时无法确认当前销售阶段。'], 'opportunity_risk_types': ['conflict', 'demand_invalidated']}`
