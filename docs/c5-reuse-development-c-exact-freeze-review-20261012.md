# 独立开发C原完整冻结与精确批准门

**最新实际执行状态：** 本人已批准修订两哈希，C已单次在worker-ready前失败并完成首次既有hub收尾/两端退休；见[C失败追加报告](c5-reuse-development-startup-failure-20261012-c.md)。下方材料准备与待批准语句仅为历史时点，不再要求同一批准，也不得恢复C入口。

**本页为原批准时点说明。** 本人随后精确批准，但GPU重启在任何grant/入口前被只读预检拦截；最新完整材料和执行门见[C boot修订](c5-reuse-development-c-boot-revision-review-20261012.md)。下方“尚无批准”和“同boot”仅为原时点记录，原04caa批准不适用于修订runtime。

本人在B单次准备预检失败并退休后明确确认[独立新候选准备](../eval/c5/reuse-development-owner-preparation-authorization-20261012-c.json)。C身份为`C5DEV-REUSE-20261012-C`／`reuse-dev-20261012-c`。此次只完成源码适配、CPU验证、两端公共部署、实际无研究作用预检及完整冻结；尚无C执行批准、state/grant/key、Rhino包装器、模型加载或生成。A/B原失败、完整源根和两端退休批准保留，旧批准不能用于C。

