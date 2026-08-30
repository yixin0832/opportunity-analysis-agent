from __future__ import annotations

import asyncio

import pytest

from backend.app.config import AppSettings
from backend.app.errors import LLMSchemaInvalidError, LLMTimeoutError
from backend.app.providers import DeepSeekProvider


def settings() -> AppSettings:
    return AppSettings(app_env="test", llm_provider="deepseek", llm_model="deepseek-chat", llm_api_key="test-key", llm_timeout_seconds=1, llm_schema_retry=1, database_url="sqlite:///:memory:")


def test_deepseek_provider_uses_chat_json_output_by_default(monkeypatch):
    captured = {}

    class Response:
        status_code = 200
        def json(self):
            return {"choices": [{"message": {"content": '{"candidate_needs":[],"candidate_scenarios":[],"candidate_budget":[],"candidate_people":[],"candidate_timeline":[],"candidate_next_actions":[],"stage_signals":[],"ambiguities":[],"possible_conflicts":[],"evidence_candidates":[]}'}}]}

    class Client:
        def __init__(self, timeout):
            self.timeout = timeout
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def post(self, url, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return Response()

    monkeypatch.setattr("backend.app.providers.httpx.AsyncClient", Client)
    raw = asyncio.run(DeepSeekProvider(settings()).invoke_structured("客户说可以安排 Demo。"))
    assert raw.evidence_candidates == []
    assert captured["url"].endswith("/chat/completions")
    assert captured["json"]["response_format"]["type"] == "json_object"
    assert captured["json"]["thinking"] == {"type": "disabled"}
    assert captured["headers"]["Authorization"] == "Bearer test-key"


def test_deepseek_responses_json_schema_method_is_available(monkeypatch):
    captured = {}

    class Response:
        status_code = 200
        def json(self):
            return {
                "status": "completed",
                "output": [{"type": "message", "content": [{"type": "output_text", "text": '{"candidate_needs":[],"candidate_scenarios":[],"candidate_budget":[],"candidate_people":[],"candidate_timeline":[],"candidate_next_actions":[],"stage_signals":[],"ambiguities":[],"possible_conflicts":[],"evidence_candidates":[]}'}]}],
            }

    class Client:
        def __init__(self, timeout):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def post(self, url, headers, json):
            captured["url"] = url
            captured["json"] = json
            return Response()

    monkeypatch.setattr("backend.app.providers.httpx.AsyncClient", Client)
    payload = asyncio.run(DeepSeekProvider(settings())._call_responses_json_schema("客户说可以安排 Demo。"))
    assert payload["evidence_candidates"] == []
    assert captured["url"].endswith("/responses")
    assert captured["json"]["text"]["format"]["type"] == "json_schema"
    assert captured["json"]["thinking"] == {"type": "disabled"}

def test_deepseek_schema_retry_then_fails(monkeypatch):
    class BadResponse:
        status_code = 200
        def json(self):
            bad_json = '{"stage_signals":[{"signal_type":"not_a_real_signal","explicitness":"explicit","polarity":"positive","attribution":"customer","current_validity":"active","evidence_id":"E01"}],"evidence_candidates":[]}'
            return {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": bad_json}]}]}

    class Client:
        def __init__(self, timeout):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def post(self, url, headers, json):
            return BadResponse()

    monkeypatch.setattr("backend.app.providers.httpx.AsyncClient", Client)
    with pytest.raises(LLMSchemaInvalidError):
        asyncio.run(DeepSeekProvider(settings()).invoke_structured("客户说可以安排 Demo。"))


def test_deepseek_timeout_maps_to_pipeline_error(monkeypatch):
    import httpx

    class Client:
        def __init__(self, timeout):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def post(self, url, headers, json):
            raise httpx.TimeoutException("timeout")

    monkeypatch.setattr("backend.app.providers.httpx.AsyncClient", Client)
    with pytest.raises(LLMTimeoutError):
        asyncio.run(DeepSeekProvider(settings()).invoke_structured("客户说可以安排 Demo。"))


def test_deepseek_grounded_summary_uses_chat_json_output(monkeypatch):
    captured = {}

    class Response:
        status_code = 200
        def json(self):
            return {"choices": [{"message": {"content": '{"summary":"当前商机处于 S2（方案验证），客户已确认安排 Demo。"}'}}]}

    class Client:
        def __init__(self, timeout):
            self.timeout = timeout
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def post(self, url, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return Response()

    monkeypatch.setattr("backend.app.providers.httpx.AsyncClient", Client)
    summary = asyncio.run(
        DeepSeekProvider(settings()).invoke_grounded_summary(
            {"stage": {"code": "S2", "label": "方案验证"}},
            "当前商机处于 S2（方案验证），客户明确同意演示。",
        )
    )
    assert summary.startswith("当前商机处于 S2")
    assert captured["url"].endswith("/chat/completions")
    assert captured["json"]["response_format"]["type"] == "json_object"
    assert captured["json"]["thinking"] == {"type": "disabled"}
    assert "CRM 商机概览改写器" in captured["json"]["messages"][0]["content"]
    assert "structured_context" in captured["json"]["messages"][1]["content"]
