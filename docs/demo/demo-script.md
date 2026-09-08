# RhinoCoder v0.3.0 演示脚本与镜头表

总时长：约 2:35。左侧时间码与两份 `.srt` 完全一致，方便一次录制后制作中英文版本。

| 时间 | 画面与操作 | 中文旁白 | English narration |
|---|---|---|---|
| 00:00–00:15 | 标题页：RhinoCoder、`v0.3.0`、500/500、23 tools；快速切到空白 Rhino + UI。 | RhinoCoder 把自然语言设计任务变成真实 Rhino 操作，并用场景读取和程序断言证明结果，而不只是生成脚本。 | RhinoCoder turns natural-language design tasks into real Rhino operations, then proves the result with scene reads and programmatic assertions—not just generated code. |
| 00:15–00:48 | 输入“创建 20×20×2 基座，在顶面居中放半径 8 的红球”；执行。画面并排展示 Rhino 视口与 UI。 | 任务先经过本地隐私门和规则路由。Agent 通过 23 个版本化 MCP 工具调用 Rhino Listener，所有变更都在 Rhino 主线程执行。 | The task first crosses a local privacy gate and a rule-first router. The agent uses 23 versioned MCP tools; every mutation runs on Rhino's main thread. |
| 00:48–01:08 | 放大 Tool Trace、Scene Summary、断言与 metrics，再切 Rhino 成品。 | 完成并不等于模型说“完成”。系统重新读取场景，核对对象数量、尺寸、颜色和空间关系，并把运行、路由、工具和指标关联到同一个 run ID。 | Completion is not a model claiming success. The system reads the scene back, checks count, size, color, and spatial relations, and links route, tools, metrics, and evidence to one run ID. |
| 01:08–01:42 | 加载 `self_correction.json`：在首个断言失败处暂停，再继续到 `correction.started` 和二次断言通过。 | 这条合成 Replay 展示失败恢复：首次场景检查发现球体尺寸和颜色不符，闭环只修改目标对象，再次读取场景，断言通过。 | This synthetic Replay shows recovery: the first scene check finds the wrong size and color, the loop corrects only the target object, reads the scene again, and passes the assertion. |
| 01:42–02:03 | 停止 Rhino Listener 或使用 Replay 启动命令；刷新 UI，加载 `basic_stack.json`。 | 没有 Rhino 也能在五分钟内验证产品主链路。Replay 只使用经过哈希锁定和脱敏审计的合成事件，不需要模型密钥，也不会修改场景。 | Without Rhino, a reviewer can still inspect the main product loop in five minutes. Replay uses hash-locked, privacy-audited synthetic events, needs no model key, and cannot mutate a scene. |
| 02:03–02:24 | 显示架构图、数据流图与证据索引；高亮 500/500、A6 270/270、A4 0 findings。 | 公开指标都链接到版本化报告。500 条黄金数据经过断言、自检、人工确认和隐私审计；固定 30 题三路基线共 270 次通过，但它已经饱和，不能代替困难集和真实用户验证。 | Every public metric links to a versioned report. The 500 golden traces passed assertion, self-check, human approval, and privacy gates. The fixed 30-task baseline passed 270 runs, but it is saturated and does not replace a hard set or user validation. |
| 02:24–02:35 | 已知限制卡片：Local Mock / GPU gated / no production claims；结束页给出 Replay Quickstart。 | 当前本地后端仍是 Mock，只验证统一接口、隐私强制路由和安全回退。真实本地模型效果与学校 GPU 实验仍然没有被宣称完成。 | The local backend is still a Mock: it validates the interface, forced privacy routing, and safe fallback only. Real local-model quality and school-GPU experiments are not claimed as complete. |

## 录制用固定输入

成功任务：

```text
在原点创建一个 20x20x2 的基座，再在顶面居中放一个半径 8 的红色球体。
```

失败恢复：加载 `self_correction.json`。它是合成 Replay，包含首次断言失败、`correction.started`、二次场景检查与最终断言通过，不需要故意破坏真实 Rhino 场景。

无 Rhino Replay：

```bash
RHINOCODER_PYTHON=python3 ./scripts/bootstrap.sh
./scripts/start-replay.sh
```

打开 `http://127.0.0.1:7860`，选择 `basic_stack.json`。

## 剪辑验收

- 成片 2:20–2:55，1080p，字幕不遮挡 Rhino 命令行和 UI 指标。
- 至少一次展示 Rhino 视口真实变化，一次展示合成失败恢复，一次展示无 Rhino Replay。
- 不出现密钥、本机路径、用户名、学校账号、真实文件名或完整本地 Trace。
- 旁白不使用“生产级本地模型”“真实用户规模验证”或“LoRA 已完成”等不实表述。
- 成片文件在发布前单独执行人工逐帧复核；只有用户明确授权后才能上传。
