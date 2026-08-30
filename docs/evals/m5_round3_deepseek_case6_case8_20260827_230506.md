# M5 第三轮真实 DeepSeek 回归测试：Case6-Case8

创建时间：2026-08-27T23:05:16
Provider：deepseek
Model：deepseek-v4-flash

说明：本轮使用真实 DeepSeek Provider，通过 FastAPI TestClient 调用 /analyze，覆盖 LLM、Pydantic、Evidence Validator、Rule Engine、Repository 保存和 API Response。未记录 API Key、Authorization Header 或 Secret。本轮未修改代码。

## Case6：PASS

### 原始输入
客户已经完成内部审批，最终确认采用我们的方案。双方合同已经签署完成，正式订单也已经确认。项目计划下月启动实施，由客户 IT 团队配合上线。

### 预期结果 vs 实际结果
| 字段 | 预期结果 | 实际结果 | 是否一致 | 差异说明 |
| --- | --- | --- | --- | --- |
| 客户需求 | 输入未说明具体业务痛点，空或待确认可接受；不得编造需求 | 空 | 一致 | 未编造需求，符合事实边界。 |
| 核心场景 | 可为空或不得编造具体业务场景 | 空 | 一致 | 未把“IT 团队配合上线”误写成购买场景。 |
| 预算 | 未提及预算，待确认 | 待确认，reason=本次记录未提供预算金额、预算范围或明确预算安排 | 一致 | 无幻觉预算。 |
| 决策人 | 未出现具体决策人姓名，待确认 | 待确认，reason=未明确最终审批、拍板或购买决策权限 | 一致 | 无人物编造。 |
| 影响人 | 客户 IT 团队配合上线不等于购买影响人 | 空 | 一致 | 没有把实施配合方误判为影响人。 |
| 时间计划 | 下月启动实施 | 下月启动实施，confirmed，evidence=项目计划下月启动实施 | 一致 | Timeline value 粒度正确，包含时间和业务里程碑。 |
| 商机阶段 | S5 赢单签约 | S5 · 赢单签约，reason=合同或正式订单已确认 | 一致 | RawExtraction 同时抽到 contract_signed/order_confirmed；Rule Engine 高阶段优先。 |
| 风险 | 无明确商机风险 | 无风险 | 一致 | 没有把预算/决策人未知升级为风险。 |
| 下一步行动 | 不得错误生成客户已确认 Demo；可无推荐或温和建议 | 无 confirmed_next_action；无 recommended_next_actions | 一致 | S5 场景下未生成错误 Demo。 |
| 未确认信息 | 可包含预算、决策人等缺失；未知不等于风险 | 预算、决策人、客户已确认下一步行动未明确 | 一致 | 未确认项与风险分离。 |

### 问题定位链路
LLM RawExtraction 抽取 internal_project_approval、contract_signed、order_confirmed、timeline；Evidence 均定位有效；Rule Engine 因 S5 信号返回 S5。

### RawExtraction 摘要
```json
{
  "candidate_needs": [],
  "candidate_scenarios": [],
  "candidate_budget": [],
  "candidate_people": [],
  "candidate_timeline": [
    {
      "value": "下月启动实施",
      "evidence_id": "E04",
      "attribution": "third_party",
      "explicitness": "explicit",
      "polarity": "positive",
      "current_validity": "active"
    }
  ],
  "candidate_next_actions": [],
  "stage_signals": [
    {
      "signal_type": "internal_project_approval",
      "explicitness": "explicit",
      "polarity": "positive",
      "attribution": "third_party",
      "current_validity": "active",
      "evidence_id": "E01"
    },
    {
      "signal_type": "contract_signed",
      "explicitness": "explicit",
      "polarity": "positive",
      "attribution": "third_party",
      "current_validity": "active",
      "evidence_id": "E02"
    },
    {
      "signal_type": "order_confirmed",
      "explicitness": "explicit",
      "polarity": "positive",
      "attribution": "third_party",
      "current_validity": "active",
      "evidence_id": "E03"
    }
  ],
  "ambiguities": [],
  "possible_conflicts": [],
  "evidence_candidates": [
    {
      "id": "E01",
      "quote": "客户已经完成内部审批",
      "field": "stage_signal"
    },
    {
      "id": "E02",
      "quote": "双方合同已经签署完成",
      "field": "stage_signal"
    },
    {
      "id": "E03",
      "quote": "正式订单也已经确认",
      "field": "stage_signal"
    },
    {
      "id": "E04",
      "quote": "项目计划下月启动实施",
      "field": "candidate_timeline"
    }
  ]
}
```

