# P1 Prompt Value Granularity Regression Case1-Case5

- Run ID: 20260827_225848
- Created at: 2026-08-27T22:59:05
- Provider: deepseek
- Model: deepseek-v4-flash
- API Key: not recorded
- Change scope: Prompt only, budget value and timeline value granularity

## Case1 S0 线索，无明确需求

Verdict: PASS
HTTP Status: 200
Latency: 2653 ms

### Key Fields
- Stage: {"code": "S0", "label": "线索", "evidence_status": "sufficient", "reason": "只有初步接触，无明确需求。", "evidence_ids": []}
- Status: complete
- Budget: {"value": null, "status": "unknown", "evidence_ids": [], "conflicting_values": [], "reason": "本次记录未提供预算金额、预算范围或明确预算安排。"}
- Timeline: {"value": null, "status": "unknown", "evidence_ids": [], "conflicting_values": [], "reason": "本次记录未提供明确推进时间或上线计划。"}
- Decision Maker: {"name": null, "role": null, "status": "unknown", "authority_confirmed": false, "evidence_ids": [], "reason": "当前记录未明确最终审批、拍板或购买决策权限。"}
- Risks: []
- Next Action: {"confirmed": null, "recommended": [{"action": "继续了解客户背景，确认是否存在明确业务问题或改进目标", "owner": "销售负责人", "time": "待确认", "type": "ai_recommended", "reason": "当前只有初步接触，尚未形成明确需求，不宜直接推进演示、报价或采购流程。"}]}

### Checks

- PASS: stage actual="S0" expected="S0"
- PASS: status actual="complete" expected="complete"
- PASS: budget.value actual=null expected=null
- PASS: timeline.value actual=null expected=null
- PASS: decision_maker.name actual=null expected=null
- PASS: no_invalid_evidence actual=[] expected=[]

### RawExtraction Summary
```json
{
  "candidate_needs": [],
  "candidate_scenarios": [],
  "candidate_budget": [],
  "candidate_people": [
    {
      "name": "采购经理",
      "role": "采购经理",
      "kind": "unknown",
      "authority_confirmed": false,
      "evidence_id": "E01",
      "attribution": "customer",
      "explicitness": "explicit"
    }
  ],
  "candidate_timeline": [],
  "candidate_next_actions": [],
  "stage_signals": [],
  "ambiguities": [],
  "possible_conflicts": [],
  "evidence_candidates": [
    {
      "id": "E01",
      "quote": "今天第一次和远川科技采购经理简单认识了一下",
      "field": "customer_people"
    }
  ]
}
```

## Case2 S1 需求初探，有需求但未进入方案验证

Verdict: PASS
HTTP Status: 200
Latency: 3607 ms

### Key Fields
- Stage: {"code": "S1", "label": "需求初探", "evidence_status": "sufficient", "reason": "明确至少一个业务问题或使用场景。", "evidence_ids": ["E01"]}
- Status: complete
- Budget: {"value": null, "status": "unknown", "evidence_ids": [], "conflicting_values": [], "reason": "本次记录未提供预算金额、预算范围或明确预算安排。"}
- Timeline: {"value": null, "status": "unknown", "evidence_ids": [], "conflicting_values": [], "reason": "本次记录未提供明确推进时间或上线计划。"}
- Decision Maker: {"name": null, "role": null, "status": "unknown", "authority_confirmed": false, "evidence_ids": [], "reason": "当前记录未明确最终审批、拍板或购买决策权限。"}
- Risks: []
- Next Action: {"confirmed": null, "recommended": [{"action": "结合已确认需求和应用场景，推动客户选择合适的方案验证方式", "owner": "销售负责人", "time": "待确认", "type": "ai_recommended", "reason": "当前处于需求初探阶段，下一步应推动进入方案验证，但具体形式需结合客户意愿确认。"}]}

### Checks

- PASS: stage actual="S1" expected="S1"
- PASS: status actual="complete" expected="complete"
- PASS: budget.value actual=null expected=null
- PASS: timeline.value actual=null expected=null
- PASS: decision_maker.name actual=null expected=null
- PASS: no_invalid_evidence actual=[] expected=[]

