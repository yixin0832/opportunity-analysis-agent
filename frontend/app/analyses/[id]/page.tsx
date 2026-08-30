"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { clarify, getAnalysis, getAnalysisRevision } from "@/lib/api";
import type { AnalysisRevisionDetail, AnalysisSessionDetail, ValidatedOpportunity } from "@/lib/types";
import { ErrorBlock, LoadingBlock, ResultView } from "@/components/result-view";

export default function AnalysisDetailPage() {
  const params = useParams<{ id: string }>();
  const analysisId = params.id;
  const [session, setSession] = useState<AnalysisSessionDetail | null>(null);
  const [activeResult, setActiveResult] = useState<ValidatedOpportunity | null>(null);
  const [activeRevision, setActiveRevision] = useState<number | null>(null);
  const [activeCreatedAt, setActiveCreatedAt] = useState<string | null>(null);
  const [activeInputText, setActiveInputText] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadSession = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const detail = await getAnalysis(analysisId);
      const currentRevision = await getAnalysisRevision(analysisId, detail.current_revision).catch(() => null);
      setSession(detail);
      setActiveResult(currentRevision?.validated_opportunity ?? detail.current_result);
      setActiveRevision(detail.current_revision);
      setActiveCreatedAt(currentRevision?.created_at ?? detail.revisions.find((item) => item.revision === detail.current_revision)?.created_at ?? detail.updated_at);
      setActiveInputText(currentRevision?.input_text ?? detail.original_input);
    } catch (err) {
      setError(err instanceof Error ? err.message : "分析记录暂时无法打开。");
    } finally {
      setLoading(false);
    }
  }, [analysisId]);

  useEffect(() => {
    void loadSession();
  }, [loadSession]);

  async function selectRevision(revision: number) {
    if (!session) return;
    setLoading(true);
    setError(null);
    try {
      const detail: AnalysisRevisionDetail = await getAnalysisRevision(analysisId, revision);
      setActiveResult(detail.validated_opportunity);
      setActiveRevision(revision);
      setActiveCreatedAt(detail.created_at);
      setActiveInputText(detail.input_text);
    } catch (err) {
      setError(err instanceof Error ? err.message : "历史分析结果暂时无法打开。");
    } finally {
      setLoading(false);
    }
  }

  async function handleClarify(payload: { question_id?: string | null; answer: string }[]) {
    setUpdating(true);
    setError(null);
    setSuccess(null);
    try {
      await clarify(analysisId, payload);
      const detail = await getAnalysis(analysisId);
      const currentRevision = await getAnalysisRevision(analysisId, detail.current_revision).catch(() => null);
      setSession(detail);
      setActiveResult(currentRevision?.validated_opportunity ?? detail.current_result);
      setActiveRevision(detail.current_revision);
      setActiveCreatedAt(currentRevision?.created_at ?? detail.updated_at);
      setActiveInputText(currentRevision?.input_text ?? detail.original_input);
      setSuccess("已根据补充事实重新分析商机");
    } catch (err) {
      setError(err instanceof Error ? err.message : "本次更新未能完成，请稍后重试。");
    } finally {
      setUpdating(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-5 py-8 sm:py-9">
      <div className="mb-6">
        <div>
          <h1 className="text-[28px] font-semibold leading-9 text-slate-950">当前商机分析</h1>
          <p className="mt-1.5 text-[14px] leading-6 text-slate-500">查看结构化商机结果、引用原文、风险与下一步行动。</p>
        </div>
      </div>
      {success ? <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{success}</div> : null}
      {error ? <div className="mb-4"><ErrorBlock message={error} /></div> : null}
      {loading ? <LoadingBlock text="正在加载商机分析……" /> : null}
      {!loading && activeResult ? (
        <ResultView
          result={activeResult}
          session={session ?? undefined}
          viewingRevision={activeRevision ?? undefined}
          viewingCreatedAt={activeCreatedAt ?? undefined}
          onReturnCurrent={() => session && void selectRevision(session.current_revision)}
          onSelectRevision={(revision) => void selectRevision(revision)}
          onClarify={handleClarify}
          clarifyBusy={updating}
          sourceText={activeInputText ?? undefined}
        />
      ) : null}
    </div>
  );
}
