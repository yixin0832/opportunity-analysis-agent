from __future__ import annotations

from .config import APP_VERSION, get_settings
from .database import check_db
from .errors import PipelineError
from .input_builder import validate_correction_answers
from .pipeline import list_examples, run_pipeline_with_trace
from .providers import DeepSeekProvider
from .repository import AnalysisRepository
from .schemas import AnalyzeRequest, BulkDeleteRequest, ClarifyRequest, DeleteResult

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
except ModuleNotFoundError:  # pragma: no cover - allows rule tests before deps install.
    FastAPI = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[assignment]
    CORSMiddleware = None  # type: ignore[assignment]
    JSONResponse = None  # type: ignore[assignment]


def _error_response(exc: PipelineError):
    return JSONResponse(status_code=exc.http_status, content={"error": {"code": exc.code, "message": exc.message, "retryable": exc.retryable}})


def create_app():
    if FastAPI is None:
        raise RuntimeError("FastAPI is not installed. Install project dependencies before running the API.")
    settings = get_settings()
    app = FastAPI(title="FDE 商机录入与分析 Agent")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )
    @app.get("/health")
    async def health():
        settings = get_settings()
        provider_connected = None
        if settings.llm_provider == "deepseek" and settings.provider_configured:
            provider_connected = await DeepSeekProvider(settings).check_connection()
        elif settings.llm_provider == "mock":
            provider_connected = True
        return {
            "status": "ok",
            "app_version": APP_VERSION,
            "db": "ok" if check_db() else "error",
            "provider_configured": settings.provider_configured,
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "provider_connected": provider_connected,
        }

    @app.get("/examples")
    def examples():
        return [example.model_dump() for example in list_examples()]

    @app.post("/analyze")
    async def analyze(request: AnalyzeRequest):
        try:
            trace = await run_pipeline_with_trace(request, revision=1)
            AnalysisRepository().create_session(request.input_text.strip(), trace)
            return trace.result.model_dump(mode="json")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PipelineError as exc:
            return _error_response(exc)

    @app.post("/clarify")
    async def clarify(request: ClarifyRequest):
        try:
            validate_correction_answers(request.answers)
            repository = AnalysisRepository()
            next_input = repository.build_next_revision_input(request.analysis_id, request.answers)
            if next_input is None:
                raise HTTPException(status_code=404, detail="未找到分析会话。")
            trace = await run_pipeline_with_trace(
                AnalyzeRequest(input_text=next_input.input_text, provider=next_input.provider),
                analysis_id=request.analysis_id,
                revision=next_input.revision,
            )
            repository.save_revision(request.analysis_id, next_input.revision, next_input.input_text, request.answers, trace)
            return trace.result.model_dump(mode="json")
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PipelineError as exc:
            return _error_response(exc)

    @app.get("/analyses")
    def analyses():
        try:
            return [item.model_dump(mode="json") for item in AnalysisRepository().list_sessions()]
        except PipelineError as exc:
            return _error_response(exc)

    @app.delete("/analyses")
    def clear_analyses():
        try:
            deleted_count = AnalysisRepository().clear_sessions()
            return DeleteResult(deleted_count=deleted_count).model_dump(mode="json")
        except PipelineError as exc:
            return _error_response(exc)

    @app.post("/analyses/bulk-delete")
    def bulk_delete_analyses(request: BulkDeleteRequest):
        try:
            deleted_count = AnalysisRepository().delete_sessions(request.analysis_ids)
            return DeleteResult(deleted_count=deleted_count).model_dump(mode="json")
        except PipelineError as exc:
            return _error_response(exc)

    @app.delete("/analyses/{analysis_id}")
    def delete_analysis(analysis_id: str):
        try:
            deleted_count = AnalysisRepository().delete_session(analysis_id)
            return DeleteResult(deleted_count=deleted_count).model_dump(mode="json")
        except PipelineError as exc:
            return _error_response(exc)

    @app.get("/analyses/{analysis_id}/revisions/{revision}")
    def analysis_revision(analysis_id: str, revision: int):
        try:
            result = AnalysisRepository().get_revision(analysis_id, revision)
            if result is None:
                raise HTTPException(status_code=404, detail="未找到分析版本。")
            return result.model_dump(mode="json")
        except HTTPException:
            raise
        except PipelineError as exc:
            return _error_response(exc)

    @app.get("/analyses/{analysis_id}")
    def analysis_detail(analysis_id: str):
        try:
            result = AnalysisRepository().get_session(analysis_id)
            if result is None:
                raise HTTPException(status_code=404, detail="未找到分析会话。")
            return result.model_dump(mode="json")
        except HTTPException:
            raise
        except PipelineError as exc:
            return _error_response(exc)

    return app


app = create_app() if FastAPI is not None else None
