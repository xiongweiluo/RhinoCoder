# C5 模型桥开发探针 B：守卫修正后的新单次预注册

2026-10-03。状态：**新 ID/source/spec/runtime 已冻结；等待 B 的双 CI 与新的精确所有者批准，未运行。**这是已[失败退休的 A](c5-modelbridge-development-failure.md)之后的独立开发兼容性门，不是 A 重试、正式20题、最终 holdout 或整体 C5 GO。A 的原始私有证据与 17.614 秒远端资源结算保留；其 Idle hook/九份临时密钥已在另一次精确批准下人工安全收尾，不把收尾改判为 A 成功。

## 新身份、变更与不变项

- 新 ID 为 `C5DEV-MODELBRIDGE-20261003-B`，独立 Mac 状态 `data/training/c5/modelbridge-development-state-20261003-B/`、隔离远端源码 `/data/RhinoCoder-c5-modelbridge-B`、隔离远端状态 `/data/c5-modelbridge-state-20261003-B`。旧 A 根/claim/批准/密钥不可复用。
- [B 固定开发 spec](../eval/c5/modelbridge-development-spec-20261003-b.json)规范化 SHA-256 `be91b9b3ae28a18d69781b8c23d78341ea8be74177ce347895cfb97b93537de9`（文件字节 SHA `20103fc9bd4f7d5f213fbf1c6736aace80211863f776240ff9c727c9e35a2b3f`），继续使用相同公开的八个开发槽（A 在首个 open 前停止，0 次生成/夹具/派发）；这些题不进入将来的正式20题。每槽新的未保存 headless 毫米夹具，基座与原 checkpoint132 LoRA 各对写、只读、澄清和不支持操作一次；最多8请求/16双阶段生成、无自动重试或修复。
- [B 完整 runtime freeze](../eval/c5/modelbridge-runtime-freeze-20261003-b.json)规范化 SHA-256 `686c3a1cc2b04c24e974353857983500b221fe2c107d99d4e31caf631b7e54b4`（文件字节 SHA `aca812f434a63ceac119e7f5de30d9d3ecd71d48ac09a62f32c6f7fec1460393`），绑定源码 commit `608008fc22c766ee03cc725dd87f68585e835839` 的144份项目源码/原schema、Mac 3551份实际导入文件、远端21,614份依赖文件、原基座/adapter身份与资源 v3。隔离远端 spec/freeze 字节已对齐，本地 CPU 重渲染最大含预留1757/2048 token；以上均是预执行证据，不是模型兼容性结果。
- B 仅修正活动 UI 文档的守卫：复用原生执行器已有的 `active_content_digest`，同时保留活动文档 serial 和 UI 主线程检查。A 误复用了含全局对象及 undo 水位的 `rhino_scene_digest`；两组只读 Rhino 检查显示水位/旧摘要改变而内容摘要保持 `de8fa792…ec6cfa`。**可变夹具的原子账本仍使用含水位的摘要，不削弱其防重放/ABA。**合成负控须证明活动文档 serial 或内容变化仍会拒绝。
- 基座 revision、原 adapter SHA、C5 v4 selector/v3 JSON invoker、23工具选择目录/单工具 schema、2048 token、128/512 输出、严格解析、许可签名、原生执行和独立联合审计与 A 完全相同；无训练、无产品路线切换、无原80正文读取。开发工程门仍要求八槽完整可解释、至少一个真实模型衍生写和一个只读、零额外派发/危险写/未核实清理；语义结果单列，不等于正式质量。

## 资源、冻结和批准顺序

[资源 v3](../eval/c5/rhino-resource-boundary-v3-20261003.json)在所有者报告的 2026-10-04 20:00 苏黎世时间到期与19:45生成截止不变的前提下，计入 A 已发生的 17.614 秒含加载/等待时间。B 的开发硬上限缩至3500秒，使 A+B 小于原开发3600秒；正式配对≤3小时、开发+正式≤4小时、原累计≤16小时仍不变。服务商精确到期时间未独立复核；资源边界不授权 B 运行或租赁延长。

1. 本地全仓回归为 520 passed、8 skipped；secret/release/diff 检查已通过。隔离远端 B 的只读模型资产、依赖导入闭包、源码/配置字节清单一致；上述**新** B source commit、spec 与完整 runtime freeze 已固定。冻结文件生成后源码/契约不得暗改。仍须核查新推送的双 CI，不能以本地测试代替。
2. 仅在新 B 双 CI 通过、GPU/租期与空白 Rhino 再核对，且仓库所有者作为 `repository_owner` 直接批准 B 的**两个精确规范化 SHA-256** 后，才建立 B 私有700目录/600批准台账与永久 claim。A 或 R/native12 的批准不适用。
3. 新 B ScriptEditor hub、Mac driver、远端 worker 各只启动一次。任何未知回执、守卫漂移、模型失败、预算/租期触线均保留原始台账并使 B 退休，不沿用 ID/配置重跑。只在八槽真实完成并有远端结算后做只读导出及独立模型→许可→原生几何/读回→关闭/删钥→stop 审计。
4. 只有 B 工程门通过，才提出真正新的20题、家族排除承诺、独立保管人与正式40路线槽的另一次冻结/批准。正式门槛 LoRA≥14/20、相对基座≥15pp、配对净胜≥3、安全/重复写/未核实清理=0 不下调；B 开发题不得混入正式集。

本文件中的 B **不具有当前执行授权**。仓库所有者也仍是 PR 唯一 reviewer_1；PR 不自动合并。
