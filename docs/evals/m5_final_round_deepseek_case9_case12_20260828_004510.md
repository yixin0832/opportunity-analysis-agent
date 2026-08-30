# M5 最终轮真实 DeepSeek 回归测试：Case9-Case12

创建时间：2026-08-28T00:45:10
Provider：deepseek
Model：deepseek-v4-flash

说明：本轮使用真实 DeepSeek Provider，通过 FastAPI TestClient 调用 /analyze，覆盖 RawExtraction、Pydantic、Evidence Validator、Rule Engine、Repository 保存与 API Response。未记录 API Key、Authorization Header 或 Secret。本轮未修改代码。

## Case9：PARTIAL PASS

问题分类：New Capability Issue

### 原始输入
客户上个月已经讨论过 40 万预算，也评估过我们的客服自动化方案。但客户今天明确表示，由于业务调整，这个项目已经暂停，今年不再推进，最快明年再重新评估。

### 预期结果 vs 实际结果
| 字段 | 预期结果 | 实际结果 | 是否一致 | 差异说明 |
| --- | --- | --- | --- | --- |
| 客户需求 | 历史/当前可体现客服自动化方案相关需求或场景；不得丢失历史方案评估事实 | customer_needs 为空；RawExtraction 保留 historical solution_evaluation | 部分一致 | 历史方案评估通过 stage_signal 保留，但未进入 CRM 需求/场景字段；不影响阶段安全。 |
| 核心场景 | 可识别客服自动化方案，若作为场景/方案事实可接受；不得编造其他场景 | 空 | 一致 | 未编造具体场景。 |
| 预算 | 保留历史 40 万预算讨论，不应作为当前 confirmed 推进预算 | value=40 万，status=unknown，current_validity=historical | 一致 | Budget value 粒度正确，未作为当前 confirmed 预算。 |
| 决策人 | 未提及，待确认 | 待确认 | 一致 | 无决策人幻觉。 |
| 影响人 | 未提及，空 | 空 | 一致 | 无影响人幻觉。 |
| 时间计划 | 最快明年再重新评估 | 明年再重新评估，confirmed | 一致 | Timeline value 包含业务动作；“最快”限定词未保留，轻微粒度问题但未影响判断。 |
| 商机阶段 | 不能机械判 S3；当前需求暂停/不推进，应 need_confirmation 或明确风险状态 | stage=null，status=need_confirmation | 一致 | 历史 S2/S3 未被机械采纳；当前风险驱动 need_confirmation。 |
| 风险 | 应识别项目暂停/今年不再推进/延期风险 | demand_invalidated high | 一致 | 风险识别正确；evidence_ids 有重复 E03，属展示/清洁度问题。 |
| 下一步行动 | 不得推进 Demo/报价；应优先确认项目是否恢复及重新评估时间 | blocker-first 推荐 | 一致 | 未自动推荐 Demo 或报价。 |
| 未确认信息 | 预算当前有效性、决策人、时间/下一步等可待确认 | 预算、决策人、客户已确认下一步未明确 | 部分一致 | 主要缺口是 analysis_warning 错称“输入过于残缺”，而文本并不残缺。 |

### 问题定位
analysis_warnings 语义过粗：Rule Engine 中 stage is None 即生成 insufficient_input，导致被暂停/延期的有效商机文本也显示“输入信息过于残缺”。直接发生层为 Rule Engine build_analysis_warnings；根因层为 Decision/Warning 语义边界。

### RawExtraction 摘要
```json
{
  "candidate_needs": [],
  "candidate_scenarios": [],
  "candidate_budget": [
    {
      "value": "40 万",
      "evidence_id": "E01",
      "attribution": "customer",
      "explicitness": "explicit",
      "polarity": "positive",
      "current_validity": "historical"
    }
  ],
  "candidate_people": [],
  "candidate_timeline": [
    {
      "value": "明年再重新评估",
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
      "current_validity": "historical",
      "evidence_id": "E01"
    },
    {
      "signal_type": "solution_evaluation",
      "explicitness": "explicit",
      "polarity": "positive",
      "attribution": "customer",
      "current_validity": "historical",
      "evidence_id": "E02"
    },
    {
      "signal_type": "demand_invalidated",
      "explicitness": "explicit",
      "polarity": "negative",
      "attribution": "customer",
      "current_validity": "active",
      "evidence_id": "E03"
    },
    {
      "signal_type": "demand_delayed",
      "explicitness": "explicit",
      "polarity": "negative",
      "attribution": "customer",
      "current_validity": "active",
      "evidence_id": "E03"
    }
  ],
  "ambiguities": [],
  "possible_conflicts": [],
  "evidence_candidates": [
    {
      "id": "E01",
      "quote": "客户上个月已经讨论过 40 万预算",
      "field": "budget"
    },
    {
      "id": "E02",
      "quote": "也评估过我们的客服自动化方案",
      "field": "solution_evaluation"
    },
    {
      "id": "E03",
      "quote": "这个项目已经暂停，今年不再推进，最快明年再重新评估",
      "field": "demand_status"
    }
  ]
}
```

