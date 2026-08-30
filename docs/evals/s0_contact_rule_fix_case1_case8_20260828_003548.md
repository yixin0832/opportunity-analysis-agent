# S0 初步接触 Rule 修复后真实 DeepSeek 回归：Case1-Case8

创建时间：2026-08-28T00:35:48
Provider：deepseek
Model：deepseek-v4-flash

说明：本轮使用真实 DeepSeek Provider，通过 FastAPI TestClient 调用 /analyze。未记录 API Key、Authorization Header 或 Secret。

## 修改验证摘要

| Case | 预期 Stage | 实际 Stage | 预期 Status | 实际 Status | 结论 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| Case1 | S0 | S0 | complete | complete | PASS | 保持 S0；无预算/决策人/时间幻觉。 |
| Case2 | S1 | S1 | complete | complete | PASS | 保持 S1；未自动升级到 S2/S3。 |
| Case3 | S2 | S2 | complete | complete | PASS | 保持 S2；Demo 与时间同步正常。 |
| Case4 | S3 | S3 | complete | complete | PASS | 保持 S3；预算 value 与 timeline value 粒度保持正确。 |
| Case5 | S4 | S4 | complete | complete | PASS | 保持 S4；customer_needs 语义边界仍作为既有 P1 待定，不影响本轮。 |
| Case6 | S5 | S5 | complete | complete | PASS | 保持 S5；高阶段优先无回归。 |
| Case7 | S0 | S0 | complete | complete | PASS | 已从 unable_to_judge 修复为 S0；销售猜测未被采纳。 |
| Case8 | null | null | need_confirmation | need_confirmation | PASS | 按 Design Decision 保持现状；预算冲突和风险仍正确，未因 S0 修改回归。 |

## Open Issues

| 能力 | 涉及 Case | 优先级 | 状态 |
| --- | --- | --- | --- |
| customer_needs 语义边界 | Case5 | P1 | 待定，按约定暂缓 |
| Grounded LLM Summary / 商机概览 | UI Review、Case1-Case5 | P1 | 暂缓 |

## Design Decisions

- Decision-001：Case8 客户认可方案不等于明确进入方案验证，保持当前结果。
- Decision-002：Case5 “需求继续推进”暂不进入 customer_needs。

## 关键结论

- 新增 S0 接触事实规则是通用能力修复：识别真实客户沟通、交流、会面、通话等初步接触，而不是 Case7 特殊分支。
- Case3 “客户……预算……审批……”仍为 unable_to_judge，未被误判成 S0。
- Case8 保持 need_confirmation 且 stage=null，未修改 solution_evaluation 规则。
- Case1-Case8 均符合本轮预期。