# 同题复用：两端运输与原签名许可接线

2026-10-11，依赖已发布#11的源码 `ff98a9e`；#11 push/PR双CI均成功，均1499 passed/9 skipped。此追加继续第1项的实现工作，**不是完整现场入口或可执行冻结包**。旧开发/正式入口和永久消费屏障不改，不运行模型、Rhino或正式题。

## 本次具体推进

- 一份 master runtime 现在同时冻结 Mac/GPU 两组源、状态和持久准入路径，绑定本地端点。跨端消息只用共有study/instance/spec/runtime/plan/limits身份；本地raw链仍绑定完整本地scope。旧单端runtime形状、端点角色交叉、本地路径重绑均拒绝，没有把#11的匹配记录变成人工授权。
- 准入锁只覆盖完整tombstone/SQLite事务，不占据整个actor生命周期。这样worker仍活跃时，独立stop actor可以进入同一持久命名空间；同一临界区仍拒绝另一真实进程进入，未知间隙仍永久拒绝新效果。该修正解决生命周期持锁会阻止独立停止的实际接线问题。
- `training/c5_reuse_field_transport.py` 提供新的字段协议和已提供descriptor的有界channel，未扩大原synthetic运输器的用途。完整180秒包含guard、意图发布、全部发送/接收、解析验收与ACK。部分写仅推进偏移；坏帧/EOF/未知/迟到永久退休，原样接收片段先持久记录；超过单次read上限的注入数据记录截断标记，不能认证完整接收。没有SSH启动器、重连或模型加载器。
- `training/c5_reuse_field_transport_audit.py` 不导入channel/peer生产者；从控制端原始帧和模型端原始生成行独立联合复算。所观察人口的完整模型raw join不表示八槽整体完成、原生许可/清理通过或物理生成总量被独立证明。
- `training/c5_reuse_native_handoff.py` 只读取部署源根的固定公开八槽原文和政策，保留原严格解析、原ResearchSigner/ConsentStore、签名及SQLite消费/派发屏障。真实捕获必须等于生成前实际scene；原始model receipt不改，另记可信scene绑定。签名前、签名持久记录后和执行后仍检查源码/预算/完整120秒；未知永久退休。零写政策及已知prepermission拒绝在建许可数据库前分类，不修正模型调用或替换几何。
- `training/c5_reuse_native_handoff_audit.py` 不导入handoff生产者；核对原始实际捕获、未改变的模型调用、HMAC、任务/冻结身份及原许可/派发数据库。数据库只能来自当前绑定state/slot，拒绝symlink/硬链接/错误权限；拒绝槽的许可数据库缺席与原生空账本也独立读取。生命周期、结算、精确detach、几何质量及完整清理仍为另行必需证明。

这些是接线组件；guard、预算、捕获和执行提供者仍由未来完整可信入口提供。没有提供真实脚本启动命令，也不能把注入的no-op guard或CPU替身当现场安全验证。

## 当前宿主事实更新

本人已自行打开Rhino，并明确确认活动文档空白、研究期间独占、不进行其他操作，接受冻结可读文件＋信任opaque宿主＋有限可见checkpoint保证。[直接准备接受记录](../eval/c5/reuse-development-host-owner-acceptance-20261011.json)绑定只读确认的PID44652/UID501、UTC起始时刻及Mac启动时刻。这仅是新实例准备接受；没有独立进入Rhino检查文档、没有脚本/订阅/warmup，亦没有新spec/runtime精确运行批准。

[较早资产观察](../eval/c5/reuse-current-asset-preparation-observation-20261011.json)中的“Rhino未运行”属于其采样时点，不能改写成后来仍未运行；它的339/3552可读代码匹配不变，但真正冻结和执行前需重新确认当前PID/字节/接受仍适用。资源账本问题仍待本人回答：此前GPU累计保守上界、此次GPU-hours/费用上限；不沿用旧prior或将续租理解为无限预算。

## 验证与剩余完整入口

本次新增48项CPU控制，连同#11的92项共140项通过。新增覆盖master两端绑定、端点角色、stop与活跃worker共用准入、真实CPU子进程pipe、部分写偏移、完整帧/EOF/重复/截断/错误scope、持久失败/时钟期限、重新计算整条链后的运输篡改、真实原许可/原生SQLite接线、只读零写政策、source/scene/原始模型/签名/持久/派发未知、原始HMAC和账本复算。一个负控初次仅捕获ValueError，实际正确拒绝为保留库的NativeError；修正测试异常类型后重验，不放宽校验。合法但错误的盒体输出在圆柱任务上原样保留，审计不认证几何质量。

**尚未完成第1项：**实际worker加载/启动/父子PID资格与预声明单次停止策略、SSH controller、Rhino新hub/entry-return/Idle/有限观察器接线、八槽完整生命周期/结算/清理/外部准备和最终锚、完整联合现场审计入口及实际两地部署根全字节预检仍缺；当前只有supplied-descriptor和injected-native接线。必须完成这些及当前资源账本，形成实际完整开发spec/runtime和独立逐字节复核、源码与冻结双CI后，才能提出两精确哈希批准。没有批准可执行的完整材料，不能进入第2项或宣布六项已完成。

固定源码本地全仓1547 passed/9 skipped，276.78秒；原有九项前提skip，新增48项无skip。秘密扫描、release一致性、原NO-GO检查和Rhino侧Python3.9纯导入通过；源码发布双CI以PR最终head记录为准。

之后继续依门：新开发单次现场独立PASS→正式40槽另一份完整冻结/双CI/批准→本人私下单次复用/原始审计→披露式追加研究报告。PR仍Draft、merge由本人决定；原NO-GO/未知生成总量/原阈值/默认混合不改，主工作区九份修改不覆盖。R UI/P2b/精简D仍延期。
