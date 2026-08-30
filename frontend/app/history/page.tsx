"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { CalendarDays, Check, CheckSquare, ChevronDown, Clock3, Plus, Search, Trash2, X } from "lucide-react";
import { bulkDeleteAnalyses, clearAnalyses, listAnalyses } from "@/lib/api";
import { decisionStatusText, formatDateTime, stageLabels } from "@/lib/cn";
import type { AnalysisListItem, DecisionStatus, StageCode } from "@/lib/types";
import { Badge, Button, Card, Input, cn } from "@/components/ui";
import { EmptyState, ErrorBlock, LoadingBlock } from "@/components/result-view";

type StageFilter = "all" | StageCode | "unjudged";
type StatusFilter = "all" | DecisionStatus;
type TimeFilter = "all" | "7d" | "30d";

const statusFilters: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "全部状态" },
  { value: "complete", label: "分析完成" },
  { value: "need_confirmation", label: "待确认" },
  { value: "unable_to_judge", label: "无法判断" },
];

const timeFilters: { value: TimeFilter; label: string }[] = [
  { value: "30d", label: "最近 30 天" },
  { value: "7d", label: "最近 7 天" },
  { value: "all", label: "全部时间" },
];

const stageFilters: { value: StageFilter; label: string }[] = [
  { value: "all", label: "全部阶段" },
  { value: "S0", label: "S0" },
  { value: "S1", label: "S1" },
  { value: "S2", label: "S2" },
  { value: "S3", label: "S3" },
  { value: "S4", label: "S4" },
  { value: "S5", label: "S5" },
  { value: "unjudged", label: "未判断" },
];

