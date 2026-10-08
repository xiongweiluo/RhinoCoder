# 正式20题 v2：已接受范围后的代码与冻结准备

2026-10-08。D实际完整工程门PASS保留并退休；本人已接受容量/资源提案`81b799b1…49efb`，[接受记录](../eval/c5/formal20-capacity-owner-acceptance-20261007.json)只授权本次适配/CPU/冻结准备，不是正式执行许可。新正式Source/State使用v2独立目录；公开study ID仍`c5-rhino-paired-20-v1`，既有承诺`41c92c72…ebaf4`、20家族/40槽/seed20261003不变，旧v1从未运行，不追认旧草案就绪。

## 当前完整冻结与独立复核（未获执行批准）

[独立预执行核查](../eval/c5/formal20-v2-preexecution-validation-20261008.json)已完成。源码`5399281778908f210f24b1579cc54c8733909777` push37702904130/PR37702910598均成功；最终源码CI1019 passed/9 skipped（与Mac全仓1019/8及最后8项owner回归区分）。336份源码、含公开配置/spec/runtime共350文件在Git/Mac/Linux精确清单与字节一致；3552 Mac外部/339可读host/6 tokenizer/age、21614 Linux分发/960标准库/libpython、14基座/两adapter独立重哈希。实际loader import未初始化CUDA或构造模型；另一路独立环境重放不导入torch。pip原缺项保留，不安装或伪造。

- spec规范化SHA-256：`9f27e0ad16dbd1a46d200e5e258d64d5e02ccf49219c584b47bc3272b7368592`。
- [runtime](../eval/c5/rhino-formal20-runtime-freeze-v2.json)规范化SHA-256：`83f2f8974b95bea2f1120a7340d5c7a781a005e14aaafd3ff74239d9d415faba`。
- runtime文件669516字节，字节SHA-256：`4d8480e9ca384c9bd67d5ee865215046c9c965d57c8861f203ed36c275b9bf87`。

最后远端runtime写入的SSH回执30秒超时，准备器退出1，**不声称准备器正常退出**。未重跑或重传；只读核实远端完整字节/350文件人口及无遗留tee，与本地精确一致后确认这次单次写入实际完成。独立检查器的相对/绝对路径断言错误仅修正检查器，不改冻结。另发现D旧公开准备摘要环境标签69位笔误；原D文件原样保留，此处按实际D runtime重建正确环境SHA`536eac7d25305a89ca3d3ad06fa23eb0eca1e3ac8df889cc84dfb7fa7f2b9fca`，D原spec/runtime/资产/结果不变。

两地正式state/grant/key/claim均不存在，现场/模型/正式消费0。新实际host基线没有观察，必须在**新精确批准后的单次zero-stage**形成；此处只证明已冻结可读文件和已接受的整个opaque宿主信任范围，不是全部代码字节闭包。最新发布head双CI成功后才请求上述两个哈希正式批准，不借准备/旧D/一般继续授权运行。

## 新入口顺序与职责隔离

1. [保管人入口](../tools/c5_formal20_owner_run_v2.py)在本人TTY内先核对新完整spec/runtime和新的精确owner grant、已登记公开承诺、完整5小时窗口。一次性zero-started先于任何现场准备；不是holdout消费。未获精确批准不得调用。
2. [NativeAdapterV2](../training/c5_formal20_adapters_v2.py)预建40个固定ordinal槽密钥，唯一[Rhino arm](../tools/c5_rhino_formal20_arm_v2.py)核对空白研究独占文档后做一次空warmup及可核实关闭；准确一份Idle delegate，经明确entry-return后的首次非command Idle封存一次AssemblyLoad/弱host基线。此时不读私有计划、不开任务夹具、不派发工具。
3. 同一新[worker](../tools/run_c5_formal20_worker_v2.py)实际冻结模型加载/来源环境验收后发布typed zero-ready；**在读取任何任务或hash计划前**，generation0/private-row0。未知/错误/完整180秒超时永久阻断，不重连/再启动。
4. 本人才以无回显提示填写age包和identity路径；只在本人进程核对元数据/密文承诺，identity正文不预读。仓库边界从冻结指定的真实仓库根只读查询，不能在无.git源码部署里误查。之后永久formal.started先于解密和private-cases发布；开发代理永不运行此私有入口/读取正文、答案或key。
5. 只有started存在才一次性初始化私有窄计划；复用**同一**已安装Idle delegate，不再attach。各槽独立headless毫米夹具，播种每步source/可见checkpoint、一次模型请求、严格解析、逐步许可消费/签名/原子账本、三稳定读回、关闭删钥/stop。错误模型输出可分类但不修补，未知状态停止整个研究。
6. [独立私有联合审计](../training/c5_formal20_joint_audit_v2.py)由本人冻结入口运行，重建40槽/模型/许可/原生/seed/SQLite/完整资源/host与时序；只导出不含题面、答案、几何、family ID或keys的aggregate public summary。实际外部host seal从Rhino已有输出由本人/授权只读界面捕获，不从producer文件自造锚。摘要仍不自行裁决C5-7。

