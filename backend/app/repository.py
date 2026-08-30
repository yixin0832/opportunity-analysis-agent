from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from .config import APP_VERSION
from .database import connect, init_db
from .evidence import summarize_input
from .errors import DatabaseError
from .history_title import build_opportunity_title
from .input_builder import build_revision_input
from .pipeline import PipelineTrace
from .schemas import (
    AnalysisListItem,
    AnalysisRevisionDetail,
    AnalysisSessionDetail,
    ClarifyAnswer,
    RawExtraction,
    RevisionSummary,
    StageCode,
    ValidatedOpportunity,
)


@dataclass(frozen=True)
class NextRevisionInput:
    analysis_id: str
    revision: int
    input_text: str
    provider: str | None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _stage_value(result: ValidatedOpportunity) -> str | None:
    if result.stage is None or result.stage.code is None:
        return None
    return result.stage.code.value


def _load_answers(raw_json: str) -> list[ClarifyAnswer]:
    data = json.loads(raw_json or "[]")
    return [ClarifyAnswer.model_validate(item) for item in data]


class AnalysisRepository:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url

    def initialize(self) -> None:
        try:
            with connect(self.database_url) as conn:
                init_db(conn)
        except Exception as exc:  # pragma: no cover - exact sqlite errors are environment-specific.
            raise DatabaseError() from exc

    def create_session(self, original_input: str, trace: PipelineTrace) -> ValidatedOpportunity:
        result = trace.result
        now = utc_now_iso()
        try:
            with connect(self.database_url) as conn:
                init_db(conn)
                conn.execute("BEGIN")
                conn.execute(
                    """
                    INSERT INTO analysis_sessions (
                        analysis_id, created_at, updated_at, original_input, current_status,
                        current_stage, current_revision, provider, model, app_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result.analysis_id,
                        now,
                        now,
                        original_input,
                        result.status.value,
                        _stage_value(result),
                        result.revision,
                        trace.provider,
                        trace.model,
                        APP_VERSION,
                    ),
                )
                self._insert_revision(conn, result.analysis_id, 1, now, original_input, [], trace)
                conn.commit()
            return result
        except Exception as exc:
            raise DatabaseError() from exc

    def build_next_revision_input(self, analysis_id: str, answers: list[ClarifyAnswer]) -> NextRevisionInput | None:
        try:
            with connect(self.database_url) as conn:
                init_db(conn)
                session = conn.execute("SELECT * FROM analysis_sessions WHERE analysis_id = ?", (analysis_id,)).fetchone()
                if session is None:
                    return None
                revision_rows = conn.execute(
                    "SELECT revision, clarification_answers_json FROM analysis_revisions WHERE analysis_id = ? ORDER BY revision",
                    (analysis_id,),
                ).fetchall()
            historical_answers = [_load_answers(row["clarification_answers_json"]) for row in revision_rows if row["revision"] > 1]
            next_revision = int(session["current_revision"]) + 1
            input_text = build_revision_input(session["original_input"], historical_answers + [answers])
            return NextRevisionInput(analysis_id=analysis_id, revision=next_revision, input_text=input_text, provider=session["provider"])
        except Exception as exc:
            raise DatabaseError() from exc

    def save_revision(self, analysis_id: str, revision: int, input_text: str, answers: list[ClarifyAnswer], trace: PipelineTrace) -> ValidatedOpportunity:
        now = utc_now_iso()
        try:
            with connect(self.database_url) as conn:
                init_db(conn)
                conn.execute("BEGIN")
                session = conn.execute("SELECT current_revision FROM analysis_sessions WHERE analysis_id = ?", (analysis_id,)).fetchone()
                if session is None:
                    conn.rollback()
                    raise KeyError(analysis_id)
                expected_revision = int(session["current_revision"]) + 1
                if revision != expected_revision:
                    conn.rollback()
                    raise DatabaseError()
                self._insert_revision(conn, analysis_id, revision, now, input_text, answers, trace)
                conn.execute(
                    """
                    UPDATE analysis_sessions
                    SET updated_at = ?, current_status = ?, current_stage = ?, current_revision = ?, provider = ?, model = ?, app_version = ?
                    WHERE analysis_id = ?
                    """,
                    (
                        now,
                        trace.result.status.value,
                        _stage_value(trace.result),
                        revision,
                        trace.provider,
                        trace.model,
                        APP_VERSION,
                        analysis_id,
                    ),
                )
                conn.commit()
            return trace.result
        except KeyError:
            raise
        except DatabaseError:
            raise
        except Exception as exc:
            raise DatabaseError() from exc

    def _insert_revision(
        self,
        conn: sqlite3.Connection,
        analysis_id: str,
        revision: int,
        created_at: str,
        input_text: str,
        answers: list[ClarifyAnswer],
        trace: PipelineTrace,
    ) -> None:
        conn.execute(
            """
            INSERT INTO analysis_revisions (
                analysis_id, revision, created_at, input_text, clarification_answers_json,
                raw_extraction_json, validated_opportunity_json, status, stage, provider, model,
                pipeline_version, latency_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_id,
                revision,
                created_at,
                input_text,
                json.dumps([answer.model_dump(mode="json") for answer in answers], ensure_ascii=False),
                trace.raw_extraction.model_dump_json(),
                trace.result.model_dump_json(),
                trace.result.status.value,
                _stage_value(trace.result),
                trace.provider,
                trace.model,
                APP_VERSION,
                trace.latency_ms,
            ),
        )

    def list_sessions(self) -> list[AnalysisListItem]:
        try:
            with connect(self.database_url) as conn:
                init_db(conn)
                rows = conn.execute(
                    """
                    SELECT s.*, current_r.validated_opportunity_json, COUNT(r.id) AS revision_count
                    FROM analysis_sessions s
                    LEFT JOIN analysis_revisions r ON r.analysis_id = s.analysis_id
                    LEFT JOIN analysis_revisions current_r
                        ON current_r.analysis_id = s.analysis_id
                        AND current_r.revision = s.current_revision
                    GROUP BY s.analysis_id
                    ORDER BY s.updated_at DESC
                    """
                ).fetchall()
            items: list[AnalysisListItem] = []
            for row in rows:
                validated = ValidatedOpportunity.model_validate_json(row["validated_opportunity_json"]) if row["validated_opportunity_json"] else None
                title = build_opportunity_title(row["original_input"], validated) if validated else summarize_input(row["original_input"], max_len=24)
                items.append(
                    AnalysisListItem(
                        analysis_id=row["analysis_id"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                        opportunity_title=title,
                        summary=validated.summary if validated else summarize_input(row["original_input"]),
                        input_summary=summarize_input(row["original_input"]),
                        current_stage=StageCode(row["current_stage"]) if row["current_stage"] else None,
                        current_status=row["current_status"],
                        revision_count=row["revision_count"],
                    )
                )
            return items
        except Exception as exc:
            raise DatabaseError() from exc

    def delete_session(self, analysis_id: str) -> int:
        try:
            with connect(self.database_url) as conn:
                init_db(conn)
                cursor = conn.execute("DELETE FROM analysis_sessions WHERE analysis_id = ?", (analysis_id,))
                conn.commit()
                return cursor.rowcount
        except Exception as exc:
            raise DatabaseError() from exc

    def delete_sessions(self, analysis_ids: list[str]) -> int:
        unique_ids = [analysis_id for analysis_id in dict.fromkeys(analysis_ids) if analysis_id]
        if not unique_ids:
            return 0
        try:
            with connect(self.database_url) as conn:
                init_db(conn)
                cursor = conn.executemany("DELETE FROM analysis_sessions WHERE analysis_id = ?", [(analysis_id,) for analysis_id in unique_ids])
                conn.commit()
                return cursor.rowcount
        except Exception as exc:
            raise DatabaseError() from exc

    def clear_sessions(self) -> int:
        try:
            with connect(self.database_url) as conn:
                init_db(conn)
                cursor = conn.execute("DELETE FROM analysis_sessions")
                conn.commit()
                return cursor.rowcount
        except Exception as exc:
            raise DatabaseError() from exc

    def get_session(self, analysis_id: str) -> AnalysisSessionDetail | None:
        try:
            with connect(self.database_url) as conn:
                init_db(conn)
                session = conn.execute("SELECT * FROM analysis_sessions WHERE analysis_id = ?", (analysis_id,)).fetchone()
                if session is None:
                    return None
                revisions = conn.execute(
                    "SELECT * FROM analysis_revisions WHERE analysis_id = ? ORDER BY revision",
                    (analysis_id,),
                ).fetchall()
            current_row = next(row for row in revisions if row["revision"] == session["current_revision"])
            return AnalysisSessionDetail(
                analysis_id=session["analysis_id"],
                created_at=session["created_at"],
                updated_at=session["updated_at"],
                original_input=session["original_input"],
                current_status=session["current_status"],
                current_stage=StageCode(session["current_stage"]) if session["current_stage"] else None,
                current_revision=session["current_revision"],
                provider=session["provider"],
                model=session["model"],
                app_version=session["app_version"],
                current_result=ValidatedOpportunity.model_validate_json(current_row["validated_opportunity_json"]),
                revisions=[
                    RevisionSummary(
                        revision=row["revision"],
                        created_at=row["created_at"],
                        input_summary=summarize_input(row["input_text"]),
                        status=row["status"],
                        stage=StageCode(row["stage"]) if row["stage"] else None,
                    )
                    for row in revisions
                ],
            )
        except Exception as exc:
            raise DatabaseError() from exc

    def get_revision(self, analysis_id: str, revision: int) -> AnalysisRevisionDetail | None:
        try:
            with connect(self.database_url) as conn:
                init_db(conn)
                row = conn.execute(
                    "SELECT * FROM analysis_revisions WHERE analysis_id = ? AND revision = ?",
                    (analysis_id, revision),
                ).fetchone()
                if row is None:
                    return None
            return AnalysisRevisionDetail(
                analysis_id=row["analysis_id"],
                revision=row["revision"],
                created_at=row["created_at"],
                input_text=row["input_text"],
                clarification_answers=_load_answers(row["clarification_answers_json"]),
                validated_opportunity=ValidatedOpportunity.model_validate_json(row["validated_opportunity_json"]),
                raw_extraction=RawExtraction.model_validate_json(row["raw_extraction_json"]),
                provider=row["provider"],
                model=row["model"],
                pipeline_version=row["pipeline_version"],
                latency_ms=row["latency_ms"],
            )
        except Exception as exc:
            raise DatabaseError() from exc
