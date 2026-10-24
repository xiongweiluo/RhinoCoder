# 同题复用：运输与原始证据链 CPU 工程交付

2026-10-11。这是[准备协议](c5-formal20-reuse-protocol-amendment-20261011.md)后的独立工程子交付，**不是现场工程门、正式执行入口或新的执行冻结**。原20题复用决定已收到，不再要求重新确认或出题。原正式研究、C5-7 NO-GO、原消费锁、C4、v8与默认混合路线均不改。

## 1. 已实现及身份边界

- [运输模块](../training/c5_reuse_transport.py)：注入式端点；`PipeEndpoint`只包装调用者已提供的本地文件描述符，不创建SSH连接、模型、宿主或进程。测试子进程仅为标准库CPU假peer。
- [证据与独立重建](../training/c5_reuse_evidence.py)：私有合成临时目录、O_EXCL首次创建、进程生命周期flock、owner/mode/无symlink/无hardlink/准确inode核对；顺序追加、fsync、回读、哈希链，无truncate/补写/修复命令。
- [CPU正负控](../eval/test_c5_reuse_transport_evidence.py)：40个合成槽、20/20交替路由、56请求边界、真实管道假子进程故障注入、原始重建与状态/文件漂移控制。

唯一协议为`c5-reuse-cpu-synthetic-v1`，唯一study类型为`c5-rhino-paired-20-reuse-v1-synthetic-engineering`，instance必须以`cpu-`开头。旧study、候选正式study、旧wire协议、formal execution_kind都在建目录前拒绝。请求API没有任务正文、答案、路径或密钥参数，只有合成槽/冻结合成路由/步骤；夹具文字由代码生成。测试目录由pytest临时创建，不在`data/training/c5`创建run、state、grant或消费claim。

本模块没有调用旧开发/正式入口，也没有修改它们的硬编码身份、隐私规则或审批检查。临时CPU标识不是新正式ID获批证明，不能删掉`synthetic`限制后直接投入现场。

## 2. 运输、计数与未知

| 原始事件 | 持久化/含义 | 不能外推 |
| --- | --- | --- |
| open、baseline | 准确合成scope；准备锚绑定scope和genesis | 不证明真实host准备或capture来源 |
| intent | 完整合成request先fsync/回读，再允许任何端点写入 | intent之后崩溃，不能推断未发送 |
| sent | 仅在完整帧写入返回后记录已写字节数 | 没有该记录不证明远端没有收到前缀/完整请求 |
| received | 每块接收字节原样hex保存，包括坏帧、半帧和第一块越界数据 | 原样存在不等于合法ACK、生成完成或许可 |
| ack | 原始接收拼接与未修复canonical帧相同；协议/scope/request/帧哈希/阶段/raw SHA逐项重算 | synthetic receipt不是实际模型生成或Rhino执行证明 |
| dispatch | 已确认请求下的一次合成读/写观察及占位许可哈希；重复拒绝 | 不是HMAC签名实现、真实许可验证或几何读回 |
| retire、seal | 未知或人工CPU停止永久退休；封存有准确尾哈希 | 不发送系统信号，不证明GPU退出、清理或内存擦除 |

partial write只推进已返回的字节offset，不能重发此前前缀。EOF、超时、错误/重复/多余/不完整帧、迟到ACK、钟倒退、持久化失败后不重发、不重连，不换槽继续。崩溃后重开同一合成目录，会从原始链恢复未解决请求/退休状态；已ACK的原请求键也不能重新使用。步骤要求前序ACK；固定合成路由不能更名绕过消费。

同一journal的所有transport wrapper共享单个非重入exchange锁，跨线程或回调重入不能在首个请求未验收时另发请求；事件追加也单独串行。锁释放不撤销持久化退休状态。另一个进程打开同一目录由flock拒绝，不把“仅一个对象的blocked布尔值”当完整并发门。

