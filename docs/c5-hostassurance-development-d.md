# 独立D工程门：完整验收时序与结算证明，仅准备／未运行

2026-10-07本人明确“授权仅准备新工程门D，不运行”，见[准备授权记录](../eval/c5/hostassurance-d-preparation-owner-authorization-20261007.json)。新ID `C5DEV-HOSTASSURANCE-20261007-D`，独立源码/状态目录；旧A/B/C、收尾与原80均退休，不重放、改判或复用批准。D失败或未知则退休，**不自动E**；正式20题和PR merge另取授权。

## 为什么不是只延长超时

[C时序复盘](c5-retired-c-lifecycle-timing-diagnosis.md)保留原25秒失败及不确定因果。D新增的是完整接收/解码/验收及后端发布完成证明：

| 边界 | D实现与固定预算 | 失败语义 |
| --- | --- | --- |
| worker启动 | 原显式零消费ready保留，180秒涵盖完整ready解码/身份验收；另存startup-time | 错误/超时永久阻断，不发任务 |
| 模型请求 | 同一原始单次frame；180秒涵盖完整metadata验收，不把观察投影替代原frame；另存model-time | 不重发、不修输出、不继续槽 |
| 原生调用/控制 | 120秒在client guard之前开始，必须同时收到response及绑定request/response/freeze的service-time；解码、证明验收和完成后都检查期限 | 缺失/迟到/不一致永久unresolved，不猜测关闭 |
| 结算 | 新60秒逻辑窗口对每次完整来源检查、捕获和发布的前后检查；仍三个稳定采样、仅一次原execute；另存settle-time | 保存原execute/账本；后写出的done若没有有效结算/完成证明仍不可消费 |

新增[纯时钟](../plugin/rhino_listener/c5_lifecycle_deadlines.py)、[D专用bridge/hub](../plugin/rhino_listener/c5_hostassurance_lifecycle_hub_d.py)、[完整模型验收](../training/c5_lifecycle_model_transport.py)和[独立时序/原始库存审计](../training/c5_lifecycle_joint_audit.py)。轮询仍检查期限但不无限扩大journal；回调前后时间/事件有限。只采用逻辑期限，**不保证抢占阻塞CLR/磁盘或CUDA调用**。端到端callback不确定时保留实际owner/原始证据，不能以超时重发。

120/60是需另行精确批准的新操作性参数，不修改原C25/15或质量阈值。来源/已加载import/339可读宿主字节及可见checkpoint照常完整检查，不缓存或按名字放行；保留旧C可读目录并增列新D目录，不将已能读的C来源故意降为unknown。没有新增canary；原V2的整个opaque宿主信任与可见checkpoint保证不增强或改称全代码字节/因果/无瞬变/完整handler absence。

## 固定实验面与资源

[D spec](../eval/c5/hostassurance-development-spec-20261007-d.json)复用已被本人排除的四个train家族，原文本/8交叉槽/基座revision/checkpoint132/提示词/chat template/单工具schema/严格解析/2048 token完全不变；最多8请求/16生成阶段、2写2读、1空warmup＋8独立headless毫米夹具。没有新语义家族，不要求重读或重发正式20题承诺。主default、训练和模型权重不动。

[v6](../eval/c5/rhino-resource-boundary-v6-20261007.json)：2026-10-08 22:00苏黎世到期，最迟21:45停止生成并留900秒导出；D≤2470秒（向下取整剩余2470.987806），开发累计原1小时、正式3/研究4/原16 GPU-hours上限不变。原累计保守prior8329.012194秒，最终执行前重新核对实际用量/GPU。未来续约承诺不自动更改此次冻结日期或预算。

120/60窗口不能被相加解释为无限运行授权：总体预算/截止仍独立强制检查。历史耗时不能证明D八槽必能完成；任一timeout/未知都按失败封存，不补槽。pip缺失非加载launcher `pip:../../../bin/pip3.13`显式保留，不安装、伪造字节或归为唯一失败因果。

## 当前合成验证和独立准备审核

新增40项CPU控制、与旧startup/session/C相关95项控制及全仓956 passed/8 skipped通过；Python3.9 AST、secret、版本/diff通过。覆盖新scope/旧grant/准备批准不能执行、整数布尔及资源扩权拒绝、昂贵来源检查跨15秒而在新60秒内的三稳定采样、单次写/真实SQLite/关闭删钥、后发布超时不能消费done、缺失peer proof阻断且零重发、原生完整解码过期，以及真实CPU子进程启动/原始frame完整验收和模型/启动完整验收过期阻断。

CPU子进程回归在冻结前发现把validate_response返回的观察投影替换原frame的兼容错误，已修正为校验但保留原frame，测试核对完整frame和SHA。这不是现场失败或输出解析修复。实际GPU/Rhino/新夹具/订阅/holdout调用均0；合成几何后端不能代替真实Rhino。

独立审计不导入生产者时钟，从原始service/client/settle/model/startup sidecar重建固定角色/序号/freeze/request/response、完整种类与数量、单调有限事件、结束期限、零抢占/执行成功强声明。之后仍须原完整模型→许可→原生几何→账本→关闭删钥及外部host seal/所有请求checkpoint审计；只通过时序或部分槽不得promote工程门。

CPU preflight四家族原文校核/同tokenizer全部假设单工具渲染为1767/2048 token，Mac实际3552外部文件记录；旧基座/adapter只读身份已核实。完整新D已加载依赖/GPU环境和源码部署冻结还要形成实际材料，不能借9cf0ec8/旧C的CI或字节列表声称当前已通过。

## 冻结与必要精确批准

先提交当前完整源码/测试与spec，再由[显式清单部署/冻结准备器](../tools/prepare_c5_hostassurance_development_freeze_d.py)只复制已跟踪Python代码及指定公开配置，排除脏主工作区、认证、原始证据和所有task/cipher/key语料。新的Mac/Linux source路径必须不存在；不建D运行state、owner grant、ephemeral keys、订阅、fixture或模型。只读GPU资产与loader import（CUDA未初始化）复核并冻结，继承源码/可读宿主原始字节引用；未知部署回执先只读核查，不重复上传覆盖。

完整manifest与独立准备复核、最新发布双CI之后，集中提交新的spec/runtime两个完整规范化SHA-256给本人。本人未精确批准前不得执行prepare/ScriptEditor入口/drive/serve。spec或manifest的execution_ready仅表示冻结材料，不代表人类运行批准；本次准备授权不生成owner-approval.json。

工程门须八槽全部原始联合审计、至少一笔模型导出的合法写和一笔读、关键安全错误/额外或重复派发/未核实清理0、有限host连续性通过；开发语义仍逐槽如实报告，不强迫基座或LoRA成功。通过才继续已登记20题正式冻结/另获精确批准/本人终端唯一40槽私有运行和审计。C5-7仍未裁决，GO不切默认混合，C4 NO-GO和v8 formal_quality_fail59/60永久保留。
