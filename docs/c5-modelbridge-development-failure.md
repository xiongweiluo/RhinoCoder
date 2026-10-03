# C5 模型桥开发探针 A：单次失败与收尾边界

2026-10-03，仓库所有者分别批准 [开发 spec](../eval/c5/modelbridge-development-spec-20261003.json) 的规范化 SHA-256 `4911e6cd54f0f4523be4980b3973ae7419c98087ad3f378182658b8ae62edfac` 与[修正后完整 runtime freeze](../eval/c5/modelbridge-runtime-freeze-20261003.json) 的规范化 SHA-256 `1cb2adb2161ba2f14b2c80b703cc38e3573621a5a86014cf5c15b72883f6cb73`。初版 `bb697a08…ea369` 从未批准或运行。双 CI 已通过，远端 GPU 空闲、原始资产与隔离源码身份核对后，按批准范围各建立一次私有授权与 admission/driver/worker claim，再从空白未命名 Rhino 文档启动新 ScriptEditor hub。没有运行原80家族或新正式20题。

首个 hub `open` 即返回 `hub_failed_no_retry: NativeError: actual active document changed`。驱动写入 `modelbridge_fail_retired_no_replay` 并停止；第二个 hub `stop` 请求同样被守卫拒绝。本次 ID 永久封存，不能编辑配置后重启或沿用 ID。私有原始文件保留在本地 `data/training/c5/modelbridge-development-state-20261003-A/` 与隔离远端 `/data/c5-modelbridge-state-20261003-A/`；公开[失败摘要](../eval/c5/modelbridge-development-failure-20261003.json)不包含密钥、holdout 正文或模型原始输出。

远端只读结算显示：模型已加载，但 worker 请求与生成均为 0；含加载和等待共 17.614 秒，随后 worker 停止，GPU 回到 11 MiB/0%。本地没有任何 `engine-started` 或 `engine-created` 记录，Rhino 的独立只读检查也显示 child/fixture 均不存在、opened slots 为空、活动文档 0 个对象。因而这不是模型选择质量、工具执行或真实 Rhino 成功率的结果；不能据此判定 C5-6 通过或失败，更不能修改 C5 离线结果。

当前强假设是活动文档保护条件过敏：该守卫复用 `rhino_scene_digest`，其中包含进程全局对象 serial 水位及活动文档 undo 水位。两次只读 ScriptEditor 检查间，活动文档 serial 均为 `268435457`、对象数均为 0，但对象水位从 707 到 715、undo 水位从 11 到 13，摘要相应变化。第二组只读对照中水位继续从 723/15 升至 731/17，旧摘要再变化，而已有 `NativeDoc.active_content_digest` 两次均为 `de8fa792…ec6cfa`。由于首个 `open` 当刻未单独记录两项水位，不能把这说成唯一已证实的因果原因。下一版应复用已由真实只读对照支持的内容摘要保护活动文档，把原子执行账本的 ABA 水位留给可变夹具，并以单独测试证明不会放过真实活动文档修改。

失败后 hub 的 Idle hook 与九份从未使用的一次性密钥仍在，**当时不能伪装成已完成的冻结清理**。仓库所有者随后另行批准了[精确的一次性人工收尾脚本](../tools/c5_modelbridge_retired_a_reconcile.py)，字节 SHA-256 `aa269cc2d825fcffd89d13f0037c2306d545329fe1406fb14c87747c18fa0f38`。脚本先证实无夹具、无 engine claim、活动文档仍空白和 A 已退休，再以永久 claim 解绑该 Idle hook、实际删除九份未用临时密钥；私有批准/claim/result、文件缺失核对与 Rhino 命令历史成功输出均已验证。**这是单独的手工安全收尾，不是冻结协议的 clean stop，更不是探针成功。** A 的原始失败与远端结算仍保留，不重放。

之后如要继续模型兼容性，应使用全新开发 ID、修正源码、新 spec/冻结和另一次精确所有者批准；A 的授权、密钥和预算不迁移。新正式20题的构建与消费继续等待新的工程门通过。
