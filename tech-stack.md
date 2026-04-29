# RhinoCoder Hybrid — MVP 技术栈选型文档

**版本:** 1.0  
**状态:** MVP 阶段技术选型  
**作者:** 罗雄伟 (ETH Zurich, Integrated Building Systems)  
**最后更新:** 2026-04  
**关联文档:** design-document.md v0.2

---

## 目录

1. [选型原则](#1-选型原则)
2. [Agent 主控程序](#2-agent-主控程序)
3. [前端与交互界面](#3-前端与交互界面)
4. [LLM 数据蒸馏流水线](#4-llm-数据蒸馏流水线)
5. [本地数据库](#5-本地数据库)
6. [Pass@1 评估框架](#6-pass1-评估框架)
7. [完整依赖清单](#7-完整依赖清单)
8. [技术债务与升级路径](#8-技术债务与升级路径)

---

## 1. 选型原则

所有模块的选型均依据以下三个维度，按优先级排序：

| 优先级 | 维度 | 说明 |
|---|---|---|
| P1 | **开发成本低** | MVP 阶段以最小工程投入验证核心假设，避免过度设计 |
| P2 | **性能损耗小** | 不引入不必要的中间层，保证路由中枢 <800ms 端到端延迟目标 |
| P3 | **架构兼容性强** | 与 design-document.md 中已定义的进程拓扑、接口规范保持一致 |

> **MVP 阶段边界定义：** 本文档的选型服务于 Q2–Q3 原型验证阶段。各模块均标注了 Q4 生产版本的升级路径，MVP 阶段不应为生产需求提前优化。

---

## 2. Agent 主控程序

### 2.1 选型结论

**`asyncio`（标准库）+ `mcp` Python SDK + `Typer`**

排除 FastAPI 和 Streamlit 的核心理由：两者解决的是"如何对外暴露 HTTP 服务"，而 `rhinocoder-agent` 的本质是一个**长驻的事件驱动主控进程**——对外不暴露 HTTP 接口，对内需同时管理 MCP 连接、本地推理调用、云端 API 调用三条异步链路。引入 web 框架只会增加进程复杂度，无任何收益。

### 2.2 核心依赖

```
mcp              # Anthropic 官方 Python SDK，原生支持 MCP client/server 双模式
httpx            # 异步 HTTP 客户端，统一调用 vLLM 本地 API 与云端 LLM API
typer            # 声明式 CLI 入口，替代 argparse，零学习成本
pydantic         # 路由日志结构体、rhinocoder.yaml 配置文件验证
python-dotenv    # 环境变量管理，API Key 安全注入
uvloop           # 高性能事件循环（仅 Linux/macOS，Windows 自动降级）
```

### 2.3 进程启动结构

```python
# rhinocoder/cli.py — 主入口
import typer, asyncio, sys
from rhinocoder.agent import RhinoCoderAgent

app = typer.Typer()

@app.command()
def start(config: str = "rhinocoder.yaml"):
    """启动 RhinoCoder Agent 主控进程"""
    # Windows 兼容：ProactorEventLoop 与 uvloop 不兼容
    if sys.platform != "win32":
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    agent = RhinoCoderAgent.from_config(config)
    asyncio.run(agent.serve())

if __name__ == "__main__":
    app()
```

```python
# rhinocoder/agent.py — 核心异步主控逻辑骨架
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class RhinoCoderAgent:
    async def serve(self):
        async with stdio_client(self.mcp_params) as (read, write):
            async with ClientSession(read, write) as mcp_session:
                await mcp_session.initialize()
                # 启动路由中枢事件循环
                await self.router.run(mcp_session)
```

### 2.4 配置文件结构（rhinocoder.yaml）

```yaml
agent:
  log_level: INFO
  db_path: ./data/rhinocoder.db
  feedback_path: ./data/feedback.jsonl

local_model:
  base_url: http://127.0.0.1:8000/v1
  model: rhinocoder-7b
  temperature: 0.1
  max_tokens: 1024

cloud_llm:
  provider: deepseek
  model: deepseek-v4-pro
  api_key_env: RHINOCODER_CLOUD_API_KEY
  max_context_tokens: 800_000
  timeout_s: 60
  fallback_to_local: true
  fallback_provider: anthropic
  fallback_model: claude-sonnet-4-5

mcp:
  server_command: python
  server_args: ["./rhino_mcp_server.py"]
```

### 2.5 Windows / macOS 跨平台注意事项

| 问题 | Windows | macOS |
|---|---|---|
| 事件循环 | `ProactorEventLoop`（默认），禁用 `uvloop` | `SelectorEventLoop` + `uvloop` 加速 |
| 路径分隔符 | 使用 `pathlib.Path`，禁止硬编码 `\` | — |
| 进程信号 | `SIGTERM` 不可靠，用 `asyncio.Event` 做优雅退出 | 标准 `SIGTERM` |
| vLLM 推理服务 | 须在 WSL2 内启动，Agent 通过 `localhost` 访问 | 原生运行 |

---

## 3. 前端与交互界面

### 3.1 选型结论

**localhost 轻量 HTML Panel + Rhino 内嵌 WebView**

| 方案 | 开发成本 | Rhino 集成度 | 跨平台 | MVP 适合度 |
|---|---|---|---|---|
| C# Eto.Forms 原生面板 | 高（需 .NET 开发能力） | ⭐⭐⭐⭐⭐ 最原生 | ✅ | ❌ 太重，Q4 再考虑 |
| React + Electron | 极高，完全独立进程 | ❌ 割裂感强 | ✅ | ❌ 完全不适合 |
| Streamlit / Gradio 独立窗口 | 低 | ❌ 需切换窗口 | ✅ | 🟡 调试可用，不适合交付 |
| **localhost HTML + Rhino WebView** | **极低，纯 HTML/JS** | **⭐⭐⭐⭐ 嵌入感强** | **✅** | **✅ 推荐** |

### 3.2 实现方案

Agent 启动时同时启动一个轻量静态文件服务（`aiohttp`，约 20 行），Rhino 插件侧注册内嵌 WebView 面板指向该地址，交互逻辑全部写在 HTML/JS 中，修改无需重新编译 .NET 插件。

**Agent 侧：静态服务启动**

```python
# rhinocoder/ui_server.py
from aiohttp import web

async def start_ui_server(port: int = 7860):
    app = web.Application()
    app.router.add_static("/", path="./rhinocoder/ui/", name="ui")
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    return runner  # 保留引用以便优雅关闭
```

**Rhino 插件侧：注册内嵌面板（Python Script）**

```python
# rhino_mcp_server.py 内，随 MCP Server 一同初始化
import Rhino.UI, Eto.Forms, Eto.Drawing

class RhinoCoderPanel(Eto.Forms.Panel):
    def __init__(self):
        self.Content = Eto.Forms.WebView()
        self.Content.Url = System.Uri("http://127.0.0.1:7860/index.html")

# 注册面板（仅执行一次）
Rhino.UI.Panels.RegisterPanel(
    RhinoCoderPlugin.Instance,
    RhinoCoderPanel,
    "RhinoCoder",
    Eto.Drawing.Bitmap("icon.png")
)
```

**UI 目录结构（最小化）：**

```
rhinocoder/ui/
├── index.html      # 主界面：输入框 + 输出区 + 路由状态指示灯
├── style.css       # 极简样式，跟随 Rhino 深色主题
└── app.js          # 与 Agent WebSocket 通信，展示流式输出
```

### 3.3 Agent ↔ UI 通信

UI 与 Agent 通过 **WebSocket**（同一 `aiohttp` 实例）通信，避免轮询延迟：

```javascript
// app.js
const ws = new WebSocket("ws://127.0.0.1:7860/ws");

ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "stream_token") appendToOutput(msg.token);
    if (msg.type === "route_decision") updateRouteIndicator(msg.route);
    if (msg.type === "execution_result") showExecutionStatus(msg.success);
};

function sendInstruction(text) {
    ws.send(JSON.stringify({ type: "instruction", content: text }));
}
```

---

## 4. LLM 数据蒸馏流水线

### 4.1 选型结论

**`httpx` 异步批量调用大模型 API（DeepSeek-V3 / Claude 3.5）+ `asyncio` 并发控制**

放弃 McNeel 论坛爬虫的核心原因：论坛代码噪音大（大量不完整片段、过时 API、无指令上下文），清洗人工成本与最终数据质量之间投入产出比过低。改为以 rhinoscriptsyntax / RhinoCommon 官方源码与 API 文档为基础上下文，通过大模型蒸馏直接生成高质量 instruction+code 配对样本。`httpx` 已是 Agent 主控的现有依赖，复用即可，无需引入新的重型框架。

### 4.2 官方文档解析层

```python
# pipeline/doc_loader.py
import inspect, importlib

def extract_rhinoscriptsyntax_entries() -> list[str]:
    """从 rhinoscriptsyntax 库源码提取所有公开函数的文档条目。"""
    import rhinoscriptsyntax as rs
    entries = []
    for name in dir(rs):
        obj = getattr(rs, name)
        if callable(obj) and not name.startswith("_"):
            doc = inspect.getdoc(obj) or ""
            sig = str(inspect.signature(obj))
            entries.append(f"函数：rs.{name}{sig}\n文档：{doc}")
    return entries
```

### 4.3 蒸馏调用层

```python
# pipeline/distiller.py
import httpx, asyncio, json, os

SYSTEM_PROMPT = """你是 Rhino/Grasshopper 专家。根据提供的 rhinoscriptsyntax API 文档片段，
生成多样化的自然语言指令与对应的正确 Python 代码配对。
要求：指令覆盖 API 的主要使用场景（初级/中级/复合操作各占约 1/3），代码必须完整可运行。
输出格式为 JSONL，每行：{"instruction": "...", "output": "..."}"""

async def distill_api_entry(
    client: httpx.AsyncClient,
    api_doc_chunk: str,
    semaphore: asyncio.Semaphore,
) -> list[dict]:
    async with semaphore:
        response = await client.post(
            "https://api.deepseek.com/chat/completions",
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"API 文档片段：\n{api_doc_chunk}"},
                ],
                "max_tokens": 2048,
                "temperature": 0.8,
            },
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return [json.loads(line) for line in content.splitlines() if line.strip().startswith("{")]

async def run_distillation(
    api_chunks: list[str],
    output_path: str,
    max_concurrent: int = 10,
) -> int:
    semaphore = asyncio.Semaphore(max_concurrent)
    total = 0
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"},
        timeout=60.0,
    ) as client:
        tasks = [distill_api_entry(client, chunk, semaphore) for chunk in api_chunks]
        with open(output_path, "a", encoding="utf-8") as f:
            for coro in asyncio.as_completed(tasks):
                for sample in await coro:
                    f.write(json.dumps(sample, ensure_ascii=False) + "\n")
                    total += 1
    return total
```

### 4.4 流水线完整执行顺序

```
① extract_api_entries()    从官方库源码提取全量 API 条目
        │
        ▼
② chunk_api_docs()         按 API 组/模块拆分为适合单次蒸馏的片段
        │
        ▼
③ run_distillation()       并发调用 DeepSeek-V3 / Claude 3.5，每片段生成 3–5 条样本
        │
        ▼
④ validate_syntax()        ast.parse() 语法合法性过滤
        │
        ▼
⑤ validate_api_names()     比对官方文档，过滤幻觉 API 调用
        │
        ▼
⑥ format_as_sft()          确认 {"instruction": ..., "output": ...} 格式完整性
        │
        ▼
⑦ 写入 ./data/sft_dataset.jsonl
```

> **成本参考：** 以 ~43,000 条样本为目标，预计蒸馏 ~9,000 个 API 条目片段（每片段生成 ~5 条）。使用 DeepSeek-V3（$0.14/1M input tokens）估算总蒸馏成本约 $15–25，单次投入即可完成全量数据集生成。

---

## 5. 本地数据库

### 5.1 选型结论

**双轨制：SQLite（路由日志审计）+ JSONL（RLHF 训练数据）**

两者不是竞争关系，而是服务不同下游用途：SQLite 服务合规查询，JSONL 直接作为训练数据格式。

| 数据类型 | 存储方案 | 核心理由 |
|---|---|---|
| 路由决策日志 | **SQLite** | 需要按时间、`privacy_flag`、路由结果多维查询，SQL 是天然工具 |
| RLHF 用户反馈 | **JSONL** | 直接兼容 HuggingFace `datasets`，无需任何格式转换 |

### 5.2 SQLite：路由日志表结构

```sql
-- 路由决策日志，用于合规审计与路由质量监控
CREATE TABLE IF NOT EXISTS routing_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT    NOT NULL,           -- ISO 8601 时间戳
    inst_hash     TEXT    NOT NULL,           -- 指令 sha256，不存原文
    rule_result   TEXT,                       -- ROUTE_LOCAL / ROUTE_CLOUD / UNCERTAIN
    clf_label     TEXT,                       -- geo_op / api_call / concept_plan / hybrid
    clf_conf      REAL,                       -- 分类器置信度
    final_route   TEXT    NOT NULL,           -- LOCAL / CLOUD
    privacy_flag  INTEGER NOT NULL DEFAULT 0, -- 1 = 含敏感数据
    latency_ms    INTEGER                     -- 端到端路由延迟
);

-- 核心合规查询：任何一天出现该结果都应触发告警
SELECT date(ts), COUNT(*) as suspicious_count
FROM routing_log
WHERE privacy_flag = 1 AND final_route = 'CLOUD'
GROUP BY date(ts);

-- 路由质量监控：分类器置信度均值低于 0.75 时预警数据漂移
SELECT date(ts), AVG(clf_conf) as avg_conf
FROM routing_log
WHERE clf_label IS NOT NULL
GROUP BY date(ts)
HAVING avg_conf < 0.75;
```

```python
# rhinocoder/db.py — SQLite 写入封装（标准库，零依赖）
import sqlite3, json
from pathlib import Path
from dataclasses import dataclass

@dataclass
class RoutingLogEntry:
    ts: str
    inst_hash: str
    rule_result: str | None
    clf_label: str | None
    clf_conf: float | None
    final_route: str
    privacy_flag: bool
    latency_ms: int

class RoutingDB:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_schema()

    def _init_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS routing_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT, inst_hash TEXT, rule_result TEXT,
                clf_label TEXT, clf_conf REAL, final_route TEXT,
                privacy_flag INTEGER, latency_ms INTEGER
            )
        """)
        self.conn.commit()

    def insert(self, entry: RoutingLogEntry):
        self.conn.execute(
            "INSERT INTO routing_log VALUES (NULL,?,?,?,?,?,?,?,?)",
            (entry.ts, entry.inst_hash, entry.rule_result, entry.clf_label,
             entry.clf_conf, entry.final_route, int(entry.privacy_flag), entry.latency_ms)
        )
        self.conn.commit()
```

### 5.3 JSONL：RLHF 反馈格式

```python
# rhinocoder/feedback.py — JSONL 追加写入
import json
from pathlib import Path
from datetime import datetime, timezone

FEEDBACK_SCHEMA = {
    "ts":          str,   # ISO 8601
    "instruction": str,   # 原始自然语言指令（不含敏感坐标）
    "generated":   str,   # 模型生成的代码
    "edited":      str,   # 设计师修改后的代码，未修改则为 null
    "label":       str,   # accepted / corrected / rejected
    "route":       str,   # LOCAL / CLOUD，记录该样本来源路径
}

def append_feedback(path: str, entry: dict):
    """线程安全的 JSONL 追加写入"""
    entry["ts"] = datetime.now(timezone.utc).isoformat()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
```

**JSONL 样本格式示例：**

```jsonl
{"ts": "2026-04-27T10:23:01Z", "instruction": "生成一个半径5的球体", "generated": "sphere = rs.AddSphere([0,0,0], 5)", "edited": null, "label": "accepted", "route": "LOCAL"}
{"ts": "2026-04-27T10:25:33Z", "instruction": "创建参数化网格曲面", "generated": "...", "edited": "...", "label": "corrected", "route": "CLOUD"}
```

**HuggingFace Datasets 直接读取（无需转换）：**

```python
from datasets import load_dataset
ds = load_dataset("json", data_files="./data/feedback.jsonl", split="train")
accepted = ds.filter(lambda x: x["label"] in ["accepted", "corrected"])
```

---

## 6. Pass@1 评估框架

### 6.1 选型结论

**三层递进测试架构：Mock 层 + `rhino3dm` 几何验证层 + Rhino.Compute 全量集成层**

在 MVP 阶段完全模拟 Rhino 运行时是不现实的，采用成本递增的三层策略，每层解决不同粒度的问题。

| 测试层 | 工具 | 运行环境 | 执行频率 | 覆盖问题 |
|---|---|---|---|---|
| L1：API 合法性 | `pytest` + `unittest.mock` | 纯 Python，无需 Rhino | 每次提交 (CI) | 幻觉 API、语法错误 |
| L2：几何结果验证 | `pytest` + `rhino3dm` | 纯 Python，无需授权 | 每次提交 (CI) | 基础几何操作正确性 |
| L3：全量集成 | `pytest` + Rhino.Compute | 需本地 Rhino 授权 | 每周回归 | Grasshopper、显示管线 |

### 6.2 L1：API 合法性测试（Mock 层）

```python
# tests/conftest.py — 注入假 Rhino 命名空间
import sys
from unittest.mock import MagicMock

def pytest_configure(config):
    """在 pytest 收集测试前注入桩模块，拦截所有 Rhino import"""
    rhino_modules = [
        "rhinoscriptsyntax", "Rhino", "Rhino.Geometry",
        "Rhino.DocObjects", "Rhino.Commands", "scriptcontext",
    ]
    for mod in rhino_modules:
        sys.modules[mod] = MagicMock()
```

```python
# tests/test_l1_api_validity.py
import pytest
from rhinocoder.evaluator import RhinoCoderEvaluator

# 测试用例：(指令, 是否应通过 L1 测试)
TEST_CASES_L1 = [
    ("生成一个半径为5的球体", True),
    ("创建一条从原点到(1,1,1)的直线", True),
    ("调用 rs.FakeHallucinatedAPI()", False),   # 幻觉 API，应失败
    ("import os; os.system('rm -rf /')", False), # 危险代码，应失败
]

@pytest.mark.parametrize("instruction,should_pass", TEST_CASES_L1)
def test_api_validity(instruction: str, should_pass: bool, evaluator):
    code = evaluator.generate(instruction)
    result = evaluator.check_syntax_and_imports(code)
    assert result.passed == should_pass, f"代码: {code}\n错误: {result.error}"
```

### 6.3 L2：几何结果验证（rhino3dm 层）

`rhino3dm` 是 McNeel 官方开源库（Apache 2.0），提供完整的几何计算能力，无需 Rhino 许可证，可在 CI 环境直接运行。

```python
# tests/test_l2_geometry.py
import rhino3dm, pytest

# 标准测试用例：(指令, 验证函数)
def validate_sphere(result):
    """验证生成的球体半径是否符合预期"""
    assert result.sphere is not None
    assert abs(result.sphere.Radius - 5.0) < 1e-6

def validate_line(result):
    """验证生成的线段端点是否正确"""
    line = result.line
    assert line is not None
    assert line.From.DistanceTo(rhino3dm.Point3d(0, 0, 0)) < 1e-6
    assert line.To.DistanceTo(rhino3dm.Point3d(1, 1, 1)) < 1e-6

GEOMETRY_TEST_CASES = [
    ("生成一个圆心在原点、半径为5的球体", validate_sphere),
    ("创建一条从(0,0,0)到(1,1,1)的直线", validate_line),
]

@pytest.mark.parametrize("instruction,validator", GEOMETRY_TEST_CASES)
def test_geometry_correctness(instruction, validator, evaluator):
    code = evaluator.generate(instruction)
    result = evaluator.execute_with_rhino3dm(code)
    validator(result)
```

### 6.4 L3：全量集成测试（Rhino.Compute 层）

此层仅在每周回归测试中运行，需要本地 Rhino 授权。

```bash
# 启动 Rhino.Compute 无头服务（本地，需 Rhino 8 授权）
./compute.geometry.exe --port 6500 --childcount 2
```

```python
# tests/test_l3_integration.py
import pytest, httpx

COMPUTE_URL = "http://localhost:6500"

@pytest.mark.integration  # 标记为集成测试，默认跳过
async def test_grasshopper_component_execution():
    """验证生成的 GHPython 代码在真实 Grasshopper 组件中可运行"""
    code = evaluator.generate("在Grasshopper中创建一个数列并映射到曲线上")
    response = await httpx.AsyncClient().post(
        f"{COMPUTE_URL}/grasshopper",
        json={"algo": code, "pointer": None, "values": []}
    )
    assert response.status_code == 200
    result = response.json()
    assert not result.get("errors"), f"执行错误: {result['errors']}"
```

```bash
# 日常 CI：只运行 L1 + L2
pytest tests/ -m "not integration" --tb=short

# 每周回归：完整三层
pytest tests/ --tb=long -v
```

### 6.5 Pass@1 自动化统计

```python
# rhinocoder/evaluator.py — Pass@1 批量评估
from dataclasses import dataclass

@dataclass
class EvalResult:
    total: int
    passed_l1: int
    passed_l2: int
    pass_at_1_l1: float  # 语法+API合法性通过率
    pass_at_1_l2: float  # 几何正确性通过率

def run_pass_at_1_benchmark(
    test_cases: list[dict],
    evaluator: "RhinoCoderEvaluator"
) -> EvalResult:
    l1_pass, l2_pass = 0, 0
    for case in test_cases:
        code = evaluator.generate(case["instruction"])
        if evaluator.check_syntax_and_imports(code).passed:
            l1_pass += 1
            if evaluator.execute_with_rhino3dm(code).matches(case["expected"]):
                l2_pass += 1

    n = len(test_cases)
    return EvalResult(
        total=n,
        passed_l1=l1_pass,
        passed_l2=l2_pass,
        pass_at_1_l1=l1_pass / n,
        pass_at_1_l2=l2_pass / n,
    )
```

---

## 7. 完整依赖清单

```toml
# pyproject.toml
[project]
name = "rhinocoder"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    # Agent 主控
    "mcp>=1.0",
    "httpx>=0.27",
    "typer>=0.12",
    "pydantic>=2.7",
    "python-dotenv>=1.0",
    "aiohttp>=3.9",          # UI 静态服务 + WebSocket

    # 评估框架
    "rhino3dm>=8.0",         # L2 几何验证，无需 Rhino 授权
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]

[project.optional-dependencies]
mac = ["uvloop>=0.19"]           # macOS/Linux 性能加速
dev = ["ruff", "mypy", "black"]
```

**依赖规模说明：** 核心运行时依赖仅 6 个包，有意控制依赖树深度，降低跨平台兼容性风险。

---

## 8. 技术债务与升级路径

MVP 阶段的选型刻意以开发速度优先，以下技术债务需在 Q4 生产版本中偿还：

| 模块 | MVP 方案 | Q4 升级目标 | 触发条件 |
|---|---|---|---|
| 交互界面 | localhost HTML WebView | C# Eto.Forms 原生面板 | 用户反馈界面响应延迟 / 需要原生拖拽操作 |
| MCP Server | 复用 rhino-mcp 开源方案 | 自研 .NET Plugin（方案 B） | Q3 压测中出现连接不稳定 / 崩溃 |
| 数据库 | SQLite 单文件 | PostgreSQL（多用户工作室版） | 并发写入 > 4 用户时出现锁竞争 |
| 评估 L3 | Rhino.Compute 手动触发 | 自动化 CI 集成（GitHub Actions Self-hosted Runner） | Q4 模型迭代频率 > 每两周一次 |

---

*本文档为 MVP 阶段技术选型基准，所有选型在 Q2 技术评审后最终确认。生产版本升级计划随 Q3 压测结果动态调整。*