### 最终 API Response
```json
{
  "analysis_id": "45d4674a-6036-4f84-9652-0ab698edcda3",
  "revision": 1,
  "status": "need_confirmation",
  "summary": "当前销售记录信息不足，尚无法形成可靠商机阶段判断；输入信息过于残缺，无法可靠分析，需要补充客户需求、场景或推进状态。",
  "stage": null,
  "crm_fields": {
    "customer_needs": [],
    "core_scenarios": [],
    "budget": {
      "value": "40 万",
      "status": "unknown",
      "evidence_ids": [
        "E01"
      ],
      "conflicting_values": [],
      "reason": "当前原文依据不足，无法确认该字段。"
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
      "value": "明年再重新评估",
      "status": "confirmed",
      "evidence_ids": [
        "E03"
      ],
      "conflicting_values": [],
      "reason": "该信息来自客户或第三方明确表达，并且原文依据有效。"
    }
  },
  "opportunity_risks": [
    {
      "type": "demand_invalidated",
      "severity": "high",
      "description": "客户表达项目暂停、预算不可用或延期，当前需求有效性需要确认。",
      "evidence_ids": [
        "E03",
        "E03"
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
      "quote": "客户上个月已经讨论过 40 万预算",
      "start_char": 0,
      "end_char": 17,
      "field": "budget",
      "valid": true,
      "sufficient": true,
      "insufficiency_reason": null
    },
    {
      "id": "E02",
      "quote": "也评估过我们的客服自动化方案",
      "start_char": 18,
      "end_char": 32,
      "field": "solution_evaluation",
      "valid": true,
      "sufficient": true,
      "insufficiency_reason": null
    },
    {
      "id": "E03",
      "quote": "这个项目已经暂停，今年不再推进，最快明年再重新评估",
      "start_char": 50,
      "end_char": 75,
      "field": "demand_status",
      "valid": true,
      "sufficient": true,
      "insufficiency_reason": null
    }
  ],
  "clarification": {
    "needed": true,
    "questions": [
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
        "signal_type": "solution_evaluation",
        "explicitness": "explicit",
        "polarity": "positive",
        "attribution": "customer",
        "current_validity": "historical",
        "evidence_id": "E02"
      },
      {
        "signal_type": "demand_invalidated",
        "explicitness": "explicit",
        "polarity": "negative",
        "attribution": "customer",
        "current_validity": "active",
        "evidence_id": "E03"
      },
      {
        "signal_type": "demand_delayed",
        "explicitness": "explicit",
        "polarity": "negative",
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
    "input_summary": "客户上个月已经讨论过 40 万预算，也评估过我们的客服自动化方案。但客户今天明确表示，由于业务调整，这个项目已经暂停，今年不再推进，最快明年再重新评估。",
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "latency_ms": 3096
  }
}
```

## Case10：PASS

问题分类：Pass

### 原始输入
客户确认希望进一步了解方案，并同意安排一次技术交流。双方约定由我们销售团队后续组织，但客户没有确定具体参与人，也没有确定交流时间。