### RawExtraction Summary
```json
{
  "candidate_needs": [
    {
      "value": "减少人工回复压力",
      "evidence_id": "E01",
      "attribution": "customer",
      "explicitness": "explicit",
      "polarity": "positive",
      "current_validity": "active"
    },
    {
      "value": "提升客服响应效率",
      "evidence_id": "E01",
      "attribution": "customer",
      "explicitness": "explicit",
      "polarity": "positive",
      "current_validity": "active"
    }
  ],
  "candidate_scenarios": [
    {
      "value": "门店售后咨询",
      "evidence_id": "E01",
      "attribution": "customer",
      "explicitness": "explicit",
      "polarity": "positive",
      "current_validity": "active"
    }
  ],
  "candidate_budget": [],
  "candidate_people": [],
  "candidate_timeline": [],
  "candidate_next_actions": [],
  "stage_signals": [
    {
      "signal_type": "need_identified",
      "explicitness": "explicit",
      "polarity": "positive",
      "attribution": "customer",
      "current_validity": "active",
      "evidence_id": "E01"
    },
    {
      "signal_type": "solution_evaluation",
      "explicitness": "ambiguous",
      "polarity": "positive",
      "attribution": "customer",
      "current_validity": "active",
      "evidence_id": "E02"
    }
  ],
  "ambiguities": [
    "solution_evaluation: 客户表示可以先研究一下相关方案，但未明确同意评估具体方案",
    "demo: 客户未确定是否安排 Demo",
    "budget: 未讨论预算",
    "procurement: 未讨论采购流程"
  ],
  "possible_conflicts": [],
  "evidence_candidates": [
    {
      "id": "E01",
      "quote": "客户表示目前门店售后咨询量很大，客服每天需要重复回答大量退换货和物流问题，希望减少人工回复压力，并提升客服响应效率。",
      "field": "customer_needs"
    },
    {
      "id": "E02",
      "quote": "客户认为可以先研究一下相关方案",
      "field": "solution_evaluation"
    }
  ]
}
```

## Case3 S2 方案验证，Demo 已确认

Verdict: PASS
HTTP Status: 200
Latency: 3781 ms

### Key Fields
- Stage: {"code": "S2", "label": "方案验证", "evidence_status": "sufficient", "reason": "客户明确同意演示、试用、技术交流或方案评估。", "evidence_ids": ["E03"]}
- Status: complete
- Budget: {"value": null, "status": "unknown", "evidence_ids": [], "conflicting_values": [], "reason": "本次记录未提供预算金额、预算范围或明确预算安排。"}
- Timeline: {"value": "下周四", "status": "confirmed", "evidence_ids": ["E03"], "conflicting_values": [], "reason": null}
- Decision Maker: {"name": null, "role": null, "status": "unknown", "authority_confirmed": false, "evidence_ids": [], "reason": "当前记录未明确最终审批、拍板或购买决策权限。"}
- Risks: []
- Next Action: {"confirmed": {"action": "安排产品 Demo", "owner": "IT王工", "time": "下周四", "type": "customer_confirmed", "evidence_ids": ["E03"]}, "recommended": []}

### Checks

- PASS: stage actual="S2" expected="S2"
- PASS: status actual="complete" expected="complete"
- PASS: budget.value actual=null expected=null
- PASS: timeline.value actual="下周四" expected="下周四"
- PASS: decision_maker.name actual=null expected=null
- PASS: no_invalid_evidence actual=[] expected=[]

### RawExtraction Summary
```json
{
  "candidate_needs": [
    {
      "value": "解决售后客服重复咨询问题",
      "evidence_id": "E01",
      "attribution": "customer",
      "explicitness": "explicit",
      "polarity": "positive",
      "current_validity": "active"
    }
  ],
  "candidate_scenarios": [
    {
      "value": "售后客服知识库问答",
      "evidence_id": "E01",
      "attribution": "customer",
      "explicitness": "explicit",
      "polarity": "positive",
      "current_validity": "active"
    }
  ],
  "candidate_budget": [],
  "candidate_people": [
    {
      "name": "IT王工",
      "role": "技术沟通负责人",
      "kind": "influencer",
      "authority_confirmed": false,
      "evidence_id": "E02",
      "attribution": "customer",
      "explicitness": "explicit"
    }
  ],
  "candidate_timeline": [],
  "candidate_next_actions": [
    {
      "action": "安排产品 Demo",
      "owner": "IT王工",
      "time": "下周四",
      "evidence_id": "E03",
      "attribution": "customer",
      "explicitness": "explicit"
    }
  ],
  "stage_signals": [
    {
      "signal_type": "need_identified",
      "explicitness": "explicit",
      "polarity": "positive",
      "attribution": "customer",
      "current_validity": "active",
      "evidence_id": "E01"
    },
    {
      "signal_type": "demo_agreed",
      "explicitness": "explicit",
      "polarity": "positive",
      "attribution": "customer",
      "current_validity": "active",
      "evidence_id": "E03"
    }
  ],
  "ambiguities": [
    "budget: 预算金额未确认",
    "decision_maker: 最终决策人未确认"
  ],
  "possible_conflicts": [],
  "evidence_candidates": [
    {
      "id": "E01",
      "quote": "客户目前希望用 AI 知识库解决售后客服重复咨询问题",
      "field": "customer_needs"
    },
    {
      "id": "E02",
      "quote": "IT 王工负责前期技术沟通",
      "field": "candidate_people"
    },
    {
      "id": "E03",
      "quote": "王工明确表示下周四可以安排一次产品 Demo",
      "field": "candidate_next_actions"
    }
  ]
}
```

