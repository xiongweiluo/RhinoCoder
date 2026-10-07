# C5 新保证下的独立开发工程门 A（2026-10-07）

这是六项持续交付的第2项，**未运行、未完成实际冻结、未获精确运行批准**。第1项 C5OBS A 已单次消费、独立能力审计通过并退休，不重放。所有者已接受[较弱保证 spec](../eval/c5/host-assurance-transition-spec-v2-20261006.json)及[单独决定记录](../eval/c5/host-assurance-transition-owner-approval-v2-20261006.json)；这不是当前开发运行授权。

## 固定独立范围

新 ID `C5DEV-HOSTASSURANCE-20261007-A`，详见[待冻结 spec](../eval/c5/hostassurance-development-spec-20261007-a.json)。新的 Mac/GPU 源码和永久状态根；不借用 B/native12/R/观察器或原80的授权、状态、claim 或输出，不改权重、契约、阈值或默认路线。

八槽来自四个**已经冻结并由保管人排除的训练家族**，完全复用原文本：圆柱半径7/高17、只读场景摘要、缺参布尔澄清、删除审计失败记录的拒绝。train 原文件 SHA `69cdcfbf…7b192a` 与家族/selector文本均在 CPU 预检核对；不是额外生成语义家族，不读原80/新20题。slot交叉顺序与两路模型相同，最多8请求/16阶段；每槽最多1写或1读，其余0许可。

工程门是运输/控制器/来源与生命周期门，不以基座八槽语义成功率选模型或调提示。必须全八槽原始证据完整、至少一次模型来源写入和一次只读、原始双阶段可复算、无 repair，关键安全/额外或重复写入/未核实清理0；还必须通过新的有限宿主连续性原始审计。开发失败不补题、不重跑或追认成功。

## 实际宿主准备与预热必须进入新的运行批准

所有者接受的是当前空白实例研究独占窗口，不是clean新进程或第三方插件无害证明。新入口以空命名空间装载冻结项目模块，保留旧插件/程序集/脚本记录；先核对新grant、spec/runtime、339既知文件和当前空白主线程文档，再永久claim。没有该新grant，不能建立状态、密钥、hook或夹具。

一次声明的预热包括 stdlib/控制器/观察器导入、列出的15份Rhino/System类型引用，以及**仅一个空 headless 毫米夹具**的读回和 registry-verified close。没有原生tool dispatch、对象写入、模型生成、kernel图形创建或另一个native12序列；记录actual关闭与活动内容。真实hub delegate在baseline seal前附加，随后一次 AssemblyLoad订阅，保留原始基线/全部checkpoint并封存。八个模型槽另用八份独立夹具，总数最多9。

预热未证明所有晚绑定路径已经加载。seal后遇到任何新/变化的可见模块、程序集、native映像、丢失/异常事件或活动文档漂移都fail closed；不能为了继续而追加白名单/重封基线。失败或未知opening/ack/cleanup留住实际owner引用、原始claim和证据，需另行精确批准人工reconcile，而不是自动重复现场操作。

## 明确弱保证和清理边界

[会话执行层](../plugin/rhino_listener/c5_host_assurance_session.py)和[独立审计](../training/c5_host_assurance_audit.py)绑定新的两个精确哈希及已经接受的transition，而不把transition当执行许可。每checkpoint保存raw snapshot＋两次drain的事件/丢失/异常数据、source digest、forward hash chain；上限512 checkpoint/1040单记录（每条≤1MiB，最大约1GiB），不包含任务/答案/密钥。外部终端receipt SHA必须独立捕获，audit不能临时从seal捏造所谓外部锚。

dispatch guard漂移后sticky阻断；cleanup guard只允许原持有夹具的有效HMAC close/stop及精确delegate remove，不接受新的execute/capture。即使清理成功，原失败仍使整个host审计失败。源码/可读host文件漂移时不执行不可信清理代码，保留证据请求人工决策。独立审计还核对模型原始prompt/output、许可、scene、SQLite账本、几何、warmup和关闭/删钥/Idle解除；不是只检查producer的PASS字段。

AssemblyLoad解除只证明针对精确delegate的remove调用完成与观察到的队列静默；没有新的canary刺激，不声称完整handler absence或完整事件覆盖。这与已接受的有限保证一起显式进入运行spec。opaque宿主整体可信、操作独占为人为假设，不能证明发射字节/因果来源/两快照之间无瞬变；`legacy_byte_closure_verified=false`永久保留。原完整字节守卫和默认/正式入口尚未放宽或切换。

## 资源、依赖和批准准备

2026-10-07 只读GPU：RTX3090/24576MiB，11MiB、0%，driver550.107.02，恢复认证端口22159及旧pin；未加载模型。新Mac tokenizer的纯CPU最大input＋reserve为1767/2048、3552外部文件；实际完整依赖/模型文件在独立部署后重新核对，不能以版本字符串或旧B清单代替新freeze。

pip26.2.1仍有唯一缺失、不可加载的`../../../bin/pip3.13` RECORD项，Python3.11和实际pip/pip3文件可核对；新spec/runtime明确保留此异常，不安装/升级、不假造字节，也不据此声称pip缺项导致了历史失败。

当前有效租期由本人报告至 **2026-10-07 19:00 Europe/Zurich（UTC+2）**，最迟18:45停止生成、至少900秒导出；服务商到期时间未被独立核实。原A+B含加载/空闲340.027秒，剩余开发上限向下取整3259秒；正式≤10800、研究≤14400、原累计≤57600秒不扩张。执行前重新核对全部已用结算；预算/到期不足时不启动、不自动续租。

必须完成全仓CPU/合成测试、精确源码与Mac/GPU环境/模型/339可读文件/配置清单、独立部署的只读preflight、双CI，再集中向本人请求**新的spec和runtime两个规范化SHA**。spec已整理为可做完整freeze的`execution_ready=true`，**只是准备标志，不是实际runtime冻结或运行授权**；没有runtime文件/直接新grant仍拒绝，也不创建本次run。通过新的单次现场门和独立审计后，才绑定已登记公开承诺冻结正式20题并另取两个哈希批准；不重新索要承诺，不读取正文。

每份原始hub/native请求另绑定其调用前的host checkpoint序号与链摘要；独立审计同时要求完整request/check人口、请求SHA与正确dispatch/cleanup检查类型对应，不能以一次开场snapshot代替所有后续检查。