### 预期结果 vs 实际结果
| 字段 | 预期结果 | 实际结果 | 是否一致 | 差异说明 |
| --- | --- | --- | --- | --- |
| 客户需求 | 可识别进一步了解方案意向；无具体业务痛点时不得编造 | 空 | 一致 | 未把了解方案编造成具体痛点。 |
| 核心场景 | 无具体业务场景，待确认或空 | 空 | 一致 | 未编造场景。 |
| 预算 | 未提及预算，待确认 | 待确认 | 一致 | 无预算幻觉。 |
| 决策人 | 未提及，待确认 | 待确认 | 一致 | 无决策人幻觉。 |
| 影响人 | 客户具体参与人未确定，不得编造影响人 | 空 | 一致 | 无影响人误判。 |
| 时间计划 | 交流时间未确定，应待确认，不得编造日期 | 待确认 | 一致 | 无时间幻觉。 |
| 商机阶段 | S2 方案验证，技术交流已同意 | S2 · 方案验证 | 一致 | technical_exchange_agreed 被采纳。 |
| 风险 | 无明确商机风险；缺失项进入未确认信息 | 无风险 | 一致 | Unknown 未升级为 Risk。 |
| 下一步行动 | 客户已确认：安排技术交流；负责人我们销售团队；时间待确认 | 安排技术交流 / 我们销售团队 / 待确认 | 一致 | owner/time 边界正确。 |
| 未确认信息 | 客户参与人、交流时间、预算、决策人等待确认 | 预算、决策人、时间计划 | 部分一致 | 客户参与人作为 next action 参与方未进入最终 unconfirmed_info；题目 CRM 字段不强制客户参与人，非阻塞。 |

### RawExtraction 摘要
```json
{
  "candidate_needs": [],
  "candidate_scenarios": [],
  "candidate_budget": [],
  "candidate_people": [],
  "candidate_timeline": [],
  "candidate_next_actions": [
    {
      "action": "安排技术交流",
      "owner": "我们销售团队",
      "time": null,
      "evidence_id": "E01",
      "attribution": "customer",
      "explicitness": "explicit"
    }
  ],
  "stage_signals": [
    {
      "signal_type": "technical_exchange_agreed",
      "explicitness": "explicit",
      "polarity": "positive",
      "attribution": "customer",
      "current_validity": "active",
      "evidence_id": "E01"
    }
  ],
  "ambiguities": [
    "technical_exchange.participants: 客户未确定具体参与人",
    "technical_exchange.time: 交流时间未确定"
  ],
  "possible_conflicts": [],
  "evidence_candidates": [
    {
      "id": "E01",
      "quote": "客户确认希望进一步了解方案，并同意安排一次技术交流。双方约定由我们销售团队后续组织，但客户没有确定具体参与人，也没有确定交流时间。",
      "field": "next_action"
    }
  ]
}
```

### 最终 API Response
```json
{
  "analysis_id": "8dfbcab4-a1d1-4fef-89cc-bac7dea40cb2",
  "revision": 1,
  "status": "complete",
  "summary": "当前商机阶段为 S2（方案验证）；核心需求与场景：未确认；已确认推进动作：安排技术交流（待确认）；最重要未确认信息：预算未确认。",
  "stage": {
    "code": "S2",
    "label": "方案验证",
    "evidence_status": "sufficient",
    "reason": "客户明确同意演示、试用、技术交流或方案评估。",
    "evidence_ids": [
      "E01"
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
      "value": null,
      "status": "unknown",
      "evidence_ids": [],
      "conflicting_values": [],
      "reason": "本次记录未提供明确推进时间或上线计划。"
    }
  },
  "opportunity_risks": [],
  "analysis_warnings": [],
  "confirmed_next_action": {
    "action": "安排技术交流",
    "owner": "我们销售团队",
    "time": "待确认",
    "type": "customer_confirmed",
    "evidence_ids": [
      "E01"
    ]
  },
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
    }
  ],
  "evidence": [
    {
      "id": "E01",
      "quote": "客户确认希望进一步了解方案，并同意安排一次技术交流。双方约定由我们销售团队后续组织，但客户没有确定具体参与人，也没有确定交流时间。",
      "start_char": 0,
      "end_char": 65,
      "field": "next_action",
      "valid": true,
      "sufficient": true,
      "insufficiency_reason": null
    }
  ],
  "clarification": null,
  "developer_details": {
    "stage_signals": [
      {
        "signal_type": "technical_exchange_agreed",
        "explicitness": "explicit",
        "polarity": "positive",
        "attribution": "customer",
        "current_validity": "active",
        "evidence_id": "E01"
      }
    ],
    "valid_evidence_ids": [
      "E01"
    ],
    "sufficient_evidence_ids": [
      "E01"
    ],
    "input_summary": "客户确认希望进一步了解方案，并同意安排一次技术交流。双方约定由我们销售团队后续组织，但客户没有确定具体参与人，也没有确定交流时间。",
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "latency_ms": 1872
  }
}
```

## Case11：PARTIAL PASS

问题分类：New Capability Issue

### 原始输入
客户确认项目继续推进，也认可当前方案。客户表示具体上线时间还没有最终确定，后面再根据内部资源安排确认日期。目前没有说项目延期或暂停。

