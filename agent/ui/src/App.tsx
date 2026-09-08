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

const EMPTY_SCENE: SceneSnapshot = {objects: [], total: 0, capped: false};
const TERMINAL_TYPES = new Set(["run.completed", "run.failed", "run.cancelled"]);
const EVENT_FILTERS = ["all", "decision", "execution", "verification", "recovery"] as const;
type EventFilter = typeof EVENT_FILTERS[number];
type PlaybackState = "idle" | "loading" | "playing" | "complete" | "error";
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
  if (type.startsWith("privacy.") || type.startsWith("route.")) return "decision";
  if (type.startsWith("scene.") || type.startsWith("assertion.")) return "verification";
  if (type.startsWith("correction.") || type.includes("failed") || type.includes("cancelled")) return "recovery";
  return "execution";
}

function eventLabel(type: string) {
  const labels: Record<string, string> = {
    "run.started": "任务开始",
    "privacy.assessed": "隐私判断",
    "privacy.blocked": "本地阻断",
    "route.selected": "路由选择",
    "route.fallback": "安全降级",
    "planning.started": "规划",
    "tool.started": "工具调用",
    "tool.completed": "工具结果",
    "scene.checked": "场景读回",
    "assertion.checked": "几何断言",
    "correction.started": "纠错开始",
    "run.completed": "任务完成",
    "run.failed": "任务失败",
    "run.cancelled": "任务取消",
  };
  return labels[type] ?? type;
}

function statusLabel(status: string) {
  return ({
    idle: "等待任务",
    loading: "加载中",
    playing: "Replay 播放中",
    running: "执行中",
    completed: "已通过",
    failed: "失败",
    cancelled: "已取消",
    offline: "离线",
  } as Record<string, string>)[status] ?? status;
}

