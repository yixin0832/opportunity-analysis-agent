"use client";

import { useMemo, useState } from "react";
import { CheckCircle2, Circle, Clock, FileText, History, MessageSquareText } from "lucide-react";
import { Badge, Button, Card, Input, SectionTitle, cn } from "./ui";
import { decisionStatusText, formatDateTime, fullDateTime, severityText, stageLabels, stageOrder } from "@/lib/cn";
import type { AnalysisSessionDetail, Evidence, FieldStatus, ValidatedField, ValidatedOpportunity } from "@/lib/types";

type ClarifyPayload = { question_id?: string | null; answer: string }[];
type CrmFieldKey = "customer_needs" | "core_scenarios" | "budget" | "decision_maker" | "influencers" | "timeline";
type CrmDisplayItem = {
  label: string;
  fieldKey: CrmFieldKey;
  value: string;
  status: FieldStatus;
  evidenceIds: string[];
  reason?: string | null;
};
type SourceSection = { title: string | null; lines: string[]; tone: "original" | "supplement" };

function evidenceMap(evidence: Evidence[]) {
  return new Map(evidence.map((item) => [item.id, item]));
}

function valueText(value: unknown): string {
  if (value === null || value === undefined || value === "") return "待确认";
  if (Array.isArray(value)) return value.length ? value.join("、") : "待确认";
  return String(value);
}

function sourceFieldLabel(raw: string): string {
  const normalized = raw.trim();
  const map: Record<string, string> = {
    customer_needs: "客户需求",
    core_scenarios: "核心场景",
    budget: "预算",
    decision_maker: "决策人",
    influencers: "影响人",
    timeline: "时间计划",
    stage: "商机阶段",
    source_text: "销售拜访记录",
    其他补充信息: "补充信息",
    补充信息: "补充信息",
  };
  return map[normalized] ?? normalized;
}

function cleanSourceLine(line: string, tone: SourceSection["tone"]): string {
  const text = line.trim();
  if (!text) return "";
  if (tone === "original") return text;
  const correctionPrefix = "修正识别：";
  const normalized = text.startsWith(correctionPrefix) ? text.slice(correctionPrefix.length) : text;
  const separatorIndex = normalized.indexOf("：");
  if (separatorIndex === -1) return normalized;
  const rawLabel = normalized.slice(0, separatorIndex).trim();
  const labelWithoutAction = rawLabel.replace(/(修正|确认)+$/u, "");
  const label = sourceFieldLabel(labelWithoutAction || rawLabel);
  const value = normalized.slice(separatorIndex + 1).trim();
  if (!value) return "";
  return `${label}确认：${value}`;
}

function parseSourceText(sourceText: string): SourceSection[] {
  const sections: SourceSection[] = [];
  let current: SourceSection = { title: null, lines: [], tone: "original" };
  function pushCurrent() {
    const lines = current.lines.map((line) => line.trim()).filter(Boolean);
    if (lines.length) sections.push({ ...current, lines });
  }
  for (const rawLine of sourceText.split("\n")) {
    const line = rawLine.trim();
    const marker = line.match(/^【(.+)】$/);
    if (marker) {
      pushCurrent();
      const label = marker[1];
      const revision = label.match(/Revision\s*(\d+)/i)?.[1] ?? label.match(/第\s*(\d+)\s*次分析/)?.[1];
      const prefix = revision ? `第 ${revision} 次分析` : "后续分析";
      if (label.includes("原始销售拜访记录")) {
        current = { title: "原始销售拜访记录", lines: [], tone: "original" };
      } else if (label.includes("修正识别")) {
        current = { title: `${prefix}补充`, lines: [], tone: "supplement" };
      } else if (label.includes("补充确认") || label.includes("后续补充")) {
        current = { title: `${prefix}补充`, lines: [], tone: "supplement" };
      } else {
        current = { title: null, lines: [], tone: "original" };
      }
      continue;
    }
    if (line.startsWith("以下内容是用户对已识别信息的明确修正")) continue;
    current.lines.push(cleanSourceLine(line, current.tone));
  }
  pushCurrent();
  return sections.length ? sections : [{ title: null, lines: [sourceText.trim()], tone: "original" }];
}

