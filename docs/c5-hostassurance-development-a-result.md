# C5 宿主保证开发 A：FAIL/退休与下一准备边界

2026-10-07，所有者对最终spec/runtime两个哈希批准后，冻结源码`28f6fb6`、发布`898832d`双CI先于单次claim。见[不可改判的结果](../eval/c5/hostassurance-development-result-20261007-a.json)。当前不是C5-6 PASS或LoRA质量NO-GO；只是新工程门FAIL。**A永久退休，不能再次运行**。

一个空warmup毫米夹具实际读回/registry关闭，随后基线订阅与封存成功。GPU真实加载了同一基座/LoRA，但首个`write-base`打开前守卫发现差异并阻断。生成请求/claim0、模型夹具0、工具派发0、holdout0；含加载/等待37.788497秒，worker退出0、资源结算stopped_no_replay、GPU恢复11MiB/0%。

11份原始日志中唯一差异是`python_origins`删除`__main__`；Python其他模块、程序集/native映像、process/active均相同，事件/丢失/异常0。它与`runpy.run_path(..., run_name='__main__')`返回时恢复临时主模块的行为一致。CPU使用真实stdlib runpy已复现暂存模块/原对象恢复，以及在入口返回后再seal可观测到稳定对象；这不证明其他未来晚绑定也安全。

Rhino **Command History**捕获实际`C5_HOST_CONTINUITY_EXTERNAL_RECEIPT`，外部sealSHA `e9c04347…0b9825`、head `423866f1…cc148f`；冻结独立入口完整复算并返回`host_continuity_failed_or_incomplete_no_replay`，不把链完整当连续性PASS。签名stop raw request/response、hub-stop/driver、warmup关闭、活动摘要和全部九份key实际缺席交叉核实；Idle/AssemblyLoad精确解除调用完成，但没有新增canary刺激，不夸称完整handler absence。

## 可继续的授权准备：B，不重放A、不忽略主模块

新的B仅修复**采样时序**：frozen entry返回后wrapper再明确release，第一份非command Idle回调单次seal并publish ready，该回调不得派发任务；随后才启模型。seal失败sticky，不重试/重封，不按`__main__`名字或其他名字白名单放行，全部可见库存仍严格逐项比较。保证强弱选择仍是所有者已接受的同一有限策略，不改旧字节守卫、默认路线或数据/模型/门槛。

B仍为相同四个已排除训练家族、独立新ID/源/状态与两份新冻结；CPU/合成实现、只读复核及冻结准备可继续，**任何新现场仍需最新双CI及新的两个精确哈希批准**。本报告不自动批准B，也不是正式20题授权。新的累计开发用量377.815661秒，剩余上限3222.184339秒（向下取整3222），仍在今日18:45停止/19:00到期、900秒导出和原总量限制内，无自动续租。

原始开发JSON/日志/claim和已删除key的实际缺席证明私下保留，不打包全部目录或覆盖R/A历史证据。正式20题公开承诺无需重做，正文与密钥不读取。
