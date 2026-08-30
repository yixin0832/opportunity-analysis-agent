from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PipelineError(Exception):
    code: str
    message: str
    http_status: int
    retryable: bool = False

    def __str__(self) -> str:
        return self.message


class UnsupportedProviderError(PipelineError):
    def __init__(self, provider: str) -> None:
        super().__init__("UNSUPPORTED_PROVIDER", f"暂不支持 Provider：{provider}。", 400, False)


class ProviderNotConfiguredError(PipelineError):
    def __init__(self) -> None:
        super().__init__("LLM_PROVIDER_NOT_CONFIGURED", "模型服务尚未完成配置，请检查环境变量。", 500, False)


class LLMTimeoutError(PipelineError):
    def __init__(self) -> None:
        super().__init__("LLM_TIMEOUT", "模型响应超时，请稍后重试。", 504, True)


class LLMProviderError(PipelineError):
    def __init__(self, retryable: bool = True) -> None:
        super().__init__("LLM_PROVIDER_ERROR", "模型服务暂时不可用，请稍后重试。", 502, retryable)


class LLMSchemaInvalidError(PipelineError):
    def __init__(self) -> None:
        super().__init__("LLM_SCHEMA_INVALID", "模型返回结构不符合 RawExtraction Schema，已停止本次分析。", 422, True)


class SummaryGenerationError(PipelineError):
    def __init__(self, message: str = "Grounded Summary 生成失败。") -> None:
        super().__init__("SUMMARY_GENERATION_FAILED", message, 200, True)


class DatabaseError(PipelineError):
    def __init__(self) -> None:
        super().__init__("DATABASE_ERROR", "分析历史保存或读取失败，请稍后重试。", 500, True)
