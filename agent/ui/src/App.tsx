import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import type { AgentEvent, HistoryItem, SceneObject } from "./types";

const examples = [
  "在原点创建一个 20x20x2 的基座，再在顶面居中放一个半径 8 的红色球体。",
  "搭一张简易桌子：一个桌面和四条桌腿，并将它们分组。",
  "创建三个不同高度的方块，在最高方块顶面紧贴放一个红色球体。",
];

function wsUrl() {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${location.host}/ws`;
}

export default function App() {
  const [connected, setConnected] = useState(false);
  const [prompt, setPrompt] = useState(examples[0]);
  const [closedLoop, setClosedLoop] = useState(true);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [currentRun, setCurrentRun] = useState("");
  const [error, setError] = useState("");
  const [replays, setReplays] = useState<string[]>([]);
  const socketRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);

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
          setHistory(data.history ?? []);
          const activeEvents = (data.active ?? []).flatMap((run: {events: AgentEvent[]}) => run.events);
          setEvents(activeEvents);
          return;
        }
        if (data.type === "history.updated") {
          setHistory(data.history ?? []);
          return;
        }
        if (data.type === "control.accepted") {
          setCurrentRun(data.run_id);
          if (data.action === "start" || data.action === "retry") {
            setEvents((previous) => previous.filter((event) => event.run_id === data.run_id));
          }
          return;
        }
        if (data.type === "control.error") {
          setError(data.payload?.message ?? "操作失败");
          return;
        }
        if (typeof data.type === "string" && data.run_id) {
          const event = data as AgentEvent;
          setCurrentRun(event.run_id);
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
    setCurrentRun(item.run_id);
    setEvents(item.events ?? []);
  };

  const currentEvents = useMemo(
    () => events.filter((event) => !currentRun || event.run_id === currentRun).sort((a, b) => a.seq - b.seq),
    [events, currentRun],
  );
  const latest = currentEvents.at(-1);
  const toolEvents = currentEvents.filter((event) => event.type === "tool.completed");
  const sceneEvent = [...currentEvents].reverse().find((event) => event.type === "scene.checked");
  const scene = (sceneEvent?.payload.scene_summary as {objects?: SceneObject[]} | null)?.objects ?? [];
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
  const canControl = Boolean(currentRun && !latest?.replay);

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
              <button type="button" className="ghost" disabled={!canControl} onClick={() => send({type: "cancel", run_id: currentRun})}>停止</button>
              <button type="button" className="ghost" onClick={() => send({type: "undo"})}>Undo</button>
              <button type="submit" disabled={!connected || !prompt.trim()}>执行任务</button>
            </div>
          </div>
        </form>
        <div className="examples">{examples.map((item, index) => <button key={item} onClick={() => setPrompt(item)}>示例 {index + 1}</button>)}</div>
        {error && <div className="error">{error}</div>}
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
              <button className="ghost" disabled={!canControl} onClick={() => send({type: "retry", run_id: currentRun})}>重试任务</button>
              <button className="danger" disabled={!canControl} onClick={() => send({type: "rollback", run_id: currentRun})}>精准回滚</button>
              <button className="ghost" disabled={!canControl} onClick={() => send({type: "feedback", run_id: currentRun, label: "accepted"})}>正确</button>
              <button className="ghost" disabled={!canControl} onClick={() => send({type: "feedback", run_id: currentRun, label: "partial"})}>部分正确</button>
              <button className="danger" disabled={!canControl} onClick={() => send({type: "feedback", run_id: currentRun, label: "rejected"})}>错误</button>
            </div>
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
  return <article className={`event ${success === false ? "failed" : ""}`}><span className="event-dot" /><div><div className="event-head"><strong>{title}</strong><time>#{event.seq}</time></div><p>{event.type}</p>{payload.arguments ? <code>{JSON.stringify(payload.arguments)}</code> : null}</div></article>;
}

function ObjectCard({object}: {object: SceneObject}) {
  const color = object.color?.length === 3 ? `rgb(${object.color.join(",")})` : "#738087";
  const groups = object.groups?.length ? ` · ${object.groups.join(", ")}` : "";
  return <article className="object-card"><span className="swatch" style={{background: color}} /><div><strong>{object.name || object.type}</strong><p>{object.type} · {object.layer}{groups}</p><code>size {object.size?.join(" × ")} · center {object.center?.join(", ")}</code></div></article>;
}
