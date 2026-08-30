from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_MODEL", "mock-v1")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("CORS_ORIGINS", "http://127.0.0.1:3000,http://localhost:3000")
    return TestClient(create_app())


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["db"] == "ok"
    assert "app_version" in payload
    assert "provider_configured" in payload
    assert "model" in payload
    assert "provider" in payload
    assert "api_key" not in payload


def test_examples(client):
    response = client.get("/examples")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 3
    assert {item["id"] for item in payload} >= {"demo_s2", "budget_conflict", "insufficient_text"}


def test_cors_preflight_allows_frontend_analyze_request(client):
    response = client.options(
        "/analyze",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    assert "POST" in response.headers["access-control-allow-methods"]


def test_cors_preflight_allows_frontend_history_delete_requests(client):
    headers = {
        "Origin": "http://127.0.0.1:3000",
        "Access-Control-Request-Method": "DELETE",
        "Access-Control-Request-Headers": "content-type",
    }

    clear_response = client.options("/analyses", headers=headers)
    assert clear_response.status_code == 200
    assert clear_response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    allowed_methods = clear_response.headers["access-control-allow-methods"]
    assert "DELETE" in allowed_methods
    assert "PUT" not in allowed_methods

    delete_response = client.options("/analyses/example-id", headers=headers)
    assert delete_response.status_code == 200
    assert delete_response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    assert "DELETE" in delete_response.headers["access-control-allow-methods"]


def test_cors_preflight_allows_configured_public_frontend_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_MODEL", "mock-v1")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("CORS_ORIGINS", "https://sales-demo.example.com")
    client = TestClient(create_app())

    response = client.options(
        "/analyses/example-id",
        headers={
            "Origin": "https://sales-demo.example.com",
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://sales-demo.example.com"
    assert "DELETE" in response.headers["access-control-allow-methods"]


def test_analyze_demo_s2_creates_history_session(client):
    text = "今天拜访了某连锁零售客户。客户说门店客服工单处理慢，希望用智能问答先覆盖售后知识库场景。王总说下周四可以安排一次产品 Demo。"
    response = client.post("/analyze", json={"input_text": text, "provider": "mock"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["stage"]["code"] == "S2"
    assert payload["status"] == "complete"
    assert payload["confirmed_next_action"]["type"] == "customer_confirmed"
    assert payload["developer_details"]["provider"] == "mock"

    analysis_id = payload["analysis_id"]
    list_response = client.get("/analyses")
    assert list_response.status_code == 200
    assert list_response.json()[0]["analysis_id"] == analysis_id

    detail_response = client.get(f"/analyses/{analysis_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["current_revision"] == 1
    assert len(detail["revisions"]) == 1
    assert detail["current_result"]["analysis_id"] == analysis_id

    revision_response = client.get(f"/analyses/{analysis_id}/revisions/1")
    assert revision_response.status_code == 200
    revision = revision_response.json()
    assert revision["revision"] == 1
    assert revision["raw_extraction"] is not None
    assert revision["pipeline_version"].startswith("0.5.0")


def test_clarify_creates_revision_2_with_built_input(client):
    analyze_response = client.post("/analyze", json={"input_text": "客户说客服工单处理慢。", "provider": "mock"})
    assert analyze_response.status_code == 200
    analysis_id = analyze_response.json()["analysis_id"]
    assert analyze_response.json()["stage"]["code"] == "S1"

    clarify_response = client.post(
        "/clarify",
        json={
            "analysis_id": analysis_id,
            "answers": [{"question_id": "stage", "answer": "已约下周 Demo。"}],
        },
    )
    assert clarify_response.status_code == 200
    clarified = clarify_response.json()
    assert clarified["analysis_id"] == analysis_id
    assert clarified["revision"] == 2
    assert clarified["stage"]["code"] == "S2"

    detail = client.get(f"/analyses/{analysis_id}").json()
    assert detail["current_revision"] == 2
    assert len(detail["revisions"]) == 2
    assert detail["revisions"][0]["stage"] == "S1"
    assert detail["revisions"][1]["stage"] == "S2"

    v1 = client.get(f"/analyses/{analysis_id}/revisions/1").json()
    v2 = client.get(f"/analyses/{analysis_id}/revisions/2").json()
    assert v1["validated_opportunity"]["stage"]["code"] == "S1"
    assert v2["validated_opportunity"]["stage"]["code"] == "S2"
    assert "【原始销售拜访记录】" in v2["input_text"]
    assert "【第 2 次分析补充确认信息】" in v2["input_text"]
    assert "Revision" not in v2["input_text"]
    assert v2["clarification_answers"][0]["answer"] == "已约下周 Demo。"


def test_correction_fact_uses_clarify_pipeline_and_creates_new_revision(client):
    analyze_response = client.post(
        "/analyze",
        json={
            "input_text": "今天拜访了某连锁零售客户。客户说门店客服工单处理慢。王总说下周四可以安排一次产品 Demo。",
            "provider": "mock",
        },
    )
    assert analyze_response.status_code == 200
    analysis_id = analyze_response.json()["analysis_id"]

    correction = "王总只是技术负责人，李总才是最终采购决策人。"
    clarify_response = client.post(
        "/clarify",
        json={
            "analysis_id": analysis_id,
            "answers": [{"question_id": "修正识别：决策人", "answer": correction}],
        },
    )
    assert clarify_response.status_code == 200
    clarified = clarify_response.json()
    assert clarified["analysis_id"] == analysis_id
    assert clarified["revision"] == 2

    detail = client.get(f"/analyses/{analysis_id}").json()
    assert detail["current_revision"] == 2
    assert len(detail["revisions"]) == 2

    v1 = client.get(f"/analyses/{analysis_id}/revisions/1").json()
    v2 = client.get(f"/analyses/{analysis_id}/revisions/2").json()
    assert v1["revision"] == 1
    assert v2["revision"] == 2
    assert "【第 2 次分析修正识别事实】" in v2["input_text"]
    assert "Revision" not in v2["input_text"]
    assert correction in v2["input_text"]
    assert v2["clarification_answers"][0]["question_id"] == "修正识别：决策人"


def test_invalid_correction_answer_is_rejected_before_revision_creation(client):
    analyze_response = client.post(
        "/analyze",
        json={
            "input_text": "客户已经完成产品 Demo，并确认客服自动化需求会继续推进。客户表示今年预算 50 万，计划下个月完成商务评估。",
            "provider": "mock",
        },
    )
    assert analyze_response.status_code == 200
    analysis_id = analyze_response.json()["analysis_id"]

    clarify_response = client.post(
        "/clarify",
        json={
            "analysis_id": analysis_id,
            "answers": [{"question_id": "修正识别：时间计划", "answer": "下个周完成商务评估"}],
        },
    )
    assert clarify_response.status_code == 400
    assert "修正识别只用于" in clarify_response.json()["detail"]

    detail = client.get(f"/analyses/{analysis_id}").json()
    assert detail["current_revision"] == 1
    assert len(detail["revisions"]) == 1


def test_missing_budget_supplement_reanalyzes_without_direct_patch(client):
    analyze_response = client.post("/analyze", json={"input_text": "客户说客服工单处理慢。", "provider": "mock"})
    assert analyze_response.status_code == 200
    analysis_id = analyze_response.json()["analysis_id"]
    assert analyze_response.json()["crm_fields"]["budget"]["value"] is None

    clarify_response = client.post(
        "/clarify",
        json={
            "analysis_id": analysis_id,
            "answers": [{"question_id": "预算", "answer": "客户确认今年预算 80 万。"}],
        },
    )
    assert clarify_response.status_code == 200
    clarified = clarify_response.json()
    assert clarified["revision"] == 2
    assert clarified["crm_fields"]["budget"]["value"] == "80 万"

    v2 = client.get(f"/analyses/{analysis_id}/revisions/2").json()
    assert "【第 2 次分析补充确认信息】" in v2["input_text"]
    assert "Revision" not in v2["input_text"]
    assert "客户确认今年预算 80 万。" in v2["input_text"]
    assert any(item["quote"] == "预算 80 万" for item in clarified["evidence"])


def test_correction_then_later_clarification_keeps_full_context(client):
    analyze_response = client.post(
        "/analyze",
        json={
            "input_text": "客户说客服工单处理慢，预算大概 30 万，问了报价，走采购流程。最终审批人没确认。",
            "provider": "mock",
        },
    )
    assert analyze_response.status_code == 200
    analysis_id = analyze_response.json()["analysis_id"]
    assert analyze_response.json()["stage"]["code"] == "S3"
    assert analyze_response.json()["crm_fields"]["budget"]["value"] == "30 万"

    correction_response = client.post(
        "/clarify",
        json={
            "analysis_id": analysis_id,
            "answers": [{"question_id": "修正识别：预算", "answer": "我原文写错了，客户实际预算是 80 万。"}],
        },
    )
    assert correction_response.status_code == 200
    corrected = correction_response.json()
    assert corrected["revision"] == 2
    assert corrected["stage"]["code"] == "S3"
    assert corrected["crm_fields"]["budget"]["status"] == "confirmed"
    assert corrected["crm_fields"]["budget"]["value"] == "80 万"

    clarification_response = client.post(
        "/clarify",
        json={
            "analysis_id": analysis_id,
            "answers": [{"question_id": "决策人", "answer": "李总拍板。"}],
        },
    )
    assert clarification_response.status_code == 200
    clarified = clarification_response.json()
    assert clarified["revision"] == 3
    assert clarified["stage"]["code"] == "S3"
    assert clarified["crm_fields"]["budget"]["status"] == "confirmed"
    assert clarified["crm_fields"]["budget"]["value"] == "80 万"
    assert clarified["crm_fields"]["decision_maker"]["name"] == "李总"
    assert not any(risk["type"] == "conflict" for risk in clarified["opportunity_risks"])

    v3 = client.get(f"/analyses/{analysis_id}/revisions/3").json()
    assert "【原始销售拜访记录】" in v3["input_text"]
    assert "【第 2 次分析修正识别事实】" in v3["input_text"]
    assert "【第 3 次分析补充确认信息】" in v3["input_text"]
    assert "Revision" not in v3["input_text"]


def test_decision_maker_correction_reanalyzes_from_new_fact(client):
    analyze_response = client.post(
        "/analyze",
        json={
            "input_text": "客户说门店客服工单处理慢。王总说下周四可以安排一次产品 Demo。",
            "provider": "mock",
        },
    )
    assert analyze_response.status_code == 200
    analysis_id = analyze_response.json()["analysis_id"]
    assert analyze_response.json()["crm_fields"]["decision_maker"]["name"] is None

    correction = "王总只是技术负责人，李总拍板。"
    clarify_response = client.post(
        "/clarify",
        json={
            "analysis_id": analysis_id,
            "answers": [{"question_id": "修正识别：决策人", "answer": correction}],
        },
    )
    assert clarify_response.status_code == 200
    clarified = clarify_response.json()
    assert clarified["revision"] == 2
    assert clarified["crm_fields"]["decision_maker"]["name"] == "李总"
    assert clarified["crm_fields"]["decision_maker"]["authority_confirmed"] is True

    v1 = client.get(f"/analyses/{analysis_id}/revisions/1").json()
    v2 = client.get(f"/analyses/{analysis_id}/revisions/2").json()
    assert v1["validated_opportunity"]["crm_fields"]["decision_maker"]["name"] is None
    assert "【第 2 次分析修正识别事实】" in v2["input_text"]
    assert "Revision" not in v2["input_text"]
    assert v2["clarification_answers"][0]["answer"] == correction


def test_unable_to_judge_is_saved_as_normal_revision(client):
    response = client.post("/analyze", json={"input_text": "客户……预算……审批……", "provider": "mock"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unable_to_judge"
    assert payload["stage"] is None
    revision = client.get(f"/analyses/{payload['analysis_id']}/revisions/1").json()
    assert revision["validated_opportunity"]["status"] == "unable_to_judge"


def test_analyze_rejects_empty_input(client):
    response = client.post("/analyze", json={"input_text": "   ", "provider": "mock"})
    assert response.status_code == 400
    assert "请输入销售拜访记录" in response.json()["detail"]
    assert client.get("/analyses").json() == []


def test_analyze_rejects_unsupported_provider_without_creating_session(client):
    response = client.post("/analyze", json={"input_text": "客户说可以安排 Demo。", "provider": "openai"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "UNSUPPORTED_PROVIDER"
    assert client.get("/analyses").json() == []


def test_missing_analysis_or_revision_returns_404(client):
    assert client.get("/analyses/not-found").status_code == 404
    assert client.get("/analyses/not-found/revisions/1").status_code == 404
    response = client.post("/clarify", json={"analysis_id": "not-found", "answers": [{"answer": "补充"}]})
    assert response.status_code == 404


def test_history_list_returns_smart_title_and_summary(client):
    text = "今天拜访了远川科技客户。客户说客服工单处理慢，希望用智能问答先覆盖售后知识库场景。王总说下周四可以安排一次产品 Demo。"
    response = client.post("/analyze", json={"input_text": text, "provider": "mock"})
    assert response.status_code == 200

    payload = client.get("/analyses").json()[0]
    assert payload["opportunity_title"] == "远川科技 · 智能问答场景"
    assert payload["summary"]
    assert payload["input_summary"]
    assert payload["updated_at"]
    assert payload["current_stage"] == "S2"


def test_delete_analysis_removes_session_and_revisions(client):
    response = client.post("/analyze", json={"input_text": "客户说客服工单处理慢。", "provider": "mock"})
    analysis_id = response.json()["analysis_id"]

    delete_response = client.delete(f"/analyses/{analysis_id}", headers={"Origin": "http://127.0.0.1:3000"})
    assert delete_response.status_code == 200
    assert delete_response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    assert delete_response.json()["deleted_count"] == 1
    assert client.get(f"/analyses/{analysis_id}").status_code == 404
    assert client.get(f"/analyses/{analysis_id}/revisions/1").status_code == 404


def test_bulk_delete_and_clear_history(client):
    ids = []
    for text in ["客户说客服工单处理慢。", "王总说下周四可以安排一次产品 Demo。", "客户……预算……审批……"]:
        ids.append(client.post("/analyze", json={"input_text": text, "provider": "mock"}).json()["analysis_id"])

    bulk_response = client.post("/analyses/bulk-delete", json={"analysis_ids": [ids[0], ids[1], ids[1], "missing"]})
    assert bulk_response.status_code == 200
    assert bulk_response.json()["deleted_count"] == 2
    remaining = client.get("/analyses").json()
    assert [item["analysis_id"] for item in remaining] == [ids[2]]

    clear_response = client.delete("/analyses", headers={"Origin": "http://127.0.0.1:3000"})
    assert clear_response.status_code == 200
    assert clear_response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    assert clear_response.json()["deleted_count"] == 1
    assert client.get("/analyses").json() == []