### 最终 API Response
```json
{
  "analysis_id": "19e7df22-3a78-4184-932f-9be7ea21ee9c",
  "revision": 1,
  "status": "complete",
  "summary": "当前商机阶段为 S5（赢单签约）；核心需求与场景：未确认；已确认推进动作：未明确；最重要未确认信息：预算未确认。",
  "stage": {
    "code": "S5",
    "label": "赢单签约",
    "evidence_status": "sufficient",
    "reason": "合同或正式订单已确认。",
    "evidence_ids": [
      "E03"
    ]
  },
  "crm_fields": {
    "customer_needs": [],
    "core_scenarios": [],
    "budget": {
      "value": null,
      "status": "unknown",
      "evidence_ids": [],
      "conflicting_values": [],
      "reason": "本次记录未提供预算金额、预算范围或明确预算安排。"
    },
    "decision_maker": {
      "name": null,
      "role": null,
      "status": "unknown",
      "authority_confirmed": false,
      "evidence_ids": [],
      "reason": "当前记录未明确最终审批、拍板或购买决策权限。"
    },
    "influencers": [],
    "timeline": {
      "value": "下月启动实施",
      "status": "confirmed",
      "evidence_ids": [
        "E04"
      ],
      "conflicting_values": [],
      "reason": "该信息来自客户或第三方明确表达，并且原文依据有效。"
    }
  },
  "opportunity_risks": [],
  "analysis_warnings": [],
  "confirmed_next_action": null,
  "recommended_next_actions": [],
  "unconfirmed_info": [
    {
      "value": "预算未确认",
      "status": "unknown",
      "evidence_ids": [],
      "conflicting_values": [],
      "reason": "本次记录未提供预算金额、预算范围或明确预算安排。"
    },
    {
      "value": "决策人或决策权限未确认",
      "status": "unknown",
      "evidence_ids": [],
      "conflicting_values": [],
      "reason": "当前记录未明确最终审批、拍板或购买决策权限。"
    },
    {
      "value": "客户已确认下一步行动未明确",
      "status": "unknown",
      "evidence_ids": [],
      "conflicting_values": [],
      "reason": "本次记录未出现客户已经确认的下一步动作、负责人或时间。"
    }
  ],
  "evidence": [
    {
      "id": "E01",
      "quote": "客户已经完成内部审批",
      "start_char": 0,
      "end_char": 10,
      "field": "stage_signal",
      "valid": true,
      "sufficient": true,
      "insufficiency_reason": null
    },
    {
      "id": "E02",
      "quote": "双方合同已经签署完成",
      "start_char": 23,
      "end_char": 33,
      "field": "stage_signal",
      "valid": true,
      "sufficient": true,
      "insufficiency_reason": null
    },
    {
      "id": "E03",
      "quote": "正式订单也已经确认",
      "start_char": 34,
      "end_char": 43,
      "field": "stage_signal",
      "valid": true,
      "sufficient": true,
      "insufficiency_reason": null
    },
    {
      "id": "E04",
      "quote": "项目计划下月启动实施",
      "start_char": 44,
      "end_char": 54,
      "field": "candidate_timeline",
      "valid": true,
      "sufficient": true,
      "insufficiency_reason": null
    }
  ],
  "clarification": null,
  "developer_details": {
    "stage_signals": [
      {
        "signal_type": "internal_project_approval",
        "explicitness": "explicit",
        "polarity": "positive",
        "attribution": "third_party",
        "current_validity": "active",
        "evidence_id": "E01"
      },
      {
        "signal_type": "contract_signed",
        "explicitness": "explicit",
        "polarity": "positive",
        "attribution": "third_party",
        "current_validity": "active",
        "evidence_id": "E02"
      },
      {
        "signal_type": "order_confirmed",
        "explicitness": "explicit",
        "polarity": "positive",
        "attribution": "third_party",
        "current_validity": "active",
        "evidence_id": "E03"
      }
    ],
    "valid_evidence_ids": [
      "E01",
      "E02",
      "E03",
      "E04"
    ],
    "sufficient_evidence_ids": [
      "E01",
      "E02",
      "E03",
      "E04"
    ],
    "input_summary": "客户已经完成内部审批，最终确认采用我们的方案。双方合同已经签署完成，正式订单也已经确认。项目计划下月启动实施，由客户 IT 团队配合上线。",
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "latency_ms": 3687
  }
}
```

