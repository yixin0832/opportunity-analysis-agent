export type FieldStatus = "confirmed" | "inferred" | "unknown" | "conflict" | "partial";
export type DecisionStatus = "complete" | "need_confirmation" | "unable_to_judge";
export type StageCode = "S0" | "S1" | "S2" | "S3" | "S4" | "S5";

export interface Evidence {
  id: string;
  quote: string;
  field: string;
}

export interface ValidatedField<T = unknown> {
  value: T | null;
  status: FieldStatus;
  evidence_ids: string[];
  conflicting_values?: unknown[];
  reason?: string | null;
}

export interface ValidatedPerson {
  name: string | null;
  role: string | null;
  status: FieldStatus;
  authority_confirmed: boolean;
  evidence_ids: string[];
  reason?: string | null;
}

export interface StageResult {
  code: StageCode | null;
  label: string | null;
  evidence_status: "sufficient" | "insufficient" | "conflicting";
  reason: string;
  evidence_ids: string[];
}

export interface OpportunityRisk {
  type: string;
  severity: "high" | "medium" | "low";
  description: string;
  evidence_ids: string[];
}

export interface AnalysisWarning {
  type: string;
  severity: "high" | "medium" | "low";
  description: string;
  evidence_ids: string[];
}

export interface ConfirmedNextAction {
  action: string;
  owner: string;
  time: string;
  type: "customer_confirmed";
  evidence_ids: string[];
}

export interface RecommendedNextAction {
  action: string;
  owner: string;
  time: string;
  type: "ai_recommended";
  reason: string;
}

export interface ClarificationQuestion {
  field: string;
  question: string;
  priority: "high" | "medium" | "low";
  reason: string;
}

export interface Clarification {
  needed: boolean;
  questions: ClarificationQuestion[];
  max_questions: number;
}

export interface CrmFields {
  customer_needs: ValidatedField<string>[];
  core_scenarios: ValidatedField<string>[];
  budget: ValidatedField<string>;
  decision_maker: ValidatedPerson;
  influencers: ValidatedPerson[];
  timeline: ValidatedField<string>;
}

export interface ValidatedOpportunity {
  analysis_id: string;
  revision: number;
  status: DecisionStatus;
  summary: string;
  stage: StageResult | null;
  crm_fields: CrmFields;
  opportunity_risks: OpportunityRisk[];
  analysis_warnings: AnalysisWarning[];
  confirmed_next_action: ConfirmedNextAction | null;
  recommended_next_actions: RecommendedNextAction[];
  unconfirmed_info: ValidatedField<string>[];
  evidence: Evidence[];
  clarification: Clarification | null;
}

export interface ExampleInput {
  id: string;
  title: string;
  description: string;
  input_text: string;
}

export interface AnalysisListItem {
  analysis_id: string;
  created_at: string;
  updated_at: string;
  opportunity_title: string;
  summary: string;
  input_summary: string;
  current_stage: StageCode | null;
  current_status: DecisionStatus;
  revision_count: number;
}

export interface DeleteResult {
  deleted_count: number;
}

export interface RevisionSummary {
  revision: number;
  created_at: string;
  input_summary: string;
  status: DecisionStatus;
  stage: StageCode | null;
}

export interface AnalysisSessionDetail {
  analysis_id: string;
  created_at: string;
  updated_at: string;
  original_input: string;
  current_status: DecisionStatus;
  current_stage: StageCode | null;
  current_revision: number;
  current_result: ValidatedOpportunity;
  revisions: RevisionSummary[];
}

export interface AnalysisRevisionDetail {
  analysis_id: string;
  revision: number;
  created_at: string;
  input_text: string;
  validated_opportunity: ValidatedOpportunity;
}

export interface ApiErrorPayload {
  error?: {
    code?: string;
    message?: string;
    retryable?: boolean;
  };
  detail?: string;
}