### 预期结果 vs 实际结果
| 字段 | 预期结果 | 实际结果 | 是否一致 | 差异说明 |
| --- | --- | --- | --- | --- |
| 客户需求 | 项目继续推进/方案认可不是具体需求，空或待确认可接受 | 空 | 一致 | 符合当前 Design Decision，不编造需求。 |
| 核心场景 | 无具体场景，空 | 空 | 一致 | 未编造场景。 |
| 预算 | 未提及预算，待确认 | 待确认 | 一致 | 无预算幻觉。 |
| 决策人 | 未提及，待确认 | 待确认 | 一致 | 无人物幻觉。 |
| 影响人 | 未提及，空 | 空 | 一致 | 无影响人误判。 |
| 时间计划 | 具体上线时间未确定，待确认或保留模糊表达，不得延期 | 待确认 | 一致 | 未产生 demand_delayed，也未确认为延期。 |
| 商机阶段 | 没有 S2/S3/S4 明确动作时按实际已满足条件判断 | stage=null，status=unable_to_judge | 部分一致 | 未自动升级，但“输入过于残缺”解释不准确；文本有明确继续推进和非延期事实。 |
| 风险 | 不得产生 demand_delayed 或 demand_invalidated | 无风险 | 一致 | Risk 无回归。 |
| 下一步行动 | 不得生成客户已确认下一步；AI建议可围绕确认上线时间 | 无 confirmed_next_action；无推荐 | 部分一致 | 无错误确认行动；因 unable_to_judge 当前规则不推荐下一步。 |
| 未确认信息 | 预算、决策人、时间计划、下一步等待确认 | 预算、决策人、时间计划、客户已确认下一步未明确 | 一致 | 关键未确认项完整。 |

### 问题定位
analysis_warnings/decision explanation 语义过粗：文本不是严重残缺，而是缺少可采纳阶段动作或具体需求。直接发生层为 Rule Engine build_analysis_warnings 与 determine_status 的 stage=None 分支；根因层为 no-stage 原因分类不足。

### RawExtraction 摘要
```json
{
  "candidate_needs": [],
  "candidate_scenarios": [],
  "candidate_budget": [],
  "candidate_people": [],
  "candidate_timeline": [],
  "candidate_next_actions": [],
  "stage_signals": [],
  "ambiguities": [
    "timeline: 具体上线时间未确认"
  ],
  "possible_conflicts": [],
  "evidence_candidates": [
    {
      "id": "E01",
      "quote": "客户确认项目继续推进，也认可当前方案。",
      "field": "general"
    },
    {
      "id": "E02",
      "quote": "客户表示具体上线时间还没有最终确定，后面再根据内部资源安排确认日期。",
      "field": "timeline"
    },
    {
      "id": "E03",
      "quote": "目前没有说项目延期或暂停。",
      "field": "general"
    }
  ]
}
```

### 最终 API Response
```json
{
  "analysis_id": "7f4b1fed-e660-4a30-ad00-e1d7c5ed131f",
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
      "quote": "客户确认项目继续推进，也认可当前方案。",
      "start_char": 0,
      "end_char": 19,
      "field": "general",
      "valid": true,
      "sufficient": true,
      "insufficiency_reason": null
    },
    {
      "id": "E02",
      "quote": "客户表示具体上线时间还没有最终确定，后面再根据内部资源安排确认日期。",
      "start_char": 19,
      "end_char": 53,
      "field": "timeline",
      "valid": true,
      "sufficient": true,
      "insufficiency_reason": null
    },
    {
      "id": "E03",
      "quote": "目前没有说项目延期或暂停。",
      "start_char": 53,
      "end_char": 66,
      "field": "general",
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
      "E01",
      "E02",
      "E03"
    ],
    "sufficient_evidence_ids": [
      "E01",
      "E02",
      "E03"
    ],
    "input_summary": "客户确认项目继续推进，也认可当前方案。客户表示具体上线时间还没有最终确定，后面再根据内部资源安排确认日期。目前没有说项目延期或暂停。",
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "latency_ms": 1363
  }
}
```

## Case12：PASS

问题分类：Pass / S0 Rule Boundary Accepted

### 原始输入
今天客户交流情况不错，后面再看。

