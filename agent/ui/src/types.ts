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