## Case7：PARTIAL PASS

### 原始输入
今天和客户沟通后，我感觉客户挺感兴趣，应该很快会进入内部审批。王总在会上问了几个产品功能问题，我觉得他可能就是最终决策人。客户没有明确提到预算，也没有确认下一次会议时间。

### 预期结果 vs 实际结果
| 字段 | 预期结果 | 实际结果 | 是否一致 | 差异说明 |
| --- | --- | --- | --- | --- |
| 客户需求 | 无明确客户需求，待确认或空 | 空 | 一致 | 未把“挺感兴趣”或功能问题当成明确需求。 |
| 核心场景 | 无明确使用场景，待确认或空 | 空 | 一致 | 未编造场景。 |
| 预算 | 客户未明确提到预算，待确认 | 待确认 | 一致 | 无预算幻觉。 |
| 决策人 | 王总不能 confirmed decision maker | 待确认；RawExtraction 中王总 kind=unknown | 一致 | 没有把销售猜测“可能是决策人”采纳为客户事实。 |
| 影响人 | 问功能问题不足以成为影响人 | 空 | 一致 | 没有人物角色误判。 |
| 时间计划 | 未确认下一次会议时间，应待确认 | 待确认 | 一致 | 无时间幻觉。 |
| 商机阶段 | 不得 S4；可 S0 或信息不足 | stage=null，status=unable_to_judge | 部分一致 | 成功阻止 S4，但对“今天和客户沟通”这种初步接触没有兜底为 S0。首次发生在 Rule Engine 的 minimum analyzability gate。 |
| 风险 | 无明确负面商机风险 | 无风险 | 一致 | 未知项未升级为风险。 |
| 下一步行动 | 不得生成客户已确认下一步；AI建议围绕澄清需求 | 无 confirmed_next_action；无 recommended_next_actions | 部分一致 | 未生成错误确认行动，但 unable_to_judge 状态下当前规则不生成推荐行动。 |
| 未确认信息 | 预算、决策人、时间计划、客户已确认下一步应待确认 | 四项均进入 unconfirmed_info | 一致 | 待确认项完整。 |

### 问题定位链路
LLM RawExtraction 正确拒绝 sales attribution 的审批猜测与决策人猜测，只保留王总为 unknown person；无 stage_signals。Evidence Validator 正常。Rule Engine 的 _minimum_analyzable 对无有效 signal 文本只认“拜访/介绍/加微信/初步接触/认识/接触”，未覆盖“沟通”，因此返回 stage=null。

### RawExtraction 摘要
```json
{
  "candidate_needs": [],
  "candidate_scenarios": [],
  "candidate_budget": [],
  "candidate_people": [
    {
      "name": "王总",
      "role": null,
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
  "ambiguities": [
    "decision_maker: 王总是否为最终决策人未确认",
    "budget: 客户未提及预算",
    "next_action.time: 下一次会议时间未确认"
  ],
  "possible_conflicts": [],
  "evidence_candidates": [
    {
      "id": "E01",
      "quote": "王总在会上问了几个产品功能问题",
      "field": "candidate_people"
    }
  ]
}
```

