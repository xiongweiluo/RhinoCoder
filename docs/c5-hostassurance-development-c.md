# C5 独立开发 C：显式加载就绪与分阶段时限（准备中、未批准、未运行）

当前六项持续交付的第2项。B已[失败退休并独立核实安全收尾](c5-hostassurance-development-b-result.md)，A也保持失败；不修配置重跑旧ID、不追认及时收到B迟到回执。B有限可见连续性PASS，不是整个工程门或LoRA质量裁决。

## 唯一修复边界

全新ID `C5DEV-HOSTASSURANCE-20261007-C`，独立源码/状态/spec/runtime。复用相同4个已排除train家族/8交叉槽、基座与checkpoint132、system/chat template/schema/严格解析/2048 token、最多16生成阶段/2写2读、一个空warmup＋8模型夹具、一个AssemblyLoad订阅；无canary/新题/模型训练/输出修复。B入口返回屏障与第一Idle单次seal完全保留，没有模块名字例外。

模型worker加载并完成原字节检查后，发布`worker-startup-ready.json`及一份固定就绪frame，绑定study/spec-runtime/source/environment/两路model身份、model_loaded=true、所有生成/holdout消费计数0；driver等待并严格验证ready后，才打开首个模型夹具/生成槽claim/发任务。模型加载仍只在Rhino基线ready后启动。就绪不是工具许可；任何错误/重复/额外/未知frame永久阻断，不重连或重发。

新启动窗口**≤180秒**、每请求窗口**≤180秒**分别冻结。原B120秒含worker启动/加载的混合窗口不沿用；这是一项显式操作性协议变化，必须另取C精确批准，不是假装B成功，也不降低LoRA质量/安全门槛。保留所有源/环境实际字节检查，不缓存、跳过或降低检查换速度。CPU真实合成子进程验证startup超过request窗口仍只消费一请求，以及错study/freeze/source/env/model/计数、EOF/timeout/重复/额外frame、未ready发送拒绝和永久阻断；无模型/Rhino/holdout调用。

[独立就绪审计](../training/c5_startup_audit.py)不导入producer helper，从freeze重建身份与零计数，要求Mac/远端原始ready一致；同时仍完整核对host外部回执/每请求checkpoint、原始生成/许可/几何/账本/关闭/删钥。不得以ready或单一连续性PASS替代完整八槽实际工程门。

## 保证、资源与现场门禁

仍采用本人已接受的整个opaque宿主信任＋冻结源码/可读文件＋可见checkpoint有限保证。旧默认/正式完整byte闭包守卫不放宽；legacy_byte_closure_verified=false。不声称完整代码发射字节、因果来源、clean进程、无瞬变或完整handler absence。pip唯一metadata缺项原样显式保留，不安装/升级。

退休开发累计**495.6544117410086秒**（B117.8387508240121），剩余**3104.3455882589915秒**，新cap取整3104；保守原累计prior7695.654411741009秒。今日2026-10-07 **18:45苏黎世停止生成、19:00到期**，至少900秒导出，正式3/研究4/原16 GPU-hours不扩张，不自动续租。所有预检/CPU/部署冻结不代表运行许可。

完整实际源/339可读host/Mac外部/tokenizer/GPU环境/模型/资源冻结和独立核对、最终双CI成功之后，集中请求新的C spec/runtime两个精确哈希；不复用A/B/native12/观察器批准。批准前没有C run/现场/模型消费。正式20题公开承诺复用不重索，正文/答案/密钥不读取；只有C完整实际工程与独立审计通过，才继续正式freeze/另外两个精确批准。整体六项未完成，GO不自动切默认路线或合并。
