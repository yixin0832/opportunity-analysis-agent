from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from .config import get_settings
from .examples import EXAMPLES
from .evidence import summarize_input
from .providers import get_provider
from .rules import build_validated_opportunity
from .schemas import AnalyzeRequest, ExampleInput, RawExtraction, ValidatedOpportunity
from .summary import generate_grounded_summary


@dataclass(frozen=True)
class PipelineTrace:
    result: ValidatedOpportunity
    raw_extraction: RawExtraction
    provider: str
    model: str
    latency_ms: int


def normalize_input(input_text: str) -> str:
    return input_text.strip()


async def run_pipeline_with_trace(
    request: AnalyzeRequest,
    *,
    analysis_id: str | None = None,
    revision: int = 1,
) -> PipelineTrace:
    normalized = normalize_input(request.input_text)
    if not normalized:
        raise ValueError("请输入销售拜访记录。")
    settings = get_settings()
    provider = get_provider(request.provider, settings)
    started_at = perf_counter()
    raw: RawExtraction = await provider.invoke_structured(normalized)
    result = build_validated_opportunity(normalized, raw, analysis_id=analysis_id, revision=revision)
    await generate_grounded_summary(provider, result)
    latency_ms = int((perf_counter() - started_at) * 1000)
    result.developer_details["input_summary"] = summarize_input(normalized)
    result.developer_details["provider"] = provider.provider_name
    result.developer_details["model"] = provider.model_name
    result.developer_details["latency_ms"] = latency_ms
    return PipelineTrace(result=result, raw_extraction=raw, provider=provider.provider_name, model=provider.model_name, latency_ms=latency_ms)


async def run_pipeline(request: AnalyzeRequest) -> ValidatedOpportunity:
    return (await run_pipeline_with_trace(request)).result


async def run_mock_pipeline(request: AnalyzeRequest) -> ValidatedOpportunity:
    return await run_pipeline(AnalyzeRequest(input_text=request.input_text, provider="mock"))


def list_examples() -> list[ExampleInput]:
    return EXAMPLES