function badgeTone(status: string) {
  if (status === "confirmed" || status === "complete") return "green" as const;
  if (status === "conflict" || status === "need_confirmation") return "amber" as const;
  if (status === "unable_to_judge") return "red" as const;
  return "slate" as const;
}

function simpleFieldStatusText(status: FieldStatus): string {
  if (status === "confirmed") return "已确认";
  if (status === "conflict") return "存在冲突";
  return "待确认";
}

function fallbackFieldReason(fieldKey: CrmFieldKey, status: FieldStatus, value: string): string {
  if (status === "confirmed") return "当前字段已确认，但暂无可展示的引用原文。";
  if (status === "conflict") return "当前字段存在互斥信息，需要补充事实后确认。";
  if (value !== "待确认") {
    const mentionedMap: Record<CrmFieldKey, string> = {
      customer_needs: "当前记录提到了客户需求相关信息，但还不足以确认为当前有效需求。",
      core_scenarios: "当前记录提到了场景相关信息，但还不足以确认为当前有效落地场景。",
      budget: "当前记录提到了预算相关信息，但预算的当前有效性仍需确认。",
      decision_maker: "当前记录提到了相关人物，但其最终决策权限仍需确认。",
      influencers: "当前记录提到了相关参与人，但其影响购买或方案判断的角色仍需确认。",
      timeline: "当前记录提到了时间相关信息，但其是否属于当前有效推进计划仍需确认。",
    };
    return mentionedMap[fieldKey];
  }
  const map: Record<CrmFieldKey, string> = {
    customer_needs: "当前记录未形成可确认的客户业务问题、需求表达或改进目标。",
    core_scenarios: "当前记录未明确该商机对应的落地场景、使用场景或业务流程。",
    budget: "本次记录未提供预算金额、预算范围或明确预算安排。",
    decision_maker: "当前记录未明确最终审批、拍板或购买决策权限。",
    influencers: "当前记录未明确存在能实质影响方案或购买判断的参与人。",
    timeline: "本次记录未提供明确推进时间、上线计划或评估节点。",
  };
  return map[fieldKey];
}

function isNextActionRisk(description: string): boolean {
  return description.includes("下一步行动") || description.includes("推进动作") || description.includes("负责人存在多个不一致");
}

function nextActionFieldStatus(result: ValidatedOpportunity, field: "action" | "owner" | "time", value?: string | null): FieldStatus {
  const riskText = result.opportunity_risks.filter((risk) => risk.type === "conflict" && isNextActionRisk(risk.description)).map((risk) => risk.description).join("；");
  if (
    (field === "action" && riskText.includes("下一步行动存在多个不一致")) ||
    (field === "owner" && (riskText.includes("负责人") || riskText.includes("责任人"))) ||
    (field === "time" && riskText.includes("时间"))
  ) {
    return "conflict";
  }
  return value && value !== "待确认" ? "confirmed" : "unknown";
}

function evidenceQuotes(ids: string[], evidence: Evidence[]): string[] {
  const map = evidenceMap(evidence);
  const seenIds = new Set<string>();
  const seenQuotes = new Set<string>();
  return ids.flatMap((id) => {
    if (seenIds.has(id)) return [];
    seenIds.add(id);
    const quote = map.get(id)?.quote?.trim();
    if (!quote || seenQuotes.has(quote)) return [];
    seenQuotes.add(quote);
    return [quote];
  });
}

function riskTitle(type: string): string {
  const map: Record<string, string> = {
    conflict: "关键信息冲突风险",
    demand_invalidated: "项目暂停与需求有效性风险",
    budget_unavailable: "预算不可用风险",
    demand_delayed: "项目延期风险",
    unknown_decision_authority: "决策权限未确认风险",
    missing_budget: "预算信息缺失风险",
    unclear_timeline: "时间计划不明确风险",
    unknown_procurement_process: "采购流程未确认风险",
  };
  return map[type] ?? "商机推进风险";
}

function fieldItemFromField(label: string, fieldKey: CrmFieldKey, field: ValidatedField<string>): CrmDisplayItem {
  const hasConflict = field.status === "conflict";
  return {
    label,
    fieldKey,
    value: hasConflict && field.conflicting_values?.length ? field.conflicting_values.map(valueText).join("；") : valueText(field.value),
    status: field.status,
    evidenceIds: field.evidence_ids,
    reason: field.reason,
  };
}

