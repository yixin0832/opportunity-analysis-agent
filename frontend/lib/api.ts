import type {
  AnalysisListItem,
  AnalysisRevisionDetail,
  AnalysisSessionDetail,
  ApiErrorPayload,
  DeleteResult,
  ExampleInput,
  ValidatedOpportunity,
} from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

async function requestJson<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options?.headers ?? {}),
      },
      cache: "no-store",
    });
  } catch {
    throw new Error("暂时无法连接分析服务，请确认后端服务已启动。");
  }

  const body = (await response.json().catch(() => ({}))) as ApiErrorPayload;
  if (!response.ok || body.error) {
    throw new Error(body.error?.message || body.detail || "请求失败，请稍后重试。");
  }
  return body as T;
}

export function analyze(inputText: string): Promise<ValidatedOpportunity> {
  return requestJson<ValidatedOpportunity>("/analyze", {
    method: "POST",
    body: JSON.stringify({ input_text: inputText }),
  });
}

export function clarify(analysisId: string, answers: { question_id?: string | null; answer: string }[]): Promise<ValidatedOpportunity> {
  return requestJson<ValidatedOpportunity>("/clarify", {
    method: "POST",
    body: JSON.stringify({ analysis_id: analysisId, answers }),
  });
}

export function getExamples(): Promise<ExampleInput[]> {
  return requestJson<ExampleInput[]>("/examples");
}

export function listAnalyses(): Promise<AnalysisListItem[]> {
  return requestJson<AnalysisListItem[]>("/analyses");
}

export function getAnalysis(id: string): Promise<AnalysisSessionDetail> {
  return requestJson<AnalysisSessionDetail>(`/analyses/${id}`);
}

export function getAnalysisRevision(id: string, revision: number): Promise<AnalysisRevisionDetail> {
  return requestJson<AnalysisRevisionDetail>(`/analyses/${id}/revisions/${revision}`);
}

export function deleteAnalysis(id: string): Promise<DeleteResult> {
  return requestJson<DeleteResult>(`/analyses/${id}`, { method: "DELETE" });
}

export function bulkDeleteAnalyses(ids: string[]): Promise<DeleteResult> {
  return requestJson<DeleteResult>("/analyses/bulk-delete", {
    method: "POST",
    body: JSON.stringify({ analysis_ids: ids }),
  });
}

export function clearAnalyses(): Promise<DeleteResult> {
  return requestJson<DeleteResult>("/analyses", { method: "DELETE" });
}
