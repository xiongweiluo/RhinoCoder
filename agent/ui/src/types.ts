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
  control_scene?: SceneSnapshot | null;
  feedback_labels?: string[];
  rolled_back?: boolean;
  undo_applied?: boolean;
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