function buildCrmDisplayItems(result: ValidatedOpportunity): CrmDisplayItem[] {
  const decision = result.crm_fields.decision_maker;
  const items: CrmDisplayItem[] = [];
  const needs = result.crm_fields.customer_needs.length ? result.crm_fields.customer_needs : [{ value: null, status: "unknown" as FieldStatus, evidence_ids: [] }];
  const scenarios = result.crm_fields.core_scenarios.length ? result.crm_fields.core_scenarios : [{ value: null, status: "unknown" as FieldStatus, evidence_ids: [] }];
  items.push(...needs.map((field, index) => fieldItemFromField(needs.length > 1 ? `客户需求 ${index + 1}` : "客户需求", "customer_needs", field)));
  items.push(...scenarios.map((field, index) => fieldItemFromField(scenarios.length > 1 ? `核心场景 ${index + 1}` : "核心场景", "core_scenarios", field)));
  items.push(fieldItemFromField("预算", "budget", result.crm_fields.budget));
  items.push({
    label: "决策人",
    fieldKey: "decision_maker",
    value: `${decision.name ? `${decision.name}${decision.role ? ` · ${decision.role}` : ""}` : "待确认"}${decision.name && !decision.authority_confirmed ? " · 权限待确认" : ""}`,
    status: decision.status,
    evidenceIds: decision.evidence_ids,
    reason: decision.reason,
  });
  if (result.crm_fields.influencers.length) {
    items.push(...result.crm_fields.influencers.map((person, index) => ({
      label: result.crm_fields.influencers.length > 1 ? `影响人 ${index + 1}` : "影响人",
      fieldKey: "influencers" as const,
      value: `${person.name ?? "待确认"}${person.role ? ` · ${person.role}` : ""}`,
      status: person.status,
      evidenceIds: person.evidence_ids,
      reason: person.reason,
    })));
  } else {
    items.push({ label: "影响人", fieldKey: "influencers", value: "待确认", status: "unknown", evidenceIds: [], reason: "当前记录未明确存在能实质影响方案或购买判断的参与人。" });
  }
  items.push(fieldItemFromField("时间计划", "timeline", result.crm_fields.timeline));
  return items;
}

function nextActionCounts(result: ValidatedOpportunity): { confirmed: number; pending: number } {
  const action = result.confirmed_next_action;
  if (!action) return { confirmed: 0, pending: 1 };
  const values = [action.action, action.owner, action.time];
  const confirmed = values.filter((value) => value && value !== "待确认").length;
  return { confirmed, pending: values.length - confirmed };
}

const stageDescriptions = {
  S0: "初步接触，尚未形成明确需求",
  S1: "已识别业务问题或使用场景",
  S2: "客户同意演示、试用或方案评估",
  S3: "已进入预算、报价或采购评估",
  S4: "进入内部审批或供应商决策",
  S5: "合同或正式订单已确认",
} as const;