前置失败不意味着数据消费；一旦formal.started已写，无论解密/模型/几何后来如何都不复用或补题。已知worker零生成、尚未bootstrap时允许同一已知process的单次abort/退出核查，不宣称整个Mac未消费；未知ack不发abort/reconnect。现场arm/部分夹具/委托未知时不猜测安全关闭，保留精确owner和原始证据并另取安全收尾批准。

## 统一冻结契约和预算

[v2 spec](../eval/c5/rhino-formal20-spec-v2.json)仅表达准备契约；完整runtime仍须形成，execution_ready不等于人类执行批准。[容量/弱保证绑定](../plugin/rhino_listener/c5_formal20_policy_v2.py)拒绝旧D/准备批准、浮点版本、布尔容量、漂移容忍、额外订阅、跳过来源、重试或未经就绪私有加载。默认/旧512门不放宽。

normal2048、独立cleanup256、journal4096；最多8结算采样，仍须3稳定且完整60秒。120秒native计时从client guard前开始，需要response＋post-publication service proof，并涵盖解码/验收；180秒模型/启动涵盖完整元数据验收，原始frame不投影替换。只保证逻辑期限，不声称CLR/CUDA硬抢占、隐藏代码字节、无瞬变或完整handler absence。quota耗尽停止派发，cleanup记录额度本身不授权任何实际操作。

固定strata最多56模型请求/112生成阶段，较旧240上限收紧；原训练/提示/chat template/12工具schema/严格JSON/2048 token及128 native/41 hub上限不变。门槛LoRA≥14/20、配对净胜≥3、安全/重复写/未核实清理0不改。

[已接受v7边界](../eval/c5/rhino-resource-boundary-v7-formal20-20261007.json)：正式5/研究6小时，开发1/原累计16小时不变；D后研究prior2407.228115秒、原保守prior9607.228115秒。10月8日21:45苏黎世停止生成，22:00到期、900秒导出。完整5小时加zero-stage启动余量要求本人最晚**16:39苏黎世**开始；过界在admission、私有路径或模型前拒绝。该时限不是5小时必能完成证明，不自动续租、付款或扩预算。

## 已完成CPU工作与剩余冻结

专项包含策略/预算16、完整40槽与13种原始篡改负控14、真实CPU framed subprocess/时序7、保管TTY/就绪→路径→claim→loader/晚启动/完整就绪期限/初始化失败/已结算进程不得二次收尾8、冻结准备5项控制。模型/几何/SSH由注入替身模拟，签名/SQLite/文件协议/独立时序与评分是真实代码。复用仓库原合成task_text，不新造开发题面；此处不声称十二工具全现场或新私有排除人工证明。全仓1019 passed/8 skipped后，最后一处owner退出防二次结算修改的8项回归通过；最终发布源码双CI另行核实，不以此前版本的测试数量冒充最终冻结验收。

CPU准备中先修正合成夹具漏schema/admission；另发现并修复真实代码的部署根worktree查询、远端raw inventory漏owner-approval、前置ready失败不能允许后续发送、完整host就绪期限，以及已结算远端process不可二次stop/publication。修正均在正式数据未读和冻结前，未放宽审计或修改旧D部署。

2026-10-08早先只读检查：339可读host文件逐字节无漂移、当时Mac v2 source/state缺席，原SSH通道Broken pipe。本人恢复认证后完成顶部完整部署与独立核查；早先外部访问阻塞已解除，不能据该历史段再次要求恢复连接或断言runtime缺席。

[显式清单冻结准备器](../tools/prepare_c5_formal20_freeze_v2.py)仅从干净已提交代码复制已跟踪Python与指定公开配置；不打包脏主工作区、认证、原始开发证据或任何语料。先重新核实已知339可读host字节、Mac依赖/tokenizer/age、远端环境/loader import/模型资产与pip原缺项，CUDA未初始化、模型未加载；旧D观察不冒充新的formal live baseline。新实际baseline只能在新精确批准后的zero-stage生成。

全部CPU/静态、源码双CI、独立部署/完整manifest与原始字节复核已完成；最新发布双CI后集中请求顶部两个完整哈希正式批准。本人接受本页范围、旧D批准或一般继续都不能代替它们。之后才提供本人私有终端命令，不读取实际20题。整体六项目标仍未完成；C4 NO-GO、v8 formal_quality_fail59/60、原80永久消费、R历史和默认混合保持不变。
