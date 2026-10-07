# C5 宿主保证开发 B：连续性通过，运输工程 FAIL/永久退休

所有者精确批准spec `bf09d927…4a50f7d` / runtime `241b72ba…539d7d` 后，源码`aab4a5f`、事前发布`eab34f4`双CI成功，B仅一次执行。见[结果与独立审计摘要](../eval/c5/hostassurance-development-result-20261007-b.json)。失败不改判，不重放、不把迟到回执当现场及时收到。不是LoRA质量NO-GO，也不是完整C5工程门PASS。

入口返回release、第一非command Idle单次seal真实成立。实际Command History外部seal `81ac6632…e42fa9`，head `af775b1c…461c45`，15份原始记录独立复算；5个实际hub/native请求均绑定正确成功checkpoint。有限可见连续性PASS，未出现A的临时主模块漂移。仍不证明opaque宿主代码字节、因果来源、连续无瞬变或完整handler absence。

首个`write-base`空夹具打开并捕获后，120秒远端回执窗口耗尽，驱动关闭/stop并终止后续槽。远端**实际消费1请求、1 generation claim、1 selector阶段**，生成1.744秒/12tokens，严格selector解析失败；无invocation、无LoRA生成、无任何工具派发。0并不是实际生成数。原Mac模型response不存在；八份明确远端原始文件只读回收并独立校验request/freeze/model/raw SHA，保留迟到结果，不修解析或追认运输成功。

原冻结代码在模型worker完成资产/依赖预检、加载和字节检查之前，就启动首请求deadline，没有ready握手。infer记录54.711秒（不含其初始guard），而加载/等待资源117.839秒；文件mtime显示首请求1791374804.067、worker预算开始1791374847.146、loaded-runtime1791374884.011、response1791374964.969。这些跨机mtime并非独立时钟同步/单调证明，只支持阶段混用诊断，不证明唯一原因。

空warmup和唯一模型夹具实际registry关闭，账本candidate_write/c5_read均0、无签名execute，九份临时key实际不存在；Idle/AssemblyLoad精确remove、hub stop、活动摘要不变、worker退出0、GPU11MiB/0%核实。整个工程门仍FAIL。A/B以及R历史源码/冻结/原始证据全部保留。

## 当前可继续准备，不是新运行许可

只用CPU合成验证有界startup-ready握手：模型/环境/源码/freeze身份及0消费绑定，driver等待ready后才发首请求/开模型夹具；独立startup≤180秒、每请求≤180秒（原120调整明确入新spec），未知仍永久阻断、不可重发。保持全部字节检查，不用缓存或白名单换速度、不修输出、不改数据/模型/阈值/默认路线。全新C ID/源/状态、完整freeze、双CI与新精确批准后才允许现场。

开发累计495.654412秒，剩余3104.345588秒（新cap向下取3104）。今日18:45苏黎世停止生成、19:00到期/至少900秒导出及正式3/研究4/原16 GPU-hours均不扩大；不自动续租。C真实工程门及独立审计通过之前，原20题公开承诺保持不变、正式执行仍封锁，正文/答案/密钥不读取。
