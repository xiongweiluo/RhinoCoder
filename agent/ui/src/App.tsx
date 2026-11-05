import { FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  AgentEvent,
  AuditSummary,
  DemoScenario,
  HistoryItem,
  PrivacyDecision,
  ReplayPayload,
  RouteDecision,
  SceneObject,
  SceneSnapshot,
} from "./types";
import {getStaticReplay, STATIC_DEMO_SCENARIOS} from "./publicReplayData";

const EMPTY_SCENE: SceneSnapshot = {objects: [], total: 0, capped: false};
const HOSTED_PUBLIC_DEMO = import.meta.env.MODE === "public";
const TERMINAL_TYPES = new Set(["run.completed", "run.failed", "run.cancelled"]);
const EVENT_FILTERS = ["key", "all", "decision", "execution", "verification", "recovery"] as const;
type EventFilter = typeof EVENT_FILTERS[number];
type PlaybackState = "idle" | "loading" | "playing" | "complete" | "error";
type SceneMode = "shaded" | "wireframe";
type ActiveRun = {
  run_id: string;
  events: AgentEvent[];
  scene_before?: SceneSnapshot | null;
  demo_scenario_id?: string | null;
};

function wsUrl() {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${location.host}/ws`;
}

function eventGroup(type: string): Exclude<EventFilter, "all"> {
  if (type.startsWith("semantic.verification")) return "verification";
  if (type.startsWith("semantic.geometry")) return "execution";
  if (type.startsWith("privacy.") || type.startsWith("route.")) return "decision";
  if (type.startsWith("scene.") || type.startsWith("assertion.")) return "verification";
  if (type.startsWith("correction.") || type.includes("failed") || type.includes("cancelled")) return "recovery";
  return "execution";
}

function eventLabel(type: string) {
  const labels: Record<string, string> = {
    "run.started": "Run started",
    "privacy.assessed": "Privacy assessment",
    "privacy.blocked": "Blocked locally",
    "route.selected": "Route selected",
    "route.fallback": "Safe fallback",
    "planning.started": "Planning",
    "tool.started": "Tool call",
    "tool.completed": "Tool result",
    "scene.checked": "Scene readback",
    "assertion.checked": "Geometry assertion",
    "correction.started": "Correction started",
    "run.completed": "Run completed",
    "run.failed": "Run failed",
    "run.cancelled": "Run cancelled",
    "semantic.geometry": "Geometry execution",
    "semantic.verification": "Programmatic verification",
  };
  return labels[type] ?? type;
}

function statusLabel(status: string) {
  return ({
    idle: "Ready",
    loading: "Loading",
    playing: "Playing Replay",
    running: "Running",
    completed: "Passed",
    failed: "Failed",
    cancelled: "Cancelled",
    offline: "Offline",
  } as Record<string, string>)[status] ?? status;
}

function filterLabel(filter: EventFilter) {
  return ({key: "Key events", all: "All", decision: "Decisions", execution: "Execution", verification: "Verification", recovery: "Recovery"})[filter];
}

function scenarioOutcome(id: string) {
  return ({
    "normal-loop": "VERIFIED",
    "self-correction": "RECOVERED",
    "privacy-route": "MINIMIZED",
  } as Record<string, string>)[id] ?? "VERIFIED";
}

function semanticEvents(events: AgentEvent[]): AgentEvent[] {
  const output: AgentEvent[] = [];
  let toolBatch: AgentEvent[] = [];
  let assertionBatch: AgentEvent[] = [];
  let correctionSeen = false;

  const flushTools = () => {
    if (!toolBatch.length) return;
    const tools = toolBatch.map((event) => String(event.payload.name ?? event.payload.tool ?? "tool"));
    const success = toolBatch.every((event) => event.payload.success !== false);
    output.push({
      ...toolBatch.at(-1)!,
      type: "semantic.geometry",
      payload: {
        name: success ? "Geometry created or updated" : "Geometry operation failed",
        tools,
        success,
        duration_ms: toolBatch.reduce((total, event) => total + Number(event.payload.duration_ms ?? 0), 0),
      },
    });
    toolBatch = [];
  };

  const flushAssertions = () => {
    if (!assertionBatch.length) return;
    const passed = assertionBatch.filter((event) => event.payload.success === true).length;
    const success = passed === assertionBatch.length;
    output.push({
      ...assertionBatch.at(-1)!,
      type: "semantic.verification",
      payload: {
        name: success ? "Scene verified" : "Verification mismatch",
        success,
        passed,
        total: assertionBatch.length,
      },
    });
    assertionBatch = [];
  };

  for (const event of events) {
    if (event.type === "tool.completed") {
      flushAssertions();
      toolBatch.push(event);
      continue;
    }
    if (event.type === "assertion.checked") {
      flushTools();
      assertionBatch.push(event);
      continue;
    }
    flushTools();
    flushAssertions();
    if (["run.started", "privacy.assessed", "privacy.blocked", "route.selected", "route.fallback", "scene.checked", "correction.started", "run.failed", "run.cancelled"].includes(event.type)) {
      output.push(event.type === "scene.checked" ? {
        ...event,
        payload: {
          ...event.payload,
          name: correctionSeen ? "Scene re-read" : "Scene read",
          re_read: correctionSeen,
        },
      } : event);
      if (event.type === "correction.started") correctionSeen = true;
    }
  }
  flushTools();
  flushAssertions();
  return output;
}

function historyFromReplay(payload: ReplayPayload): HistoryItem {
  const terminal = [...payload.events].reverse().find((event) => TERMINAL_TYPES.has(event.type));
  const routeEvent = [...payload.events].reverse().find((event) => event.type === "route.fallback" || event.type === "route.selected");
  const privacyEvent = [...payload.events].reverse().find((event) => event.type.startsWith("privacy."));
  return {
    run_id: payload.events[0]?.run_id ?? `replay-${payload.scenario.id}`,
    prompt: payload.scenario.input,
    closed_loop: true,
    status: terminal?.type.replace("run.", "") ?? "completed",
    metrics: (terminal?.payload.metrics ?? {}) as Record<string, number | string>,
    created_object_ids: [],
    events: payload.events,
    route_decision: routeEvent?.payload as unknown as RouteDecision | undefined,
    privacy_decision: privacyEvent?.payload as unknown as PrivacyDecision | undefined,
    scene_before: payload.scene_before,
    scene_after: payload.scene_after,
    demo_scenario_id: payload.scenario.id,
    is_replay: true,
    audit_summary: payload.audit_summary,
  };
}

function formatSummaryDuration(duration?: number) {
  if (duration === undefined) return "--";
  return `${(duration / 1000).toFixed(1)} s`;
}

export default function App() {
  const initialParams = useMemo(() => new URLSearchParams(location.search), []);
  const initialDemo = initialParams.get("demo") ?? (HOSTED_PUBLIC_DEMO ? "normal-loop" : "");
  const publicReplayMode = HOSTED_PUBLIC_DEMO || initialParams.get("mode") === "replay" || Boolean(initialDemo);
  const [connected, setConnected] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [closedLoop, setClosedLoop] = useState(true);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [replayHistory, setReplayHistory] = useState<HistoryItem[]>([]);
  const [currentRun, setCurrentRun] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [sceneBeforeOverride, setSceneBeforeOverride] = useState<SceneSnapshot | null>(null);
  const [sceneAfterOverride, setSceneAfterOverride] = useState<SceneSnapshot | null>(null);
  const [scenarios, setScenarios] = useState<DemoScenario[]>(HOSTED_PUBLIC_DEMO ? STATIC_DEMO_SCENARIOS : []);
  const [selectedScenarioId, setSelectedScenarioId] = useState(initialDemo);
  const [playbackState, setPlaybackState] = useState<PlaybackState>("idle");
  const [historyQuery, setHistoryQuery] = useState("");
  const [historyFilter, setHistoryFilter] = useState("all");
  const [eventFilter, setEventFilter] = useState<EventFilter>(publicReplayMode ? "key" : "all");
  const [sceneMode, setSceneMode] = useState<SceneMode>("shaded");
  const socketRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);
  const currentRunRef = useRef("");
  const playbackTokenRef = useRef(0);
  const initialReplayLoaded = useRef(false);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const searchRef = useRef<HTMLInputElement | null>(null);

  const chooseRun = useCallback((runId: string) => {
    currentRunRef.current = runId;
    setCurrentRun(runId);
  }, []);

  const playReplay = useCallback(async (scenario: DemoScenario) => {
    const token = ++playbackTokenRef.current;
    setSelectedScenarioId(scenario.id);
    setPrompt(scenario.input);
    setError("");
    setNotice("");
    setPlaybackState("loading");
    setEvents([]);
    setSceneBeforeOverride(null);
    setSceneAfterOverride(null);
    try {
      let payload: ReplayPayload;
      if (HOSTED_PUBLIC_DEMO) {
        payload = getStaticReplay(scenario);
      } else {
        const response = await fetch(`/api/replays/${encodeURIComponent(scenario.replay)}`);
        if (!response.ok) throw new Error(`Failed to load Replay (${response.status})`);
        payload = await response.json() as ReplayPayload;
      }
      if (!payload.read_only || payload.scenario.id !== scenario.id) {
        throw new Error("Replay does not match the public scenario catalog");
      }
      const runId = payload.events[0]?.run_id ?? `replay-${scenario.id}`;
      chooseRun(runId);
      setSceneBeforeOverride(payload.scene_before ?? EMPTY_SCENE);
      setPlaybackState("playing");
      for (const event of payload.events) {
        if (playbackTokenRef.current !== token) return;
        setEvents((previous) => [...previous, {...event, replay: true}]);
        await new Promise((resolve) => window.setTimeout(resolve, 55));
      }
      if (playbackTokenRef.current !== token) return;
      setSceneAfterOverride(payload.scene_after ?? EMPTY_SCENE);
      const item = historyFromReplay(payload);
      setReplayHistory((previous) => [item, ...previous.filter((row) => row.run_id !== item.run_id)]);
      setPlaybackState("complete");
      setNotice(`${scenario.title} Replay complete: sanitized synthetic data only; no model calls, Rhino connection, or writes.`);
    } catch (reason) {
      if (playbackTokenRef.current !== token) return;
      setPlaybackState("error");
      setError(reason instanceof Error ? reason.message : "Failed to load Replay");
    }
  }, [chooseRun]);

  useEffect(() => {
    if (HOSTED_PUBLIC_DEMO) return;
    fetch("/api/demo-scenarios")
      .then((response) => {
        if (!response.ok) throw new Error(`Failed to load scenario catalog (${response.status})`);
        return response.json();
      })
      .then((data) => setScenarios((data.scenarios ?? []) as DemoScenario[]))
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Failed to load scenario catalog"));
  }, []);

  useEffect(() => {
    if (!initialDemo || initialReplayLoaded.current || scenarios.length === 0) return;
    const scenario = scenarios.find((item) => item.id === initialDemo);
    initialReplayLoaded.current = true;
    if (scenario) void playReplay(scenario);
    else setError(`Unknown public demo scenario: ${initialDemo}`);
  }, [initialDemo, playReplay, scenarios]);

  useEffect(() => {
    if (publicReplayMode) return;
    let disposed = false;
    let timer = 0;
    const connect = () => {
      const socket = new WebSocket(wsUrl());
      socketRef.current = socket;
      socket.onopen = () => { setConnected(true); retryRef.current = 0; };
      socket.onmessage = (message) => {
        const data = JSON.parse(message.data);
        if (data.type === "snapshot") {
          const nextHistory = (data.history ?? []) as HistoryItem[];
          const active = (data.active ?? []) as ActiveRun[];
          const selected = currentRunRef.current;
          const restored = active.find((run) => run.run_id === selected)
            ?? nextHistory.find((run) => run.run_id === selected)
            ?? active.at(-1)
            ?? nextHistory.at(0);
          setHistory(nextHistory);
          setEvents(restored?.events ?? []);
          setSceneBeforeOverride(restored?.scene_before ?? null);
          setSceneAfterOverride("scene_after" in (restored ?? {}) ? (restored as HistoryItem).scene_after ?? null : null);
          if (restored?.run_id) chooseRun(restored.run_id);
          return;
        }
        if (data.type === "history.updated") {
          const nextHistory = (data.history ?? []) as HistoryItem[];
          setHistory(nextHistory);
          const restored = nextHistory.find((run) => run.run_id === currentRunRef.current);
          if (restored) {
            setEvents(restored.events ?? []);
            setSceneBeforeOverride(restored.scene_before ?? null);
            setSceneAfterOverride(restored.scene_after ?? restored.control_scene ?? null);
          }
          return;
        }
        if (data.type === "run.context") {
          chooseRun(String(data.run_id));
          setSceneBeforeOverride(data.payload?.scene_before as SceneSnapshot ?? null);
          return;
        }
        if (data.type === "control.accepted") {
          chooseRun(String(data.run_id));
          if (data.action === "start" || data.action === "retry") {
            setEvents([]);
            setSceneBeforeOverride(null);
            setSceneAfterOverride(null);
          }
          return;
        }
        if (data.type === "control.completed") {
          const snapshot = data.payload?.scene_summary as SceneSnapshot | undefined;
          if (snapshot?.objects) setSceneAfterOverride(snapshot);
          setNotice(controlNotice(data.action, data.payload));
          return;
        }
        if (data.type === "control.error") {
          setError(data.payload?.message ?? "Operation failed");
          return;
        }
        if (typeof data.type === "string" && data.run_id) {
          const event = data as AgentEvent;
          chooseRun(event.run_id);
          if (event.type === "run.started") setSceneAfterOverride(null);
          setEvents((previous) => [
            ...previous.filter((item) => !(item.run_id === event.run_id && item.seq === event.seq)),
            event,
          ]);
        }
      };
      socket.onclose = () => {
        setConnected(false);
        if (!disposed) {
          const delay = Math.min(5000, 500 * 2 ** retryRef.current++);
          timer = window.setTimeout(connect, delay);
        }
      };
      socket.onerror = () => socket.close();
    };
    connect();
    return () => { disposed = true; clearTimeout(timer); socketRef.current?.close(); };
  }, [chooseRun, publicReplayMode]);

  const send = useCallback((message: Record<string, unknown>) => {
    setError("");
    setNotice("");
    if (publicReplayMode) {
      setError("Public Replay is read-only and sends no WebSocket write messages.");
      return;
    }
    if (socketRef.current?.readyState !== WebSocket.OPEN) {
      setError("The UI service is still reconnecting");
      return;
    }
    socketRef.current.send(JSON.stringify(message));
  }, [publicReplayMode]);

  const selectedScenario = scenarios.find((item) => item.id === selectedScenarioId);
  const liveScenarioId = selectedScenario?.input === prompt ? selectedScenario.id : undefined;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    send({
      type: "instruction",
      content: prompt,
      closed_loop: closedLoop,
      demo_scenario_id: liveScenarioId,
    });
  };

  const allHistory = useMemo(() => [...replayHistory, ...history], [history, replayHistory]);
  const selectHistory = (item: HistoryItem) => {
    playbackTokenRef.current += 1;
    chooseRun(item.run_id);
    setEvents(item.events ?? []);
    setSceneBeforeOverride(item.scene_before ?? null);
    setSceneAfterOverride(item.scene_after ?? item.control_scene ?? null);
    setSelectedScenarioId(item.demo_scenario_id ?? "");
    setPlaybackState(item.is_replay ? "complete" : "idle");
  };

  const currentEvents = useMemo(
    () => events.filter((event) => !currentRun || event.run_id === currentRun).sort((a, b) => a.seq - b.seq),
    [events, currentRun],
  );
  const currentHistory = allHistory.find((item) => item.run_id === currentRun);
  const latest = currentEvents.at(-1);
  const terminal = [...currentEvents].reverse().find((event) => TERMINAL_TYPES.has(event.type));
  const routeEvent = [...currentEvents].reverse().find((event) => event.type === "route.fallback" || event.type === "route.selected");
  const privacyEvent = [...currentEvents].reverse().find((event) => event.type === "privacy.blocked" || event.type === "privacy.assessed");
  const route = (routeEvent?.payload as unknown as RouteDecision | undefined) ?? currentHistory?.route_decision ?? undefined;
  const privacy = (privacyEvent?.payload as unknown as PrivacyDecision | undefined) ?? currentHistory?.privacy_decision ?? undefined;
  const metrics = ((terminal?.payload.metrics ?? currentHistory?.metrics ?? {}) as Record<string, number | string>);
  const beforeScene = sceneBeforeOverride ?? currentHistory?.scene_before ?? EMPTY_SCENE;
  const sceneEvent = [...currentEvents].reverse().find((event) => event.type === "scene.checked");
  const eventScene = (sceneEvent?.payload.scene_summary as SceneSnapshot | undefined);
  const afterScene = sceneAfterOverride ?? currentHistory?.scene_after ?? currentHistory?.control_scene ?? eventScene ?? EMPTY_SCENE;
  const assertions = currentEvents.filter((event) => event.type === "assertion.checked");
  const lastSceneSequence = [...currentEvents].reverse().find((event) => event.type === "scene.checked")?.seq ?? -1;
  const finalAssertions = assertions.filter((event) => event.seq > lastSceneSequence);
  const priorAssertions = assertions.filter((event) => event.seq <= lastSceneSequence);
  const toolEvents = currentEvents.filter((event) => event.type === "tool.completed");
  const toolErrors = toolEvents.filter((event) => event.payload.success === false).length;
  const recoveries = currentEvents.filter((event) => event.type === "correction.started" || event.type === "route.fallback").length;
  const isReplay = Boolean(currentHistory?.is_replay || latest?.replay || playbackState === "playing");
  const isRunning = Boolean(currentRun && !terminal && !isReplay);
  const runStatus = playbackState === "loading" ? "loading"
    : playbackState === "playing" ? "playing"
    : isRunning ? "running"
    : terminal?.type.replace("run.", "")
      ?? (!connected && !publicReplayMode ? "offline" : "idle");
  const canRetry = Boolean(terminal && !isReplay && connected);
  const canUndo = Boolean(connected && currentHistory && !isRunning && !currentHistory.undo_applied && !isReplay);
  const canRollback = Boolean(
    connected
    && currentHistory?.status === "completed"
    && currentHistory.created_object_ids?.length
    && !currentHistory.rolled_back
    && !isReplay,
  );
  const canFeedback = Boolean(terminal && !isReplay && connected);
  const terminalError = terminal?.type === "run.failed"
    ? terminal.payload.error as {code?: string; message?: string; recoverable?: boolean} | undefined
    : undefined;
  const visibleError = terminalError?.message ? terminalError : error ? {message: error, recoverable: true} : undefined;
  const auditSummary: AuditSummary = currentHistory?.audit_summary ?? {
    browser_payload: "minimized",
    raw_trace_exposed: false,
    object_ids: "pseudonymized",
    event_count: currentEvents.length,
  };
  const filteredEvents = eventFilter === "key"
    ? semanticEvents(currentEvents)
    : eventFilter === "all"
      ? currentEvents
      : currentEvents.filter((event) => eventGroup(event.type) === eventFilter);
  const filteredHistory = allHistory.filter((item) => {
    const query = historyQuery.trim().toLowerCase();
    const matchesQuery = !query || `${item.prompt} ${item.run_id} ${item.status} ${item.demo_scenario_id ?? ""}`.toLowerCase().includes(query);
    const matchesFilter = historyFilter === "all"
      || (historyFilter === "replay" ? item.is_replay : item.status === historyFilter);
    return matchesQuery && matchesFilter;
  });
  const metricNumber = (name: string) => typeof metrics[name] === "number" ? metrics[name] as number : undefined;
  const cost = metricNumber("estimated_cost_usd");
  const duration = metricNumber("duration_ms");
  const passedAssertions = finalAssertions.filter((event) => event.payload.success === true).length;
  const recovered = priorAssertions.some((event) => event.payload.success === false)
    && finalAssertions.length > 0
    && passedAssertions === finalAssertions.length;

  useEffect(() => {
    const onShortcut = (event: globalThis.KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const editing = target?.tagName === "INPUT" || target?.tagName === "TEXTAREA" || target?.tagName === "SELECT";
      if (event.key === "/" && !editing) {
        event.preventDefault();
        searchRef.current?.focus();
      }
      if (event.key === "Escape" && isRunning) {
        event.preventDefault();
        send({type: "cancel", run_id: currentRun});
      }
    };
    window.addEventListener("keydown", onShortcut);
    return () => window.removeEventListener("keydown", onShortcut);
  }, [currentRun, isRunning, send]);

  const composerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  };

  const prepareLiveScenario = (scenario: DemoScenario) => {
    setSelectedScenarioId(scenario.id);
    setPrompt(scenario.input);
    setNotice(`${scenario.title} is ready; run it in a blank, disposable Rhino document.`);
    window.setTimeout(() => composerRef.current?.focus(), 0);
  };

  return (
    <main className={`shell ${publicReplayMode ? "public-shell" : ""}`} id="main-content">
      <a className="skip-link" href="#evidence-chain">Skip to run evidence</a>
      <header className="topbar">
        <div className="brand-lockup"><span className="brand-token" aria-hidden="true">RC</span><div><h1>RhinoCoder</h1><p>{publicReplayMode ? "Replay Console" : "Verifiable Spatial Agent"}</p></div></div>
        <div className="topbar-actions">
          <nav className="project-links" aria-label="Project links">
            <a href="https://github.com/xiongweiluo/RhinoCoder" target="_blank" rel="noreferrer">GitHub ↗</a>
          </nav>
          <div className="demo-statuses">
            <div className={`connection ${connected ? "online" : publicReplayMode ? "readonly" : "offline"}`} role="status" aria-live="polite">
              <span />{publicReplayMode ? "Read-only demo" : connected ? "Connected" : "Reconnecting"}
            </div>
            {publicReplayMode && <span className="replay-origin" tabIndex={0} aria-describedby="synthetic-replay-help">
              Synthetic Replay <b aria-hidden="true">i</b>
              <span role="tooltip" id="synthetic-replay-help">Sanitized recorded execution. No live Rhino connection, model call, or Rhino write.</span>
            </span>}
          </div>
        </div>
      </header>

      {publicReplayMode ? (
        <section className="replay-deck" aria-label="Choose a Replay scenario">
          <div className="scenario-tabs" role="tablist" aria-label="Replay scenarios">
            {scenarios.map((scenario, index) => (
              <button
                type="button"
                role="tab"
                aria-selected={selectedScenarioId === scenario.id}
                className={selectedScenarioId === scenario.id ? "selected" : ""}
                onClick={() => void playReplay(scenario)}
                key={scenario.id}
              >
                <span>0{index + 1}</span>
                <strong>{scenario.title}</strong>
                <small className={`scenario-outcome ${scenario.id}`}>{scenarioOutcome(scenario.id)}</small>
              </button>
            ))}
          </div>
          {selectedScenario ? (
            <div className="run-brief">
              <span className="brief-label">Task</span>
              <p>{selectedScenario.input}</p>
              <details><summary>Acceptance criteria</summary><ul>{selectedScenario.expected.map((item) => <li key={item}>{item}</li>)}</ul></details>
              <a href={selectedScenario.evidence.href} target="_blank" rel="noreferrer">Source ↗</a>
            </div>
          ) : <div className="run-brief" aria-busy="true">Loading…</div>}
        </section>
      ) : (
        <>
          <section className="hero-grid" aria-labelledby="demo-heading">
            <div><span className="eyebrow">THREE FIXED DEMOS</span><h2 id="demo-heading">See the result, then explore the trace</h2><p>Choose a fixed scenario to inspect the evidence from execution to assertions.</p></div>
            <div className="hero-proof"><strong>Public demo boundary</strong><span>0 model calls</span><span>0 Rhino writes</span><span>0 raw traces</span></div>
          </section>
          <section className="scenario-grid" aria-label="Fixed demo scenarios">
            {scenarios.length === 0 && <div className="panel loading-card" aria-busy="true">Loading three demo scenarios…</div>}
            {scenarios.map((scenario, index) => (
              <article className={`scenario-card panel ${selectedScenarioId === scenario.id ? "selected" : ""}`} key={scenario.id}>
                <div className="scenario-number">0{index + 1}</div><span className="eyebrow">{scenario.kicker}</span><h3>{scenario.title}</h3><p>{scenario.goal}</p>
                <details><summary>Input and expected result</summary><code className="prompt-code">{scenario.input}</code><ul>{scenario.expected.map((item) => <li key={item}>{item}</li>)}</ul></details>
                <div className="scenario-actions"><button type="button" onClick={() => void playReplay(scenario)}>Play Replay</button><button type="button" className="ghost" onClick={() => prepareLiveScenario(scenario)}>Use in Rhino</button><a href={scenario.evidence.href} target="_blank" rel="noreferrer">Evidence ↗</a><a href={scenario.read_only_url}>Read-only link</a></div>
              </article>
            ))}
          </section>
        </>
      )}

      {!publicReplayMode ? (
        <section className="composer panel" aria-labelledby="composer-heading">
          <div className="section-title"><div><span className="eyebrow">LIVE RHINO</span><h2 id="composer-heading">Run task</h2></div><span>⌘/Ctrl + Enter to run · Esc to stop</span></div>
          <form onSubmit={submit}>
            <label className="sr-only" htmlFor="prompt">Rhino task instruction</label>
            <textarea id="prompt" ref={composerRef} value={prompt} onKeyDown={composerKeyDown} onChange={(event) => setPrompt(event.target.value)} rows={3} placeholder="Choose a fixed scenario or enter a Rhino modeling task." />
            <div className="composer-actions">
              <label><input type="checkbox" checked={closedLoop} onChange={(event) => setClosedLoop(event.target.checked)} /> Closed-loop scene verification</label>
              <div className="button-row">
                <button type="button" className="ghost" disabled={!isRunning} onClick={() => send({type: "cancel", run_id: currentRun})}>Stop</button>
                <button type="submit" disabled={!connected || !prompt.trim()}>Run task</button>
              </div>
            </div>
          </form>
        </section>
      ) : null}

      {!connected && !publicReplayMode && <div className="state-banner offline" role="status"><strong>UI service offline</strong><span>Reconnecting with exponential backoff. Read-only Replay is still available above.</span></div>}
      {notice && !publicReplayMode && <div className="state-banner success" role="status" aria-live="polite">{notice}</div>}
      {visibleError && <div className="recovery-error" role="alert">
        <div><strong>{visibleError.code ?? "Operation failed"}</strong><p>{visibleError.message}</p><small>{recoveryGuidance(visibleError.code)}</small></div>
        {visibleError.recoverable !== false && !isReplay && <button type="button" className="danger" disabled={!canRetry} onClick={() => send({type: "retry", run_id: currentRun})}>Retry</button>}
      </div>}

      <section className={`dashboard ${publicReplayMode ? "public-dashboard" : ""}`} id="evidence-chain" aria-label="Run metrics dashboard">
        <Metric label={publicReplayMode ? "Status" : "Run status"} value={statusLabel(runStatus)} tone={runStatus === "failed" ? "bad" : runStatus === "completed" ? "good" : "neutral"} />
        <Metric label="run_id" value={currentRun || "--"} mono />
        <Metric label="Privacy" value={privacy?.action ?? "--"} mono />
        <Metric label="Route" value={route?.selected_backend ?? "--"} mono />
        <Metric label="Runtime" value={publicReplayMode ? formatSummaryDuration(duration) : duration !== undefined ? `${Math.round(duration)} ms` : "--"} mono />
        {publicReplayMode ? <Metric label="Assertions" value={finalAssertions.length ? `${passedAssertions} / ${finalAssertions.length}` : "--"} tone={finalAssertions.length && passedAssertions === finalAssertions.length ? "good" : "neutral"} mono /> : <><Metric label="Cost" value={cost !== undefined ? `$${cost.toFixed(6)}` : "--"} /><Metric label="Tool errors" value={String(toolErrors)} tone={toolErrors ? "bad" : "good"} /><Metric label="Recoveries" value={String(recoveries)} tone={recoveries ? "warn" : "neutral"} /></>}
      </section>

      {!publicReplayMode && <section className={`routing panel ${route?.degraded ? "degraded" : ""}`} aria-labelledby="routing-heading">
        <div><span className="eyebrow">PRIVACY + ROUTE</span><h2 id="routing-heading">{route ? `${route.selected_backend} · ${route.selected_model}` : privacy?.action === "block" ? "Request blocked locally" : "Awaiting decision"}</h2></div>
        <p>{route?.reason ?? privacy?.reasons?.join("; ") ?? "Privacy checks precede the model and MCP. Route reasons and fallback share the run_id."}</p>
        <div className="route-signals">
          <span>Risk {privacy?.risk ?? "--"}</span><span>Action {privacy?.action ?? "--"}</span>
          <span>{privacy ? privacy.cloud_allowed ? "Minimized cloud requests allowed" : "Cloud requests blocked" : "Cloud access pending"}</span>
          <span>{route?.degraded ? `Fallback from ${route.fallback_from} · ${route.fallback_error_code}` : "No fallback"}</span>
        </div>
      </section>}

      {publicReplayMode ? <section className="spatial-workspace" aria-label="Replay spatial evidence workspace">
        <div className="panel trace-panel spatial-trace">
          <div className="section-title"><div><span className="eyebrow">RUN TRACE</span><h2>Execution timeline</h2></div><span>{filteredEvents.length}/{currentEvents.length} events</span></div>
          <div className="filter-row" role="group" aria-label="Timeline filters">
            {EVENT_FILTERS.map((filter) => <button type="button" className={eventFilter === filter ? "active" : "ghost"} aria-pressed={eventFilter === filter} onClick={() => setEventFilter(filter)} key={filter}>{filterLabel(filter)}</button>)}
          </div>
          <div className="timeline" aria-live="polite">
            {playbackState === "loading" && <Empty title="Loading Replay" text="Playback starts when the read-only data has loaded." />}
            {playbackState !== "loading" && filteredEvents.length === 0 && <Empty title="No events yet" text="Choose a scenario above to inspect its execution evidence." />}
            {filteredEvents.map((event) => <EventRow key={`${event.run_id}-${event.seq}`} event={event} />)}
          </div>
        </div>

        <section className="panel scene-stage" aria-labelledby="scene-stage-heading">
          <div className="scene-stage-head">
            <div><span className="eyebrow">SCENE RESULT</span><h2 id="scene-stage-heading">Rhino scene result</h2></div>
            <div className="scene-stage-tools">
              <span>{afterScene.total} objects</span>
              <div className="view-switch" role="group" aria-label="Scene display mode">
                <button type="button" aria-pressed={sceneMode === "shaded"} className={sceneMode === "shaded" ? "active" : ""} onClick={() => setSceneMode("shaded")}>Shaded</button>
                <button type="button" aria-pressed={sceneMode === "wireframe"} className={sceneMode === "wireframe" ? "active" : ""} onClick={() => setSceneMode("wireframe")}>Wireframe</button>
              </div>
            </div>
          </div>
          <PublicSceneCanvas scenarioId={selectedScenarioId} scene={afterScene} mode={sceneMode} />
          <div className="scene-delta" aria-label="Object count before and after">
            <div><span>BEFORE</span><strong>{beforeScene.total}</strong><small>objects</small></div>
            <i aria-hidden="true">→</i>
            <div><span>AFTER</span><strong>{afterScene.total}</strong><small>objects</small></div>
            <SceneObjectIndex scene={afterScene} />
          </div>
        </section>

        <aside className="spatial-evidence">
          <section className={`panel proof-verdict ${finalAssertions.length && passedAssertions === finalAssertions.length ? "passed" : ""} ${recovered ? "recovered" : ""}`} aria-label="Verification verdict">
            <div className="proof-status"><span className="eyebrow">VERIFICATION</span><strong>{finalAssertions.length ? recovered ? "RECOVERED" : passedAssertions === finalAssertions.length ? "VERIFIED" : "CHECK" : "—"}</strong>{recovered && <small>Verified after correction</small>}</div>
            <div className="proof-count"><b>{finalAssertions.length ? `${passedAssertions} / ${finalAssertions.length}` : "—"}</b><span>{finalAssertions.length ? recovered ? "final assertions passed" : "assertions passed" : "awaiting evidence"}</span></div>
          </section>
          <section className="panel assertion-panel" aria-labelledby="assertion-heading">
            <div className="section-title"><div><span className="eyebrow">PROGRAMMATIC PROOF</span><h2 id="assertion-heading">Why it passed</h2></div><span>EXPECTED / ACTUAL</span></div>
            {finalAssertions.length === 0 && <Empty title="No assertions yet" text="Verification results appear after Replay completes." />}
            {recovered && <div className="recovery-proof"><strong>Mismatch → correction → re-read</strong><span>The first readback failed. The agent corrected the target object, read the scene again, and checked the final assertions.</span></div>}
            <div className="assertion-list">
              {finalAssertions.slice(0, 3).map((event) => <AssertionRow event={event} key={`${event.run_id}-assert-${event.seq}`} />)}
              {finalAssertions.length > 3 && <details className="more-assertions"><summary>View {finalAssertions.length - 3} more checks</summary><div>{finalAssertions.slice(3).map((event) => <AssertionRow event={event} key={`${event.run_id}-assert-${event.seq}`} />)}</div></details>}
              {recovered && <details className="prior-assertions"><summary>View the initial mismatch evidence</summary><div>{priorAssertions.filter((event) => event.payload.success === false).map((event) => <AssertionRow event={event} key={`${event.run_id}-prior-assert-${event.seq}`} />)}</div></details>}
            </div>
          </section>
          <section className="panel scene-inspector" aria-labelledby="scene-inspector-heading">
            <div className="section-title"><div><span className="eyebrow">OBJECT INSPECTOR</span><h2 id="scene-inspector-heading">Object details</h2></div></div>
            <SceneInspector scene={afterScene} />
          </section>
        </aside>
      </section> : <section className="workspace">
        <div className="panel trace-panel">
          <div className="section-title"><div><span className="eyebrow">RUN TRACE</span><h2>Execution timeline</h2></div><span>{filteredEvents.length}/{currentEvents.length} events</span></div>
          <div className="filter-row" role="group" aria-label="Timeline filters">
            {EVENT_FILTERS.map((filter) => <button type="button" className={eventFilter === filter ? "active" : "ghost"} aria-pressed={eventFilter === filter} onClick={() => setEventFilter(filter)} key={filter}>{filterLabel(filter)}</button>)}
          </div>
          <div className="timeline" aria-live="polite">
            {playbackState === "loading" && <Empty title="Loading Replay" text="Playback starts after the read-only GET request completes." />}
            {playbackState !== "loading" && filteredEvents.length === 0 && <Empty title="No events yet" text="Play a Replay or run a task to inspect decisions, execution, verification, and recovery." />}
            {filteredEvents.map((event) => <EventRow key={`${event.run_id}-${event.seq}`} event={event} />)}
          </div>
        </div>

        <div className="right-column">
          <section className="panel comparison-panel" aria-labelledby="comparison-heading">
            <div className="section-title"><div><span className="eyebrow">BEFORE / AFTER</span><h2 id="comparison-heading">Rhino scene comparison</h2></div><span>{beforeScene.total} → {afterScene.total}</span></div>
            <div className="comparison-grid">
              <SceneColumn title="Before" scene={beforeScene} empty="Live scenarios read a baseline first. Replay starts with a declared empty synthetic scene." />
              <SceneColumn title="After" scene={afterScene} empty="The final Scene Summary has not arrived yet." />
            </div>
          </section>

          <section className="panel assertion-panel" aria-labelledby="assertion-heading">
            <div className="section-title"><div><span className="eyebrow">PROGRAMMATIC PROOF</span><h2 id="assertion-heading">Assertion details</h2></div><span>{assertions.length ? `${passedAssertions}/${assertions.length}` : "--"}</span></div>
            {assertions.length === 0 && <Empty title="No assertions yet" text="Expected values, actual values, and pass status appear when the scenario completes." />}
            <div className="assertion-list">{assertions.map((event) => <AssertionRow event={event} key={`${event.run_id}-assert-${event.seq}`} />)}</div>
          </section>

          {!publicReplayMode && <section className="panel controls" aria-labelledby="recovery-heading">
            <div className="section-title"><div><span className="eyebrow">ONE-CLICK RECOVERY</span><h2 id="recovery-heading">Recovery and feedback</h2></div></div>
            {isReplay ? <p className="control-context">Replay is read-only. All mutation controls below are disabled.</p> : <p className="control-context">Retry creates a new run_id. Undo reverses the last operation. Targeted rollback deletes only objects recorded for this task.</p>}
            <div className="button-grid">
              <button className="ghost" disabled={!canRetry} onClick={() => send({type: "retry", run_id: currentRun})}>Retry task</button>
              <button className="ghost" disabled={!canUndo} onClick={() => send({type: "undo", run_id: currentRun})}>Undo</button>
              <button className="danger" disabled={!canRollback} onClick={() => send({type: "rollback", run_id: currentRun})}>Targeted rollback</button>
              <button className="ghost" disabled={!canFeedback} onClick={() => send({type: "feedback", run_id: currentRun, label: "accepted"})}>Mark accepted</button>
              <button className="ghost" disabled={!canFeedback} onClick={() => send({type: "feedback", run_id: currentRun, label: "partial"})}>Partial</button>
              <button className="danger" disabled={!canFeedback} onClick={() => send({type: "feedback", run_id: currentRun, label: "rejected"})}>Mark rejected</button>
            </div>
            {currentHistory?.feedback_labels?.length ? <p className="feedback-state">Recorded: {currentHistory.feedback_labels.map(feedbackLabel).join(", ")}</p> : null}
          </section>}
        </div>
      </section>}

      <section className={`panel audit-panel ${publicReplayMode ? "compact" : ""}`} aria-labelledby="audit-heading">
        <div><span className="eyebrow">DATA BOUNDARY</span><h2 id="audit-heading">Privacy audit summary</h2>{selectedScenarioId === "privacy-route" && publicReplayMode ? <p className="privacy-causality"><strong>Before outbound request</strong>Sensitive fields are minimized before the outbound model request.</p> : !publicReplayMode ? <p>The browser receives only minimized display data, excluding full local traces, model messages, and real object GUIDs.</p> : null}</div>
        <div className="audit-grid">
          <AuditFact label="Payload" value={auditSummary.browser_payload} />
          <AuditFact label="Raw trace" value={auditSummary.raw_trace_exposed ? "Exposed" : "Not exposed"} good={!auditSummary.raw_trace_exposed} />
          <AuditFact label="Object IDs" value={auditSummary.object_ids} good />
          <AuditFact label="Source" value={auditSummary.provenance ?? (isReplay ? "synthetic" : "local run")} good={isReplay} />
        </div>
      </section>

      {!publicReplayMode && <section className="panel history" aria-labelledby="history-heading">
        <div className="section-title"><div><span className="eyebrow">MINIMIZED RUN INDEX</span><h2 id="history-heading">Recent Runs</h2></div><span>{filteredHistory.length}/{allHistory.length}</span></div>
        <div className="history-tools">
          <label><span className="sr-only">Search recent runs</span><input ref={searchRef} type="search" value={historyQuery} onChange={(event) => setHistoryQuery(event.target.value)} placeholder="Search instructions or run_id (shortcut /)" /></label>
          <label><span className="sr-only">Filter run status</span><select value={historyFilter} onChange={(event) => setHistoryFilter(event.target.value)}><option value="all">All statuses</option><option value="completed">Passed</option><option value="failed">Failed</option><option value="cancelled">Cancelled</option><option value="replay">Replay</option></select></label>
        </div>
        <div className="history-list">
          {filteredHistory.length === 0 && <Empty title="No matching runs" text={allHistory.length ? "Adjust the search or status filter." : "Play a Replay or run a task to create a sanitized index."} />}
          {filteredHistory.slice(0, 30).map((item) => <button type="button" className={item.run_id === currentRun ? "selected" : ""} key={`${item.is_replay ? "replay" : "live"}-${item.run_id}`} onClick={() => selectHistory(item)}><span className={`status-pill ${item.status}`}>{item.is_replay ? "REPLAY" : statusLabel(item.status)}</span><span>{item.prompt}</span><code title={item.run_id}>{item.run_id.slice(0, 12)}</code></button>)}
        </div>
      </section>}

      {publicReplayMode && <section className="panel project-status" aria-labelledby="project-status-heading">
        <div className="section-title"><div><span className="eyebrow">PROJECT UPDATE · NOV 5, 2026</span><h2 id="project-status-heading">Research progress, with clear limits</h2></div></div>
        <p>The C5 research stack and reports are merged through PR #29. Release v0.3.0 and the default hybrid route remain current; the original C4 and C5 decisions remain <strong>NO-GO</strong>.</p>
        <details><summary>Read the latest results and work under review</summary>
          <p>The frozen 80-family offline evaluation scored LoRA 77/80 versus base 20/80 on sequence exact match. Later interrupted field phases produced descriptive scores of 13/20 versus 2/20. Exposed tasks, repairs, and retained audit rejections prevent treating those field scores as a new blind test or a product-readiness claim.</p>
          <p>PRs #30 and #31 remain unmerged. Phase-one diagnosis is complete, and the owner sealed a new 40-family / 80-slot comparison set on November 1. Its receipt is validated and PR #31 CI passed; the set is unconsumed and execution is not authorized. Target-Linux CPU checks, a current resource window, and approval of the final execution plan remain pending. Full historical overlap is owner-reported, not fully machine-checked.</p>
          <p><a href="https://github.com/xiongweiluo/RhinoCoder/blob/main/docs/c5-descriptive-score-analysis-20261025.md" target="_blank" rel="noreferrer">Merged research evidence ↗</a> · <a href="https://github.com/xiongweiluo/RhinoCoder/pull/31" target="_blank" rel="noreferrer">Comparison preparation · PR #31 ↗</a></p>
        </details>
        <p>All three scenarios above are synthetic browser-only fixtures. They do not run these models or reproduce research evaluations.</p>
      </section>}

      <footer className="site-footer">
        <p>v0.3.0 · Synthetic Replay · No Rhino writes</p>
        <a href="https://github.com/xiongweiluo/RhinoCoder/releases/tag/v0.3.0" target="_blank" rel="noreferrer">Release and verification evidence ↗</a>
      </footer>
    </main>
  );
}

function Metric({label, value, tone = "neutral", mono = false}: {label: string; value: string; tone?: "neutral" | "good" | "warn" | "bad"; mono?: boolean}) {
  return <div className={`metric panel ${tone}`}><span>{label}</span><strong className={mono ? "mono" : ""}>{value}</strong></div>;
}

function Empty({title, text}: {title: string; text: string}) {
  return <div className="empty"><strong>{title}</strong><p>{text}</p></div>;
}

function EventRow({event}: {event: AgentEvent}) {
  const payload = event.payload as Record<string, unknown>;
  const failed = payload.success === false || event.type === "run.failed" || event.type === "privacy.blocked";
  const title = String(payload.name ?? payload.tool ?? eventLabel(event.type));
  const error = payload.error as {message?: string; code?: string} | string | undefined;
  const errorText = typeof error === "string" ? error : error?.message ?? "";
  const summary = eventSummary(event);
  return <article className={`event ${eventGroup(event.type)} ${failed ? "failed" : ""}`}>
    <div className="event-rail"><span className="event-dot" /><span className="event-line" /></div>
    <div><div className="event-head"><span className="event-kind">{eventLabel(event.type)}</span><time dateTime={event.timestamp}>#{event.seq}</time></div><strong>{title}</strong>{summary && <p>{summary}</p>}{errorText && <code className="event-error">{errorText}</code>}
      {payload.arguments ? <details className="event-details"><summary>View sanitized arguments</summary><code>{JSON.stringify(payload.arguments)}</code></details> : null}
    </div>
  </article>;
}

function eventSummary(event: AgentEvent) {
  const payload = event.payload as Record<string, unknown>;
  if (event.type === "semantic.geometry") return `${(payload.tools as string[] | undefined)?.join(" + ") ?? "tool"} · ${payload.success === false ? "failed" : "completed"}`;
  if (event.type === "semantic.verification") return `${payload.passed ?? 0} / ${payload.total ?? 0} assertions ${payload.success ? "passed" : "require correction"}`;
  if (event.type === "run.started") return `Input summary: ${String(payload.prompt ?? "Minimized")}`;
  if (event.type.startsWith("privacy.")) return `risk=${payload.risk ?? "--"} · action=${payload.action ?? "--"} · cloud=${payload.cloud_allowed ? "minimized/allowed" : "blocked"}`;
  if (event.type.startsWith("route.")) return `${payload.selected_backend ?? "--"} · ${payload.reason ?? "No route reason provided"}`;
  if (event.type === "planning.started") return `Planning round ${payload.round ?? "--"}`;
  if (event.type === "tool.completed") return `${payload.success === false ? "Failed" : "Success"} · ${Math.round(Number(payload.duration_ms ?? 0))} ms`;
  if (event.type === "scene.checked") {
    const scene = payload.scene_summary as SceneSnapshot | undefined;
    return `${payload.re_read === true ? "Re-read" : "Read"} ${scene?.total ?? scene?.objects?.length ?? 0} objects`;
  }
  if (event.type === "assertion.checked") return `${payload.success ? "Pass" : "Fail"} · Expected ${String(payload.expected ?? "--")}`;
  if (event.type === "correction.started") return `Round ${payload.round ?? "--"} · ${payload.reason ?? payload.tool ?? "Replan from the scene"}`;
  if (TERMINAL_TYPES.has(event.type)) {
    const metrics = payload.metrics as Record<string, unknown> | undefined;
    return `${payload.status ?? event.type.replace("run.", "")} · ${Math.round(Number(metrics?.duration_ms ?? 0))} ms`;
  }
  return "";
}

function AssertionRow({event}: {event: AgentEvent}) {
  const payload = event.payload as Record<string, unknown>;
  const ok = payload.success === true;
  return <article className={`assertion-row ${ok ? "passed" : "failed"}`}><span aria-hidden="true">{ok ? "✓" : "×"}</span><div><strong className="machine-name">{String(payload.name ?? "Geometry assertion")}</strong><dl><div><dt>Expected</dt><dd>{String(payload.expected ?? "--")}</dd></div><div><dt>Actual</dt><dd className="actual-value">{String(payload.actual ?? "--")}{ok && <b aria-label="Match">✓</b>}</dd></div></dl></div></article>;
}

function sceneObjectColor(scene: SceneSnapshot, name: string, fallback: string) {
  const object = scene.objects.find((item) => item.name.toLowerCase() === name.toLowerCase());
  return object?.color?.length === 3 ? `rgb(${object.color.join(",")})` : fallback;
}

type ProjectedBounds = {x: number; y: number; width: number; height: number};

const PROJECTED_SCENE_BOUNDS: Record<string, ProjectedBounds> = {
  "normal-loop": {x: 223, y: 161, width: 322, height: 285},
  "self-correction": {x: 256, y: 163, width: 252, height: 242},
  "privacy-route": {x: 230, y: 174, width: 318, height: 284},
};

function fittedSceneViewBox(scenarioId: string, objectCount: number) {
  const bounds = PROJECTED_SCENE_BOUNDS[scenarioId] ?? {x: 188, y: 145, width: 384, height: 310};
  const frameAspect = 760 / 520;
  const targetFill = objectCount >= 5 ? .7 : objectCount === 1 ? .56 : .64;
  let width = bounds.width / targetFill;
  let height = bounds.height / targetFill;
  if (width / height < frameAspect) width = height * frameAspect;
  else height = width / frameAspect;
  const centerX = bounds.x + bounds.width / 2;
  const centerY = bounds.y + bounds.height / 2;
  return [centerX - width / 2, centerY - height / 2, width, height]
    .map((value) => Math.round(value * 10) / 10)
    .join(" ");
}

function tableLegs(scene: SceneSnapshot) {
  const legs = scene.objects.filter((object) => /^Leg\s+\d+$/i.test(object.name ?? ""));
  if (legs.length < 2) return [];
  const signature = (object: SceneObject) => JSON.stringify({
    type: object.type,
    size: object.size,
    color: object.color,
    layer: object.layer,
    groups: object.groups,
  });
  return legs.every((object) => signature(object) === signature(legs[0])) ? legs : [];
}

function colorStyle(object: SceneObject) {
  return object.color?.length === 3 ? `rgb(${object.color.join(",")})` : undefined;
}

function SceneObjectIndex({scene}: {scene: SceneSnapshot}) {
  const legs = tableLegs(scene);
  const legIds = new Set(legs.map((object) => object.object_id));
  const singles = scene.objects.filter((object) => !legIds.has(object.object_id)).slice(0, 5);
  return <div className="scene-object-index">
    {singles.map((object) => <span key={object.object_id}><i style={{background: colorStyle(object)}} />{object.name || object.type}</span>)}
    {legs.length > 0 && <span><i style={{background: colorStyle(legs[0])}} />Legs ×{legs.length}</span>}
  </div>;
}

function PublicSceneCanvas({scenarioId, scene, mode}: {scenarioId: string; scene: SceneSnapshot; mode: SceneMode}) {
  const hasScene = scene.objects.length > 0;
  const sphereColor = sceneObjectColor(scene, "Sphere", "rgb(24,89,230)");
  const baseColor = sceneObjectColor(scene, "Base", "rgb(80,88,92)");
  const tableColor = sceneObjectColor(scene, "TableTop", "rgb(160,120,80)");
  return <div className={`scene-viewport ${mode}`}>
    <div className="viewport-meta"><span>SCENE SUMMARY PROJECTION · WORLD XY</span></div>
    <svg viewBox={hasScene ? fittedSceneViewBox(scenarioId, scene.objects.length) : "0 0 760 520"} preserveAspectRatio="xMidYMid slice" data-auto-fit={hasScene ? "bounds" : "pending"} role="img" aria-labelledby="scene-canvas-title scene-canvas-description">
      <title id="scene-canvas-title">{hasScene ? "Rhino scene after Replay" : "Waiting for scene results"}</title>
      <desc id="scene-canvas-description">{hasScene ? `${mode === "shaded" ? "Shaded" : "Wireframe"} projection of ${scene.objects.length} sanitized synthetic objects` : "No objects read yet"}</desc>
      <g className="cad-grid" aria-hidden="true">
        <path d="M36 410H724M75 366H685M112 326H648M150 290H610M188 257H572M226 228H534" />
        <path d="M380 112V478M296 134L230 478M464 134L530 478M210 165L78 478M550 165L682 478" />
      </g>
      <g className="cad-axis" aria-hidden="true"><path d="M92 416h74M92 416v-74M92 416l-42 29" /><text x="171" y="421">X</text><text x="86" y="335">Z</text><text x="32" y="458">Y</text></g>
      {hasScene && scenarioId === "privacy-route" ? <g className="cad-model cad-table cad-subject" style={{color: tableColor}}>
        <path d="M230 242L382 174L548 247L386 326Z" />
        <path d="M230 242v26l156 79v-21M548 247v26l-162 74" />
        <path d="M253 279v121l23 12V291M504 282v118l-23 12V293M359 338v108l23 12V347M431 332v111l-22 11V343" />
      </g> : null}
      {hasScene && scenarioId === "self-correction" ? <g className="cad-model cad-ball cad-subject" style={{color: sphereColor}} data-object-color={scene.objects.find((item) => item.name === "Sphere")?.color?.join(",")}>
        <ellipse cx="382" cy="284" rx="126" ry="121" />
        <ellipse cx="382" cy="284" rx="126" ry="37" />
        <path d="M382 163c-49 35-49 207 0 242M382 163c49 35 49 207 0 242" />
      </g> : null}
      {hasScene && scenarioId !== "privacy-route" && scenarioId !== "self-correction" ? <g className="cad-stack cad-subject">
        <g className="cad-model cad-base" style={{color: baseColor}}><path d="M223 337L378 267L545 341L384 422Z" /><path d="M223 337v27l161 82v-24M545 341v28l-161 77" /></g>
        <g className="cad-model cad-sphere" style={{color: sphereColor}} data-object-color={scene.objects.find((item) => item.name === "Sphere")?.color?.join(",")}><ellipse cx="382" cy="252" rx="96" ry="91" /><ellipse cx="382" cy="252" rx="96" ry="28" /><path d="M382 161c-38 26-38 156 0 182M382 161c38 26 38 156 0 182" /></g>
      </g> : null}
      {!hasScene ? <g className="cad-empty"><circle cx="380" cy="286" r="34" /><path d="M380 267v38M361 286h38" /><text x="380" y="344">WAITING FOR SCENE SUMMARY</text></g> : null}
    </svg>
    <div className={`viewport-state ${hasScene ? "ready" : ""}`}><i />{hasScene ? "SCENE VERIFIED" : "SCENE PENDING"}</div>
  </div>;
}

function SceneColumn({title, scene, empty}: {title: string; scene: SceneSnapshot; empty: string}) {
  return <div className="scene-column"><div className="scene-column-head"><strong>{title}</strong><span>{scene.total ?? scene.objects.length} objects{scene.capped ? " · capped" : ""}</span></div><div className="objects">{scene.objects.length === 0 ? <p className="scene-empty">{empty}</p> : scene.objects.slice(0, 8).map((object) => <ObjectCard key={object.object_id} object={object} />)}</div></div>;
}

function SceneInspector({scene}: {scene: SceneSnapshot}) {
  if (scene.objects.length === 0) return <div className="inspector-list"><Empty title="Empty scene" text="Waiting for the final Scene Summary." /></div>;
  const legs = tableLegs(scene);
  const legIds = new Set(legs.map((object) => object.object_id));
  const singles = scene.objects.filter((object) => !legIds.has(object.object_id));
  return <div className="inspector-list">
    {singles.map((object) => <ObjectCard key={object.object_id} object={object} />)}
    {legs.length > 0 && <ObjectGroupCard label="Legs" objects={legs} />}
  </div>;
}

function ObjectGroupCard({label, objects}: {label: string; objects: SceneObject[]}) {
  const sample = objects[0];
  const color = colorStyle(sample) ?? "#738087";
  return <article className="object-card object-group-card"><span className="swatch" style={{background: color}} aria-label={`RGB ${sample.color?.join(" / ")}`} /><div><div className="object-title"><strong>{label} × {objects.length}</strong><code>{sample.type}</code></div><dl className="object-facts">
    <div><dt>Dimensions</dt><dd>{sample.size?.join(" × ")}</dd></div>
    <div><dt>Color</dt><dd>RGB {sample.color?.join(" / ")}</dd></div>
    <div><dt>Layer</dt><dd>{sample.layer}</dd></div>
    <div><dt>Group</dt><dd>{sample.groups?.join(", ") || "—"}</dd></div>
  </dl><details><summary>View individual objects</summary><ul>{objects.map((object) => <li key={object.object_id}><span>{object.name}</span><code>[{object.center?.join(", ")}]</code></li>)}</ul></details></div></article>;
}

function ObjectCard({object}: {object: SceneObject}) {
  const color = object.color?.length === 3 ? `rgb(${object.color.join(",")})` : "#738087";
  const isSphere = object.name?.toLowerCase().includes("sphere") && object.size?.length === 3 && object.size.every((value) => Math.abs(value - object.size[0]) < .01);
  const radius = isSphere ? object.size[0] / 2 : undefined;
  return <article className="object-card"><span className="swatch" style={{background: color}} aria-label={`RGB ${object.color?.join(" / ")}`} /><div><div className="object-title"><strong>{object.name || object.type}</strong><code>{object.type}</code></div><dl className="object-facts">
    {radius !== undefined && <div><dt>Radius</dt><dd>{radius}</dd></div>}
    <div><dt>Dimensions</dt><dd>{object.size?.join(" × ")}</dd></div>
    <div><dt>Center</dt><dd>[{object.center?.join(", ")}]</dd></div>
    <div><dt>Color</dt><dd>RGB {object.color?.join(" / ")}</dd></div>
    <div><dt>Layer</dt><dd>{object.layer}</dd></div>
  </dl></div></article>;
}

function AuditFact({label, value, good = false}: {label: string; value: string; good?: boolean}) {
  return <div className={good ? "audit-fact good" : "audit-fact"}><span>{label}</span><strong>{value}</strong></div>;
}

function recoveryGuidance(code?: string) {
  if (code === "privacy.request_blocked") return "Remove credentials, data-exfiltration requests, or prompt injection before resubmitting. Neither the model nor Rhino has been called.";
  if (code === "demo.assertion_failed") return "Inspect failed assertions and before/after scenes, then retry or roll back this task's objects.";
  if (code === "llm.timeout") return "The model produced no new tool calls this round. You can retry.";
  if (code?.startsWith("mcp.")) return "Check that the MCP server can start, then retry without restarting the UI.";
  if (code?.startsWith("rhino.")) return "Check Rhino Listener health, then retry. Idempotency keys prevent duplicate objects from network retries.";
  if (code?.includes("invalid") || code?.includes("argument")) return "Correct the GUID or required arguments, then run again.";
  return "Inspect the failed stage in the timeline. Run the task again once the connection is restored.";
}

function feedbackLabel(label: string) {
  return ({accepted: "Accepted", partial: "Partial", rejected: "Rejected"} as Record<string, string>)[label] ?? label;
}

function controlNotice(action: string, payload: Record<string, unknown> = {}) {
  if (action === "cancel") return "Stop requested. The agent will issue no further tool calls.";
  if (action === "feedback") return `Feedback saved: ${feedbackLabel(String(payload.label ?? ""))}`;
  if (action === "rollback") {
    const result = (payload.result ?? {}) as {deleted?: string[]; failed?: string[]};
    return `Targeted rollback complete: ${result.deleted?.length ?? 0} objects deleted${result.failed?.length ? `; ${result.failed.length} objects not found` : ""}.`;
  }
  if (action === "undo") return "Undo complete. Scene Summary refreshed.";
  return "Operation completed.";
}