## Case4 S3 商务评估，需求仍有效

Verdict: PASS
HTTP Status: 200
Latency: 4046 ms

### Key Fields
- Stage: {"code": "S3", "label": "商务评估", "evidence_status": "sufficient", "reason": "已讨论预算、报价、采购流程或合同条款之一，且需求仍有效。", "evidence_ids": ["E03"]}
- Status: complete
- Budget: {"value": "约 50 万", "status": "confirmed", "evidence_ids": ["E02"], "conflicting_values": [], "reason": "该信息来自客户或第三方明确表达，并且原文依据有效。"}
- Timeline: {"value": "下个月完成商务评估", "status": "confirmed", "evidence_ids": ["E05"], "conflicting_values": [], "reason": "该信息来自客户或第三方明确表达，并且原文依据有效。"}
- Decision Maker: {"name": null, "role": null, "status": "unknown", "authority_confirmed": false, "evidence_ids": [], "reason": "当前记录未明确最终审批、拍板或购买决策权限。"}
- Risks: []
- Next Action: {"confirmed": null, "recommended": [{"action": "澄清报价、采购流程和合同条款中的未决事项", "owner": "销售负责人", "time": "待确认", "type": "ai_recommended", "reason": "当前已进入商务评估，下一步应推动商务条件和采购路径明确。"}]}

### Checks

- PASS: stage actual="S3" expected="S3"
- PASS: status actual="complete" expected="complete"
- PASS: budget.value actual="约 50 万" expected="约 50 万"
- PASS: timeline.value actual="下个月完成商务评估" expected="下个月完成商务评估"
- PASS: decision_maker.name actual=null expected=null
- PASS: no_invalid_evidence actual=[] expected=[]

### RawExtraction Summary
```json
{
  "candidate_needs": [
    {
      "value": "客服自动化需求会继续推进",
      "evidence_id": "E01",
      "attribution": "customer",
      "explicitness": "explicit",
      "polarity": "positive",
      "current_validity": "active"
    }
  ],
  "candidate_scenarios": [],
  "candidate_budget": [
    {
      "value": "约 50 万",
      "evidence_id": "E02",
      "attribution": "customer",
      "explicitness": "explicit",
      "polarity": "positive",
      "current_validity": "active"
    }
  ],
  "candidate_people": [],
  "candidate_timeline": [
    {
      "value": "下个月完成商务评估",
      "evidence_id": "E05",
      "attribution": "third_party",
      "explicitness": "explicit",
      "polarity": "positive",
      "current_validity": "active"
    }
  ],
  "candidate_next_actions": [],
  "stage_signals": [
    {
      "signal_type": "demo_agreed",
      "explicitness": "explicit",
      "polarity": "positive",
      "attribution": "third_party",
      "current_validity": "historical",
      "evidence_id": "E01"
    },
    {
      "signal_type": "budget_discussed",
      "explicitness": "explicit",
      "polarity": "positive",
      "attribution": "customer",
      "current_validity": "active",
      "evidence_id": "E02"
    },
    {
      "signal_type": "quote_discussed",
      "explicitness": "explicit",
      "polarity": "positive",
      "attribution": "customer",
      "current_validity": "active",
      "evidence_id": "E03"
    },
    {
      "signal_type": "procurement_discussed",
      "explicitness": "explicit",
      "polarity": "positive",
      "attribution": "customer",
      "current_validity": "active",
      "evidence_id": "E04"
    }
  ],
  "ambiguities": [
    "decision_maker: 最终审批人未确认",
    "timeline: 商务评估的具体时间未确认"
  ],
  "possible_conflicts": [],
  "evidence_candidates": [
    {
      "id": "E01",
      "quote": "客户已经完成产品 Demo，并确认客服自动化需求会继续推进",
      "field": "customer_needs"
    },
    {
      "id": "E02",
      "quote": "客户表示今年有约 50 万预算",
      "field": "customer_budget"
    },
    {
      "id": "E03",
      "quote": "同时询问了正式报价和付款方式",
      "field": "customer_quote"
    },
    {
      "id": "E04",
      "quote": "采购同事提到后续需要走采购申请流程",
      "field": "customer_procurement"
    },
    {
      "id": "E05",
      "quote": "计划下个月完成商务评估",
      "field": "customer_timeline"
    }
  ]
}
```