独立`verify`不使用运行器summary，重算序号、前哈希、scope、合法事件迁移、request/ACK原始字节和receipt哈希。即使攻击者重算整条链，重复ACK、非法派发或缺接收原文也不能通过状态机。缺记录/断尾/篡改拒绝；没有外部尾锚时不能认证尾部没被删。字段分别报告intent、完整发送帧、ACK、合成生成receipt、合成dispatch和未解决请求，**实际模型生成/实际Rhino派发始终null**，不把局部“记录0”提升为物理零调用。

ACK在持久化后才超过完整验收期限，会保留这份已观测ACK，再退休；不擦掉原记录，也不继续下一请求。deadline包括写入、收帧、解析、校验与ACK持久化，是逻辑期限，不能抢占卡死的内核、CLR或CUDA调用。测试没有用单纯延长超时代替这些修复。

## 3. 两类外部锚与保证边界

准备锚为`external_cpu_readiness`，绑定scope＋genesis；最终锚为`external_cpu_final_seal`，绑定scope＋真正最后record SHA＋记录总数，只有seal后可匹配。两者不能替换、不能把baseline当final。外部输入来自测试假witness，校验器只认证绑定一致，**`external_witness_origin_verified=false`**；不是凭传入dict或自报seal就认证真人独立捕获。

即使40合成槽完整、两个假锚匹配，返回也只允许`synthetic_recorded_coverage_complete=true`、`execution_ready=false`。没有真实host/worker原始链、可信跨进程覆盖或完整联合审计，不声称零未知生成、全过程安全或正式质量PASS。

剩余明确限制：

- 不提供跨目录/两地的全局admission、防另建目录重放的签名冻结或分布式事务；真正现场适配须在新精确批准下绑定唯一目录与身份。
- 没有真实peer请求消费/每次生成尝试日志、模型加载/导出/退出证据。这里只复算已接收的合成receipt。
- `PipeEndpoint`拒绝同一读块中的多帧；后续到达的迟到/重复帧会因请求绑定不符退休，但不能声称已证明未来永不出现多余字节或异步写入的因果范围。
- fd、flock、fsync和可读字节核查信任本机内核/文件系统，不证明整个OS闭包、敌对同UID无篡改或崩溃硬件存储保证。
- 合成dispatch不是完整许可/HMAC/SQLite/几何/清理联合链；还没有实际部署根全传递清单、宿主连续性适配、真实预算或独立进程stop冻结。

这些是后续有限工程依赖，不能由本轮CPU/CI成功勾选现场PASS。旧Rhino已经退出，原研究宿主承诺不能迁移到新进程；原10月9日租期也不能作为新预算。

## 4. 验证与可审阅交接

在本工程分支/PR中：

```sh
python -m pytest -q -p no:cacheprovider eval/test_c5_reuse_transport_evidence.py
python -m pytest -q -p no:cacheprovider eval/test_c5_formal20_reuse_draft.py eval/test_c5_final_decision.py
python tools/check_c5_formal20_reuse_draft.py
python tools/audit_c5_final_decision.py
python tools/check_release_consistency.py
python tools/check_secrets.py
git diff --check
```

只读检查器仍输出`execution_ready=false`，原NO-GO一致性回归保持。新测试的文件/字节只来自临时CPU夹具；没有原20/原80/A5/P2、远端或Rhino操作。README不登记未运行功能。

本地专项验收：新增97项控制与原准备53项/裁决16项，共166 passed；文档链接/发布一致性、密钥扫描与`git diff --check`通过。完整分支CI结果按最终提交在PR核实，不把这些专项计数写成现场工程PASS。

当前主线是完成剩余有限适配：新身份下的许可/账本/几何替身与独立联合评分、部署根传递清单预检，再按[冻结准备方案](c5-formal20-reuse-freeze-preparation-20261011.md)核实真实环境/资产/新宿主/资源并准备单次合成现场门。现场前仍须完整source/runtime、双CI和owner两个精确哈希批准；没有新正式spec/runtime，不能给正式启动命令。推送/PR已持续授权，merge仍由本人决定。#8文档准备与本工程分支均不是main已实施的新研究。
