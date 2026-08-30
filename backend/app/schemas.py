from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class Explicitness(StrEnum):
    EXPLICIT = "explicit"
    AMBIGUOUS = "ambiguous"


class Polarity(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class Attribution(StrEnum):
    CUSTOMER = "customer"
    SALES = "sales"
    THIRD_PARTY = "third_party"
    UNKNOWN = "unknown"


class CurrentValidity(StrEnum):
    ACTIVE = "active"
    HISTORICAL = "historical"
    INVALIDATED = "invalidated"
    UNKNOWN = "unknown"


class FieldStatus(StrEnum):
    CONFIRMED = "confirmed"
    INFERRED = "inferred"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"
    PARTIAL = "partial"


class DecisionStatus(StrEnum):
    COMPLETE = "complete"
    NEED_CONFIRMATION = "need_confirmation"
    UNABLE_TO_JUDGE = "unable_to_judge"


class StageCode(StrEnum):
    S0 = "S0"
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"
    S5 = "S5"


STAGE_LABELS: dict[StageCode, str] = {
    StageCode.S0: "线索",
    StageCode.S1: "需求初探",
    StageCode.S2: "方案验证",
    StageCode.S3: "商务评估",
    StageCode.S4: "决策审批",
    StageCode.S5: "赢单签约",
}


class EvidenceCandidate(BaseModel):
    id: str
    quote: str
    field: str
    start_char: int | None = None
    end_char: int | None = None


class Evidence(BaseModel):
    id: str
    quote: str
    start_char: int | None = None
    end_char: int | None = None
    field: str
    valid: bool
    sufficient: bool = True
    insufficiency_reason: str | None = None


class CandidateFact(BaseModel):
    value: str
    evidence_id: str | None = None
    attribution: Attribution = Attribution.UNKNOWN
    explicitness: Explicitness = Explicitness.AMBIGUOUS
    polarity: Polarity = Polarity.POSITIVE
    current_validity: CurrentValidity = CurrentValidity.UNKNOWN


class CandidatePerson(BaseModel):
    name: str | None = None
    role: str | None = None
    kind: Literal["decision_maker", "influencer", "unknown"] = "unknown"
    authority_confirmed: bool = False
    evidence_id: str | None = None
    attribution: Attribution = Attribution.UNKNOWN
    explicitness: Explicitness = Explicitness.AMBIGUOUS


class CandidateNextAction(BaseModel):
    action: str
    owner: str | None = None
    time: str | None = None
    evidence_id: str | None = None
    attribution: Attribution = Attribution.UNKNOWN
    explicitness: Explicitness = Explicitness.AMBIGUOUS


class StageSignal(BaseModel):
    signal_type: Literal[
        "need_identified",
        "demo_agreed",
        "trial_agreed",
        "technical_exchange_agreed",
        "solution_evaluation",
        "budget_discussed",
        "quote_discussed",
        "procurement_discussed",
        "contract_terms_discussed",
        "internal_project_approval",
        "vendor_decision",
        "contract_signed",
        "order_confirmed",
        "demand_invalidated",
        "budget_unavailable",
        "demand_delayed",
    ]
    explicitness: Explicitness
    polarity: Polarity
    attribution: Attribution
    current_validity: CurrentValidity
    evidence_id: str | None = None


class PossibleConflict(BaseModel):
    field: str
    description: str
    evidence_ids: list[str] = Field(default_factory=list)


class RawExtraction(BaseModel):
    candidate_needs: list[CandidateFact] = Field(default_factory=list)
    candidate_scenarios: list[CandidateFact] = Field(default_factory=list)
    candidate_budget: list[CandidateFact] = Field(default_factory=list)
    candidate_people: list[CandidatePerson] = Field(default_factory=list)
    candidate_timeline: list[CandidateFact] = Field(default_factory=list)
    candidate_next_actions: list[CandidateNextAction] = Field(default_factory=list)
    stage_signals: list[StageSignal] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    possible_conflicts: list[PossibleConflict] = Field(default_factory=list)
    evidence_candidates: list[EvidenceCandidate] = Field(default_factory=list)




class AnalyzeRequest(BaseModel):
    input_text: str = Field(min_length=1)
    provider: str | None = None


class ClarifyAnswer(BaseModel):
    question_id: str | None = None
    answer: str


class ClarifyRequest(BaseModel):
    analysis_id: str
    answers: list[ClarifyAnswer]


class ExampleInput(BaseModel):
    id: str
    title: str
    description: str
    input_text: str

class ValidatedField(BaseModel):
    value: Any = None
    status: FieldStatus = FieldStatus.UNKNOWN
    evidence_ids: list[str] = Field(default_factory=list)
    conflicting_values: list[Any] = Field(default_factory=list)
    reason: str | None = None


class ValidatedPerson(BaseModel):
    name: str | None = None
    role: str | None = None
    status: FieldStatus = FieldStatus.UNKNOWN
    authority_confirmed: bool = False
    evidence_ids: list[str] = Field(default_factory=list)
    reason: str | None = None


class StageResult(BaseModel):
    code: StageCode | None = None
    label: str | None = None
    evidence_status: Literal["sufficient", "insufficient", "conflicting"]
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)