## Case5 S4 决策审批，供应商评审

Verdict: PASS
HTTP Status: 200
Latency: 3186 ms

### Key Fields
- Stage: {"code": "S4", "label": "决策审批", "evidence_status": "sufficient", "reason": "已进入内部立项、审批或供应商决策。", "evidence_ids": ["E04"]}
- Status: complete
- Budget: {"value": "80 万", "status": "confirmed", "evidence_ids": ["E01"], "conflicting_values": [], "reason": "该信息来自客户或第三方明确表达，并且原文依据有效。"}
- Timeline: {"value": "本月底完成供应商选择", "status": "confirmed", "evidence_ids": ["E03"], "conflicting_values": [], "reason": "该信息来自客户或第三方明确表达，并且原文依据有效。"}
- Decision Maker: {"name": "李总", "role": null, "status": "confirmed", "authority_confirmed": true, "evidence_ids": ["E02"], "reason": "该人物的最终审批、拍板或购买决策权限已有明确原文依据。"}
- Risks: []
- Next Action: {"confirmed": null, "recommended": [{"action": "跟进内部审批或供应商决策进展，确认签约前阻塞事项", "owner": "销售负责人", "time": "待确认", "type": "ai_recommended", "reason": "当前已进入决策审批阶段，需要围绕审批与供应商决策推进。"}]}

### Checks

- PASS: stage actual="S4" expected="S4"
- PASS: status actual="complete" expected="complete"
- PASS: budget.value actual="80 万" expected="80 万"
- PASS: timeline.value actual="本月底完成供应商选择" expected="本月底完成供应商选择"
- PASS: decision_maker.name actual="李总" expected="李总"
- PASS: no_invalid_evidence actual=[] expected=[]

### RawExtraction Summary
```json
{
  "candidate_needs": [],
  "candidate_scenarios": [],
  "candidate_budget": [
    {
      "value": "80 万",
      "evidence_id": "E01",
      "attribution": "customer",
      "explicitness": "explicit",
      "polarity": "positive",
      "current_validity": "active"
    }
  ],
  "candidate_people": [
    {
      "name": "李总",
      "role": null,
      "kind": "decision_maker",
      "authority_confirmed": true,
      "evidence_id": "E02",
      "attribution": "customer",
      "explicitness": "explicit"
    }
  ],
  "candidate_timeline": [
    {
      "value": "本月底完成供应商选择",
      "evidence_id": "E03",
      "attribution": "customer",
      "explicitness": "explicit",
      "polarity": "positive",
      "current_validity": "active"
    }
  ],
  "candidate_next_actions": [],
  "stage_signals": [
    {
      "signal_type": "budget_discussed",
      "explicitness": "explicit",
      "polarity": "positive",
      "attribution": "customer",
      "current_validity": "active",
      "evidence_id": "E01"
    },
    {
      "signal_type": "internal_project_approval",
      "explicitness": "explicit",
      "polarity": "positive",
      "attribution": "third_party",
      "current_validity": "active",
      "evidence_id": "E04"
    },
    {
      "signal_type": "vendor_decision",
      "explicitness": "explicit",
      "polarity": "positive",
      "attribution": "third_party",
      "current_validity": "active",
      "evidence_id": "E05"
    }
  ],
  "ambiguities": [],
  "possible_conflicts": [],
  "evidence_candidates": [
    {
      "id": "E01",
      "quote": "预算已经落实为 80 万",
      "field": "budget"
    },
    {
      "id": "E02",
      "quote": "最终由李总负责审批",
      "field": "people"
    },
    {
      "id": "E03",
      "quote": "采购团队计划本月底完成供应商选择",
      "field": "timeline"
    },
    {
      "id": "E04",
      "quote": "项目目前已经进入内部审批流程",
      "field": "stage_signal"
    },
    {
      "id": "E05",
      "quote": "同时正在进行三家供应商比选",
      "field": "stage_signal"
    }
  ]
}
```
