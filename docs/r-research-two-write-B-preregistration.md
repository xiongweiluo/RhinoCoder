# R 研究安全开发烟测 B：事前冻结

2026-10-02。状态：**源码/spec 已冻结；所有者已对 B 两个精确哈希批准单次两写，现场尚未执行。** 人类实际回复为“以 repository_owner 身份授权上述 B spec 和源码冻结的单次两写烟测”；不得将这一批准扩展为其他 probe、模型或正式20题授权。不属于 C5 最终 holdout，不是模型质量评测，不覆盖十二工具。原失败 A 永久保留、退休；本版本不是 A 的重跑或追认。

## 身份与固定范围

- ID：`RSDEV-TWO-WRITE-20261002-B`；入口：[v2 固定入口](../tools/r_research_two_write_v2.py)。旧默认入口仍是已退休 A，没有接受任意新 ID 的 CLI。
- [冻结清单](../eval/r_research/two-write-B-freeze-20261002.json)：130 份跟踪运行源码/锁定依赖，源码 revision `3e8ee53c480954a106a694d2f52b8433f223b87d`。清单自身与本文件随后提交，不造成源码自引用；实际源字节必须同时匹配清单及该 Git 对象。
- spec canonical SHA-256：`9d69c89a9d63512df516206b28dd2a284efc04a9377cb0eca297d6ee183b9c41`。
- 整份冻结清单 canonical SHA-256：`7b31d0f23b99c8faecf96101f274bab2a95b768bdbe0308620671a3815f02e39`；源码 inventory canonical SHA-256：`d3fad8821e7c603d9e3b4d9c2ba2fd3982df10a936243782b7cafaec36268fde`。
- 仅一个全新、独立、未保存、初始空的 headless 毫米夹具；创建原点盒体 347×353×359，再将 `box-1` 平移 (7,-11,13)。复用 A 的数值仅作工程开发验证，不声称新未见测试家族。
- 最多两次签名写入/两份许可，模型/GPU/holdout 调用为 0；不读取、修改或替换任何模型。不向活动文档写入，不切换默认 Listener/产品路线。

## 批准与单次执行

仓库所有者必须明确批准以上 **B spec 与 runtime freeze 两个哈希**；A 的批准、推送授权、代理生成的 JSON 或笼统“全部完成”不能替代本次精确批准。私有授权收据记录真实人类回复，`authorized_by=repository_owner`、`approved=true`、`probe_spec_sha256`、`runtime_freeze_sha256` 和固定 authorization_basis 必须相符；收据本身不是人类授权的来源。

在任何 open 前核对源文件、实际加载的本地 import、Rhino bootstrap 和完整 source inventory，并拒绝已有请求/响应/failure 的 controller。私有固定目录 `data/training/c5/research-probe-state` 必须由所有者持有、无符号链接、权限 700；入口不接受替代 state/output 路径。

原子独占发布永久 B claim，随后共享执行器再发布一次性 engine-started claim；包括尚未建输出目录就中断的情形，均不得重新执行 B。竞争进程最多一个进入执行器。B 成功、失败、超时或基础设施中断后均不删除 claim，不用新输出目录绕过。直接调用共享执行器也不能绕过 B 的固定冻结/批准/claim。更改源码或再次尝试需要另一个版本、ID、冻结及所有者决定。

## 通过条件与独立审计

全部条件同时满足，才记 `independently_verified_fixed_two_write_safety_only`：

1. 仅一次 open、一次 close、一次 stop，各自 case/session/序号和 scope 一致；空夹具 revision 0 合法，负数、bool、float 非法。
2. 恰有两份唯一 execute/响应、两份签名载荷、两行 `done` 账本及其一致 SQLite backup；禁止重复保留、补发或重试。
3. 真实 capture 独立重算整个对象集合及盒体两次 bbox；第一写 max(347,353,359)，第二写 min(7,-11,13)、max(354,342,372)。逐步场景/文档/revision、任务及签名参数链完整绑定。
4. 恰有两份 consumed 许可、八个事件，与实际执行和持久账本交叉一致；不以自报的 `readback_verified` 或 `ledger_state` 替代原始证据。
5. 同一 Rhino UI 关闭回调记录初始/关闭前/关闭后活动内容哈希，stop 哈希也一致；准确夹具关闭、实际 `handoff.key`/旧 `secret` 均不存在、控制器停止。
6. [只读独立审计](../tools/audit_r_research_two_write.py)复核真实请求、载荷、captures、原始数据库、backup、授权、两个永久 claim 与冻结源码。审计不重开夹具，不恢复已删除 HMAC key，不签名或授予许可。

即使通过，`full_R_research_safety_gate_passed=false`、`c5_6_authorized=false` 仍保持：只闭合两工具研究子门。完整研究交接还缺远端 C5 模型/源码血缘；十二工具适配、评分、独立负控、新20题及所有者排除承诺、租期/研究预算和正式执行冻结须分别通过。

## 失败、清理与证据

使用既有有界 RPC：lifecycle 30 秒、scene capture 20 秒、execute 30 秒；每步许可 TTL 300 秒。超时不补发、不重试模型或写入、不强杀在途 Rhino。仅已知准确 session 才发送固定 close→stop；未知/不确定身份保留失败并人工收尾，不把排队清理当成成功。

核验前保存 raw step；任务失败与严格证明的 cleanup 分开记录，已核实清理不能把失败任务改为 PASS。保留所有部分步骤、claim、请求/响应及失败；归档只选本次必要文件，SQLite 用一致 backup，不整包收集脏 R 资产、密钥或 holdout。

活动内容 digest 仅涵盖既有几何/对象属性、图层、单位与容差序列化，不能表述为整个 3dm/摄像机/所有表的完整证明。A 的原 FAIL、原 cleanup_verified=false 与独立事后清理核验仍并列保存，详见 [R 交接记录](r-research-safety-handoff-20261002.md)。

## 工程准备状态

源码冻结前干净跟踪文件快照：368 passed / 5 skipped；相关研究 CPU 正负控 96 passed。这些证明 admission、revision 边界和证据核验逻辑，不是 B 现场成功。文档/公开冻结随后提交，远端 CI 须按最新提交复核。仅记录实际人类批准，尚无 claim、现场结果或新的正式20题；公开报告留空直到真实独立审计完成。

PR #7 保留 draft，所有者唯一 reviewer_1 决定合并；无需 reviewer_2。持续推送/建 PR 授权不包含自动 merge。C4 NO-GO、v8 formal_quality_fail/59/60、原 C5 已消费80家族和默认混合路线全部不变。
