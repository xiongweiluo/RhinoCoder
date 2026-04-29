/*
 * rhinocoder/agent/ui/app.js
 * UI ↔ Agent WebSocket 通信逻辑。
 *
 * 消息类型（下行）：
 *   stream_token      — 追加流式 token 至输出区
 *   route_decision    — 更新路由状态指示灯（LOCAL / CLOUD）
 *   execution_result  — 显示代码执行成功/失败状态
 *
 * 消息类型（上行）：
 *   instruction       — 用户输入的自然语言指令
 */
