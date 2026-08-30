from __future__ import annotations

import sqlite3

from backend.app.config import APP_VERSION
from backend.app.database import connect, init_db
from backend.app.pipeline import PipelineTrace
from backend.app.repository import AnalysisRepository
from backend.app.rules import build_validated_opportunity
from backend.app.schemas import (
    Attribution,
    CandidateNextAction,
    ClarifyAnswer,
    CurrentValidity,
    EvidenceCandidate,
    Explicitness,
    Polarity,
    RawExtraction,
    StageSignal,
)


def sig(signal_type: str, evidence_id: str) -> StageSignal:
    return StageSignal(signal_type=signal_type, explicitness=Explicitness.EXPLICIT, polarity=Polarity.POSITIVE, attribution=Attribution.CUSTOMER, current_validity=CurrentValidity.ACTIVE, evidence_id=evidence_id)  # type: ignore[arg-type]


def trace_for(text: str, *, analysis_id: str = "analysis-test", revision: int = 1) -> PipelineTrace:
    raw = RawExtraction(
        evidence_candidates=[EvidenceCandidate(id="E01", quote="已约下周 Demo", field="next_action")],
        candidate_next_actions=[CandidateNextAction(action="安排产品 Demo", time="下周", evidence_id="E01", attribution=Attribution.CUSTOMER, explicitness=Explicitness.EXPLICIT)],
        stage_signals=[sig("demo_agreed", "E01")],
    )
    result = build_validated_opportunity(text, raw, analysis_id=analysis_id, revision=revision)
    return PipelineTrace(result=result, raw_extraction=raw, provider="mock", model="mock-v1", latency_ms=7)


def test_init_db_creates_constraints_and_indexes(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'app.db'}"
    with connect(db_url) as conn:
        init_db(conn)
        indexes = {row[1] for row in conn.execute("PRAGMA index_list('analysis_revisions')").fetchall()}
        foreign_keys = conn.execute("PRAGMA foreign_key_list('analysis_revisions')").fetchall()
    assert "idx_analysis_revisions_analysis_revision" in indexes
    assert foreign_keys


def test_repository_creates_session_and_revision_then_lists_and_reads(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'app.db'}"
    repo = AnalysisRepository(db_url)
    trace = trace_for("已约下周 Demo")
    repo.create_session("已约下周 Demo", trace)

    items = repo.list_sessions()
    assert len(items) == 1
    assert items[0].revision_count == 1
    assert items[0].opportunity_title
    assert items[0].summary
    assert items[0].updated_at
    detail = repo.get_session("analysis-test")
    assert detail is not None
    assert detail.current_revision == 1
    assert detail.current_result.stage.code == "S2"
    revision = repo.get_revision("analysis-test", 1)
    assert revision is not None
    assert revision.raw_extraction is not None
    assert revision.pipeline_version == APP_VERSION


def test_repository_builds_v2_from_original_and_clarification_records(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'app.db'}"
    repo = AnalysisRepository(db_url)
    repo.create_session("客户有客服问题。", trace_for("客户有客服问题。"))
    answers = [ClarifyAnswer(question_id="stage", answer="已约下周 Demo。")]
    next_input = repo.build_next_revision_input("analysis-test", answers)
    assert next_input is not None
    assert next_input.revision == 2
    assert next_input.provider == "mock"
    assert "【原始销售拜访记录】" in next_input.input_text
    assert "【第 2 次分析补充确认信息】" in next_input.input_text
    assert "商机阶段确认：已约下周 Demo。" in next_input.input_text
    assert "Revision" not in next_input.input_text

    repo.save_revision("analysis-test", 2, next_input.input_text, answers, trace_for(next_input.input_text, revision=2))
    detail = repo.get_session("analysis-test")
    assert detail is not None
    assert detail.current_revision == 2
    assert len(detail.revisions) == 2
    v2 = repo.get_revision("analysis-test", 2)
    assert v2 is not None
    assert v2.clarification_answers[0].answer == "已约下周 Demo。"
    assert v2.input_text.count("【原始销售拜访记录】") == 1


def test_unique_analysis_revision_constraint(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'app.db'}"
    with connect(db_url) as conn:
        init_db(conn)
        conn.execute("INSERT INTO analysis_sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", ("a1", "now", "now", "input", "complete", "S0", 1, "mock", "mock-v1", APP_VERSION))
        payload = ("a1", 1, "now", "input", "[]", "{}", "{}", "complete", "S0", "mock", "mock-v1", APP_VERSION, 1)
        conn.execute("INSERT INTO analysis_revisions (analysis_id, revision, created_at, input_text, clarification_answers_json, raw_extraction_json, validated_opportunity_json, status, stage, provider, model, pipeline_version, latency_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", payload)
        try:
            conn.execute("INSERT INTO analysis_revisions (analysis_id, revision, created_at, input_text, clarification_answers_json, raw_extraction_json, validated_opportunity_json, status, stage, provider, model, pipeline_version, latency_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", payload)
            raised = False
        except sqlite3.IntegrityError:
            raised = True
    assert raised


def test_repository_deletes_one_session_and_cascades_revisions(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'app.db'}"
    repo = AnalysisRepository(db_url)
    repo.create_session("已约下周 Demo", trace_for("已约下周 Demo", analysis_id="a1"))
    repo.create_session("客户有客服问题", trace_for("客户有客服问题", analysis_id="a2"))

    assert repo.delete_session("a1") == 1
    assert repo.get_session("a1") is None
    assert repo.get_revision("a1", 1) is None
    assert repo.get_session("a2") is not None


def test_repository_bulk_delete_and_clear(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'app.db'}"
    repo = AnalysisRepository(db_url)
    repo.create_session("已约下周 Demo", trace_for("已约下周 Demo", analysis_id="a1"))
    repo.create_session("客户有客服问题", trace_for("客户有客服问题", analysis_id="a2"))
    repo.create_session("客户只是初步接触", trace_for("客户只是初步接触", analysis_id="a3"))

    assert repo.delete_sessions(["a1", "a2", "a2", "missing"]) == 2
    assert [item.analysis_id for item in repo.list_sessions()] == ["a3"]
    assert repo.clear_sessions() == 1
    assert repo.list_sessions() == []
