import type { DecisionStatus, FieldStatus, StageCode } from "./types";

export const stageLabels: Record<StageCode, string> = {
  S0: "线索",
  S1: "需求初探",
  S2: "方案验证",
  S3: "商务评估",
  S4: "决策审批",
  S5: "赢单签约",
};

export const stageOrder: StageCode[] = ["S0", "S1", "S2", "S3", "S4", "S5"];

export function decisionStatusText(status: DecisionStatus): string {
  const map: Record<DecisionStatus, string> = {
    complete: "分析完成",
    need_confirmation: "需要补充确认",
    unable_to_judge: "信息不足，暂时无法判断",
  };
  return map[status] ?? "待确认";
}

export function fieldStatusText(status: FieldStatus): string {
  const map: Record<FieldStatus, string> = {
    confirmed: "已确认",
    inferred: "尚未完全确认",
    unknown: "待确认",
    conflict: "信息存在冲突",
    partial: "部分信息待确认",
  };
  return map[status] ?? "待确认";
}

export function severityText(severity: "high" | "medium" | "low"): string {
  const map = { high: "高", medium: "中", low: "低" } as const;
  return map[severity] ?? "中";
}

export function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

export function fullDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}
