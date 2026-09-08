import catalog from "../../../docs/demo/p1-scenarios.json";
import basicStack from "../../../eval/replays/basic_stack.json";
import selfCorrection from "../../../eval/replays/self_correction.json";
import tableGroup from "../../../eval/replays/table_group.json";
import type {AgentEvent, DemoScenario, ReplayPayload, SceneSnapshot} from "./types";

const REPOSITORY_DOCS = "https://github.com/xiongweiluo/RhinoCoder/blob/main/docs";
const EMAIL = /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi;

type ReplaySource = {
  name: string;
  demo_scenario: string;
  privacy?: {
    reviewed?: boolean;
    contains_real_trace_data?: boolean;
  };
  scene_before?: SceneSnapshot;
  scene_after?: SceneSnapshot;
  events: AgentEvent[];
};

const replaySources = {
  "basic_stack.json": basicStack,
  "self_correction.json": selfCorrection,
  "table_group.json": tableGroup,
} as unknown as Record<string, ReplaySource>;

export const STATIC_DEMO_SCENARIOS: DemoScenario[] = catalog.scenarios.map((scenario) => ({
  id: scenario.id,
  title: scenario.title,
  kicker: scenario.kicker,
  goal: scenario.goal,
  input: scenario.input.replace(EMAIL, "<EMAIL_REDACTED>"),
  expected: scenario.expected,
  replay: scenario.replay,
  evidence: {
    ...scenario.evidence,
    href: `${REPOSITORY_DOCS}/${scenario.evidence.path}`,
  },
  read_only_url: `/?demo=${scenario.id}&mode=replay`,
}));

function sceneFromEvents(events: AgentEvent[]): SceneSnapshot {
  const event = [...events].reverse().find((item) => item.type === "scene.checked");
  return (event?.payload.scene_summary as SceneSnapshot | undefined)
    ?? {objects: [], total: 0, capped: false};
}

export function getStaticReplay(scenario: DemoScenario): ReplayPayload {
  const source = replaySources[scenario.replay];
  if (!source || source.demo_scenario !== scenario.id) {
    throw new Error("Replay 与公开场景清单不一致");
  }
  const events = source.events.map((event) => ({...event, replay: true}));
  return {
    name: source.name,
    scenario,
    events,
    scene_before: source.scene_before ?? {objects: [], total: 0, capped: false},
    scene_after: source.scene_after ?? sceneFromEvents(events),
    read_only: true,
    audit_summary: {
      provenance: "synthetic",
      privacy_reviewed: source.privacy?.reviewed === true,
      contains_real_trace_data: source.privacy?.contains_real_trace_data === true,
      browser_payload: "minimized",
      raw_trace_exposed: false,
      object_ids: "pseudonymized",
      event_count: events.length,
    },
  };
}