### 最终 API Response
```json
{
  "analysis_id": "cab934e4-7f22-442a-adc2-a3d007258586",
  "revision": 1,
  "status": "unable_to_judge",
  "summary": "当前销售记录信息不足，尚无法形成可靠商机阶段判断；输入信息过于残缺，无法可靠分析，需要补充客户需求、场景或推进状态。",
  "stage": null,
  "crm_fields": {
    "customer_needs": [],
    "core_scenarios": [],
    "budget": {
      "value": null,
      "status": "unknown",
      "evidence_ids": [],
      "conflicting_values": [],
      "reason": "本次记录未提供预算金额、预算范围或明确预算安排。"
    },
    "decision_maker": {
      "name": null,
      "role": null,
      "status": "unknown",
      "authority_confirmed": false,
      "evidence_ids": [],
      "reason": "当前记录未明确最终审批、拍板或购买决策权限。"
    },
    "influencers": [],
    "timeline": {
      "value": null,
      "status": "unknown",
      "evidence_ids": [],
      "conflicting_values": [],
      "reason": "本次记录未提供明确推进时间或上线计划。"
    }
  },
  "opportunity_risks": [],
  "analysis_warnings": [
    {
      "type": "insufficient_input",
      "severity": "high",
      "description": "输入信息过于残缺，无法可靠分析。",
      "evidence_ids": []
    }
  ],
  "confirmed_next_action": null,
  "recommended_next_actions": [],
  "unconfirmed_info": [
    {
      "value": "预算未确认",
      "status": "unknown",
      "evidence_ids": [],
      "conflicting_values": [],
      "reason": "本次记录未提供预算金额、预算范围或明确预算安排。"
    },
    {
      "value": "决策人或决策权限未确认",
      "status": "unknown",
      "evidence_ids": [],
      "conflicting_values": [],
      "reason": "当前记录未明确最终审批、拍板或购买决策权限。"
    },
    {
      "value": "时间计划未确认",
      "status": "unknown",
      "evidence_ids": [],
      "conflicting_values": [],
      "reason": "本次记录未提供明确推进时间或上线计划。"
    },
    {
      "value": "客户已确认下一步行动未明确",
      "status": "unknown",
      "evidence_ids": [],
      "conflicting_values": [],
      "reason": "本次记录未出现客户已经确认的下一步动作、负责人或时间。"
    }
  ],
  "evidence": [
    {
      "id": "E01",
      "quote": "王总在会上问了几个产品功能问题",
      "start_char": 31,
      "end_char": 46,
      "field": "candidate_people",
      "valid": true,
      "sufficient": true,
      "insufficiency_reason": null
    }
  ],
  "clarification": {
    "needed": true,
    "questions": [
      {
        "field": "customer_needs",
        "question": "客户当前具体有什么业务需求或使用场景？",
        "priority": "high",
        "reason": "当前文本不足以判断是否存在明确需求。"
      },
      {
        "field": "stage",
        "question": "“审批”是指已经进入内部审批，还是只讨论了审批流程？",
        "priority": "high",
        "reason": "单个关键词不能证明已进入 S4。"
      }
    ],
    "max_questions": 3
  },
  "developer_details": {
    "stage_signals": [],
    "valid_evidence_ids": [
      "E01"
    ],
    "sufficient_evidence_ids": [
      "E01"
    ],
    "input_summary": "今天和客户沟通后，我感觉客户挺感兴趣，应该很快会进入内部审批。王总在会上问了几个产品功能问题，我觉得他可能就是最终决策人。客户没有明确提到预算，也没有确认下一…",
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "latency_ms": 2459
  }
}
```

## Case8：PARTIAL PASS

### 原始输入
客户上午表示今年项目预算大约 60 万，可以继续推进。下午再次沟通时，客户又表示今年预算目前已经被冻结，暂时无法确认是否还能继续采购。产品方案本身客户仍表示认可。

