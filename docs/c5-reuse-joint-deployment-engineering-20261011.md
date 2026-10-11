# 同题复用：CPU 联合原始审计与部署根预检

2026-10-11，Europe/Zurich。当前交付承接[运输与原始证据链](c5-reuse-transport-evidence-engineering-20261011.md)，只使用独立 CPU 合成夹具。**不是现场工程 PASS、正式 spec/runtime 冻结、执行批准或 C5 整体完成。**原20题的复用决定已收到，原正式失败、消费屏障和 C5-7 NO-GO 保留，实际历史生成总量仍 unknown/null。模型、契约、提示词、解析器与评分门槛未改。

## 已实现的联合链

[合成生产者](../training/c5_reuse_joint.py)只接受既有 synthetic protocol/study 和 `cpu-` instance。联合根名绑定 instance，首次 mkdir 及 O_EXCL 文件创建就是永久单次 admission；成功、异常或真实 CPU 子进程死亡后都不能重新创建、补槽或重放。没有旧 state/claim、正式授权文件或 live adapter。

40槽/20对仅使用代码生成的毫米 box 替身，两个 route 的同对输入相同。每槽先取得既有运输原始 ACK，再依次完成：

1. HMAC 许可分别绑定 scope、合成 spec/runtime 身份、原始 request 哈希、槽/route/夹具、operation、场景前态、ordinal 与一次使用上限。
2. SQLite `synchronous=FULL` 提交消费；ordinal 主键和 permit_id 唯一索引拒绝重复。原始 consume 记录 fsync 并回读后，才允许 write/read/cleanup 替身操作。
3. 几何操作记录 before、after 和独立读回快照；每槽恰一写、一次目标几何读回、一次空夹具清理。操作前再次核对文件身份、原始 native/transport 字节及 SQLite 逻辑行。
4. 最终运输 seal 与 native seal 分开，最终假 witness 同时绑定两条原始链尾和 SQLite 行哈希。准备 witness 绑定两个 genesis，不能代替 final。

正常完整链是40个请求、80个合成生成 receipt、120份一次性许可、40个写入/读回/清理。公共测试 key 只用于 CPU 夹具，不是新正式 grant 或私钥。合成 spec/runtime 哈希只是固定夹具身份，**不证明执行代码/环境字节冻结**，不能用于申请现场批准。继承运输模块的 scope 和固定合成排程；不把该排程宣称为原正式20题顺序。

[独立审计器](../training/c5_reuse_joint_audit.py)不 import 联合生产者或运输生产者，不接收 producer summary。它从原始运输、native hash chain、只读 SQLite 重新验证 ACK/HMAC、消费先后、全部逻辑行、几何目标、读回和清理，逐对重算合成分数。合法但错误的几何保持失败，不修复或放宽断言。正控的 base/LoRA 各20/20、净胜0只证明这组 CPU 替身一致，不是模型质量或 GO。

数据库提交后但原始 consume 未完成，最多留一个认证的未知 gap；consume 后缺 effect/读回也是 unknown。真实 CPU 子进程突然退出时可能没有 retire 记录；`retirement_recorded=false` 不撤销 admission，`replay_allowed=false`。篡改、缺字段、未知事件、重排、重复、缺日志、读回不符或未清理都会拒绝/保持不完整；不靠补零得到完整。实际模型生成和 Rhino 派发始终 null，`external_witness_origin_verified=false`、`execution_ready=false`。

## 完整公共部署根预检

[预检模块](../training/c5_reuse_deployment.py)从固定六个 CPU entrypoint 的实际字节递归推导本地 Python import、package initializer 及显式公共 JSON/Markdown 依赖。`training/__init__.py` 的传递 `training/config.py`、公开训练配置与 requirements 文件也进入清单，但不调用 readiness 的数据读取方法。旧正式 spec 只是公开比较/NO-GO 检查的输入，不作为新运行 spec。

当前固定闭包20文件。独立核查实际 CPU stage 根的每份字节、精确文件/目录人口、无 symlink/hardlink、owner/mode、import 闭包和全新 state 根。额外的旧批准、空目录、缓存或私有材料也会拒绝。目标 source/state 名及 manifest 中的完整路径绑定同一新 CPU instance；旧/正式 study、跨 instance/root/state、被使用的 state 根拒绝。

manifest 的规范化 SHA 必须由审核者在目标根外持有。只核对目标自带的可重写清单不足以验收。`stage_cpu_public` 只支持新的本地 CPU 目录，全部文件 O_EXCL、fsync、回读；已有或部分 stage 不覆盖、不清理、不修复重试。它不执行目标代码或生成运行 state/grant/claim。真实 Mac/GPU/Rhino 部署仍未实施。

[CLI](../tools/check_c5_reuse_deployment.py)应由可信源码目录运行，使用该目录的检查器读取目标字节；不 import/运行 target 根代码。公开的[CPU 验证材料](../eval/c5/reuse-cpu-joint-preflight-validation-20261011.json)含实际本地 stage 的完整清单与独立核查摘要，供复核，不是未来现场部署证明。

保证边界明确：闭包针对已审阅的固定 CPU entrypoint 与上述公共文件访问，不是任意 Python 程序的动态访问证明。第三方/动态 import、eval/exec 拒绝；解释器、stdlib、SQLite/native library 与 OS 是显式信任边界，没有声称完整代码字节闭包或对敌对同 UID 的无篡改保证。源码 AST 的名称/依赖分析用于发现缺项，**验收仍逐文件验证实际字节 SHA**。现场环境/模型/宿主连续性和独立停止尚需另外冻结。

## 验证与剩余门禁

```sh
python -m pytest -q -p no:cacheprovider eval/test_c5_reuse_joint.py eval/test_c5_reuse_deployment.py eval/test_c5_reuse_transport_evidence.py eval/test_c5_formal20_reuse_draft.py eval/test_c5_final_decision.py
python tools/check_c5_formal20_reuse_draft.py
python tools/audit_c5_final_decision.py
python tools/check_release_consistency.py
python tools/check_secrets.py
git diff --check
```

控制覆盖：40槽联合正控、逐许可字段重签/重哈希篡改、SQL 缺行/额外行/trigger/schema、合法错误几何、原始断尾、每操作提交/派发前后故障、真实 CPU 进程直接退出、真实线程竞争、每份传递文件缺失、字节/链接/身份/state 漂移、部分 stage 不覆盖和可信 CLI 对目标恶意代码的拒绝。中间测试曾发现无 gap 的完整账本被错误拒绝及 SQLite 默认线程亲和性阻止跨线程正控；修正后重新验收，不追认失败轮成功。

只完成 I 中本次两项 CPU 依赖；I 的真实来源/peer 覆盖、host 连续性、跨目录全局 admission、进程停止与现场适配仍未完成。下一项是集中准备新现场门的访问/资产/宿主与资源核查材料，再完成实际完整冻结和独立复核；不由本轮自动执行。本人已报告 GPU 租期续至2026-10-13，CPU准备不受旧10月9日到期阻断；准确时刻/时区、剩余时数和历史保守用量仍须现场冻结前核实，不视为无限预算。

现场工程门与正式复用仍分别需要完整冻结、绑定最终提交的 push/PR 双 CI、本人批准对应 spec/runtime **两个完整精确哈希**。CPU/CI成功、资源可用或 PR 合并不替代批准。R UI/用户开放、P2b、精简D继续延期，默认混合路线不变。此交付在独立分支，依赖 #9/#8；未经本人决定不合入父分支或 main。
