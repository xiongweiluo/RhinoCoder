import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import type { AgentEvent, HistoryItem, PrivacyDecision, RouteDecision, SceneObject, SceneSnapshot } from "./types";

const examples = [
  "在原点创建一个 20x20x2 的基座，再在顶面居中放一个半径 8 的红色球体。",
  "搭一张简易桌子：一个桌面和四条桌腿，并将它们分组。",
  "创建三个不同高度的方块，在最高方块顶面紧贴放一个红色球体。",
];

function wsUrl() {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${location.host}/ws`;
}

type RunErrorPayload = {code?: string; message?: string; recoverable?: boolean};
type ActiveRun = {run_id: string; events: AgentEvent[]};

export default function App() {
  const [connected, setConnected] = useState(false);
  const [prompt, setPrompt] = useState(examples[0]);
  const [closedLoop, setClosedLoop] = useState(true);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [currentRun, setCurrentRun] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [sceneOverride, setSceneOverride] = useState<SceneSnapshot | null>(null);
  const [replays, setReplays] = useState<string[]>([]);
  const socketRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);
  const currentRunRef = useRef("");

  const chooseRun = (runId: string) => {
    currentRunRef.current = runId;
    setCurrentRun(runId);
  };

  useEffect(() => {
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
          setSceneOverride(
            restored && "control_scene" in restored
              ? (restored as HistoryItem).control_scene ?? null
              : null,
          );
          if (restored?.run_id) chooseRun(restored.run_id);
          return;
        }
        if (data.type === "history.updated") {
          const nextHistory = (data.history ?? []) as HistoryItem[];
          setHistory(nextHistory);
          const restored = nextHistory.find((run) => run.run_id === currentRunRef.current);
          if (restored) {
            setEvents(restored.events ?? []);
            setSceneOverride(restored.control_scene ?? null);
          }
          return;
        }
        if (data.type === "control.accepted") {
          chooseRun(data.run_id);
          if (data.action === "start" || data.action === "retry") {
            setEvents((previous) => previous.filter((event) => event.run_id === data.run_id));
            setSceneOverride(null);
          }
          return;
        }
        if (data.type === "control.completed") {
          const snapshot = data.payload?.scene_summary as SceneSnapshot | undefined;
          if (snapshot?.objects) setSceneOverride(snapshot);
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
          if (event.type === "run.started") setSceneOverride(null);
          setEvents((previous) => [...previous.filter((item) => !(item.run_id === event.run_id && item.seq === event.seq)), event]);
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
    fetch("/api/replays").then((response) => response.json()).then((data) => setReplays(data.replays ?? [])).catch(() => undefined);
    return () => { disposed = true; clearTimeout(timer); socketRef.current?.close(); };
  }, []);

  const send = (message: Record<string, unknown>) => {
    setError("");
    setNotice("");
    if (socketRef.current?.readyState !== WebSocket.OPEN) {
      setError("UI 服务连接尚未恢复");
      return;
    }
    socketRef.current.send(JSON.stringify(message));
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    send({ type: "instruction", content: prompt, closed_loop: closedLoop });
  };

  const selectHistory = (item: HistoryItem) => {
    chooseRun(item.run_id);
    setEvents(item.events ?? []);
    setSceneOverride(item.control_scene ?? null);
  };

  const currentEvents = useMemo(
    () => events.filter((event) => !currentRun || event.run_id === currentRun).sort((a, b) => a.seq - b.seq),
    [events, currentRun],
  );
  const latest = currentEvents.at(-1);
  const toolEvents = currentEvents.filter((event) => event.type === "tool.completed");
  const sceneEvent = [...currentEvents].reverse().find((event) => event.type === "scene.checked");
  const scene = sceneOverride?.objects
    ?? (sceneEvent?.payload.scene_summary as {objects?: SceneObject[]} | null)?.objects
    ?? [];
  const terminal = [...currentEvents].reverse().find((event) => ["run.completed", "run.failed", "run.cancelled"].includes(event.type));
  const metrics = (terminal?.payload.metrics ?? {}) as Record<string, number | string>;
  const metricNumber = (name: string) => typeof metrics[name] === "number" ? metrics[name] as number : undefined;
  const durationMs = metricNumber("duration_ms");
  const toolRounds = metricNumber("tool_rounds");
  const toolCalls = metricNumber("tool_calls");
  const totalTokens = metricNumber("total_tokens");
  const cacheHitTokens = metricNumber("prompt_cache_hit_tokens");
  const cacheMissTokens = metricNumber("prompt_cache_miss_tokens");
  const estimatedCost = metricNumber("estimated_cost_usd");
  const costStatus = String(metrics.cost_estimate_status ?? "");
  const currentHistory = history.find((item) => item.run_id === currentRun);
  const routeEvent = [...currentEvents].reverse().find((event) =>
    event.type === "route.fallback" || event.type === "route.selected"
  );
  const route = (routeEvent?.payload as unknown as RouteDecision | undefined)
    ?? currentHistory?.route_decision
    ?? undefined;
  const privacyEvent = [...currentEvents].reverse().find((event) =>
    event.type === "privacy.blocked" || event.type === "privacy.assessed"
  );
  const privacy = (privacyEvent?.payload as unknown as PrivacyDecision | undefined)
    ?? currentHistory?.privacy_decision
    ?? undefined;
  const isReplay = Boolean(latest?.replay);
  const isRunning = Boolean(currentRun && !terminal && !isReplay);
  const canRetry = Boolean(terminal && !isReplay);
  const canUndo = Boolean(
    connected
    && currentHistory
    && !isRunning
    && !currentHistory.undo_applied
    && !isReplay,
  );
  const canRollback = Boolean(
    currentHistory?.status === "completed"
    && currentHistory.created_object_ids?.length
    && !currentHistory.rolled_back
    && !isReplay,
  );
  const canFeedback = Boolean(terminal && !isReplay);
  const terminalError = terminal?.type === "run.failed"
    ? (terminal.payload.error as RunErrorPayload | undefined)
    : undefined;
  const visibleError: RunErrorPayload | undefined = terminalError?.message
    ? terminalError
    : error ? {message: error, recoverable: true} : undefined;

  return (
    <main className="shell">
      <header className="topbar">
        <div><span className="eyebrow">SPATIAL AGENT</span><h1>RhinoCoder</h1></div>
        <div className={`connection ${connected ? "online" : "offline"}`}><span />{connected ? "Connected" : "Reconnecting"}</div>
      </header>

      <section className="composer panel">
        <form onSubmit={submit}>
          <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={3} />
          <div className="composer-actions">
            <label><input type="checkbox" checked={closedLoop} onChange={(event) => setClosedLoop(event.target.checked)} /> 闭环场景自检</label>
            <div className="button-row">
              <button type="button" className="ghost" disabled={!isRunning} onClick={() => send({type: "cancel", run_id: currentRun})}>停止</button>
              <button type="button" className="ghost" disabled={!canUndo} onClick={() => send({type: "undo", run_id: currentRun})}>Undo</button>
              <button type="submit" disabled={!connected || !prompt.trim()}>执行任务</button>
            </div>
          </div>
        </form>
        <div className="examples">{examples.map((item, index) => <button key={item} onClick={() => setPrompt(item)}>示例 {index + 1}</button>)}</div>
        {notice && <div className="control-notice" role="status">{notice}</div>}
        {visibleError && <div className="recovery-error" role="alert">
          <div><strong>{visibleError.code ?? "操作失败"}</strong><p>{visibleError.message}</p><small>{recoveryGuidance(visibleError.code)}</small></div>
          {visibleError.recoverable !== false && <button type="button" className="danger" disabled={!canRetry} onClick={() => send({type: "retry", run_id: currentRun})}>重试任务</button>}
        </div>}
      </section>

      <section className="metrics">
        <Metric label="状态" value={(latest?.type ?? "idle").replace("run.", "")} />
        <Metric label="耗时" value={durationMs ? `${Math.round(durationMs)} ms` : "--"} />
        <Metric label="调用轮数" value={toolRounds?.toString() ?? "--"} />
        <Metric label="工具调用" value={toolCalls?.toString() ?? toolEvents.length.toString()} />
        <Metric label="Token" value={totalTokens?.toString() ?? "--"} />
        <Metric label="缓存 命中/未命中" value={cacheHitTokens !== undefined && cacheMissTokens !== undefined ? `${cacheHitTokens} / ${cacheMissTokens}` : "--"} />
        <Metric label={costStatus === "exact" ? "精确成本" : "估算成本"} value={estimatedCost !== undefined ? `$${estimatedCost.toFixed(6)}` : "--"} />
      </section>

      <section className={`routing panel ${route?.degraded ? "degraded" : ""}`}>
        <div>
          <span className="eyebrow">MODEL ROUTE</span>
          <strong>{route ? `${route.selected_backend} · ${route.selected_model}` : privacy?.action === "block" ? "请求已在本地阻断" : "等待路由决策"}</strong>
        </div>
        <p>{route?.reason ?? privacy?.reasons?.join("；") ?? "提交任务后将显示后端、路由理由和降级状态。"}</p>
        {privacy && <div className="route-signals">
          <span>风险 {privacy.risk}</span>
          <span>动作 {privacy.action}</span>
          <span>{privacy.cloud_allowed ? "允许最小化云请求" : "禁止云请求"}</span>
          {privacy.reason_codes.map((code) => <span key={code}>{code}</span>)}
        </div>}
        {route && <div className="route-signals">
          <span>隐私 {route.privacy_level}</span>
          <span>难度 L{route.task_difficulty}</span>
          <span>工具复杂度 {route.tool_complexity}</span>
          <span>{route.degraded ? `已从 ${route.fallback_from} 降级（${route.fallback_error_code}）` : "未降级"}</span>
        </div>}
      </section>

      <section className="workspace">
        <div className="panel trace-panel">
          <div className="section-title"><h2>Tool Trace</h2><span>{currentEvents.length} events</span></div>
          <div className="timeline">
            {currentEvents.length === 0 && <Empty text="运行任务后，规划、工具和验证事件会显示在这里。" />}
            {currentEvents.map((event) => <EventRow key={`${event.run_id}-${event.seq}`} event={event} />)}
          </div>
        </div>

        <div className="right-column">
          <div className="panel scene-panel">
            <div className="section-title"><h2>Scene Summary</h2><span>{scene.length} objects</span></div>
            <div className="objects">
              {scene.length === 0 && <Empty text="场景自检后显示真实对象尺寸、位置和颜色。" />}
              {scene.map((object) => <ObjectCard key={object.object_id} object={object} />)}
            </div>
          </div>
          <div className="panel controls">
            <div className="section-title"><h2>Recovery & Feedback</h2></div>
            <div className="button-grid">
              <button className="ghost" disabled={!canRetry} onClick={() => send({type: "retry", run_id: currentRun})}>重试任务</button>
              <button className="danger" disabled={!canRollback} onClick={() => send({type: "rollback", run_id: currentRun})}>精准回滚</button>
              <button className="ghost" disabled={!canFeedback} onClick={() => send({type: "feedback", run_id: currentRun, label: "accepted"})}>正确</button>
              <button className="ghost" disabled={!canFeedback} onClick={() => send({type: "feedback", run_id: currentRun, label: "partial"})}>部分正确</button>
              <button className="danger" disabled={!canFeedback} onClick={() => send({type: "feedback", run_id: currentRun, label: "rejected"})}>错误</button>
            </div>
            {currentHistory?.feedback_labels?.length ? <p className="feedback-state">已记录反馈：{currentHistory.feedback_labels.map(feedbackLabel).join("、")}</p> : null}
            {replays.length > 0 && <select defaultValue="" onChange={(event) => event.target.value && send({type: "replay", name: event.target.value})}><option value="">加载 Replay…</option>{replays.map((name) => <option key={name}>{name}</option>)}</select>}
          </div>
        </div>
      </section>

      <section className="panel history">
        <div className="section-title"><h2>Recent Runs</h2><span>{history.length}</span></div>
        {history.slice(0, 8).map((item) => <button key={item.run_id} onClick={() => selectHistory(item)}><strong>{item.status}</strong><span>{item.prompt}</span><code>{item.run_id.slice(0, 8)}</code></button>)}
      </section>
    </main>
  );
}

function Metric({label, value}: {label: string; value: string}) {
  return <div className="metric panel"><span>{label}</span><strong>{value}</strong></div>;
}

function Empty({text}: {text: string}) { return <p className="empty">{text}</p>; }

function EventRow({event}: {event: AgentEvent}) {
  const payload = event.payload as Record<string, unknown>;
  const title = String(payload.name ?? payload.tool ?? event.type);
  const success = payload.success;
  const failed = success === false || event.type === "run.failed";
  const rawError = failed ? payload.error ?? payload.output ?? "" : "";
  const errorText = typeof rawError === "string" ? rawError : rawError ? JSON.stringify(rawError) : "";
  const privacyReasons = event.type.startsWith("privacy.") && Array.isArray(payload.reason_codes)
    ? payload.reason_codes.join(", ")
    : "";
  return <article className={`event ${failed || event.type === "privacy.blocked" ? "failed" : ""}`}><span className="event-dot" /><div><div className="event-head"><strong>{title}</strong><time>#{event.seq}</time></div><p>{event.type}</p>{payload.arguments ? <code>{JSON.stringify(payload.arguments)}</code> : null}{privacyReasons ? <code className={event.type === "privacy.blocked" ? "event-error" : ""}>{privacyReasons}</code> : null}{errorText ? <code className="event-error">{errorText}</code> : null}</div></article>;
}

function recoveryGuidance(code?: string) {
  if (code === "privacy.request_blocked") return "移除凭证、数据窃取或 Prompt 注入内容后再提交；该请求尚未调用模型或 Rhino。";
  if (code === "llm.timeout") return "模型本轮未产生新的工具调用；可直接重试。";
  if (code?.startsWith("mcp.")) return "确认 MCP Server 可启动后重试，无需重启 UI。";
  if (code?.startsWith("rhino.")) return "确认 Rhino Listener 健康后重试；幂等键会防止网络重试产生重复对象。";
  if (code?.includes("invalid") || code?.includes("argument")) return "修正 GUID 或必填参数后重新执行。";
  return "检查错误原因后可从此处重新运行相同任务。";
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

function ObjectCard({object}: {object: SceneObject}) {
  const color = object.color?.length === 3 ? `rgb(${object.color.join(",")})` : "#738087";
  const groups = object.groups?.length ? ` · ${object.groups.join(", ")}` : "";
  return <article className="object-card"><span className="swatch" style={{background: color}} /><div><strong>{object.name || object.type}</strong><p>{object.type} · {object.layer}{groups}</p><code>size {object.size?.join(" × ")} · center {object.center?.join(", ")}</code></div></article>;
}