### 预期结果 vs 实际结果
| 字段 | 预期结果 | 实际结果 | 是否一致 | 差异说明 |
| --- | --- | --- | --- | --- |
| 客户需求 | 可识别项目/方案继续推进信息；无具体痛点时不得编造 | 空 | 一致 | 未编造业务痛点。 |
| 核心场景 | 无具体业务场景，待确认或空 | 空 | 一致 | 未编造场景。 |
| 预算 | conflict，不得选择单一事实 | conflict；conflicting_values=大约 60 万、今年预算目前已经被冻结 | 一致 | Budget value 粒度正确，冲突传播到正式 CRM 字段。 |
| 决策人 | 未提及，待确认 | 待确认 | 一致 | 无人物幻觉。 |
| 影响人 | 未提及，空 | 空 | 一致 | 无人物角色误判。 |
| 时间计划 | 未提及明确时间计划，待确认 | 待确认 | 一致 | 无时间幻觉。 |
| 商机阶段 | 不能稳定 S3；若方案认可被接纳，可保留 S2 + need_confirmation | stage=null，status=need_confirmation | 部分一致 | S3 被正确阻止，但 RawExtraction 的 active solution_evaluation 未被 Rule Engine evidence sufficiency 接纳，导致未保留 S2。 |
| 风险 | 预算冲突/预算冻结/继续采购不确定 | 包含 conflict 和 demand_invalidated 类高风险 | 一致 | 风险动态来自当前负向信号和预算冲突。 |
| 下一步行动 | blocker-first，优先确认预算和是否继续采购 | 优先确认项目当前是否仍计划推进，并澄清阻塞推进的关键信息 | 一致 | 未机械推进 Demo 或报价。 |
| 未确认信息 | 预算冲突、决策人、时间计划、客户已确认下一步等 | 四项均体现 | 一致 | 冲突与未知均进入待确认，但风险只承载高影响负面信号。 |

### 问题定位链路
LLM RawExtraction 抽到 budget_discussed(historical)、budget_unavailable(active)、solution_evaluation(active) 和 budget conflict；Evidence 均有效。Rule Engine 因 budget conflict 与 budget_unavailable 阻止 S3，这是正确的；但 _signal_has_sufficient_evidence 对 solution_evaluation 只接受“方案评估/评估方案/可以评估”等模式，不接受“产品方案本身客户仍表示认可”，因此 S2 未保留。

### RawExtraction 摘要
```json
{
  "candidate_needs": [],
  "candidate_scenarios": [],
  "candidate_budget": [
    {
      "value": "大约 60 万",
      "evidence_id": "E01",
      "attribution": "customer",
      "explicitness": "explicit",
      "polarity": "positive",
      "current_validity": "historical"
    },
    {
      "value": "今年预算目前已经被冻结",
      "evidence_id": "E02",
      "attribution": "customer",
      "explicitness": "explicit",
      "polarity": "negative",
      "current_validity": "active"
    }
  ],
  "candidate_people": [],
  "candidate_timeline": [],
  "candidate_next_actions": [],
  "stage_signals": [
    {
      "signal_type": "budget_discussed",
      "explicitness": "explicit",
      "polarity": "positive",
      "attribution": "customer",
      "current_validity": "historical",
      "evidence_id": "E01"
    },
    {
      "signal_type": "budget_unavailable",
      "explicitness": "explicit",
      "polarity": "negative",
      "attribution": "customer",
      "current_validity": "active",
      "evidence_id": "E02"
    },
    {
      "signal_type": "solution_evaluation",
      "explicitness": "explicit",
      "polarity": "positive",
      "attribution": "customer",
      "current_validity": "active",
      "evidence_id": "E03"
    }
  ],
  "ambiguities": [
    "budget: 预算金额约 60 万，但预算被冻结，金额是否有效未确认",
    "timeline: 项目推进时间未确认"
  ],
  "possible_conflicts": [
    {
      "field": "budget",
      "description": "上午表示今年预算约 60 万，下午表示预算被冻结，无法确认是否继续采购",
      "evidence_ids": [
        "E01",
        "E02"
      ]
    }
  ],
  "evidence_candidates": [
    {
      "id": "E01",
      "quote": "客户上午表示今年项目预算大约 60 万，可以继续推进",
      "field": "budget"
    },
    {
      "id": "E02",
      "quote": "客户又表示今年预算目前已经被冻结，暂时无法确认是否还能继续采购",
      "field": "budget"
    },
    {
      "id": "E03",
      "quote": "产品方案本身客户仍表示认可",
      "field": "solution_evaluation"
    }
  ]
}
```