function filterLabel(filter: EventFilter) {
  return ({all: "全部", decision: "决策", execution: "执行", verification: "验证", recovery: "恢复"})[filter];
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

export default function App() {
  const initialParams = useMemo(() => new URLSearchParams(location.search), []);
  const initialDemo = initialParams.get("demo") ?? "";
  const publicReplayMode = initialParams.get("mode") === "replay" || Boolean(initialDemo);
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
  const [scenarios, setScenarios] = useState<DemoScenario[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState(initialDemo);
  const [playbackState, setPlaybackState] = useState<PlaybackState>("idle");
  const [historyQuery, setHistoryQuery] = useState("");
  const [historyFilter, setHistoryFilter] = useState("all");
  const [eventFilter, setEventFilter] = useState<EventFilter>("all");
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
      const response = await fetch(`/api/replays/${encodeURIComponent(scenario.replay)}`);
      if (!response.ok) throw new Error(`Replay 加载失败 (${response.status})`);
      const payload = await response.json() as ReplayPayload;
      if (!payload.read_only || payload.scenario.id !== scenario.id) {
        throw new Error("Replay 与公开场景清单不一致");
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
      setNotice(`${scenario.title} Replay 已完成：仅使用脱敏合成数据，未调用模型、Rhino 或写操作。`);
    } catch (reason) {
      if (playbackTokenRef.current !== token) return;
      setPlaybackState("error");
      setError(reason instanceof Error ? reason.message : "Replay 加载失败");
    }
  }, [chooseRun]);

  useEffect(() => {
    fetch("/api/demo-scenarios")
      .then((response) => {
        if (!response.ok) throw new Error(`场景清单加载失败 (${response.status})`);
        return response.json();
      })
      .then((data) => setScenarios((data.scenarios ?? []) as DemoScenario[]))
      .catch((reason) => setError(reason instanceof Error ? reason.message : "场景清单加载失败"));
  }, []);

  useEffect(() => {
    if (!initialDemo || initialReplayLoaded.current || scenarios.length === 0) return;
    const scenario = scenarios.find((item) => item.id === initialDemo);
    initialReplayLoaded.current = true;
    if (scenario) void playReplay(scenario);
    else setError(`未知公开演示场景：${initialDemo}`);
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
          setError(data.payload?.message ?? "操作失败");
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
      setError("公开 Replay 模式为只读，不发送 WebSocket 写消息。");
      return;
    }
    if (socketRef.current?.readyState !== WebSocket.OPEN) {
      setError("UI 服务连接尚未恢复");
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
  const filteredEvents = eventFilter === "all" ? currentEvents : currentEvents.filter((event) => eventGroup(event.type) === eventFilter);
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
  const passedAssertions = assertions.filter((event) => event.payload.success === true).length;

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
    setNotice(`${scenario.title} 已填入；请在空白、可丢弃的 Rhino 文档中执行。`);
    window.setTimeout(() => composerRef.current?.focus(), 0);
  };

  return (
    <main className="shell" id="main-content">
      <a className="skip-link" href="#evidence-chain">跳到运行证据</a>
      <header className="topbar">
        <div><span className="eyebrow">VERIFIABLE SPATIAL AGENT</span><h1>RhinoCoder</h1><p>从指令到几何证据，一条 run_id 可复核链路。</p></div>
        <div className={`connection ${connected ? "online" : publicReplayMode ? "readonly" : "offline"}`} role="status" aria-live="polite">
          <span />{publicReplayMode ? "Read-only demo" : connected ? "Connected" : "Reconnecting"}
        </div>
      </header>

      <section className="hero-grid" aria-labelledby="demo-heading">
        <div>
          <span className="eyebrow">THREE FIXED DEMOS</span>
          <h2 id="demo-heading">先看结果，再钻进 Trace</h2>
          <p>每个场景都固定目标、输入、预期结果、Replay 和证据入口。Replay 只通过 GET 读取脱敏合成数据。</p>
        </div>
        <div className="hero-proof"><strong>公开边界</strong><span>0 模型调用</span><span>0 Rhino 写操作</span><span>0 原始 Trace</span></div>
      </section>

      <section className="scenario-grid" aria-label="固定演示场景">
        {scenarios.length === 0 && <div className="panel loading-card" aria-busy="true">正在加载三个演示场景…</div>}
        {scenarios.map((scenario, index) => (
          <article className={`scenario-card panel ${selectedScenarioId === scenario.id ? "selected" : ""}`} key={scenario.id}>
            <div className="scenario-number">0{index + 1}</div>
            <span className="eyebrow">{scenario.kicker}</span>
            <h3>{scenario.title}</h3>
            <p>{scenario.goal}</p>
            <details><summary>输入与预期结果</summary><code className="prompt-code">{scenario.input}</code><ul>{scenario.expected.map((item) => <li key={item}>{item}</li>)}</ul></details>
            <div className="scenario-actions">
              <button type="button" onClick={() => void playReplay(scenario)} aria-label={`播放${scenario.title}只读 Replay`}>播放 Replay</button>
              {!publicReplayMode && <button type="button" className="ghost" onClick={() => prepareLiveScenario(scenario)}>填入 Rhino</button>}
              <a href={scenario.evidence.href} target="_blank" rel="noreferrer">证据 ↗</a>
              <a href={scenario.read_only_url}>只读链接</a>
            </div>
          </article>
        ))}
      </section>

      {!publicReplayMode ? (
        <section className="composer panel" aria-labelledby="composer-heading">
          <div className="section-title"><div><span className="eyebrow">LIVE RHINO</span><h2 id="composer-heading">执行任务</h2></div><span>⌘/Ctrl + Enter 执行 · Esc 停止</span></div>
          <form onSubmit={submit}>
            <label className="sr-only" htmlFor="prompt">Rhino 任务指令</label>
            <textarea id="prompt" ref={composerRef} value={prompt} onKeyDown={composerKeyDown} onChange={(event) => setPrompt(event.target.value)} rows={3} placeholder="选择一个固定场景，或输入 Rhino 建模任务。" />
            <div className="composer-actions">
              <label><input type="checkbox" checked={closedLoop} onChange={(event) => setClosedLoop(event.target.checked)} /> 闭环场景自检</label>
              <div className="button-row">
                <button type="button" className="ghost" disabled={!isRunning} onClick={() => send({type: "cancel", run_id: currentRun})}>停止</button>
                <button type="submit" disabled={!connected || !prompt.trim()}>执行任务</button>
              </div>
            </div>
          </form>
        </section>
      ) : (
        <section className="readonly-banner panel" role="note"><strong>公开只读模式</strong><p>此页面不建立 WebSocket，也不发送 instruction、retry、Undo、rollback 或 feedback 消息。请选择上方任一场景播放。</p></section>
      )}

      {!connected && !publicReplayMode && <div className="state-banner offline" role="status"><strong>UI 服务离线</strong><span>正在指数退避重连；Replay 仍可通过上方按钮只读加载。</span></div>}
      {notice && <div className="state-banner success" role="status" aria-live="polite">{notice}</div>}
      {visibleError && <div className="recovery-error" role="alert">
        <div><strong>{visibleError.code ?? "操作失败"}</strong><p>{visibleError.message}</p><small>{recoveryGuidance(visibleError.code)}</small></div>
        {visibleError.recoverable !== false && !isReplay && <button type="button" className="danger" disabled={!canRetry} onClick={() => send({type: "retry", run_id: currentRun})}>一键重试</button>}
      </div>}

      <section className="dashboard" id="evidence-chain" aria-label="运行指标仪表盘">
        <Metric label="运行状态" value={statusLabel(runStatus)} tone={runStatus === "failed" ? "bad" : runStatus === "completed" ? "good" : "neutral"} />
        <Metric label="run_id" value={currentRun || "--"} mono />
        <Metric label="隐私动作" value={privacy?.action ?? "--"} />
        <Metric label="模型路由" value={route?.selected_backend ?? "--"} />
        <Metric label="端到端延迟" value={duration !== undefined ? `${Math.round(duration)} ms` : "--"} />
        <Metric label="成本" value={cost !== undefined ? `$${cost.toFixed(6)}` : "--"} />
        <Metric label="工具错误" value={String(toolErrors)} tone={toolErrors ? "bad" : "good"} />
        <Metric label="恢复次数" value={String(recoveries)} tone={recoveries ? "warn" : "neutral"} />
      </section>

      <section className={`routing panel ${route?.degraded ? "degraded" : ""}`} aria-labelledby="routing-heading">
        <div><span className="eyebrow">PRIVACY + ROUTE</span><h2 id="routing-heading">{route ? `${route.selected_backend} · ${route.selected_model}` : privacy?.action === "block" ? "请求已在本地阻断" : "等待决策"}</h2></div>
        <p>{route?.reason ?? privacy?.reasons?.join("；") ?? "隐私门先于模型与 MCP；路由理由、降级与 run_id 一起记录。"}</p>
        <div className="route-signals">
          <span>风险 {privacy?.risk ?? "--"}</span><span>动作 {privacy?.action ?? "--"}</span>
          <span>{privacy ? privacy.cloud_allowed ? "允许最小化云请求" : "禁止云请求" : "云边界待判断"}</span>
          <span>{route?.degraded ? `从 ${route.fallback_from} 降级 · ${route.fallback_error_code}` : "无降级"}</span>
        </div>
      </section>

      <section className="workspace">
        <div className="panel trace-panel">
          <div className="section-title"><div><span className="eyebrow">SCAN IN SECONDS</span><h2>Evidence Timeline</h2></div><span>{filteredEvents.length}/{currentEvents.length} events</span></div>
          <div className="filter-row" role="group" aria-label="时间线筛选">
            {EVENT_FILTERS.map((filter) => <button type="button" className={eventFilter === filter ? "active" : "ghost"} aria-pressed={eventFilter === filter} onClick={() => setEventFilter(filter)} key={filter}>{filterLabel(filter)}</button>)}
          </div>
          <div className="timeline" aria-live="polite">
            {playbackState === "loading" && <Empty title="正在加载 Replay" text="只读 GET 请求完成后开始播放。" />}
            {playbackState !== "loading" && filteredEvents.length === 0 && <Empty title="尚无事件" text="播放 Replay 或执行任务后，这里按决策、执行、验证和恢复阶段展示证据。" />}
            {filteredEvents.map((event) => <EventRow key={`${event.run_id}-${event.seq}`} event={event} />)}
          </div>
        </div>

        <div className="right-column">
          <section className="panel comparison-panel" aria-labelledby="comparison-heading">
            <div className="section-title"><div><span className="eyebrow">BEFORE / AFTER</span><h2 id="comparison-heading">Rhino 场景对比</h2></div><span>{beforeScene.total} → {afterScene.total}</span></div>
            <div className="comparison-grid">
              <SceneColumn title="操作前" scene={beforeScene} empty="固定场景执行前会读取基线；Replay 使用声明为空的合成场景。" />
              <SceneColumn title="操作后" scene={afterScene} empty="最终 Scene Summary 尚未到达。" />
            </div>
          </section>

          <section className="panel assertion-panel" aria-labelledby="assertion-heading">
            <div className="section-title"><div><span className="eyebrow">PROGRAMMATIC PROOF</span><h2 id="assertion-heading">断言明细</h2></div><span>{assertions.length ? `${passedAssertions}/${assertions.length}` : "--"}</span></div>
            {assertions.length === 0 && <Empty title="暂无断言" text="固定 Replay 或固定 Rhino 场景完成后显示期望、实际值和通过状态。" />}
            <div className="assertion-list">{assertions.map((event) => <AssertionRow event={event} key={`${event.run_id}-assert-${event.seq}`} />)}</div>
          </section>

          <section className="panel controls" aria-labelledby="recovery-heading">
            <div className="section-title"><div><span className="eyebrow">ONE-CLICK RECOVERY</span><h2 id="recovery-heading">恢复与反馈</h2></div></div>
            {isReplay ? <p className="control-context">Replay 为只读；下列变更操作全部禁用。</p> : <p className="control-context">重试创建新 run_id；Undo 撤销最后操作；精准回滚只删除本任务记录的对象。</p>}
            <div className="button-grid">
              <button className="ghost" disabled={!canRetry} onClick={() => send({type: "retry", run_id: currentRun})}>重试任务</button>
              <button className="ghost" disabled={!canUndo} onClick={() => send({type: "undo", run_id: currentRun})}>Undo</button>
              <button className="danger" disabled={!canRollback} onClick={() => send({type: "rollback", run_id: currentRun})}>精准回滚</button>
              <button className="ghost" disabled={!canFeedback} onClick={() => send({type: "feedback", run_id: currentRun, label: "accepted"})}>标记正确</button>
              <button className="ghost" disabled={!canFeedback} onClick={() => send({type: "feedback", run_id: currentRun, label: "partial"})}>部分正确</button>
              <button className="danger" disabled={!canFeedback} onClick={() => send({type: "feedback", run_id: currentRun, label: "rejected"})}>标记错误</button>
            </div>
            {currentHistory?.feedback_labels?.length ? <p className="feedback-state">已记录：{currentHistory.feedback_labels.map(feedbackLabel).join("、")}</p> : null}
          </section>
        </div>
      </section>

      <section className="panel audit-panel" aria-labelledby="audit-heading">
        <div><span className="eyebrow">SANITIZED BROWSER SURFACE</span><h2 id="audit-heading">脱敏审计摘要</h2><p>浏览器接收的是最小化展示载荷；完整本地 Trace、模型消息和真实对象 GUID 不通过 UI API 下发。</p></div>
        <div className="audit-grid">
          <AuditFact label="载荷" value={auditSummary.browser_payload} />
          <AuditFact label="原始 Trace" value={auditSummary.raw_trace_exposed ? "暴露" : "未暴露"} good={!auditSummary.raw_trace_exposed} />
          <AuditFact label="对象 ID" value={auditSummary.object_ids} good />
          <AuditFact label="来源" value={auditSummary.provenance ?? (isReplay ? "synthetic" : "local run")} good={isReplay} />
        </div>
      </section>

      <section className="panel history" aria-labelledby="history-heading">
        <div className="section-title"><div><span className="eyebrow">MINIMIZED RUN INDEX</span><h2 id="history-heading">Recent Runs</h2></div><span>{filteredHistory.length}/{allHistory.length}</span></div>
        <div className="history-tools">
          <label><span className="sr-only">搜索最近运行</span><input ref={searchRef} type="search" value={historyQuery} onChange={(event) => setHistoryQuery(event.target.value)} placeholder="搜索指令或 run_id（快捷键 /）" /></label>
          <label><span className="sr-only">筛选运行状态</span><select value={historyFilter} onChange={(event) => setHistoryFilter(event.target.value)}><option value="all">全部状态</option><option value="completed">已通过</option><option value="failed">失败</option><option value="cancelled">已取消</option><option value="replay">Replay</option></select></label>
        </div>
        <div className="history-list">
          {filteredHistory.length === 0 && <Empty title="没有匹配的运行" text={allHistory.length ? "调整搜索词或状态筛选。" : "播放 Replay 或执行任务后生成脱敏索引。"} />}
          {filteredHistory.slice(0, 30).map((item) => <button type="button" className={item.run_id === currentRun ? "selected" : ""} key={`${item.is_replay ? "replay" : "live"}-${item.run_id}`} onClick={() => selectHistory(item)}><span className={`status-pill ${item.status}`}>{item.is_replay ? "REPLAY" : statusLabel(item.status)}</span><span>{item.prompt}</span><code title={item.run_id}>{item.run_id.slice(0, 12)}</code></button>)}
        </div>
      </section>
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
      {payload.arguments ? <details className="event-details"><summary>查看脱敏参数</summary><code>{JSON.stringify(payload.arguments)}</code></details> : null}
    </div>
  </article>;
}

function eventSummary(event: AgentEvent) {
  const payload = event.payload as Record<string, unknown>;
  if (event.type === "run.started") return `输入摘要：${String(payload.prompt ?? "已最小化")}`;
  if (event.type.startsWith("privacy.")) return `risk=${payload.risk ?? "--"} · action=${payload.action ?? "--"} · cloud=${payload.cloud_allowed ? "minimized/allowed" : "blocked"}`;
  if (event.type.startsWith("route.")) return `${payload.selected_backend ?? "--"} · ${payload.reason ?? "路由理由未提供"}`;
  if (event.type === "planning.started") return `第 ${payload.round ?? "--"} 轮规划`;
  if (event.type === "tool.completed") return `${payload.success === false ? "失败" : "成功"} · ${Math.round(Number(payload.duration_ms ?? 0))} ms`;
  if (event.type === "scene.checked") {
    const scene = payload.scene_summary as SceneSnapshot | undefined;
    return `读取 ${scene?.total ?? scene?.objects?.length ?? 0} 个对象`;
  }
  if (event.type === "assertion.checked") return `${payload.success ? "通过" : "不通过"} · 期望 ${String(payload.expected ?? "--")}`;
  if (event.type === "correction.started") return `第 ${payload.round ?? "--"} 轮 · ${payload.reason ?? payload.tool ?? "根据场景重新规划"}`;
  if (TERMINAL_TYPES.has(event.type)) {
    const metrics = payload.metrics as Record<string, unknown> | undefined;
    return `${payload.status ?? event.type.replace("run.", "")} · ${Math.round(Number(metrics?.duration_ms ?? 0))} ms`;
  }
  return "";
}

function AssertionRow({event}: {event: AgentEvent}) {
  const payload = event.payload as Record<string, unknown>;
  const ok = payload.success === true;
  return <article className={`assertion-row ${ok ? "passed" : "failed"}`}><span aria-hidden="true">{ok ? "✓" : "×"}</span><div><strong>{String(payload.name ?? "几何断言")}</strong><p><b>期望</b> {String(payload.expected ?? "--")}</p><p><b>实际</b> {String(payload.actual ?? "--")}</p></div></article>;
}

function SceneColumn({title, scene, empty}: {title: string; scene: SceneSnapshot; empty: string}) {
  return <div className="scene-column"><div className="scene-column-head"><strong>{title}</strong><span>{scene.total ?? scene.objects.length} objects{scene.capped ? " · capped" : ""}</span></div><div className="objects">{scene.objects.length === 0 ? <p className="scene-empty">{empty}</p> : scene.objects.slice(0, 8).map((object) => <ObjectCard key={object.object_id} object={object} />)}</div></div>;
}

function ObjectCard({object}: {object: SceneObject}) {
  const color = object.color?.length === 3 ? `rgb(${object.color.join(",")})` : "#738087";
  const groups = object.groups?.length ? ` · ${object.groups.join(", ")}` : "";
  return <article className="object-card"><span className="swatch" style={{background: color}} /><div><strong>{object.name || object.type}</strong><p>{object.type} · {object.layer}{groups}</p><code>size {object.size?.join(" × ")} · center {object.center?.join(", ")}</code></div></article>;
}

function AuditFact({label, value, good = false}: {label: string; value: string; good?: boolean}) {
  return <div className={good ? "audit-fact good" : "audit-fact"}><span>{label}</span><strong>{value}</strong></div>;
}

function recoveryGuidance(code?: string) {
  if (code === "privacy.request_blocked") return "移除凭证、数据窃取或 Prompt 注入内容后再提交；模型和 Rhino 尚未被调用。";
  if (code === "demo.assertion_failed") return "查看不通过的断言与前后场景，再重试或精准回滚本任务对象。";
  if (code === "llm.timeout") return "模型本轮未产生新的工具调用；可直接重试。";
  if (code?.startsWith("mcp.")) return "确认 MCP Server 可启动后重试，无需重启 UI。";
  if (code?.startsWith("rhino.")) return "确认 Rhino Listener 健康后重试；幂等键会防止网络重试产生重复对象。";
  if (code?.includes("invalid") || code?.includes("argument")) return "修正 GUID 或必填参数后重新执行。";
  return "检查时间线中的失败阶段；连接恢复后可重新运行相同任务。";
}

function feedbackLabel(label: string) {
  return ({accepted: "正确", partial: "部分正确", rejected: "错误"} as Record<string, string>)[label] ?? label;
}

function controlNotice(action: string, payload: Record<string, unknown> = {}) {
  if (action === "cancel") return "停止请求已发送；Agent 将不再发起新的工具调用。";
  if (action === "feedback") return `反馈已保存：${feedbackLabel(String(payload.label ?? ""))}`;
  if (action === "rollback") {
    const result = (payload.result ?? {}) as {deleted?: string[]; failed?: string[]};
    return `精准回滚完成：删除 ${result.deleted?.length ?? 0} 个对象${result.failed?.length ? `，${result.failed.length} 个对象未找到` : ""}。`;
  }
  if (action === "undo") return "Undo 完成，Scene Summary 已刷新。";
  return "操作已完成。";
}
