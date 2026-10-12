# 单次公开8槽开发入口启动失败：不重试

本人已直接批准完整开发spec `32f02512402ada907f6ed07381417d7f91c41896acef79ec5fe9b5d037b6d900` 与runtime `6c27d31987bed8289b498fd547dd680402b0f526cd773bd58a5c09dfaa9b2ac6`，见[本人批准记录](../eval/c5/reuse-development-owner-exact-approval-20261012.json)。批准时源码/完整冻结发布head为`9d1b27a8039861e59163dbbd63692180c872f4b2`，双CI38183213433/38183216914均SUCCESS（各1781 passed/9 skipped）。两端源码逐文件及完整公共模型/环境/宿主/tokenizer资产批准后重核通过，完整5小时准入窗口通过。

**本次结果是启动失败并退休，不是开发工程门PASS，也不是八槽模型质量结论。** 两端各一次登记同一批准，Mac `--prepare`一次成功；代理通过Rhino Script Editor只按一次Run执行新冻结包装器。真实终端 traceback在`run_c5_reuse_rhino_entry.py:42`加载准入模块时以`ModuleNotFoundError: No module named 'plugin'`终止；完整结构化事实见[失败记录](../eval/c5/reuse-development-startup-failure-20261012.json)。没有再次Run、修改后重跑、补槽或换身份续跑。

入口创建临时`rhino_c5_<uuid>.plugin`命名空间；准入模块第15行却绝对导入`plugin.rhino_listener.c5_reuse_field_scope`。真实Rhino解释器没有该顶层包。CPU替身联合测试直接从顶层`plugin`导入，Python3.9安全导入也没有覆盖实际临时包启动路径，因而先前全量通过并未发现该问题。这里是本次实际traceback及源码对应的根因解释，不推断GPU/模型质量或更后阶段是否能成功。

失败发生在hub-start claim、warmup、宿主订阅和基线之前。只读复核Mac新state精确人口为prepare输出：八目录各只有handoff.key，无native/控制器/宿主日志；全局准入SQLite完整性通过且0行、无消费tombstone。GPU新state当时只有owner-approval，无准入/worker/supervisor/stop；计算列表为空、同UUID显存11MiB。控制器未启动，实际加载/模型请求和生成阶段均未发生在此入口链路；本次记录槽启动/完成均0。不能把这些证据变成基座/LoRA各0/4的质量评分，实际物理生成总量独立证明仍null。

两端本次grant均已可恢复改名为`owner-approval.retired-no-retry.json`，原入口要求的`owner-approval.json`缺席，并各一次追加`entry-retired-no-retry.json`。原批准/冻结/失败保留；部署源码与两个完整哈希未修改。已知prepare密钥仍保留在私有目录，不宣称全宿主清理或内存擦除；没有新模型子进程或资格目标，因此没有臆造目标发送stop。没有退出/重启Rhino或执行另一个清理脚本。

完整八槽原始联合审计和外部ready/final custody没有形成，工程门不通过。正式40槽冻结与正式20题消费依赖因此未满足，不能自动进入；原C5 NO-GO、原正式失败、模型/契约/阈值和默认混合路线不变。这份追加失败报告与原研究报告分开，主线PR未自动合并。

后续只可由本人审阅这一失败与根因，再决定是否另行授权新的准备工作；当前单次身份和批准不能恢复或复用。