function EvidenceDisclosure({ ids, evidence, reason, status }: { ids: string[]; evidence: Evidence[]; reason?: string | null; status?: FieldStatus }) {
  const [open, setOpen] = useState(false);
  const quotes = useMemo(() => evidenceQuotes(ids, evidence), [evidence, ids]);
  const showQuotes = status ? status === "confirmed" && quotes.length > 0 : quotes.length > 0;
  const showReason = status ? status !== "confirmed" && Boolean(reason) : Boolean(reason);
  if (!showQuotes && !showReason) return null;
  return (
    <div className="mt-3">
      <button type="button" onClick={() => setOpen((value) => !value)} className="text-[13px] font-medium text-blue-700 transition-colors hover:text-blue-900">
        {open ? "收起说明" : "查看说明"}
      </button>
      {open ? (
        <div className="mt-2 space-y-3 text-sm leading-6 text-slate-700">
          {showQuotes ? (
            <div>
              <p className="mb-1 text-[13px] font-medium text-slate-500">引用原文</p>
              <div className="space-y-2 border-l-2 border-slate-300 pl-3">
                {quotes.map((quote, index) => (
                  <p key={`${quote}-${index}`} className="text-slate-700">“{quote}”</p>
                ))}
              </div>
            </div>
          ) : null}
          {showReason ? (
            <div>
              <p className="mb-1 text-[13px] font-medium text-slate-500">判断说明</p>
              <p className="border-l-2 border-slate-300 pl-3 text-slate-700">{reason}</p>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function FieldExplainability({
  open,
  onToggle,
  status,
  fieldKey,
  value,
  quotes,
  reason,
}: {
  open: boolean;
  onToggle: () => void;
  status: FieldStatus;
  fieldKey: CrmFieldKey;
  value: string;
  quotes: string[];
  reason?: string | null;
}) {
  const normalizedReason = reason?.trim();
  const shouldShowQuotes = quotes.length > 0 && (status === "confirmed" || Boolean(normalizedReason));
  const shouldShowReason = Boolean(normalizedReason) || !shouldShowQuotes;
  const reasonText = normalizedReason || fallbackFieldReason(fieldKey, status, value);
  return (
    <div className="mt-auto border-t border-slate-100 pt-3">
      <div className="flex flex-wrap items-center gap-2 text-[13px] font-medium">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          className="text-blue-700 transition-colors hover:text-blue-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
        >
          {open ? "收起说明" : "查看说明"}
        </button>
      </div>
      {open ? (
        <div className="mt-3 space-y-3 text-sm leading-6 text-slate-700">
          {shouldShowQuotes ? (
            <div>
              <p className="mb-1 text-[13px] font-medium text-slate-500">引用原文</p>
              <div className="space-y-2 border-l-2 border-slate-300 pl-3">
                {quotes.map((quote, index) => (
                  <p key={`${quote}-${index}`} className="text-slate-700">“{quote}”</p>
                ))}
              </div>
            </div>
          ) : null}
          {shouldShowReason ? (
            <div>
              <p className="mb-1 text-[13px] font-medium text-slate-500">判断说明</p>
              <p className="border-l-2 border-slate-300 pl-3 text-slate-700">{reasonText}</p>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function StageStepper({ result }: { result: ValidatedOpportunity }) {
  const crmItems = buildCrmDisplayItems(result);
  const nextActionStats = nextActionCounts(result);
  const confirmedCount = crmItems.filter((item) => item.status === "confirmed").length + nextActionStats.confirmed;
  const pendingCount = crmItems.filter((item) => item.status !== "confirmed").length + nextActionStats.pending;
  const riskCount = result.opportunity_risks.length;
  const warning = result.analysis_warnings[0];
  const effectiveStatus = pendingCount || riskCount ? "need_confirmation" : result.status;
  if (!result.stage?.code) {
    return (
      <Card>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <SectionTitle title="商机阶段" />
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={pendingCount ? "amber" : "slate"}>{pendingCount} 项待确认</Badge>
            <Badge tone={riskCount ? "amber" : "slate"}>{riskCount} 项风险</Badge>
            <Badge tone={badgeTone(effectiveStatus)}>{decisionStatusText(effectiveStatus)}</Badge>
          </div>
        </div>
        <div className="rounded-md border border-slate-200 bg-slate-50 p-4">
          <p className="text-[22px] font-semibold leading-8 text-slate-950">暂未确认当前阶段</p>
          <p className="mt-1 text-[15px] leading-7 text-slate-700">{warning?.description ?? "当前记录不足以确认销售阶段。"}</p>
          <p className="mt-1 text-sm leading-6 text-slate-500">请补充客户需求、推进状态、冲突信息或关键上下文后再更新商机分析。</p>
        </div>
        {warning?.evidence_ids?.length ? (
          <div className="mt-3">
            <EvidenceDisclosure ids={warning.evidence_ids} evidence={result.evidence} reason={warning.description} />
          </div>
        ) : null}
      </Card>
    );
  }
  const currentIndex = stageOrder.indexOf(result.stage.code);
  return (
    <Card>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <SectionTitle title="商机阶段" />
          <h1 className="mt-1 text-[26px] font-semibold leading-9 text-slate-950">
            {result.stage.code} · {stageLabels[result.stage.code]}
          </h1>
          <p className="mt-1 text-sm leading-6 text-slate-500">{stageDescriptions[result.stage.code]}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="green">{confirmedCount} 项已确认</Badge>
          <Badge tone={pendingCount ? "amber" : "slate"}>{pendingCount} 项待确认</Badge>
          <Badge tone={riskCount ? "amber" : "slate"}>{riskCount} 项风险</Badge>
          <Badge tone={badgeTone(effectiveStatus)}>{decisionStatusText(effectiveStatus)}</Badge>
        </div>
      </div>
      <div className="grid gap-2 md:grid-cols-6">
        {stageOrder.map((stage, index) => {
          const active = stage === result.stage?.code;
          const passed = index < currentIndex;
          return (
            <div key={stage} className={cn("rounded-md border p-3", active ? "border-blue-300 bg-blue-50" : passed ? "border-slate-200 bg-slate-50" : "border-slate-200 bg-white")}>
              <div className={cn("text-sm font-semibold", active ? "text-blue-800" : passed ? "text-slate-600" : "text-slate-400")}>{stage}</div>
              <div className={cn("mt-1 text-xs", active ? "text-blue-700" : "text-slate-500")}>{stageLabels[stage]}</div>
            </div>
          );
        })}
      </div>
      <EvidenceDisclosure ids={result.stage.evidence_ids} evidence={result.evidence} reason={result.stage.reason} />
    </Card>
  );
}

function FieldItem({
  label,
  fieldKey,
  value,
  status,
  evidenceIds,
  evidence,
  reason,
}: {
  label: string;
  fieldKey: CrmFieldKey;
  value: string;
  status: FieldStatus;
  evidenceIds: string[];
  evidence: Evidence[];
  reason?: string | null;
}) {
  const [explainOpen, setExplainOpen] = useState(false);
  const quotes = useMemo(() => evidenceQuotes(evidenceIds, evidence), [evidence, evidenceIds]);
  return (
    <div className={cn("flex rounded-lg border border-slate-200 bg-white p-4 transition-colors hover:border-slate-300", explainOpen ? "h-auto flex-col" : "h-[148px] flex-col")}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[14px] font-semibold leading-5 text-slate-700">{label}</p>
          <p className="mt-1 line-clamp-2 text-[16px] font-medium leading-7 text-slate-950">{value}</p>
        </div>
        <div className="flex-none">
          <Badge tone={badgeTone(status)}>{simpleFieldStatusText(status)}</Badge>
        </div>
      </div>
      <FieldExplainability
        open={explainOpen}
        onToggle={() => setExplainOpen((value) => !value)}
        status={status}
        fieldKey={fieldKey}
        value={value}
        quotes={quotes}
        reason={reason}
      />
    </div>
  );
}

function Risks({ result }: { result: ValidatedOpportunity }) {
  const risks = result.opportunity_risks;
  const unableToJudge = result.status === "unable_to_judge";
  return (
    <Card>
      <SectionTitle title="风险分析" />
      {risks.length ? (
        <div className="space-y-3">
          {risks.map((risk, index) => (
            <div key={`${risk.description}-${index}`} className="rounded-md border border-slate-200 bg-white p-4 shadow-sm shadow-slate-200/40">
              <div className="flex flex-wrap items-center justify-between gap-2 border-l-2 border-amber-300 pl-3">
                <p className="text-[15px] font-semibold leading-6 text-slate-800">{riskTitle(risk.type)}</p>
                <Badge tone={risk.severity === "high" ? "red" : "amber"}>{severityText(risk.severity)}</Badge>
              </div>
              <div className="mt-3">
                <p className="text-[14px] font-semibold leading-5 text-slate-700">风险原因</p>
                <p className="mt-1 text-[15px] leading-7 text-slate-900">{risk.description}</p>
              </div>
              <EvidenceDisclosure ids={risk.evidence_ids} evidence={result.evidence} />
            </div>
          ))}
        </div>
      ) : unableToJudge ? (
        <p className="text-sm leading-6 text-slate-600">当前信息不足，暂时无法形成可靠商机风险判断。</p>
      ) : (
        <div className="rounded-md border border-slate-200 bg-slate-50 p-4">
          <p className="font-medium text-slate-950">暂未发现明确风险</p>
          <p className="mt-1 text-sm leading-6 text-slate-600">当前记录中没有发现会直接阻碍商机推进的事实。</p>
        </div>
      )}
    </Card>
  );
}

function NextActions({ result }: { result: ValidatedOpportunity }) {
  const confirmed = result.confirmed_next_action;
  const hasNextActionConflict = result.opportunity_risks.some((risk) => risk.type === "conflict" && isNextActionRisk(risk.description));
  const actionStatus = nextActionFieldStatus(result, "action", confirmed?.action);
  const ownerStatus = nextActionFieldStatus(result, "owner", confirmed?.owner);
  const timeStatus = nextActionFieldStatus(result, "time", confirmed?.time);
  const pendingOnly = !confirmed;
  const cardTone = pendingOnly || hasNextActionConflict ? "border-amber-200 bg-amber-50/60" : "border-emerald-200 bg-emerald-50";
  const titleTone = pendingOnly || hasNextActionConflict ? "text-amber-800" : "text-emerald-800";
  const title = pendingOnly ? "下一步行动待确认" : hasNextActionConflict ? "客户已确认的下一步存在待确认信息" : "客户已确认的下一步";
  return (
    <Card>
      <SectionTitle title="下一步行动" />
      <div className={cn("rounded-md border p-4", cardTone)}>
        <div className={cn("mb-2 flex items-center gap-2 text-sm font-semibold", titleTone)}>
          <CheckCircle2 className="h-4 w-4" /> {title}
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <InfoBlock label="行动" value={confirmed?.action || "待确认"} status={pendingOnly ? "unknown" : actionStatus} />
          <InfoBlock label="建议负责人" value={confirmed?.owner || "待确认"} status={pendingOnly ? "unknown" : ownerStatus} />
          <InfoBlock label="时间" value={confirmed?.time || "待确认"} status={pendingOnly ? "unknown" : timeStatus} />
        </div>
        {confirmed ? <EvidenceDisclosure ids={confirmed.evidence_ids} evidence={result.evidence} /> : null}
      </div>
    </Card>
  );
}

function InfoBlock({ label, value, status }: { label: string; value: string; status?: FieldStatus }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white/70 p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[14px] font-semibold leading-5 text-slate-700">{label}</p>
        {status && status !== "confirmed" ? <Badge tone={badgeTone(status)}>{simpleFieldStatusText(status)}</Badge> : null}
      </div>
      <p className="mt-1 text-[15px] font-medium leading-6 text-slate-950">{value}</p>
    </div>
  );
}

function ClarificationBox({ result, onSubmit, busy }: { result: ValidatedOpportunity; onSubmit?: (payload: ClarifyPayload) => Promise<void>; busy?: boolean }) {
  const questions = result.clarification?.questions ?? [];
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [extra, setExtra] = useState("");
  const unconfirmed = result.unconfirmed_info.filter((item) => valueText(item.value) !== "");
  if (!questions.length && !unconfirmed.length && !onSubmit) return null;
  function questionPlaceholder(field: string | null | undefined): string {
    if (field === "next_action.action") return "例如：安排产品 Demo";
    if (field === "next_action.owner") return "例如：销售顾问林敏；如未确定可填“待确认”";
    if (field === "next_action.time") return "例如：下周四下午；如未确定可填“待确认”";
    if (field === "next_action") return "例如：安排产品 Demo，负责人待确认，时间下周四下午";
    return "在这里补充已确认的信息";
  }
  async function handleSubmit() {
    if (!onSubmit) return;
    const fromQuestions = questions
      .map((question, index) => {
        const key = `${question.field || "question"}-${question.question}-${index}`;
        return { question_id: question.field || `question_${index + 1}`, answer: answers[key]?.trim() || "" };
      })
      .filter((item) => item.answer);
    const payload = [...fromQuestions];
    if (extra.trim()) payload.push({ question_id: "其他补充信息", answer: extra.trim() });
    if (!payload.length) return;
    await onSubmit(payload);
    setAnswers({});
    setExtra("");
  }
  return (
    <Card>
      <SectionTitle
        title="待确认事项"
        description={questions.length ? "当前存在会影响阶段判断或风险判断的关键问题。补充事实后，系统会重新分析当前商机。" : "系统提示当前缺少的关键信息。补充事实后，系统会重新分析当前商机。"}
      />
      {questions.length ? (
        <div className="space-y-3">
          {questions.map((question, index) => {
            const key = `${question.field || "question"}-${question.question}-${index}`;
            return (
              <div key={`${question.field}-${index}`} className="rounded-md border border-slate-200 bg-white p-4 transition-colors hover:border-slate-300">
                <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
                  <div className="flex gap-2">
                    <Circle className="mt-1 h-3.5 w-3.5 flex-none text-amber-500" />
                    <div>
                      <p className="text-[15px] font-semibold leading-6 text-slate-950">{question.question}</p>
                      <p className="mt-1 text-sm leading-6 text-slate-600">{question.reason}</p>
                    </div>
                  </div>
                  <Badge tone={question.priority === "high" ? "amber" : "slate"}>待确认</Badge>
                </div>
                {onSubmit ? (
                  <Input
                    value={answers[key] ?? ""}
                    onChange={(event) => setAnswers((current) => ({ ...current, [key]: event.target.value }))}
                    placeholder={questionPlaceholder(question.field)}
                    className="mt-3 border-slate-200 shadow-none"
                  />
                ) : null}
              </div>
            );
          })}
        </div>
      ) : unconfirmed.length ? (
        <div className="space-y-2">
          {unconfirmed.map((item, index) => (
            <div key={index} className="flex gap-2 rounded-md border border-slate-200 bg-white p-3.5 text-sm text-slate-700 transition-colors hover:border-slate-300">
              <Circle className="mt-1 h-3.5 w-3.5 flex-none text-amber-500" />
              <div>
                <p className="text-[15px] font-medium leading-6 text-slate-900">{valueText(item.value)}</p>
                {item.reason ? <p className="mt-0.5 text-sm leading-6 text-slate-500">{item.reason}</p> : null}
              </div>
            </div>
          ))}
        </div>
      ) : null}
      {onSubmit ? (
        <div className="mt-4 space-y-3">
          <div className="space-y-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2.5 text-[13px] leading-6 text-slate-600">
            <p>补充事实会触发完整重新分析，上方问题可直接填写答案。</p>
            <p>在“其他补充信息”里补充商机信息时，请写清字段，例如“预算约 60 万”“最终决策人是客服负责人王总”。</p>
            <p>更新下一步行动时，请写清要做什么、负责人和时间；负责人或时间未确定可写“待确认”。</p>
          </div>
          <Input value={extra} onChange={(event) => setExtra(event.target.value)} placeholder="例如：预算约 60 万；下一步行动是安排产品 Demo，负责人待确认，时间下周四下午" className="border-slate-200 shadow-none" />
          <Button onClick={handleSubmit} disabled={busy}>{busy ? "正在更新……" : "更新商机分析"}</Button>
        </div>
      ) : null}
    </Card>
  );
}

function Progress({ session, activeRevision, onSelect }: { session?: AnalysisSessionDetail; activeRevision?: number; onSelect?: (revision: number) => void }) {
  if (!session || session.revisions.length <= 1) return null;
  return (
    <Card>
      <SectionTitle title="商机进展" />
      <div className="flex flex-wrap items-center gap-2">
        {session.revisions.map((revision, index) => {
          const current = revision.revision === session.current_revision;
          const active = activeRevision === revision.revision;
          return (
            <button
              key={revision.revision}
              type="button"
              onClick={() => onSelect?.(revision.revision)}
              className={cn(
                "rounded-md border px-3 py-2 text-left text-sm transition-colors",
                active ? "border-blue-300 bg-blue-50 text-blue-900" : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50",
              )}
            >
              <span className="font-medium">第 {revision.revision} 次分析{current ? " · 当前" : ""}</span>
              <span className="ml-2 text-slate-500">{formatDateTime(revision.created_at)}</span>
              <span className="ml-2">{revision.stage ? `${revision.stage} · ${stageLabels[revision.stage]}` : decisionStatusText(revision.status)}</span>
            </button>
          );
        })}
      </div>
    </Card>
  );
}

export function ResultView({
  result,
  session,
  viewingRevision,
  viewingCreatedAt,
  onReturnCurrent,
  onSelectRevision,
  onClarify,
  clarifyBusy,
  sourceText,
}: {
  result: ValidatedOpportunity;
  session?: AnalysisSessionDetail;
  viewingRevision?: number;
  viewingCreatedAt?: string;
  onReturnCurrent?: () => void;
  onSelectRevision?: (revision: number) => void;
  onClarify?: (payload: ClarifyPayload) => Promise<void>;
  clarifyBusy?: boolean;
  sourceText?: string;
}) {
  const isHistorical = Boolean(session && viewingRevision && viewingRevision !== session.current_revision);
  const crmItems = useMemo(() => buildCrmDisplayItems(result), [result]);
  const confirmedCrmCount = crmItems.filter((item) => item.status === "confirmed").length;
  const conflictCrmCount = crmItems.filter((item) => item.status === "conflict").length;
  const pendingCrmCount = crmItems.length - confirmedCrmCount - conflictCrmCount;
  const sourceSections = useMemo(() => (sourceText ? parseSourceText(sourceText) : []), [sourceText]);
  return (
    <div className="space-y-5">
      {isHistorical ? (
        <Card className="border-amber-200 bg-amber-50">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="font-semibold text-amber-950">历史分析结果</p>
              <p className="mt-1 text-sm text-amber-800">你正在查看 {viewingCreatedAt ? fullDateTime(viewingCreatedAt) : "过去某次"} 的历史分析结果。</p>
            </div>
            <Button variant="outline" onClick={onReturnCurrent}>返回当前分析</Button>
          </div>
        </Card>
      ) : null}
      {sourceText ? (
        <Card className="p-6">
          <SectionTitle title="本次销售拜访记录" />
          <div className="space-y-5 text-[15px] leading-7 text-slate-700">
            {sourceSections.map((section, index) => (
              <div key={`${section.title ?? "source"}-${index}`}>
                {section.title ? <p className={cn("mb-1.5 text-[14px] font-semibold", section.tone === "supplement" ? "text-slate-700" : "text-slate-800")}>{section.title}</p> : null}
                <div className="space-y-1">
                  {section.lines.map((line, lineIndex) => (
                    <p key={`${line}-${lineIndex}`} className="whitespace-pre-wrap">{line}</p>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>
      ) : null}
      <StageStepper result={result} />
      <Card>
        <SectionTitle title="商机概览" />
        <p className="text-base leading-8 text-slate-800">{result.summary}</p>
      </Card>
      <Card>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <SectionTitle title="商机信息" />
          <div className="flex gap-2">
            <Badge tone="green">{confirmedCrmCount} 项已确认</Badge>
            <Badge tone={pendingCrmCount ? "amber" : "slate"}>{pendingCrmCount} 项待确认</Badge>
            {conflictCrmCount ? <Badge tone="amber">{conflictCrmCount} 项存在冲突</Badge> : null}
          </div>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {crmItems.map((item, index) => (
            <FieldItem
              key={`${item.fieldKey}-${item.label}-${index}`}
              label={item.label}
              fieldKey={item.fieldKey}
              value={item.value}
              status={item.status}
              evidenceIds={item.evidenceIds}
              evidence={result.evidence}
              reason={item.reason}
            />
          ))}
        </div>
      </Card>
      <Risks result={result} />
      <NextActions result={result} />
      {!isHistorical ? <ClarificationBox result={result} onSubmit={onClarify} busy={clarifyBusy} /> : <ClarificationBox result={result} />}
      <Progress session={session} activeRevision={viewingRevision ?? session?.current_revision} onSelect={onSelectRevision} />
    </div>
  );
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-lg border border-dashed bg-white p-10 text-center">
      <FileText className="mx-auto h-9 w-9 text-slate-400" />
      <h2 className="mt-4 text-lg font-semibold text-slate-950">{title}</h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">{description}</p>
    </div>
  );
}

export function LoadingBlock({ text }: { text: string }) {
  return (
    <div className="rounded-lg border bg-white p-8 text-center shadow-sm">
      <Clock className="mx-auto h-8 w-8 animate-pulse text-blue-700" />
      <p className="mt-3 text-sm text-slate-600">{text}</p>
    </div>
  );
}

export function ErrorBlock({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-800">
      {message}
    </div>
  );
}

export function SectionIcon({ type }: { type: "history" | "message" }) {
  return type === "history" ? <History className="h-4 w-4" /> : <MessageSquareText className="h-4 w-4" />;
}
