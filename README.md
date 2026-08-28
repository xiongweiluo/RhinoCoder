# RhinoCoder

RhinoCoder 是一个基于 MCP 的 Rhino 8 空间设计 Agent。系统把自然语言任务转换为可审计的工具调用，并通过场景感知和程序化断言验证真实几何结果。

当前稳定原型版本：`0.2.0`。Prompt、工具 Schema、Trace Schema、运行时和依赖锁定信息见 [版本清单](docs/version-manifest.json)。

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
- 30 题、两种模式、各重复 3 次的真实基准已完成，Pass@1 均为 100%。
- DeepSeek 缓存命中、未命中与输出 token 的版本化成本核算。
- React + TypeScript WebSocket 交互面板与三份脱敏 Replay。
- 停止、重试、Undo、精准回滚和三类用户反馈。
- 用户反馈、敏感字段脱敏和黄金样本准入规则。
- 三个核心场景已在真实 Rhino 环境中各连续运行 3 次成功，详见 [UI 真实环境验收报告](docs/ui-acceptance-report.md)。
- WebSocket 快照恢复、Rhino Listener 热重启和四类故障恢复已完成真实验收，详见 [断线与故障恢复验收报告](docs/recovery-acceptance-report.md)。
- 停止、重试、Undo、任务级精准回滚和三类反馈已完成真实演练，详见 [交互控制真实环境验收报告](docs/interaction-control-acceptance-report.md)。

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

前置要求：

- macOS 14 或更高版本。
- Rhino 8。
- Python 3.11–3.13；不要使用版本低于 3.11 的 macOS 系统 Python。
- Node.js `^20.19.0` 或 `>=22.12.0`。

推荐使用一键安装。脚本会创建项目 `.venv`、安装 `requirements-lock.txt` 中的固定 Python 依赖、执行 `npm ci` 并构建前端：

```bash
RHINOCODER_PYTHON=python3 ./scripts/bootstrap.sh
```

如果 `python3 --version` 低于 3.11，请把 `RHINOCODER_PYTHON` 改成新解释器的完整路径。安装完成后填写 `.env` 中的模型配置，不要提交真实密钥。

手动等价步骤：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
npm ci --prefix agent/ui
npm run build --prefix agent/ui
cp .env.example .env
```

在 Rhino Script Editor 中启动 Listener：

```text
_-ScriptEditor _Run "/absolute/path/to/RhinoCoder/plugin/start_rhinocoder_listener.py"
```

该命令使用 Rhino 8 的新脚本基础设施，并支持在 Listener 已运行时安全热重载。也可以在 Script Editor 中直接打开并运行该文件。旧的 `RunPythonScript` 命令可能调用不兼容的旧 Python 引擎，不应用于此入口。

底层等价导入方式：

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

首次安装建议先运行只读任务，确认 LLM、MCP 与 Rhino 链路，不改变当前场景：

```bash
.venv/bin/python agent/main.py --prompt "读取当前 Rhino 场景摘要并报告对象数量；不要创建、删除、移动或修改任何对象。"
```

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

在临时目录重建公开工作区、虚拟环境和前端，并运行 Replay 首任务；`--local-rhino` 会额外通过 localhost MCP 执行只读 Rhino 首任务，不会把场景数据发送给外部模型：

```bash
python tools/verify_clean_install.py --local-rhino
```

该脚本不复制 `.env`、`.git`、本地 Trace 或现有虚拟环境；只读 Rhino 检查不打印或保存场景内容，临时工作区在验收后删除。

真实端到端评测需要 Rhino Listener、有效模型配置以及 `.env` 中的 `RHINOCODER_EVAL_TOKEN`。配置或更换令牌后必须在 Rhino 中重新启动 Listener；可通过 `python tools/doctor.py` 确认 `Rhino eval reset` 已启用。

完整 Baseline / Closed-loop 对照：

```bash
./scripts/benchmark.sh
```

最近一次脱敏汇总见 [30 题基准报告](docs/benchmark-report.md)。完整 JSON、工具轨迹和场景快照仅保留在本地。

DeepSeek 官方模型会按版本化的缓存命中、缓存未命中和输出单价自动估算成本；历史结果可在不重新调用 Rhino 或 LLM 的情况下重算：

```bash
python tools/recalculate_benchmark_cost.py eval/results/<benchmark>.json
```

审计本地黄金数据准入、Partial/Fail 分流和公开报告/Replay 脱敏：

```bash
python tools/audit_trace_data.py
python tools/audit_release_data.py
```

新黄金数据只写入 `data/golden_traces_v2.jsonl`。旧的根目录 `golden_dataset.jsonl` 缺少当前准入元数据，只作为本地 legacy 数据保留，不会进入新 SFT 正样本。完整验收证据见 [数据与脱敏验收报告](docs/data-sanitization-acceptance-report.md)。

## 真实黄金数据采集

无需 GPU 即可在单台 Mac 上启动第一阶段 30 条真实黄金轨迹采集。清单包含 30 条唯一指令和 29 个标签，并覆盖旋转、移动、分布、对齐、Undo、布尔、感知和空间关系等任务。

先校验清单和查看进度：

```bash
python agent/data_collector.py --dry-run
python agent/data_collector.py --status
```

在 Rhino 中打开空白、可丢弃的专用文档后，每次先采一条：

```bash
python agent/data_collector.py --allow-reset --limit 1
```

采集器不会默认清空非空场景。每条轨迹仍必须通过程序断言、场景自检、人工确认、脱敏审计和 campaign 任务去重才能进入黄金集。完整操作与人工验收标准见[真实黄金轨迹采集指南](docs/golden-data-collection.md)。

## 安全边界

- Listener 仅绑定 `127.0.0.1`。
- `.env`、运行轨迹、评测结果和真实数据默认不进入 Git。
- `reset_environment` 只用于显式评测流程，不应暴露给普通 UI。
- 仓库历史中曾出现过密钥格式的值；使用者必须轮换对应密钥，删除工作区内容不能使旧密钥失效。

## 已知限制

- 当前主要验证环境为 macOS 15.6 arm64 + Rhino 8；clean-room 安装已在该环境完成，尚未在另一台物理 Mac 或 Intel Mac 上复验。
- 完整30题基准需要交互式 Rhino 环境，CI 只运行离线测试。
- 混合路由、本地微调模型和生产级并发不属于当前稳定原型。

架构和恢复策略见 [docs/architecture.md](docs/architecture.md)，常见问题见 [docs/troubleshooting.md](docs/troubleshooting.md)，发布门槛见 [docs/release-checklist.md](docs/release-checklist.md)。
