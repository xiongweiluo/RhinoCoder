# formal20失败审计：保管人入口准备（不是新评测）

2026-10-09，CPU核查核心与独立保管人TTY入口已实现，完整公共部署冻结/发布审核与本人执行仍待完成。实际正式v4已消费并停止，绝不重复解密、恢复模型、补槽或再次运行Rhino包装。本人已明确确认未捕获HOST_EXTERNAL_RECEIPT；不从producer seal补造外部锚。

[审计核心](../training/c5_formal20_incomplete_audit.py)仅由保管人侧未来冻结入口读取七份**已有**记录：started、run-result、public-progress、private-cases、native-prepared、model-plans-hashed、resource-settlement。以同一正式spec/runtime重新核对消费绑定、20家族Merkle、40槽顺序及两类窄计划绑定。代理只使用[既有合成家族CPU测试](../eval/test_c5_formal20_incomplete_audit.py)，不调用此核心读取真实状态；私有案例仅在本人终端参与校验，不向代理导出正文、答案、家族ID或任务哈希。

这是失败证据的**部分核查**，不是对原完整联合审计的修改或替代。闭合公开摘要永久保留：actual_generation_total=null、paired_summary=null、full_joint_audit_complete=false、host_continuity_verified=false、host_cleanup_verified=false、remote_gpu_absence_verified=false、replay_allowed=false。阶段确认计数0不变成实际生成总数0，槽0不变成两路质量0/20；资源原记录不改，墙钟差异只报告，不猜因果。未来单独GPU停止回执也不自动使本核心的宿主/私有审计通过。

[独立本人入口](../tools/c5_formal20_owner_failure_audit.py)使用新公共源码/审计元数据目录，不在旧source-v4里加文件或改旧runtime。`-I -S -B`隔离解释器，TTY条件先于原证据访问；先核对固定v4两哈希与338源码、审计自身字节及实际可读外部运行时，再永久audit admission，读取上述七份已有记录，末次核对后仅追加闭合公开摘要。密文/identity、密钥、stderr、模型帧/协议、Rhino均不访问。新运行时仍信任内核/未列opaque映像，不称全OS字节闭包；缺少外部锚不因新摘要而被修复。

[公共准备器](../tools/prepare_c5_formal20_incomplete_audit.py)只复制已登记源码并调用`inspect-runtime`（私有证据读取0），O_EXCL形成独立新review-runtime，未知/已有目录不覆盖；它不能触发`audit`。CPU负控覆盖TTY先行、源码/环境/冻结漂移、已有admission、失败保留claim、错误脱敏、无模型/解密/信号/删除入口。冻结审核完成前不给出真实执行命令。本人入口失败不自动重跑，不重读密文或启动新评测；未具备的完整连续性、清理和质量证据如实列为缺失，不能通过新审计追认原失败成功；C5-7按既定证据完整性规则裁决，任何后续新研究须另行决定。
