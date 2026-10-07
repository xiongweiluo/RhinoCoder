# C收尾B：有限人工安全关闭已核实，原C仍FAIL

仓库所有者对`C5SAFE-HOSTASSURANCE-C-20261007-B`的spec `505891816aa4cc471816689c31aa774deadfc30384828c7fe0ac7031bd900100`、runtime `2aab184fd2a54545dc8c3c2b75cc9f55ca02a0dc0b6cd52dea0e03da4d4dae3d`直接精确批准后，按源码`2a1f6f2`、发布`143fafa`及双CI（37655424174/37655430888）单次运行。入口字节SHA `05d3fa3ab5813c169b4898001507fc5e6c6d45132a879612f2cf249eb2a492d6`与批准一致；wrapper逐字节匹配spec，Run一次，无重试。见[公开结果与哈希索引](../eval/c5/hostassurance-c-cleanup-result-20261007-b.json)、[事前准备](c5-retired-c-cleanup-b-preparation.md)。

## 已完成的精确安全范围

- 新永久admission先于现场检查，effects claim先于实际收尾。原289源码/339可读文件、七份新执行闭包及八份开发证据重新核对。
- 历史read9 HMAC仅用保留内存secret核验，不重放请求或读取密钥正文。当前UI/backend线程、精确owner、空headless未保存fixture475及active457/content均通过。
- 原空fixture268435475单次Dispose，原生close capture确认registry缺席；活动文档前后serial268435457及内容SHA `de8fa792…ec6cfa`不变。
- 七指定临时key文件实际删除，独立磁盘检查均缺席；前两write槽已删除的key也仍缺席。只删除这些key文件，未删除目录、账本或历史证据。key文件不可恢复；不承诺内存或外部副本擦除。
- 两份原Idle精确remove完成，既有AssemblyLoad准确remove完成，原owner在全部核查通过后释放；不声称完整handler absence。
- 原C失败结果文件SHA `6093aa3a…b3c3a9`不变；只读SQL前后逻辑行SHA `2aba3153…cf3420`不变，历史expected0/当前stored1 drift保留。无snapshot、账本更新或状态修复。

模型/GPU/工具/holdout/新夹具/新订阅调用均0。180秒是逻辑预算，不是CLR抢占保证。仅形成`retired_C_manual_safety_closed_not_experiment_PASS`，B永久退休，不能再次执行。

## 独立联合审计与仍然失败的连续性

实际CUA Script Editor的两条外部终端回执单独保全，而非从producer文件制造外部锚。UI packet canonical SHA `b8a423ee…ec3ddf`，实际safety result canonical SHA `ec89097f…9ef0a`。[独立收尾审计器](../training/c5_cleanup_b_audit.py)复核grant/admission/effects、外部结果、raw close/key/账本/活动保护；再以只读SQL、磁盘缺席和原C文件字节交叉核验，最终重放没有导入收尾生产者。

[独立原始host审计器](../training/c5_host_assurance_audit.py)重放全部58记录、48普通checkpoint及39请求绑定；链/外部seal/解绑记录一致，外部seal canonical SHA `41c7cdbf2e7c4f07b5ae36a762be0c2d95148419475641fdd22d12427ae66985`。原55记录保留，新55/56为detach attempt/detached，57为cleanup checkpoint。最后快照的`python_origins`不同于基线，事件/错误/丢失均0，`continuity_error_type=NativeError`。审计如实返回`host_continuity_failed_or_incomplete_no_replay`、`blocked=true`，**不是连续性PASS**。不按名称白名单、不把结构指纹改称字节证明，也不从快照差异证明唯一因果或无瞬变。

有限安全关闭已核实与C整体工程失败是两个不同结论。C/收尾A失败、atomic drift和全部账本不改判；完整代码字节闭包、隐藏发射/因果来源、整个宿主零副作用、完整handler absence、内存/外部密钥擦除均未证明。私有原始开发证据留在原私有状态目录，公开仅汇总/哈希，不打包脏工作区、认证材料或任何正式题目。

## 路线选择：在这里止损，不自动D

现有工程A/B/C均退休，C未完成八槽门；正式20题仍封存且未由代理读取/消费，已登记公开承诺不重索。原GPU最迟2026-10-07 18:45苏黎世停止生成、19:00租期已结束，收尾B不使用GPU、不扩张边界或自动续租。开发累计1129.012194秒未增加；未花完GPU-hours不等于仍有租期授权。

建议所有者选择**暂停现场模型路线，先交付截至当前证据的阶段报告与PR审核材料**：保留离线77/80对20/80、部分原生开发能力和A/B/C失败；明确C5-6未完成、C5-7未裁决，不将缺失正式证据追认为GO或强行判LoRA无效。若所有者另选继续，必须先明确新的研究/资源边界，重新决策后才可能准备新独立工程研究；此文件不设计或授权D，不以只加超时代替生命周期/成本验证，也不自动冻结/运行正式20题。

整体六项Goal未完成。推送/PR更新已授权，merge仍仅由所有者决定；C4 NO-GO、v8 formal_quality_fail59/60、默认混合不变。
