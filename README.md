# RhinoCoder

RhinoCoder 是一个基于 MCP 的 Rhino 8 空间设计 Agent。系统把自然语言任务转换为可审计的工具调用，并通过场景感知和程序化断言验证真实几何结果。

## 当前状态

### 已实现

- Python Agent、FastMCP Server 与 Rhino HTTP Listener 端到端链路。
- 23 项几何、变换、属性与感知工具。
- `get_scene_summary` 场景闭环感知。
- 数量、属性和空间关系断言，以及 Partial Pass 评分。
- 30 条分级评测任务和半自动轨迹采集器。
- 精准删除、评测环境重置与基础错误接管。
- 结构化 `AgentRunResult`、统一事件流与任务级 Trace。
- Baseline / Closed-loop 多轮对照评测与 JSON/Markdown 报告生成。
- React + TypeScript WebSocket 交互面板与三份脱敏 Replay。
- 停止、重试、Undo、精准回滚和三类用户反馈。
- 用户反馈、敏感字段脱敏和黄金样本准入规则。

### 待真实环境验收

- macOS + Rhino 8 + DeepSeek 兼容 API 的 30 题重复基准。
- Closed-loop Pass@1 不低于 70% 的发布门槛。
- 三个核心场景在真实 Rhino 环境中连续 3 次成功。
- 新环境首次安装、Rhino 重连与 WebSocket 断线恢复演练。

### 后续规划

- 本地/云端混合路由和 SQLite 审计。
- 隐私红队任务。
- 小规模 LoRA 与多模型对照实验。
- Windows 验证、原生插件与多用户部署。

完整路线见 [PROJECT_OPTIMIZATION_PLAN.md](PROJECT_OPTIMIZATION_PLAN.md)。

## 架构

```text
User / UI
   | WebSocket events
RhinoCoder Agent -- OpenAI-compatible LLM
   | MCP stdio
FastMCP Server
   | localhost HTTP
Rhino Listener -- Rhino main thread -- Rhino document
   |
Scene Summary -> Eval assertions -> Trace / feedback
```

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

填写 `.env` 中的模型配置。不要提交真实密钥。

也可以使用项目脚本完成依赖安装与前端构建：

```bash
./scripts/bootstrap.sh
```

在 Rhino Script Editor 中启动 Listener：

```python
import sys
sys.path.insert(0, "/absolute/path/to/RhinoCoder/plugin")
from rhino_listener import listener_main
listener_main.start_listener()
```

执行任务：

```bash
python agent/main.py --prompt "在原点创建一个半径为 10 的球体"
```

启动交互 UI：

```bash
./scripts/start.sh
```

然后打开 `http://127.0.0.1:7860`。离线时可从界面加载三份脱敏 Replay。

## 评测与验证

仅校验30条任务格式，不连接 Rhino 或模型：

```bash
python eval/run_eval.py --dry-run
```

运行本地自动检查：

```bash
python -m compileall -q agent data_pipeline eval plugin tools
python -m pytest -q
python tools/check_secrets.py
```

等价的一键检查：

```bash
./scripts/check.sh
```

真实端到端评测需要 Rhino Listener、有效模型配置以及 `.env` 中的 `RHINOCODER_EVAL_TOKEN`。配置或更换令牌后必须在 Rhino 中重新启动 Listener；可通过 `python tools/doctor.py` 确认 `Rhino eval reset` 已启用。

完整 Baseline / Closed-loop 对照：

```bash
./scripts/benchmark.sh
```

## 安全边界

- Listener 仅绑定 `127.0.0.1`。
- `.env`、运行轨迹、评测结果和真实数据默认不进入 Git。
- `reset_environment` 只用于显式评测流程，不应暴露给普通 UI。
- 仓库历史中曾出现过密钥格式的值；使用者必须轮换对应密钥，删除工作区内容不能使旧密钥失效。

## 已知限制

- 当前主要验证环境为 macOS + Rhino 8。
- 完整30题基准需要交互式 Rhino 环境，CI 只运行离线测试。
- 混合路由、本地微调模型和生产级并发不属于当前稳定原型。

架构和恢复策略见 [docs/architecture.md](docs/architecture.md)，常见问题见 [docs/troubleshooting.md](docs/troubleshooting.md)，发布门槛见 [docs/release-checklist.md](docs/release-checklist.md)。