### 最终 API Response
```json
{
  "analysis_id": "f459e857-b7e9-4ca5-a8b2-066e4166cf4a",
  "revision": 1,
  "status": "need_confirmation",
  "summary": "当前销售记录信息不足，尚无法形成可靠商机阶段判断；输入信息过于残缺，无法可靠分析，需要补充客户需求、场景或推进状态。",
  "stage": null,
  "crm_fields": {
    "customer_needs": [],
    "core_scenarios": [],
    "budget": {
      "value": null,
      "status": "conflict",
      "evidence_ids": [
        "E01",
        "E02"
      ],
      "conflicting_values": [
        "大约 60 万",
        "今年预算目前已经被冻结"
      ],
      "reason": "记录中存在互相冲突的信息，不能自动选择其中一条作为最终事实。"
    },
    "decision_maker": {
      "name": null,
      "role": null,
      "status": "unknown",
      "authority_confirmed": false,
      "evidence_ids": [],
      "reason": "当前记录未明确最终审批、拍板或购买决策权限。"
    },
    "influencers": [],
    "timeline": {
      "value": null,
      "status": "unknown",
      "evidence_ids": [],
      "conflicting_values": [],
      "reason": "本次记录未提供明确推进时间或上线计划。"
    }
  },
  "opportunity_risks": [
    {
      "type": "conflict",
      "severity": "high",
      "description": "上午表示今年预算约 60 万，下午表示预算被冻结，无法确认是否继续采购",
      "evidence_ids": [
        "E01",
        "E02"
      ]
    },
    {
      "type": "demand_invalidated",
      "severity": "high",
      "description": "客户表达项目暂停、预算不可用或延期，当前需求有效性需要确认。",
      "evidence_ids": [
        "E02"
      ]
    }
  ],
  "analysis_warnings": [
    {
      "type": "insufficient_input",
      "severity": "high",
      "description": "输入信息过于残缺，无法可靠分析。",
      "evidence_ids": []
    }
  ],
  "confirmed_next_action": null,
  "recommended_next_actions": [
    {
      "action": "优先确认项目当前是否仍计划推进，并澄清阻塞推进的关键信息",
      "owner": "销售负责人",
      "time": "待确认",
      "type": "ai_recommended",
      "reason": "当前存在预算冲突、需求暂停、预算不可用或延期等高影响风险，需先解除阻塞后再推进下一阶段。"
    }
  ],
  "unconfirmed_info": [
    {
      "value": "预算存在冲突",
      "status": "conflict",
      "evidence_ids": [
        "E01",
        "E02"
      ],
      "conflicting_values": [
        "大约 60 万",
        "今年预算目前已经被冻结"
      ],
      "reason": "记录中存在互相冲突的信息，不能自动选择其中一条作为最终事实。"
    },
    {
      "value": "决策人或决策权限未确认",
      "status": "unknown",
      "evidence_ids": [],
      "conflicting_values": [],
      "reason": "当前记录未明确最终审批、拍板或购买决策权限。"
    },
    {
      "value": "时间计划未确认",
      "status": "unknown",
      "evidence_ids": [],
      "conflicting_values": [],
      "reason": "本次记录未提供明确推进时间或上线计划。"
    },
    {
      "value": "客户已确认下一步行动未明确",
      "status": "unknown",
      "evidence_ids": [],
      "conflicting_values": [],
      "reason": "本次记录未出现客户已经确认的下一步动作、负责人或时间。"
    }
  ],
  "evidence": [
    {
      "id": "E01",
      "quote": "客户上午表示今年项目预算大约 60 万，可以继续推进",
      "start_char": 0,
      "end_char": 26,
      "field": "budget",
      "valid": true,
      "sufficient": true,
      "insufficiency_reason": null
    },
    {
      "id": "E02",
      "quote": "客户又表示今年预算目前已经被冻结，暂时无法确认是否还能继续采购",
      "start_char": 35,
      "end_char": 66,
      "field": "budget",
      "valid": true,
      "sufficient": true,
      "insufficiency_reason": null
    },
    {
      "id": "E03",
      "quote": "产品方案本身客户仍表示认可",
      "start_char": 67,
      "end_char": 80,
      "field": "solution_evaluation",
      "valid": true,
      "sufficient": true,
      "insufficiency_reason": null
    }
  ],
  "clarification": {
    "needed": true,
    "questions": [
      {
        "field": "budget",
        "question": "请确认客户当前预算状态：今年仍有约 50 万元预算，还是今年暂无预算、计划延期到明年？",
        "priority": "high",
        "reason": "该问题可直接解除预算冲突并影响 S3 判断。"
      },
      {
        "field": "stage",
        "question": "请确认该项目当前是否仍有效推进，还是已经暂停或延期到明年？",
        "priority": "high",
        "reason": "需求有效性会影响 S3 阶段判断。"
      }
    ],
    "max_questions": 3
  },
  "developer_details": {
    "stage_signals": [
      {
        "signal_type": "budget_discussed",
        "explicitness": "explicit",
        "polarity": "positive",
        "attribution": "customer",
        "current_validity": "historical",
        "evidence_id": "E01"
      },
      {
        "signal_type": "budget_unavailable",
        "explicitness": "explicit",
        "polarity": "negative",
        "attribution": "customer",
        "current_validity": "active",
        "evidence_id": "E02"
      },
      {
        "signal_type": "solution_evaluation",
        "explicitness": "explicit",
        "polarity": "positive",
        "attribution": "customer",
        "current_validity": "active",
        "evidence_id": "E03"
      }
    ],
    "valid_evidence_ids": [
      "E01",
      "E02",
      "E03"
    ],
    "sufficient_evidence_ids": [
      "E01",
      "E02",
      "E03"
    ],
    "input_summary": "客户上午表示今年项目预算大约 60 万，可以继续推进。下午再次沟通时，客户又表示今年预算目前已经被冻结，暂时无法确认是否还能继续采购。产品方案本身客户仍表示认…",
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "latency_ms": 4129
  }
}
```

