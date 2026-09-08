export type AgentEvent = {
  type: string;
  run_id: string;
  seq: number;
  timestamp: string;
  payload: Record<string, unknown>;
  replay?: boolean;
};

export type HistoryItem = {
  run_id: string;
  prompt: string;
  closed_loop: boolean;
  status: string;
  metrics: Record<string, number | string>;
  created_object_ids: string[];
  events: AgentEvent[];
  route_decision?: RouteDecision | null;
  privacy_decision?: PrivacyDecision | null;
  control_scene?: SceneSnapshot | null;
  feedback_labels?: string[];
  rolled_back?: boolean;
  undo_applied?: boolean;
  scene_before?: SceneSnapshot | null;
  scene_after?: SceneSnapshot | null;
  scene_capture_error?: string | null;
  evaluation?: SceneEvaluation | null;
  demo_scenario_id?: string | null;
  is_replay?: boolean;
  audit_summary?: AuditSummary;
};

export type RouteDecision = {
  selected_backend: string;
  selected_model: string;
  privacy_level: string;
  task_difficulty: number;
  tool_complexity: number;
  reason: string;
  fallback_from?: string | null;
  fallback_error_code?: string | null;
  degraded: boolean;
};

export type PrivacyDecision = {
  decision_id: string;
  risk: string;
  action: string;
  reason_codes: string[];
  reasons: string[];
  cloud_allowed: boolean;
  requires_minimization: boolean;
};

export type SceneSnapshot = {
  objects: SceneObject[];
  total: number;
  capped: boolean;
};

export type SceneObject = {
  object_id: string;
  name: string;
  type: string;
  center: number[];
  size: number[];
  color: number[];
  layer: string;
  groups: string[];
};

export type DemoEvidence = {
  label: string;
  path: string;
  href: string;
};

export type DemoScenario = {
  id: string;
  title: string;
  kicker: string;
  goal: string;
  input: string;
  expected: string[];
  replay: string;
  evidence: DemoEvidence;
  read_only_url: string;
};

export type AssertionResult = {
  spec: Record<string, unknown>;
  ok: boolean;
  reason: string;
};

export type SceneEvaluation = {
  score: number;
  passed: boolean;
  partial: boolean;
  results: AssertionResult[];
  failed_reasons: string[];
};

export type AuditSummary = {
  provenance?: string;
  privacy_reviewed?: boolean;
  contains_real_trace_data?: boolean;
  browser_payload: string;
  raw_trace_exposed: boolean;
  object_ids: string;
  event_count: number;
};

export type ReplayPayload = {
  name: string;
  scenario: DemoScenario;
  events: AgentEvent[];
  scene_before: SceneSnapshot;
  scene_after: SceneSnapshot;
  read_only: true;
  audit_summary: AuditSummary;
};
