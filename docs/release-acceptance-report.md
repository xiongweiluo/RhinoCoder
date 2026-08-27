# 版本、macOS 安装与文档一致性验收报告

验收日期：2026-08-27  
发布版本：RhinoCoder `0.2.0` stable prototype  
验收平台：macOS 15.6、Apple Silicon arm64、Rhino 8、CPython 3.13.5、Node.js 22.23.1、npm 10.9.8

## 验收结论

- 应用版本固定为 `0.2.0`，Prompt 固定为 `closed-loop-v1`，工具 Schema 与 Trace Schema 固定为 `1.0`。
- Python 依赖由 `requirements-lock.txt` 固定，前端依赖由 `package-lock.json` 固定；两份锁文件的 SHA-256 写入版本清单。官方 MCP Python SDK 固定为 `mcp 1.29.1`，并在意图依赖中限制为 `mcp>=1.0,<2.0`，避免安装不兼容的同名 2.x 包。
- MCP 工具数量固定为 23，版本、工具数量和依赖锁漂移会使 CI 失败。
- macOS clean-room 从不含 `.env`、虚拟环境、`node_modules`、构建产物和本地 Trace 的公开工作区副本完成安装。
- clean-room 完成 Python 虚拟环境创建、锁定依赖安装、前端安装与构建、全量测试、30 题格式检查、版本一致性检查和三份 Replay 发现。
- 离线首次任务通过 WebSocket 重放 `basic_stack.json`，完整收到严格递增事件并以 `run.completed` 结束。
- 使用 clean-room Python 环境启动全新 MCP 子进程，通过 localhost 完成只读 Rhino 首任务；不调用外部 LLM，不打印或保存场景内容，也没有创建、删除、移动或修改对象。
- MCP 成功日志只保留字段名、对象数量和总数，不记录请求值、GUID、对象名称、坐标或图层；对应脱敏行为有自动测试。
- README、架构、故障排查、已知限制、CHANGELOG、发布清单和实际代码已逐项核对并接入自动一致性检查。

本轮版本固定、macOS clean-room 安装和文档一致性验收通过。

## 版本冻结边界

版本真源为 `agent/version.py` 和 [version-manifest.json](version-manifest.json)：

| 边界 | 固定值 |
|---|---|
| 应用版本 | `0.2.0` |
| 发布状态 | `stable_prototype` |
| Prompt | `closed-loop-v1` |
| MCP 工具 Schema | `1.0` |
| Trace Schema | `1.0` |
| MCP 工具数量 | 23 |
| Python | `>=3.11,<3.14` |
| Node.js | `^20.19.0 || >=22.12.0` |
| Rhino | 8 |
| 首要平台 | macOS 14+ |

`tools/check_release_consistency.py` 同时验证 Python 常量、UI `package.json`、`package-lock.json`、版本清单、架构文档、README、CHANGELOG、发布清单、MCP 装饰器数量、依赖锁哈希和 Markdown 本地链接。

## clean-room 安装验收

### 隔离边界

`tools/verify_clean_install.py` 只复制 Git 可发布文件及本轮待提交文件，不复制：

- `.git` 与任何 Git 凭证。
- `.env` 与真实 API Key。
- `.venv`、`node_modules` 或现有构建产物。
- 本地 Trace、评测 JSON、反馈和 legacy 黄金数据。

临时目录内重新创建 `.venv`，安装结束后自动删除。首次尝试使用 macOS 旧系统 `python3` 时被版本检查正确拒绝；显式选择 Python 3.13 后安装成功，因此 README 已明确要求 Python 3.11–3.13。

### 验收步骤

1. 从公开文件清单复制全新工作区。
2. 执行 `scripts/bootstrap.sh` 创建 `.venv`。
3. 从 `requirements-lock.txt` 安装精确 Python 依赖。
4. 执行 `npm ci` 和 Vite 生产构建。
5. 验证新 `.env` 只含占位符。
6. 使用 clean-room Python 运行全量测试、任务格式和发布一致性检查。
7. 启动 clean-room UI Server，读取健康接口和三份 Replay 清单。
8. 通过 WebSocket 重放第一个合成任务并验证事件顺序。
9. 使用 clean-room Python 启动 MCP 子进程，发现 23 个工具并只读调用 Rhino 场景摘要；摘要内容不输出、不保存，也不发送给外部模型。
10. 删除临时工作区。

最终执行结果：复制 116 个公开文件；70 项自动测试通过；30 条评测任务格式通过；发现 23 个 MCP 工具；Replay 收到 7 个连续事件；localhost Rhino 只读首任务通过；临时工作区已自动删除。

执行命令：

```bash
python tools/verify_clean_install.py --local-rhino
```

这属于同一台 Mac 上的全新工作区和全新依赖环境验收，不等同于另一台物理 Mac。Intel Mac 和第二台物理设备仍属于扩展兼容性验证，不影响当前 Apple Silicon 稳定原型边界。

## 文档一致性复核

| 文档 | 复核内容 | 结果 |
|---|---|---|
| README | 版本、前置条件、安装、启动、首任务、评测、安全和限制 | 通过 |
| Architecture | 运行拓扑、事件流、版本和安全边界 | 通过 |
| Troubleshooting | Python/Node/依赖锁、Listener、UI、模型、超时、MCP、Undo 和版本漂移 | 通过 |
| CHANGELOG | `0.2.0` 功能、安全变更和真实验收 | 通过 |
| Release checklist | 所有稳定原型发布门槛 | 通过 |
| Markdown links | README 与 `docs/*.md` 的本地目标 | 通过 |

## 自动门禁

```bash
python tools/check_release_consistency.py
./scripts/check.sh
```

版本一致性检查已经加入本地检查和 GitHub CI。修改版本、Prompt、Schema、依赖锁或文档时必须同步更新版本清单，否则检查失败。