| 完整材料 | canonical SHA-256 |
| --- | --- |
| [C development spec](../eval/c5/reuse-development-spec-20261012-c.json) | `10f821cacb0e5681c3b2f8286230eab7dfdd69102ed7ca3adf540f6cd2148446` |
| [C complete runtime freeze](https://github.com/xiongweiluo/RhinoCoder/blob/84a0336ab32883c4f16cf7bca775421062387d0a/eval/c5/reuse-development-runtime-freeze-20261012-c.json) | `04caaac2a915b635211751f35d020ec79134d5bdd46d7efff88120be17992df2` |

上述哈希覆盖整个JSON，按sort_keys、紧凑separators、ensure_ascii=true、allow_nan=false规范化；不是原始文件SHA或缩写。[完整environment plan](https://github.com/xiongweiluo/RhinoCoder/blob/84a0336ab32883c4f16cf7bca775421062387d0a/eval/c5/reuse-field-environment-plan-20261012-c.json)绑定模型、环境、宿主接受、资源、停止和两条退休关系。material-ready不等于执行批准或工程PASS。实际逐文件与预检证据见[独立完成记录](../eval/c5/reuse-development-complete-preexecution-validation-20261012-c.json)；精确发布head双CI以该准备PR当前实际检查结果为准，归档的发布前记录不冒充后来CI结果。

## 操作权限预检与防止恢复旧执行

B失败来自代理在受限沙箱中调用Mac prepare时，系统拒绝只读`kern.bootsessionuuid`查询；此前CPU成功没有证明该实际调用权限路径可用。C新增`preflight_c5_reuse_candidate.py`，在实际固定解释器、源根和将来入口使用的主机权限下运行。同一`readable_scope`同时服务无研究作用Mac预检和正式Mac scope：核对原PID/UID/UTC启动时刻/boot-session、宿主339、控制器3552、tokenizer6字节、所有当前加载来源及SSH程序/known-hosts/master锚。实际GPU预检检查固定Python3.11、UID1000、boot/UUID、原模型与环境字节；只解析惰性依赖，不加载模型或初始化CUDA。

预检没有真实或合成owner grant；纯材料检查只返回`execution_authority=false`。它不创建研究state、key、claim、宿主订阅或准入角色；预算对象仅核实完整窗口，不代表研究已开始。真正`approved_entry`仍必须读取并核对直接本人精确批准的私有grant，保持所有源码/前序/环境守卫和单次屏障。

C每次入口和公共部署都同时钉住A/B原始失败及两端退休字节。任何旧grant恢复、退休缺失/漂移、alias/hardlink/权限不符或共享准入非空/未知，均拒绝；没有清空表或改换全局准入命名空间。B公开失败记录原始SHA为`07eed8000f03ef49a35d9106499a9b8712cefc357e5e2c51d1510ff8b0582e2c`，B退休记录为`3110dd38a8b318150526394ae98e7b36233fa6ac91a64a2adb08a1f1b529afda`。其历史`record_epoch`含义仍按B失败记录说明，不追认精确失败时刻。

## 实际完整材料与保证范围

两端源根为`/Users/xiongweiluo/RhinoCoder/data/training/c5/reuse-dev-20261012-c-source`和`/data/reuse-dev-20261012-c-source`，各307个清单文件＋runtime，308个公共文件，payload 3,330,367字节。可读完整副本在`/private/tmp/rhinocoder-c5-reuse-development-c-freeze-20261012`；未获执行批准的原型副本另保留，不是可恢复旧运行。仅在C state/grant缺席、旧公共人口/字节与原型runtime精确锚全部通过时刷新了注释/排版；spec与plan不变，没有研究操作重试。

原GPU基座14/adapter2、非缓存分发21614、stdlib960、两libpython及RTX3090/驱动550.107.02匹配。Mac宿主339、控制器3552和tokenizer6匹配。保留Rhino PID44652、UID501、UTC启动2026-10-11T16:14:32Z、boot-session F873EC8A-960B-4B86-B35E-65A973D84E99，GPU仍同boot/UUID；接受依据为原本人三项确认及相同进程当前只读重核，没有制造新的本人宿主声明。真实Rhino入口仍在warmup/订阅前要求主线程和空白文档。

保证仍为可读文件冻结＋opaque宿主信任＋有限可见检查点；不保证全部执行字节闭包、隐藏handler缺席、检查点间无瞬变、密码学人类/物理来源、完整宿主清理或内存擦除。A准备密钥仍私下保留；历史GPU累计继续未知，原pip metadata和缓存字节码例外不归零或隐去。

## 资源、单次操作与保管门

沿用本人已确认的额外23小时有限修订：开发5小时、正式18小时，含加载/idle/停止/保守释放观察，开发余量不自动转给正式。不追认原16小时累计合规，不是平台余额，没有新续租/付款事实。实际租期仍为2026-10-13 20:00 Europe/Zurich（UTC+2），19:45停止生成，900秒导出；开发完整5小时准入最迟10月13日14:45。正式完整18小时还须与实际租期、开发用时和阶段等待另行核实，不能静默截短或扩充预算。

本人新两精确哈希批准后，先重新核实最终字节、退休和余量；**代理用`require_escalated`主机权限调用Mac入口，避免再次把准备/drive放在受限沙箱。**两端批准各一次登记→Mac一次prepare→本人先在私下TTY启动ready保管工具并报告已就绪→代理只Run一次C冻结wrapper→返回后首非命令Idle封存基线→controller一次drive，stdout以O_EXCL/0600写入C state的`controller-output.log`→本人核对真实host/worker ready锚并输入“确认并保管”→固定公开8槽、退出/有限清理/资格目标释放观察/导出→本人核对实际Rhino终止回执并final custody→完整原始联合审计。实时ready等待仅120秒，保管终端必须先就绪，代理不能代签。

仅在批准和prepare完成后由本人在私下交互终端运行：

```sh
/opt/anaconda3/bin/python3.13 -I -B /Users/xiongweiluo/RhinoCoder/data/training/c5/reuse-dev-20261012-c-source/tools/run_c5_reuse_owner_custody.py --ready
```

完成后同一工具`--final`要求本人粘贴Rhino实际`C5_HOST_CONTINUITY_EXTERNAL_RECEIPT`完整一行并确认保管；独立原始审计使用同根`tools/audit_c5_reuse_field_eight.py`。准备时的无研究作用实际权限预检命令为：

```sh
/opt/anaconda3/bin/python3.13 -I -B /Users/xiongweiluo/RhinoCoder/data/training/c5/reuse-dev-20261012-c-source/tools/preflight_c5_reuse_candidate.py --endpoint mac
```

该预检与ready/final/单次入口是不同步骤，不批准生成或证实保管人来源。C保管字节回执固定为`/private/tmp/rhinocoder-c5-reuse-c-actual-deployment-byte-receipts.json`，不得读B回执代填。

C仅原固定公开8槽一次；原模型/契约/顺序、180秒模型请求、120秒native ACK、60秒settlement、无parser repair不改。失败/未知退休，不补槽、不重发、不重试，不自动改后重跑或再生成候选。工程门要求8槽完整原始联合审计、至少模型导出合法写1/read1、关键违规/重复派发/未核实清理0及有限连续性通过；槽语义质量分别披露。只有完整工程门PASS才准备另一个正式40槽冻结/双CI/新两哈希批准；原20题仅由本人私下消费并审计，代理只接收脱敏摘要。原NO-GO、原正式失败、同题复用披露、阈值与默认混合保持，不自动产品切换或PR merge。

## CPU与实际验证

本地完整CPU：1852 passed／11 skipped，316.42秒；双前序负控、真实临时包/Python3.9隔离bootstrap与本人保管边界首批119通过，无grant材料/权限拒绝及资源/资产控制40通过。增加19项有意义控制：B前序15种拒绝分支和4项grant-free/退休身份/真实宿主身份拒绝边界。此前1项CPU失败源于退休A身份负控的预期错误码已改变，已改为当前C资源边界负控并通过，原失败日志保留；首次资产归约缺实际manifest原始公开字节，采集器已补齐并在实际GPU重采验证。最终前序注释/排版与此前全仓源码的功能AST相同，最终字节和实际预检另行核对；精确发布双CI覆盖最终commit，CPU/CI均不能替代真实链路、质量或完整原始审计。
