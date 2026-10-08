# formal20失败审计：保管人入口准备（不是新评测）

2026-10-09，CPU核查核心与独立保管人TTY入口已实现，完整公共部署冻结/发布审核与本人执行仍待完成。实际正式v4已消费并停止，绝不重复解密、恢复模型、补槽或再次运行Rhino包装。本人已明确确认未捕获HOST_EXTERNAL_RECEIPT；不从producer seal补造外部锚。

[审计核心](../training/c5_formal20_incomplete_audit.py)仅由保管人侧未来冻结入口读取七份**已有**记录：started、run-result、public-progress、private-cases、native-prepared、model-plans-hashed、resource-settlement。以同一正式spec/runtime重新核对消费绑定、20家族Merkle、40槽顺序及两类窄计划绑定。代理只使用[既有合成家族CPU测试](../eval/test_c5_formal20_incomplete_audit.py)，不调用此核心读取真实状态；私有案例仅在本人终端参与校验，不向代理导出正文、答案、家族ID或任务哈希。

这是失败证据的**部分核查**，不是对原完整联合审计的修改或替代。闭合公开摘要永久保留：actual_generation_total=null、paired_summary=null、full_joint_audit_complete=false、host_continuity_verified=false、host_cleanup_verified=false、remote_gpu_absence_verified=false、replay_allowed=false。阶段确认计数0不变成实际生成总数0，槽0不变成两路质量0/20；资源原记录不改，墙钟差异只报告，不猜因果。未来单独GPU停止回执也不自动使本核心的宿主/私有审计通过。

[独立本人入口](../tools/c5_formal20_owner_failure_audit.py)使用新公共源码/审计元数据目录，不在旧source-v4里加文件或改旧runtime。`-I -S -B`隔离解释器，TTY条件先于原证据访问；先核对固定v4两哈希与338源码、审计自身字节及实际可读外部运行时，再永久audit admission，读取上述七份已有记录，末次核对后仅追加闭合公开摘要。密文/identity、密钥、stderr、模型帧/协议、Rhino均不访问。新运行时仍信任内核/未列opaque映像，不称全OS字节闭包；缺少外部锚不因新摘要而被修复。

[公共准备器](../tools/prepare_c5_formal20_incomplete_audit.py)只复制已登记源码并调用`inspect-runtime`（私有证据读取0），O_EXCL形成独立新review-runtime，未知/已有目录不覆盖；它不能触发`audit`。CPU负控覆盖TTY先行、源码/环境/冻结漂移、已有admission、失败保留claim、错误脱敏、无模型/解密/信号/删除入口。冻结审核完成前不给出真实执行命令。本人入口失败不自动重跑，不重读密文或启动新评测；未具备的完整连续性、清理和质量证据如实列为缺失，不能通过新审计追认原失败成功；C5-7按既定证据完整性规则裁决，任何后续新研究须另行决定。

## 公共部署导入回归

[v1公共准备停止](../eval/c5/formal20-v4-incomplete-audit-public-preparation-v1-stop.json)仅创建两公共源码，`-S`下缺jsonschema导致inspect-runtime拒绝；没有review-runtime、owner audit admission或私有读取。v1保留且不覆盖/重跑，不是新的正式消费。v2保持`-I -S -B`，只显式呈现原Mac冻结已包含的`/opt/anaconda3/lib/python3.13/site-packages`，导入前重新核对其已冻结可读字节，导入后验证实际外部依赖仍在原清单；不调用site.main、不执行.pth。新review-runtime同时冻结实际sys.path和可读已加载外部文件，真实owner审计先验证这些字节后再加载核心/读私有证据。CPU真实隔离子进程只导入公共测试源码验证此修复，不接触原state。

**当前仅v3候选可交付：**v2公共导入及199外部文件冻结已形成，但未运行owner audit。独立核查发现原清单不包含jsonschema包的静态schema资源；不假称全部依赖资源字节闭包。此失败审计本来只须证明已存案例与原Merkle/顺序/计划相同，不需重做参数语义验证。因此v3改为独立标准库Merkle/顺序重算、严格七文件读取与O_EXCL摘要；不导入旧工程/语义验证器、site-packages或Rhino，也不执行.pth。CPU逐项比较新算法与原算法（四个seed），真实`-I -S -B`子进程验证无项目/第三方导入；新增摘要明确`case_semantic_or_arguments_schema_revalidated=false`。这是缩小到原有部分核查目的，不降低完整正式联合审计或GO门槛；v1/v2公共包及v2冻结原样保留，均无owner audit claim/私有读取，不再使用。