function FilterControl<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: { value: T; label: string }[]; onChange: (value: T) => void }) {
  const [open, setOpen] = useState(false);
  const selected = options.find((item) => item.value === value) ?? options[0];
  return (
    <div className="relative">
      <Button type="button" variant="outline" className="h-10 min-w-32 justify-between gap-3 px-3 text-slate-600 shadow-sm shadow-slate-200/40" onClick={() => setOpen((next) => !next)} aria-expanded={open}>
        <span className="text-[13px]">{label}</span>
        <span className="font-medium text-slate-800">{selected.label}</span>
        <ChevronDown className={cn("h-4 w-4 text-slate-400 transition-transform", open && "rotate-180")} aria-hidden="true" />
      </Button>
      {open ? (
        <div className="absolute right-0 z-20 mt-2 w-40 rounded-md border border-slate-200 bg-white p-1.5 shadow-lg shadow-slate-200/70">
          {options.map((item) => (
            <button
              key={item.value}
              type="button"
              className={cn("flex h-9 w-full items-center justify-between rounded px-2.5 text-left text-sm text-slate-700 hover:bg-slate-50 focus:bg-slate-50 focus:outline-none", item.value === value && "bg-blue-50 text-blue-700")}
              onClick={() => {
                onChange(item.value);
                setOpen(false);
              }}
            >
              {item.label}
              {item.value === value ? <Check className="h-4 w-4" aria-hidden="true" /> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function stageBadge(item: AnalysisListItem) {
  if (!item.current_stage) {
    return <Badge tone="amber">未判断</Badge>;
  }
  return <Badge tone="blue">{item.current_stage} · {stageLabels[item.current_stage]}</Badge>;
}

function statusTone(status: DecisionStatus): "green" | "amber" | "red" {
  if (status === "complete") return "green";
  if (status === "need_confirmation") return "amber";
  return "red";
}

function withinTimeFilter(item: AnalysisListItem, filter: TimeFilter) {
  if (filter === "all") return true;
  const days = filter === "7d" ? 7 : 30;
  const createdAt = new Date(item.created_at).getTime();
  if (Number.isNaN(createdAt)) return true;
  return Date.now() - createdAt <= days * 24 * 60 * 60 * 1000;
}

export default function HistoryPage() {
  const [items, setItems] = useState<AnalysisListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [stageFilter, setStageFilter] = useState<StageFilter>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [timeFilter, setTimeFilter] = useState<TimeFilter>("30d");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [deleting, setDeleting] = useState(false);

  function refresh() {
    setLoading(true);
    setError(null);
    listAnalyses()
      .then((nextItems) => {
        setItems(nextItems);
        setSelectedIds((ids) => ids.filter((id) => nextItems.some((item) => item.analysis_id === id)));
      })
      .catch((err) => setError(err instanceof Error ? err.message : "分析历史暂时无法加载。"))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    refresh();
  }, []);

  const filteredItems = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return items.filter((item) => {
      if (stageFilter !== "all") {
        if (stageFilter === "unjudged" && item.current_stage) return false;
        if (stageFilter !== "unjudged" && item.current_stage !== stageFilter) return false;
      }
      if (statusFilter !== "all" && item.current_status !== statusFilter) return false;
      if (!withinTimeFilter(item, timeFilter)) return false;
      if (!normalizedQuery) return true;
      const haystack = `${item.opportunity_title} ${item.summary} ${item.input_summary}`.toLowerCase();
      return haystack.includes(normalizedQuery);
    });
  }, [items, query, stageFilter, statusFilter, timeFilter]);

  const filteredIds = filteredItems.map((item) => item.analysis_id);
  const selectedSet = new Set(selectedIds);
  const selectedVisibleCount = filteredIds.filter((id) => selectedSet.has(id)).length;
  const allVisibleSelected = filteredIds.length > 0 && selectedVisibleCount === filteredIds.length;

  function toggleOne(id: string) {
    setSelectedIds((ids) => (ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id]));
  }

  function toggleVisible() {
    setSelectedIds((ids) => {
      const current = new Set(ids);
      if (allVisibleSelected) {
        filteredIds.forEach((id) => current.delete(id));
      } else {
        filteredIds.forEach((id) => current.add(id));
      }
      return Array.from(current);
    });
  }

  async function deleteSelected() {
    if (!selectedIds.length) return;
    if (!window.confirm(`确认删除选中的 ${selectedIds.length} 条分析历史？此操作无法撤销。`)) return;
    setDeleting(true);
    try {
      await bulkDeleteAnalyses(selectedIds);
      setItems((current) => current.filter((item) => !selectedIds.includes(item.analysis_id)));
      setSelectedIds([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败，请稍后重试。");
    } finally {
      setDeleting(false);
    }
  }

  async function clearAll() {
    if (!items.length) return;
    if (!window.confirm("确认清空全部分析历史？此操作无法撤销。")) return;
    setDeleting(true);
    try {
      await clearAnalyses();
      setItems([]);
      setSelectedIds([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "清空历史失败，请稍后重试。");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl px-5 py-8 sm:py-9">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-[28px] font-semibold leading-9 text-slate-950">分析历史</h1>
          <p className="mt-1.5 text-[14px] leading-6 text-slate-500">按客户、项目和摘要快速回看历史分析。</p>
        </div>
        <Button asChild variant="outline" className="gap-2">
          <Link href="/">
            <Plus className="h-4 w-4" aria-hidden="true" />
            分析拜访记录
          </Link>
        </Button>
      </div>

      <Card className="mb-5 p-4">
        <div className="grid gap-3 lg:grid-cols-[minmax(260px,1fr)_auto]">
          <label className="relative block">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden="true" />
            <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索客户、项目或摘要" className="pl-9" />
          </label>
          <div className="flex flex-wrap gap-2 lg:justify-end">
            <FilterControl label="阶段" value={stageFilter} options={stageFilters} onChange={setStageFilter} />
            <FilterControl label="状态" value={statusFilter} options={statusFilters} onChange={setStatusFilter} />
            <FilterControl label="时间" value={timeFilter} options={timeFilters} onChange={setTimeFilter} />
          </div>
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-3">
          <div className="flex flex-wrap items-center gap-2 text-[13px] text-slate-400">
            <span>{filteredItems.length} 条结果</span>
            <Button type="button" variant="ghost" size="sm" className="h-8 gap-1.5 px-2 text-slate-500" onClick={toggleVisible} disabled={!filteredItems.length || deleting}>
              <CheckSquare className="h-4 w-4" aria-hidden="true" />
              {allVisibleSelected ? "取消选择" : "选择当前"}
            </Button>
            {selectedIds.length ? <span>已选择 {selectedIds.length} 条</span> : null}
          </div>
          <div className="flex flex-wrap gap-2">
            {selectedIds.length ? (
              <Button type="button" variant="outline" size="sm" className="gap-2 text-rose-700 hover:border-rose-200 hover:bg-rose-50" onClick={deleteSelected} disabled={deleting}>
                <Trash2 className="h-4 w-4" aria-hidden="true" />
                删除所选
              </Button>
            ) : null}
            <Button type="button" variant="ghost" size="sm" className="h-8 gap-1.5 px-2 text-slate-400 hover:text-rose-700" onClick={clearAll} disabled={!items.length || deleting}>
              <X className="h-4 w-4" aria-hidden="true" />
              清空历史
            </Button>
          </div>
        </div>
      </Card>

      {loading ? <LoadingBlock text="正在加载分析历史……" /> : null}
      {error ? <ErrorBlock message={error} /> : null}
      {!loading && !error && !items.length ? <EmptyState title="暂无历史分析" description="完成第一次商机分析后，记录会显示在这里。" /> : null}
      {!loading && !error && items.length > 0 && !filteredItems.length ? <EmptyState title="没有匹配的历史分析" description="调整搜索、阶段、状态或时间筛选后再试。" /> : null}

      <div className="space-y-2.5">
        {filteredItems.map((item) => (
          <Card key={item.analysis_id} className={cn("p-4 transition-all hover:border-slate-300 hover:bg-white hover:shadow-sm hover:shadow-slate-200/70", selectedSet.has(item.analysis_id) && "border-blue-200 bg-blue-50/30")}>
            <div className="flex gap-3">
              <input
                type="checkbox"
                aria-label={`选择 ${item.opportunity_title}`}
                checked={selectedSet.has(item.analysis_id)}
                onChange={() => toggleOne(item.analysis_id)}
                className="mt-1 h-4 w-4 flex-none rounded border-slate-300 text-blue-600 focus:ring-blue-500"
              />
              <Link href={`/analyses/${item.analysis_id}`} className="min-w-0 flex-1">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <h2 className="line-clamp-1 text-[18px] font-semibold leading-7 text-slate-950">{item.opportunity_title}</h2>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2">
                      {stageBadge(item)}
                      <Badge tone={statusTone(item.current_status)}>{decisionStatusText(item.current_status)}</Badge>
                    </div>
                    <p className="mt-2 line-clamp-1 text-[14px] leading-6 text-slate-600">{item.summary || item.input_summary}</p>
                  </div>
                  <div className="flex flex-none flex-wrap gap-2 text-[13px] leading-5 text-slate-500 sm:max-w-44 sm:justify-end">
                    <span className="inline-flex items-center gap-1.5">
                      <Clock3 className="h-3.5 w-3.5" aria-hidden="true" />
                      {formatDateTime(item.created_at)}
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                      <CalendarDays className="h-3.5 w-3.5" aria-hidden="true" />
                      {item.revision_count} 次分析
                    </span>
                  </div>
                </div>
              </Link>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
