# RhinoCoder v0.3.0 发布检查清单

当前状态：**Released**。`v0.3.0` 已完成本地门禁、Git Tag、push、GitHub Release 与公开链接验证。真实 Rhino 视频按项目所有者决定延期；现有合成 Replay GIF、脚本与字幕可独立复核，视频项不会被虚假勾选。

## 1. 版本与招聘者入口

- [x] 应用、UI 与版本清单统一为 `0.3.0`；已发布 Tag 的 Prompt 为 `closed-loop-v1`，当前 Unreleased P2 通用修复提升为 `closed-loop-v2`；工具与 Trace Schema 保持 `1.0`。
- [x] README 第一屏说明问题、真实 Rhino 闭环、500/500、A1–A7、核心差异和诚实限制。
- [x] 中文 README 与独立英文 README 均提供指标、Quickstart、架构、证据和限制入口。
- [x] CHANGELOG 包含 `0.3.0` 的功能、验证、安全与候选发布状态。
- [x] README、架构、计划、版本清单与报告中的 500/500、46 标签、270/270 和 Local Mock 口径一致。

## 2. 架构、数据流与证据

- [x] 可直接浏览的运行架构 SVG 覆盖 UI、隐私门、路由、模型接口、Agent、MCP、Listener、Rhino 与证据存储。
- [x] 可直接浏览的数据流 SVG 覆盖黄金准入、任务级分区、A5 holdout、未来 P2 困难集与公开边界。
- [x] 公开指标索引逐项链接 A4、A6、A7、版本清单与训练就绪报告。
- [x] 合成 `self_correction` Replay 展示隐私、路由、首次断言失败、纠错、复检和最终通过。
- [x] README 明确 `local-mock` 不是生产本地模型，30 题 100% 不代表开放世界或困难集效果。

## 3. Quickstart 与运行验证

- [x] 无 Rhino clean-room 可按 README 安装、构建 UI、发现三份 Replay 并完成首个 Replay。
- [x] 真实 Rhino 入口、Listener 命令、健康检查、只读首任务、预期输出和空白文档警告完整。
- [x] `start-replay.sh` 在不连接 Rhino/模型的条件下启动本地 UI。
- [x] 招聘者在线只读演示公开可访问；根链接自动加载正常闭环，三场景无需 Rhino、模型密钥或本地安装。
- [x] `release-verify.sh` 覆盖 diff、全量检查、演示资产与 clean-room，且不执行 Git 发布操作。

## 4. 演示与求职材料

- [x] 2:35 镜头表覆盖真实成功任务、合成失败恢复、无 Rhino Replay、证据和诚实限制。
- [x] 中英文旁白与 SRT 字幕时间码一致，提供 macOS 录制、字幕烧录和逐帧隐私检查命令。
- [x] 9 帧 Replay GIF 由隐私复核的合成数据生成；源与产物 SHA-256、尺寸和帧数由自动检查锁定。
- [x] 一页中英文简历项目描述、30 秒开场和面试深挖提纲已准备。
- [ ] [外部门禁] 项目所有者在空白演示文档中录制真实 Rhino 视频，并逐帧确认无身份、路径、密钥或真实项目数据。
- [ ] [外部门禁] 项目所有者选择视频托管位置并授权上传；README 再补充可访问链接。

## 5. 本地发布质量门禁

- [x] `git diff --check` 通过。
- [x] Python 编译、完整 pytest、30 题格式与采集/A7 静态检查通过。
- [x] 前端 TypeScript 构建通过。
- [x] 密钥、Trace、Replay、隐私与 SQLite 存储面审计通过，敏感发现为 0。
- [x] 版本、依赖锁、Markdown 本地链接与演示资产一致性检查通过。
- [x] A5 holdout 与未来 P2 困难集未用于训练或反复调参，C1–C4 未执行。
- [x] 发布验证结果已记录到 [v0.3.0 发布验证报告](v0.3.0-release-verification.md)。

## 6. 外部发布门禁

- [x] [外部门禁] 项目所有者审阅发布范围，并明确授权 commit。
- [x] [外部门禁] 项目所有者明确授权创建 `v0.3.0` Tag 与 push。
- [x] [外部门禁] GitHub Release 已附 CHANGELOG 摘要、GIF、发布验证报告，并明确标注视频延期。
- [x] [外部门禁] GitHub Release、README、GIF 与双语入口可从公开网络访问；未将延期视频描述为可访问。

正式发布状态由 `docs/version-manifest.json` 锁定为 `released`，并记录 Git Tag、GitHub Release 与公开链接。真实 Rhino 视频仍是单独的延期门禁，完成录制、逐帧隐私复核和上传后再勾选，不影响当前版本作为招聘作品集开始投递。