## Case1-Case8 当前未解决问题池

| 能力 | 状态 | 涉及 Case | 优先级 | 是否建议本轮后修复 |
| --- | --- | --- | --- | --- |
| customer_needs 语义边界 | 待定，Case5 “客户确认需求继续推进”未进入 customer_needs | Case5 | P1 | 否，按用户要求暂缓 |
| Grounded LLM Summary / 商机概览 | 偏模板化，表达不够 CRM 专业 | Case1-Case5、UI Review | P1 | 否，本轮只测试 |
| S0 初步接触表达覆盖 | “今天和客户沟通后”未兜底为 S0，而是 unable_to_judge | Case7 | P1 | 是，后续统一修复 |
| S2 solution_evaluation 证据充分性 | RawExtraction 已抽到“产品方案认可”，Rule Engine sufficiency gate 未采纳 | Case8 | P1 | 是，后续统一修复 |

## 四个结论

1. 是否发现新的 P0：否。
2. 是否出现 Case1-Case5 已修能力的回归迹象：否。Budget value 与 Timeline value 粒度未见回归。
3. Case6-Case8 是否形成明确、值得统一修复的 P1 能力问题：是，S0 初步接触表达覆盖与 S2 solution_evaluation 证据充分性。
4. 下一步建议：A. 先修 Case6-Case8 暴露的能力问题。应修能力仅列为：S0 初步接触表达覆盖；S2 solution_evaluation 证据充分性规则与 Prompt 语义对齐。