### 预期结果 vs 实际结果
| 字段 | 预期结果 | 实际结果 | 是否一致 | 差异说明 |
| --- | --- | --- | --- | --- |
| 客户需求 | 无明确需求，不得补全 | 空 | 一致 | 无需求幻觉。 |
| 核心场景 | 无明确场景，不得补全 | 空 | 一致 | 无场景幻觉。 |
| 预算 | 未提及，待确认 | 待确认 | 一致 | 无预算幻觉。 |
| 决策人 | 未提及，待确认 | 待确认 | 一致 | 无决策人幻觉。 |
| 影响人 | 未提及，空 | 空 | 一致 | 无影响人误判。 |
| 时间计划 | 后面再看不是明确时间计划，待确认 | 待确认 | 一致 | 未把“后面再看”确认为时间计划。 |
| 商机阶段 | 信息不足或最多 S0，不能进入更高阶段 | S0 · 线索 | 一致 | “客户交流”被视为真实接触事实，符合 S0 兜底；未进入更高阶段。 |
| 风险 | 无明确商机风险；输入质量问题不进 OpportunityRisk | 无风险 | 一致 | Unknown 未升级为 Risk。 |
| 下一步行动 | 不得生成客户已确认下一步，不得默认 Demo | 无 confirmed_next_action；AI建议继续了解客户背景 | 一致 | 未默认 Demo。 |
| 未确认信息 | 关键字段待确认 | 预算、决策人、时间计划、客户已确认下一步未明确 | 一致 | 待确认项完整。 |

### RawExtraction 摘要
```json
{
  "candidate_needs": [],
  "candidate_scenarios": [],
  "candidate_budget": [],
  "candidate_people": [],
  "candidate_timeline": [],
  "candidate_next_actions": [],
  "stage_signals": [],
  "ambiguities": [],
  "possible_conflicts": [],
  "evidence_candidates": []
}
```

### 最终 API Response
```json
{
  "analysis_id": "801ac1e8-2f5b-469f-83c4-e2cadbbb4a2b",
  "revision": 1,
  "status": "complete",
  "summary": "当前商机阶段为 S0（线索）；核心需求与场景：未确认；已确认推进动作：未明确；最重要未确认信息：预算未确认。",
  "stage": {
    "code": "S0",
    "label": "线索",
    "evidence_status": "sufficient",
    "reason": "只有初步接触，无明确需求。",
    "evidence_ids": []
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
      "value": null,
      "status": "unknown",
      "evidence_ids": [],
      "conflicting_values": [],
      "reason": "本次记录未提供明确推进时间或上线计划。"
    }
  },
  "opportunity_risks": [],
  "analysis_warnings": [],
  "confirmed_next_action": null,
  "recommended_next_actions": [
    {
      "action": "继续了解客户背景，确认是否存在明确业务问题或改进目标",
      "owner": "销售负责人",
      "time": "待确认",
      "type": "ai_recommended",
      "reason": "当前只有初步接触，尚未形成明确需求，不宜直接推进演示、报价或采购流程。"
    }
  ],
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
  "evidence": [],
  "clarification": null,
  "developer_details": {
    "stage_signals": [],
    "valid_evidence_ids": [],
    "sufficient_evidence_ids": [],
    "input_summary": "今天客户交流情况不错，后面再看。",
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "latency_ms": 1110
  }
}
```

## Case1-Case12 Open Issues

| 能力 | 分类 | 涉及 Case | 优先级 | 状态 |
| --- | --- | --- | --- | --- |
| Analysis Warning / no-stage explanation semantics | New Capability Issue | Case9、Case11 | P1 | Open |
| Grounded LLM Summary / 商机概览 | Product Experience | UI Review、Case1-Case5 | P2 | Open，不阻塞内容正确性 |

## Design Decisions

| Decision ID | 标题 | 状态 |
| --- | --- | --- |
| Decision-001 | Case8：客户认可方案不等于明确进入方案验证 | 保持 |
| Decision-002 | Case5：“需求继续推进”暂不进入 customer_needs | 保持 |

## Content Freeze Assessment

| 检查项 | 结果 |
| --- | --- |
| Prompt 已稳定 | PASS，本轮未发现 Prompt 回归 |
| Rule Engine 已稳定 | PARTIAL，发现 stage=null 时 analysis_warning 语义过粗 |
| Validator 已稳定 | PASS，Evidence 定位和 sufficiency 未见回归 |
| Schema 已稳定 | PASS，本轮未发现 Schema 问题 |
| Golden Cases Case1-Case12 全部通过 | PARTIAL，Case9/Case11 有 P1 解释问题 |
| Open Issues 不影响内容正确性 | FAIL，Case9/Case11 的 insufficient_input 文案会误导业务用户 |

结论：暂不建议进入 Content Freeze v1.0。