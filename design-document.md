# RhinoCoder Hybrid — 技术设计文档

**版本:** 0.2  
**状态:** 内部评审草案（架构升级修订）  
**作者:** 罗雄伟 (ETH Zurich, Integrated Building Systems)  
**最后更新:** 2026-04  
**变更摘要 (v0.1 → v0.2):** 云端大脑升级为 DeepSeek-V4-Pro；补充 16GB 统一内存部署规范；新增 API 成本经济性对比分析

---

## 目录

1. [系统概述](#1-系统概述)
2. [整体架构](#2-整体架构)
3. [混合路由中枢](#3-混合路由中枢)
4. [本地执行模型 RhinoCoder-7B](#4-本地执行模型-rhinocoder-7b)
5. [云端推理模型接入层](#5-云端推理模型接入层)
6. [MCP 空间交互通道](#6-mcp-空间交互通道)
7. [数据隐私与安全边界](#7-数据隐私与安全边界)
8. [组件间接口定义](#8-组件间接口定义)
9. [微调数据流水线](#9-微调数据流水线)
10. [部署与运维](#10-部署与运维)
11. [开放问题与风险](#11-开放问题与风险)

---

## 1. 系统概述

### 1.1 设计目标

RhinoCoder Hybrid 的核心命题是：在**不泄露企业设计数据**的前提下，将大语言模型的零样本规划能力与本地微调模型的精确 API 执行能力结合，为 Rhino/Grasshopper 提供毫秒级 AI 辅助建模体验。

### 1.2 核心设计原则

| 原则 | 说明 |
|---|---|
| **数据重力 (Data Gravity)** | 敏感几何数据永远不离开本地网络边界，计算向数据靠拢而非反之 |
| **厂商无关 (Vendor Agnostic)** | 云端模型通过统一适配器接入，支持运行时动态切换 |
| **渐进增强 (Progressive Enhancement)** | 断网环境下系统降级为纯本地模式，核心建模能力不中断 |
| **可审计路由 (Auditable Routing)** | 每条指令的路由决策均记录原因，便于调试与合规审查 |

### 1.3 关键性能目标

| 指标 | 当前基线 | 目标值 |
|---|---|---|
| 基础建模指令延迟 | > 5s (纯云端) | < 800ms |
| Rhino API 代码 Pass@1 | ~40% (通用模型) | ≥ 85% |
| 几何坐标数据云端泄露率 | 不可控 | 0% |
| 断网可用建模覆盖率 | 0% | ≥ 70% |

---

## 2. 整体架构

### 2.1 架构图

```
┌─────────────────────────────────────────────────────────┐
│                    设计师工作环境 (本地)                    │
│                                                         │
│  ┌──────────────┐    ┌──────────────────────────────┐   │
│  │  Rhino /     │◄───│      RhinoCoder Agent        │   │
│  │ Grasshopper  │    │  ┌────────────────────────┐  │   │
│  │  (Plugin)    │───►│  │   混合路由中枢 (Router)  │  │   │
│  └──────────────┘    │  │  ① 规则引擎 (快速通道)   │  │   │
│        ▲             │  │  ② 意图分类器 (兜底)     │  │   │
│        │ MCP         │  └────────┬───────┬────────┘  │   │
│        │             │           │       │            │   │
│        │             │  ┌────────▼─┐ ┌───▼─────────┐ │   │
│        │             │  │本地执行层 │ │ 云端规划层   │ │   │
│        │             │  │RhinoCoder│ │  DeepSeek   │ │   │
│        └─────────────│  │  -7B SFT │ │  Adapter    │ │   │
│                      │  │(INT4/GPU)│ │             │ │   │
│                      │  └──────────┘ └─────────────┘ │   │
│                      └──────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                                          │ HTTPS (脱敏后)
                              ┌───────────▼──────────────┐
                              │   DeepSeek-V4-Pro API     │
                              │   1M Token Context Window │
                              │  (备选: Claude / GPT-4o)  │
                              └──────────────────────────┘
```

### 2.2 进程拓扑

系统在设计师本地机器上运行以下进程：

- **rhinocoder-agent** — 主控进程，托管路由中枢与 MCP 客户端（Python）
- **rhinocoder-inference** — 本地模型推理服务，提供 OpenAI-compatible REST API（vLLM）
- **rhino-mcp-server** — 嵌入 Rhino 的 MCP Server 插件（.NET/Python Bridge）

---

## 3. 混合路由中枢

路由中枢采用**规则优先、模型兜底**的两阶段判断架构，在保证低延迟的同时维持高准确率。

### 3.1 第一阶段：规则引擎（<5ms）

规则引擎基于关键词、语法模式和上下文信号，对绝大多数明确指令进行快速分类，无需调用任何模型。

**强制本地路由的触发条件（隐私优先）：**

```python
FORCE_LOCAL_PATTERNS = [
    r"\b(坐标|coordinate|xyz|point\s*\()",   # 含具体坐标值
    r"\b(图层|layer)\s*['\"][\w\u4e00-\u9fff]+['\"]", # 含项目专有图层名
    r"(移动|旋转|缩放|偏移)\s*([\d.]+)",       # 含数值的几何微调
    r"(再|more|less|一点|稍微)",               # 增量式调整指令
]
```

**倾向云端路由的触发条件（复杂规划）：**

```python
PREFER_CLOUD_PATTERNS = [
    r"(方案|strategy|concept|设计一个|generate\s+a)",
    r"(如何|怎么|what\s+if|explore|比较.+和.+)",
    r"(参数化|parametric|algorithm|逻辑|整体)",
]
```

**规则引擎输出三种结果：** `ROUTE_LOCAL`、`ROUTE_CLOUD`、`UNCERTAIN`（交给第二阶段）。

### 3.2 第二阶段：意图分类器（<80ms，仅在 UNCERTAIN 时触发）

对规则引擎无法判断的指令，调用一个轻量级本地分类器进行意图识别。

**分类器方案：** 基于 `Qwen2.5-0.5B` 蒸馏的 4 分类头，直接运行在 CPU，避免抢占 GPU 推理资源。

**4 个分类标签：**

| 标签 | 说明 | 路由目标 |
|---|---|---|
| `geo_op` | 明确几何操作，参数明确 | 本地 |
| `api_call` | 已知 Rhino API 直接调用 | 本地 |
| `concept_plan` | 概念设计、方案探索 | 云端 |
| `hybrid` | 需要规划+执行协同 | 云端规划 → 本地执行 |

### 3.3 路由决策日志格式

每条指令均记录完整的路由溯源，支持合规审计：

```json
{
  "timestamp": "2026-04-27T10:23:01Z",
  "instruction_hash": "sha256:a3f...",
  "rule_stage_result": "UNCERTAIN",
  "classifier_label": "geo_op",
  "classifier_confidence": 0.91,
  "final_route": "LOCAL",
  "privacy_flag": false,
  "latency_ms": 43
}
```

---

## 4. 本地执行模型 RhinoCoder-7B

### 4.1 基座模型选型

**选定：Qwen2.5-Coder-7B-Instruct**

| 维度 | Qwen2.5-Coder-7B | DeepSeek-Coder-V2-Lite | Llama-3.1-8B |
|---|---|---|---|
| Python 代码能力 (HumanEval) | **88.4%** | 81.1% | 72.6% |
| 中文指令理解 | **优秀** | 良好 | 一般 |
| 4-bit 量化后显存 (7B) | **~5.5GB** | ~6.5GB (16B MoE) | ~5.5GB |
| 开源协议 | Apache 2.0 | MIT | Llama 3.1 License |
| 社区微调案例 | **丰富** | 较少 | 丰富 |

Qwen2.5-Coder-7B 在代码能力和中文指令理解上具有明显优势，且 Apache 2.0 协议对商业部署友好。

### 4.2 RTX 4090 部署方案

RTX 4090 显存为 24GB，原始 BF16 权重约 14GB，**必须量化**以留出 KV Cache 空间。

**推荐量化方案：AWQ INT4**

```
模型权重:  ~4.5 GB  (AWQ INT4)
KV Cache:  ~8.0 GB  (128K context, batch=4)
推理开销:  ~2.0 GB
─────────────────
总计:      ~14.5 GB  ✅ (24GB 显存充裕)
```

**推理服务框架：vLLM**

```bash
python -m vllm.entrypoints.openai.api_server \
  --model ./rhinocoder-7b-awq \
  --quantization awq \
  --max-model-len 8192 \
  --max-num-seqs 4 \        # 支持4并发设计师
  --port 8000 \
  --trust-remote-code
```

**预期性能（RTX 4090, AWQ INT4）：**

| 场景 | 预期延迟 |
|---|---|
| 短指令代码生成 (≤200 tokens) | 150–350ms |
| 中等代码块 (≤500 tokens) | 350–700ms |
| 复杂函数 (≤1000 tokens) | 700–1400ms |

### 4.3 Apple Silicon / 16GB 统一内存部署规范（INT4）

> **适用场景：** 设计师使用 MacBook Pro / Mac Studio（Apple M 系列芯片，16GB 统一内存），或 Windows 工作站无独立 GPU 仅依赖系统内存推理的边缘部署场景。

#### 4.3.1 统一内存架构约束分析

Apple Silicon 的统一内存（Unified Memory）由 CPU 和 GPU 共享，16GB 配置在同时运行 Rhino 8（macOS 版）时，可用推理预算受到严格限制：

```
系统预留 (macOS + Rhino 8 + Grasshopper):  ~6.0 GB
模型权重 (INT4 量化):                       ~4.5 GB
KV Cache (8K context, batch=1):            ~2.0 GB
推理运行时开销:                             ~1.5 GB
────────────────────────────────────────────────────
总计:                                      ~14.0 GB  ✅ (16GB 可用)
安全余量:                                  ~2.0 GB
```

**关键约束：** 16GB 统一内存环境下 **batch size 必须设为 1**，即不支持多用户并发，仅适用于单设计师本地场景。

#### 4.3.2 推荐量化方案：GGUF Q4_K_M

Apple Silicon 环境下 vLLM 的 Metal 后端成熟度不及 CUDA，推荐改用 **llama.cpp / MLX** 作为推理框架，使用 GGUF 格式量化权重。

```
量化格式对比（Qwen2.5-Coder-7B，16GB 统一内存）：

┌──────────────┬──────────┬────────────┬──────────────────────┐
│ 量化方案      │ 文件大小  │ 推理速度    │ 代码质量损失（估算）  │
├──────────────┼──────────┼────────────┼──────────────────────┤
│ Q8_0         │ ~7.7 GB  │ ~15 tok/s  │ < 0.5%（几乎无损）   │
│ Q4_K_M ★    │ ~4.5 GB  │ ~28 tok/s  │ ~2–3%（可接受）      │
│ Q4_K_S       │ ~4.2 GB  │ ~30 tok/s  │ ~3–5%               │
│ Q3_K_M       │ ~3.5 GB  │ ~35 tok/s  │ ~6–8%（不推荐）      │
└──────────────┴──────────┴────────────┴──────────────────────┘
★ 推荐：Q4_K_M 在质量与速度之间取得最佳平衡
```

**推理服务启动命令（llama.cpp server 模式）：**

```bash
# macOS Apple Silicon
./llama-server \
  --model ./rhinocoder-7b-q4_k_m.gguf \
  --n-gpu-layers 99 \          # 全部层卸载至 GPU（Metal）
  --ctx-size 8192 \            # 限制上下文避免内存溢出
  --parallel 1 \               # 单并发，适配 16GB 限制
  --port 8000 \
  --host 127.0.0.1
```

**MLX 备选方案（Apple 官方框架，性能更优）：**

```bash
pip install mlx-lm
python -m mlx_lm.server \
  --model ./rhinocoder-7b-mlx-4bit \
  --max-tokens 1024 \
  --port 8000
```

#### 4.3.3 16GB 统一内存 vs RTX 4090 性能对比

| 指标 | RTX 4090 (AWQ INT4) | Apple M3 Pro 16GB (Q4_K_M) |
|---|---|---|
| 短代码生成延迟 (≤200 tokens) | 150–350ms | 400–800ms |
| 中等代码块 (≤500 tokens) | 350–700ms | 800–1,800ms |
| 最大并发用户数 | 4 | **1** |
| 离线可用性 | ✅ | ✅ |
| 硬件成本 | ~¥15,000 (GPU) | 含于 Mac 设备 |
| 适用场景 | 工作室共享推理服务器 | 个人设计师本地端侧 |

> **延迟说明：** 16GB 统一内存场景下，500ms 以内的基础微调指令（"再弯一点"类增量操作）仍可满足，但复杂代码块生成延迟会超出 800ms 目标，需在路由策略中对此类环境适当放宽性能 SLA 至 2000ms。

#### 4.3.4 内存压力监控

```python
# macOS 内存压力监控钩子（集成至 Agent 健康检查）
import subprocess

def check_memory_pressure() -> str:
    """返回: normal / warn / critical"""
    result = subprocess.run(
        ["memory_pressure"], capture_output=True, text=True
    )
    # 解析 System-wide memory free percentage
    ...

# 当内存压力为 critical 时，自动降低 ctx-size 并触发告警
```

### 4.4 SFT 微调策略

**微调目标：** 提升 rhinoscriptsyntax 和 RhinoCommon 的 API 调用准确率，消除通用模型的"幻觉 API"问题。

**数据构成（预估）：**

| 数据来源 | 数量 | 说明 |
|---|---|---|
| rhinoscriptsyntax / RhinoCommon 官方文档蒸馏 | ~20,000 | 每个 API 条目蒸馏 3–5 条多样化指令样本 |
| 内部项目脚本（脱敏） | ~3,000 | 高价值真实场景 |
| DeepSeek-V3 / Claude 3.5 合成增强 | ~20,000 | 覆盖复合场景与长尾 API |
| **总计** | **~43,000** | |

**微调超参数（LoRA + QLoRA）：**

```yaml
lora_rank: 64
lora_alpha: 128
lora_target_modules: ["q_proj", "v_proj", "k_proj", "o_proj"]
learning_rate: 2e-4
epochs: 3
batch_size: 4
gradient_accumulation_steps: 8
```

### 4.5 自愈 Debug 机制

当本地模型生成的代码在 Rhino 中执行报错时，触发自动修复循环：

```
执行失败
   │
   ▼
收集错误信息 (stderr + Rhino exception)
   │
   ▼
组装 Debug Prompt:
  [原始指令] + [生成代码] + [错误信息] + [API文档片段]
   │
   ▼
本地模型重新生成 (最多重试 2 次)
   │
   ├── 成功 → 执行 + 记录为正样本 (用于后续 RLHF)
   └── 失败 → 上报云端模型 + 提示用户
```

---

## 5. 云端推理模型接入层

> **v0.2 架构升级：** 云端大脑由通用 SOTA LLM 切换为 **DeepSeek-V4-Pro**，作为默认首选模型，原适配器架构保持不变以支持备选切换。

### 5.1 主力模型：DeepSeek-V4-Pro

#### 5.1.1 选型依据

| 对比维度 | DeepSeek-V4-Pro | Claude Sonnet 系列 | GPT-4o |
|---|---|---|---|
| **上下文窗口** | **1,000,000 tokens** | 200,000 tokens | 128,000 tokens |
| 代码推理能力 (LiveCodeBench) | **领先** | 优秀 | 优秀 |
| API 输入价格 ($/1M tokens) | **$0.27 (cache hit)** | ~$3.00 | ~$2.50 |
| API 输出价格 ($/1M tokens) | **$1.10** | ~$15.00 | ~$10.00 |
| 中文指令理解 | **原生优秀** | 良好 | 良好 |
| 数学/空间推理 | **顶级** | 优秀 | 优秀 |

#### 5.1.2 百万 Token 超长上下文对宏观设计规划的价值

DeepSeek-V4-Pro 的 **1,000,000 token 上下文窗口**是本次升级的核心驱动力，在参数化建筑设计场景中带来三类不可替代的规划质量提升：

**① 全项目脉络注入（Project-Wide Context Injection）**

传统 128K 上下文窗口严格限制了可注入云端模型的项目背景体量。以中型建筑事务所的典型项目为例，其设计规范文档、历史版本 Grasshopper 脚本逻辑、结构工程师批注和材料供应商约束文件加总通常超过 200K tokens，必须人工裁剪后才能送入模型，导致规划方案缺乏项目整体感。

1M 上下文使得以下内容可以**同时**注入单次云端规划请求：

```
System Context (最大 ~800K tokens):
├── 项目设计规范与约束文档          (~50K tokens)
├── 全量 Grasshopper 脚本历史       (~200K tokens)
├── Rhino API 完整参考文档          (~300K tokens)
├── 历史对话与设计决策记录          (~150K tokens)
└── 当前会话 + 规划指令              (~100K tokens)
```

**② 跨阶段一致性保障（Cross-Phase Coherence）**

在超高层建筑或复杂表皮设计项目中，概念方案阶段（SD）的参数逻辑必须向深化设计阶段（DD）无缝传递。短上下文模型在处理"基于我们三个月前确定的幕墙分格逻辑，为这片异形区域生成过渡曲面"时，往往因无法追溯早期决策而产生逻辑断裂。

1M 上下文允许将**全量设计历史**作为活跃上下文维持，模型可在规划新阶段方案时显式引用并保持与既定设计语言的一致性。

**③ 批量方案并行评估（Batch Scenario Evaluation）**

规划阶段常需对多个形态变体进行对比推理（如"比较这 8 种网壳分格方式在结构效率和视觉韵律上的权衡"）。1M 上下文允许将所有候选方案的完整描述同时送入单次请求，模型在**全局视野**下进行一致性对比，避免多次独立请求带来的评估基准漂移。

**实际 Context 配置策略：**

```python
# 根据任务类型动态分配上下文预算
CONTEXT_BUDGET = {
    "concept_plan": {
        "project_docs":     300_000,   # 设计规范 + 历史记录
        "rhino_api_ref":    200_000,   # Rhino API 文档
        "session_history":  100_000,   # 当前会话历史
        "instruction":       10_000,   # 当前指令
    },
    "batch_evaluation": {
        "scenarios":        600_000,   # 所有候选方案描述
        "evaluation_criteria": 50_000,
        "instruction":       10_000,
    }
}
```

### 5.2 适配器架构：厂商无关接口

云端模型层保留 **适配器模式 (Adapter Pattern)**，DeepSeek-V4-Pro 作为默认 Provider，支持运行时切换至备选模型（适用于企业合规或 API 可用性降级场景）。

```python
class CloudLLMProvider(ABC):
    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        system_prompt: str,
        max_tokens: int = 4096,
        context_window_used: int = 0,   # 新增：追踪实际上下文消耗
    ) -> str: ...

# 具体实现
class DeepSeekProvider(CloudLLMProvider): ...    # ★ 默认：DeepSeek-V4-Pro
class AnthropicProvider(CloudLLMProvider): ...   # 备选：Claude 系列
class OpenAIProvider(CloudLLMProvider): ...      # 备选：GPT-4o / Azure OpenAI
```

**配置文件示例（支持运行时热切换）：**

```yaml
cloud_llm:
  provider: deepseek                    # 默认: deepseek
  model: deepseek-v4-pro
  api_key_env: RHINOCODER_CLOUD_API_KEY
  max_context_tokens: 800_000           # 保留 20% 余量
  timeout_s: 60                         # 长上下文推理需更长超时
  fallback_to_local: true               # 超时后降级本地模型
  fallback_provider: anthropic          # 云端降级备选
  fallback_model: claude-sonnet-4-5
```

### 5.3 API 成本经济性对比（v0.1 → v0.2）

#### 5.3.1 基准假设

| 参数 | 值 |
|---|---|
| 活跃设计师数量 | 10 人 |
| 每人每日云端规划请求次数 | 20 次 |
| 平均输入 token / 请求 | 50,000（长上下文注入） |
| 平均输出 token / 请求 | 2,000 |
| 工作日 / 月 | 22 天 |

#### 5.3.2 月度 API 成本对比

| 成本项 | v0.1（Claude Sonnet / GPT-4o） | v0.2（DeepSeek-V4-Pro） | 变化 |
|---|---|---|---|
| 输入 Token 月用量 | 10 × 20 × 50K × 22 = **220M tokens** | 同上 | — |
| 输出 Token 月用量 | 10 × 20 × 2K × 22 = **8.8M tokens** | 同上 | — |
| 输入费用 ($/月) | 220M × $3.00/1M = **$660** | 220M × $0.27/1M = **$59** | **↓ 91%** |
| 输出费用 ($/月) | 8.8M × $15.00/1M = **$132** | 8.8M × $1.10/1M = **$9.7** | **↓ 93%** |
| **月度总 API 成本** | **$792 / 月** | **$68.7 / 月** | **↓ 91%** |
| **年度总 API 成本** | **~$9,500 / 年** | **~$825 / 年** | **↓ ~$8,700** |

> **注：** DeepSeek-V4-Pro 定价基于其 Prompt Cache 命中价格（$0.27/1M input tokens）。项目文档类系统提示具有高度重复性，实际 Cache 命中率预计 > 85%，上述成本估算具有合理保守性。Cache Miss 价格为 $0.81/1M，即便按 50% 命中率计算，月度成本仍低于 $120。

#### 5.3.3 成本节约再投资建议

91% 的 API 成本削减释放出约 **$8,700/年**的预算空间，建议优先投入：

- **微调数据合成**：用节省的费用调用 DeepSeek-V4-Pro 自身生成更多高质量 SFT 数据（预计可增加 ~30,000 条合成样本）
- **Q4 RLHF 计算资源**：补贴本地模型增量微调的 GPU 时间

### 5.4 云端调用的数据脱敏规则

在向任何云端 API 发送请求前，必须经过脱敏管道：

| 数据类型 | 处理方式 |
|---|---|
| 具体坐标值 `(x, y, z)` | 替换为占位符 `<COORD_REDACTED>` |
| 项目专有图层名 | 替换为通用名 `layer_A`, `layer_B` |
| 文件路径 | 替换为 `<PATH_REDACTED>` |
| 企业自定义函数名 | 替换为 `custom_func_N` |

> **设计约束：** 凡是触发脱敏规则的指令，路由中枢的规则引擎应已将其标记为 `FORCE_LOCAL`，云端脱敏层是双重保险，不应成为常规路径。注意超长上下文场景下，脱敏校验器的性能开销需纳入端到端延迟预算。

### 5.5 云端模型的职责边界

云端 DeepSeek-V4-Pro **仅负责**：
- 在全项目上下文视野下分解复杂设计意图，输出步骤化的伪代码逻辑框架
- 提供参数化设计的拓扑策略、算法建议与跨阶段一致性保障
- 批量方案对比评估，输出带权衡分析的设计决策建议
- 当本地模型自愈失败时，提供高质量的 Debug 参考

云端模型**不直接**生成可执行的 RhinoCommon/rhinoscriptsyntax 代码，最终可执行代码由本地模型填充，以确保 API 准确性并规避幻觉。

---

## 6. MCP 空间交互通道

### 6.1 技术选型分析

MCP Server 需要嵌入 Rhino 运行时，实现对 Rhino 文档状态的读写。以下是三种候选方案的对比：

#### 方案 A：复用开源 rhino-mcp 并扩展（**推荐**）

> 已有社区项目 [rhino-mcp](https://github.com/jrothenbuhler/rhino-mcp) 实现了基础的 Rhino ↔ MCP 桥接。

| 维度 | 评估 |
|---|---|
| 开发成本 | ⭐⭐⭐⭐⭐ 最低，已有基础框架 |
| 成熟度 | ⭐⭐⭐ 社区早期项目，需验证稳定性 |
| 扩展性 | ⭐⭐⭐⭐ 可在其基础上添加自定义工具 |
| 实现语言 | Python（通过 Rhino Script Editor 运行） |

**推荐理由：** Q3 插件原型阶段优先复用，降低工程风险；Q4 视稳定性决定是否自研替换核心部分。

#### 方案 B：自开发 Rhino .NET Plugin（备选）

| 维度 | 评估 |
|---|---|
| 开发成本 | ⭐⭐ 需要 .NET/C# 开发能力，周期长 |
| 性能 | ⭐⭐⭐⭐⭐ 最优，直接访问 RhinoCommon |
| 稳定性 | ⭐⭐⭐⭐⭐ 最可控 |
| 适用阶段 | Q4 生产版本考虑 |

#### 方案 C：基于 Rhino.Compute 封装（排除）

Rhino.Compute 为无头服务器模式设计，不适合本场景中需要与设计师交互式 Rhino 会话绑定的需求，**排除**。

### 6.2 MCP 工具集定义

RhinoCoder MCP Server 暴露以下工具供 Agent 调用：

```python
@mcp.tool()
def get_rhino_context() -> RhinoContext:
    """获取当前文档状态：图层列表、选中对象属性、当前坐标系"""

@mcp.tool()
def execute_python_script(code: str) -> ExecutionResult:
    """在 Rhino Python 环境中执行代码，返回结果或错误信息"""

@mcp.tool()
def get_object_properties(object_ids: list[str]) -> list[ObjectProps]:
    """获取指定对象的几何属性（类型、边界盒、顶点数等，不含原始坐标）"""

@mcp.tool()
def undo_last_operation() -> bool:
    """撤销上一次代码执行的结果"""
```

### 6.3 状态同步机制

```
Rhino 文档变化
      │
      ▼ (Rhino Event Hook)
MCP Server 更新内部状态缓存
      │
      ▼ (Agent 轮询 or SSE Push)
Router 更新 Context Window
      │
      ▼
下一条指令携带最新上下文
```

---

## 7. 数据隐私与安全边界

### 7.1 数据分类

| 数据类别 | 示例 | 允许位置 |
|---|---|---|
| **红色：严禁出境** | 原始坐标、项目图纸、企业专有逻辑 | 仅本地 |
| **黄色：脱敏后可出境** | 抽象设计意图、通用 API 问题 | 脱敏后云端 |
| **绿色：可自由流动** | 公开 Rhino API 文档查询、通用代码片段 | 本地/云端 |

### 7.2 安全审计要求

- 所有向云端 API 的请求必须在发送前通过脱敏校验器，并记录请求哈希
- 本地推理服务仅监听 `localhost`，拒绝任何外部网络连接
- API Key 通过环境变量注入，禁止写入配置文件或代码

---

## 8. 组件间接口定义

### 8.1 Agent ↔ 本地推理服务

本地推理服务暴露 OpenAI-compatible API，Agent 使用标准客户端：

```python
# 本地模型调用
response = local_client.chat.completions.create(
    model="rhinocoder-7b",
    messages=[
        {"role": "system", "content": RHINOCODER_SYSTEM_PROMPT},
        {"role": "user", "content": instruction}
    ],
    max_tokens=1024,
    temperature=0.1,   # 低温度保证代码确定性
)
```

### 8.2 指令处理完整流程

```
用户输入 (自然语言指令)
    │
    ▼
Router.rule_engine(instruction) → ROUTE_LOCAL / ROUTE_CLOUD / UNCERTAIN
    │
    ├── ROUTE_LOCAL ──────────────────────────────────────────────────┐
    │                                                                  │
    ├── ROUTE_CLOUD ────────────────────┐                             │
    │                                   ▼                             │
    │                         CloudLLM.plan(instruction)              │
    │                                   │                             │
    │                         提取执行步骤列表                          │
    │                                   │                             │
    └── UNCERTAIN                       ▼                             │
         │                    Router.classify(instruction)             │
         │                             │                              │
         ▼                             ▼                              ▼
    LocalModel.generate(              LocalModel.generate(          LocalModel.generate(
      instruction,                      step,                         instruction,
      context=rhino_ctx                 context=plan+rhino_ctx        context=rhino_ctx
    )                                 )                             )
         │                             │                              │
         └─────────────────────────────▼──────────────────────────────┘
                                       │
                               MCP.execute_python_script(code)
                                       │
                               ┌───────┴───────┐
                             成功              失败
                               │                │
                          返回结果           自愈 Debug Loop (最多2次)
```

---

## 9. 微调数据流水线

### 9.1 数据生成方案（LLM 蒸馏）

**Sprint 1 Pivot：** 放弃 McNeel 论坛爬虫方案（数据噪音过高、标注成本高），改为以 rhinoscriptsyntax / RhinoCommon 官方源码与 API 文档为基础上下文，通过异步调用大模型 API（DeepSeek-V3 / Claude 3.5）直接蒸馏生成 instruction+code 配对的 JSONL 训练集。

**蒸馏流水线：**

```
① extract_api_entries()    从官方库源码提取全量 API 条目（函数签名 + docstring）
        │
        ▼
② chunk_api_docs()         按 API 组/模块拆分为适合单次蒸馏的片段
        │
        ▼
③ run_distillation()       并发调用大模型 API，每片段生成 3–5 条多样化样本
        │
        ▼
④ validate_syntax()        ast.parse() 语法合法性过滤
        │
        ▼
⑤ validate_api_names()     比对官方文档，过滤幻觉 API 调用
        │
        ▼
⑥ 写入 ./data/sft_dataset.jsonl
```

**蒸馏后的样本须通过以下验证：**

1. **语法合法性验证**：通过 `ast.parse()` 确认无语法错误
2. **API 合法性验证**：所有调用的方法必须存在于目标 Rhino 版本的 API 文档中（蒸馏上下文本身即为官方文档，可交叉验证）
3. **输入输出配对完整性**：每个样本包含自然语言指令 + 对应代码，格式受蒸馏提示词约束自动保证

### 9.2 闭环迭代机制（Q4 RLHF）

```
设计师使用 RhinoCoder
        │
        ├── 接受生成代码 → 正样本
        ├── 手动修改后使用 → (原始代码, 修改代码) 对齐样本
        └── 拒绝/重试 → 负样本
              │
              ▼
        匿名化处理（移除坐标/图层名）
              │
              ▼
        定期（每月）增量微调
              │
              ▼
        A/B 测试验证 Pass@1 提升
```

### 9.3 架构决策记录（ADR-001）

**标题：** 放弃 McNeel 论坛爬虫，采用官方文档驱动的 LLM 数据蒸馏方案  
**状态：** 已接受（Sprint 1 Pivot）  
**日期：** 2026-04

**背景：** Sprint 1 原计划通过爬取 discourse.mcneel.com 的脚本类帖子，经 AST 结构去重后构建 SFT 数据集。

**决策：** 放弃论坛爬虫方案，改为以 rhinoscriptsyntax / RhinoCommon 官方库源码与 API 文档为基础上下文，通过异步调用大模型 API（DeepSeek-V3 / Claude 3.5）直接蒸馏生成 instruction+code 配对的 JSONL 训练集。

**原因：**

1. **数据噪音过高：** 论坛代码片段存在大量不完整代码、过时 API（Rhino 5/6 时代）、无上下文的裸代码块，清洗人工成本与最终数据质量之间投入产出比过低。
2. **标注成本：** 论坛帖子不自带 instruction 标签，需额外进行指令–代码配对工作，人工成本难以规模化。
3. **官方文档可信度：** rhinoscriptsyntax 库源码与 API 文档经 McNeel 官方维护，以此为上下文蒸馏出的代码幻觉率显著低于基于论坛片段的方案。
4. **成本可控：** 单次全量蒸馏估算成本约 $15–25（DeepSeek-V3 定价），远低于人工数据清洗成本，且可重复执行。

**后果：**

- 训练集 API 准确性提升；真实用户场景多样性由大模型合成增强（~20,000 条）补偿。
- 论坛爬虫相关代码（`pipeline/scraper.py`、`pipeline/dedup.py`）可移除。
- `beautifulsoup4` 依赖已从 `requirements.txt` 删除。

---

## 10. 部署与运维

### 10.1 本地部署要求

| 组件 | 最低配置 | 推荐配置（工作室） | 轻量配置（个人） |
|---|---|---|---|
| GPU / 计算 | RTX 3090 (24GB) | **RTX 4090 (24GB)** | Apple M3 Pro+ (16GB 统一内存) |
| 内存 | 32 GB | 64 GB | 16 GB (统一内存) |
| 存储 | 50 GB SSD | 100 GB NVMe SSD | 50 GB SSD |
| 操作系统 | Windows 10 + WSL2 | Windows 11 + WSL2 | macOS 14+ |
| 推理框架 | vLLM | vLLM (AWQ) | llama.cpp / MLX (Q4_K_M) |
| 并发用户数 | 1 | 4 | **1（单设计师）** |
| Rhino 版本 | Rhino 7 | Rhino 8 | Rhino 8 (macOS) |

### 10.2 服务启动顺序

```bash
# 1. 启动本地推理服务
rhinocoder-inference start --model rhinocoder-7b-awq --port 8000

# 2. 启动 Rhino MCP Server（在 Rhino 内执行）
# RunScript: rhinocoder_mcp_server.py

# 3. 启动主 Agent
rhinocoder-agent start --config rhinocoder.yaml
```

### 10.3 健康监控

| 监控项 | 告警阈值 |
|---|---|
| GPU 显存使用率 | > 90% |
| 本地模型 P99 延迟 | > 1500ms |
| 路由中枢分类器置信度均值 | < 0.75（数据漂移预警）|
| 云端 API 连续超时 | > 3 次 |

---

## 11. 开放问题与风险

| # | 问题 | 风险等级 | 计划解决时间 |
|---|---|---|---|
| R1 | rhino-mcp 开源方案稳定性未经生产验证 | 🟡 中 | Q3 原型期评估，必要时切方案 B |
| R2 | Qwen2.5-Coder AWQ/Q4_K_M 量化后 Pass@1 实测值未知 | 🟡 中 | Q2 微调完成后基准测试 |
| R3 | 多设计师并发（>4人）场景下 RTX 4090 单卡可能成为瓶颈 | 🟠 高 | Q3 压测，多卡/多实例方案备案 |
| R4 | 路由规则误判导致敏感数据意外路由至云端 | 🔴 严重 | 双重脱敏校验 + Q3 红队测试 |
| R5 | 设计师反馈数据收集的合规授权流程 | 🟡 中 | Q3 与法务确认数据使用协议 |
| R6 | DeepSeek-V4-Pro API 在企业合规环境下的数据驻留政策需核实 | 🟠 高 | Q2 评估 DeepSeek 企业版/私有化部署选项 |
| R7 | 16GB 统一内存场景下 Rhino + 推理服务内存竞争导致 OOM | 🟡 中 | Q3 压测，实现内存压力自适应降级 |
| R8 | 超长上下文（>500K tokens）场景下 DeepSeek API 响应延迟超出云端超时阈值 | 🟡 中 | Q3 实测，按需调整 Prompt Cache 预热策略 |

---

*本文档为技术设计草案，架构决策在 Q2 技术评审后最终确认。*
