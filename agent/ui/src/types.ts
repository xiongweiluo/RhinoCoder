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
  control_scene?: SceneSnapshot | null;
  feedback_labels?: string[];
  rolled_back?: boolean;
  undo_applied?: boolean;
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