class OpportunityRisk(BaseModel):
    type: Literal[
        "missing_budget",
        "unknown_decision_authority",
        "conflict",
        "demand_invalidated",
        "budget_unavailable",
        "demand_delayed",
        "unclear_timeline",
        "unknown_procurement_process",
    ]
    severity: Literal["high", "medium", "low"]
    description: str
    evidence_ids: list[str] = Field(default_factory=list)


class AnalysisWarning(BaseModel):
    type: Literal["insufficient_input", "weak_evidence"]
    severity: Literal["high", "medium", "low"]
    description: str
    evidence_ids: list[str] = Field(default_factory=list)


class ConfirmedNextAction(BaseModel):
    action: str
    owner: str
    time: str
    type: Literal["customer_confirmed"] = "customer_confirmed"
    evidence_ids: list[str]


class RecommendedNextAction(BaseModel):
    action: str
    owner: str
    time: str
    type: Literal["ai_recommended"] = "ai_recommended"
    reason: str


class ClarificationQuestion(BaseModel):
    field: str
    question: str
    priority: Literal["high", "medium", "low"]
    reason: str


class Clarification(BaseModel):
    needed: bool
    questions: list[ClarificationQuestion] = Field(default_factory=list)
    max_questions: int = 3


class CrmFields(BaseModel):
    customer_needs: list[ValidatedField] = Field(default_factory=list)
    core_scenarios: list[ValidatedField] = Field(default_factory=list)
    budget: ValidatedField = Field(default_factory=ValidatedField)
    decision_maker: ValidatedPerson = Field(default_factory=ValidatedPerson)
    influencers: list[ValidatedPerson] = Field(default_factory=list)
    timeline: ValidatedField = Field(default_factory=ValidatedField)


class ValidatedOpportunity(BaseModel):
    analysis_id: str
    revision: int
    status: DecisionStatus
    summary: str
    stage: StageResult | None = None
    crm_fields: CrmFields
    opportunity_risks: list[OpportunityRisk] = Field(default_factory=list)
    analysis_warnings: list[AnalysisWarning] = Field(default_factory=list)
    confirmed_next_action: ConfirmedNextAction | None = None
    recommended_next_actions: list[RecommendedNextAction] = Field(default_factory=list)
    unconfirmed_info: list[ValidatedField] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    clarification: Clarification | None = None
    developer_details: dict[str, Any] = Field(default_factory=dict)



class AnalysisListItem(BaseModel):
    analysis_id: str
    created_at: str
    updated_at: str
    opportunity_title: str
    summary: str
    input_summary: str
    current_stage: StageCode | None = None
    current_status: DecisionStatus
    revision_count: int


class BulkDeleteRequest(BaseModel):
    analysis_ids: list[str] = Field(default_factory=list)


class DeleteResult(BaseModel):
    deleted_count: int

class RevisionSummary(BaseModel):
    revision: int
    created_at: str
    input_summary: str
    status: DecisionStatus
    stage: StageCode | None = None


class AnalysisSessionDetail(BaseModel):
    analysis_id: str
    created_at: str
    updated_at: str
    original_input: str
    current_status: DecisionStatus
    current_stage: StageCode | None = None
    current_revision: int
    provider: str
    model: str
    app_version: str
    current_result: ValidatedOpportunity
    revisions: list[RevisionSummary] = Field(default_factory=list)


class AnalysisRevisionDetail(BaseModel):
    analysis_id: str
    revision: int
    created_at: str
    input_text: str
    clarification_answers: list[ClarifyAnswer] = Field(default_factory=list)
    validated_opportunity: ValidatedOpportunity
    raw_extraction: RawExtraction | None = None
    provider: str
    model: str
    pipeline_version: str
    latency_ms: int | None = None
