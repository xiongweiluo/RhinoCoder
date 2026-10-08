# 正式20题资源续接 v4（未启动研究，协议仍v2）

> 当前优先：[完整冻结与独立复核已完成](#完整冻结与独立复核已完成)。中断的未知写入经只读确认缺席后，从确定边界补齐公共元数据，两地355文件及完整环境模型独立重哈希通过。待最新发布双CI和新两哈希批准；未创建v4 grant或运行。

2026-10-08。本人直接确认服务商到期为**2026-10-09 22:00 Europe/Zurich（UTC+2）**。这是本人报告，不冒称已独立核验服务商计费。原v3精确批准已收到，但在任何admission前错过16:39启动窗口，见[停止证据](../eval/c5/formal20-v3-pre-admission-window-stop-20261008.json)；两地旧grant可恢复封存，claim/key/模型/Rhino/私有消费均0。不要运行旧v2/v3包装，不再次请求20题/原80/密钥或重新封存。

## 仅续接资源和明确部署身份

- [v8资源边界](../eval/c5/rhino-resource-boundary-v8-formal20-20261008.json)：10月9日21:45停止生成、22:00到期、900秒导出，最晚当天16:39本人入口（五小时加360秒zero-stage余量）。
- [spec-v4](../eval/c5/rhino-formal20-spec-v4.json)改为独立Mac/Linux source-v4/state-v4；同一未消费`c5-rhino-paired-20-v1`，field protocol v2、原公开承诺/家族根/40槽顺序不变。v3冻结/批准/停止及原宿主和R历史证据不覆盖。
- 模型revision/checkpoint132、契约/12工具、最大56请求/112阶段、评分/≥14/20/净胜≥3/安全及重复写/未核实清理0、normal2048/cleanup256/journal4096、三稳定60秒、原生120/模型startup180、有限宿主保证全部不变；不补槽、修解析、重试或切默认路线。
- 正式18000/研究21600/开发3600/原累计57600秒均不变，prior原9607.228115136008/研究2407.228115136008不增加。容量提案81b799b1仍保留历史参数来源，新日期由本次本人确认及未来新两哈希批准绑定；不把旧日期的精确批准默认为新运行授权。
- 新冻结仍须源码和发布双CI、两地完整字节/依赖/模型重哈希、实际部署公开预检，再新spec/runtime两个精确哈希。当前只是准备，v4 state/grant/模型/夹具/订阅/私有消费均0。本人仍唯一reviewer_1/独立保管人，私下TTY运行与审计隔离不变。

## 公共准备传输回归

[准备器](../tools/prepare_c5_formal20_freeze_v2.py)以精确长度+SHA校验+O_EXCL/NOFOLLOW新文件+回执替代等待SSH stdin EOF的tee。v3续接已使用并独立核对同类传输；这里将其归入可审代码，不修改模型/native协议或任何现场超时。未知结果仍先只读核对，不能重传或覆盖。

[七项新CPU控制](../eval/test_c5_formal20_resource_renewal_preparation.py)验证保持所有契约/预算字段、新资源文件确实进入部署、ACK不等待EOF、尺寸/截断/错误哈希拒绝、已有或符号链接文件不覆盖、发送器要求精确回执。与部署依赖/冻结/owner控制合计26 passed。全仓/双CI与完整实际冻结继续执行，不把CPU正控当现场结果。

## 2026-10-08中断后的实际准备状态

源码`67f131d`双CI37796706531/37796722763成功，本地全仓1033 passed/8 skipped、push CI1032 passed/9 skipped分别保留。[runtime-v4](../eval/c5/rhino-formal20-runtime-freeze-v4.json)已形成，但不是远端部署完成证明或新运行授权，见[准备状态证据](../eval/c5/formal20-v4-preparation-status-20261008.json)。

首次准备器在最后SSH公共runtime写入回执处30秒超时并退出1；不能写成退出0或断言远端未写。中断后固定认证socket已缺席、BatchMode无法认证，远端最后文件/人口/依赖独立复核未完成。精确长度CPU正控只证明接收器无需EOF，不保证网络成功，也不能据此断言超时唯一原因。没有重跑准备器/重传、覆盖或任何正式模型/Rhino/私题操作。

本地独立复核355 Git/Mac文件、3552 Mac外部、339已知可读host、6 tokenizer/age通过，实际部署Mac公开承诺预检通过；远端builder preflight和loader import已返回并进入冻结，CUDA未初始化/模型未加载，但独立远端复核仍待连接，不把两者混为一项。恢复SSH后首先只读检查同一v4的未知结果，不自动恢复/重放正式研究。

spec规范化SHA为`1ce7dba2a75a853a6a2b8d81027235c442586f30718f05dc177f64a04b002fa7`，本地runtime规范化SHA为`9f72a0491b49bbb5f21dd83e6c87bb16530218a375593e0308e69caee134f1a3`；**当前不请求或登记正式批准**，待远端完整独立核查和最新发布双CI成功再集中给这份（或经实际必要修正后唯一有效的）完整冻结。旧v3批准不复用，新state/grant未创建。私有资料仍只由本人TTY处理。

## 完整冻结与独立复核已完成

上述“远端未知/待认证”为恢复前历史，原[中断状态](../eval/c5/formal20-v4-preparation-status-20261008.json)保留。[最终独立预执行核查](../eval/c5/formal20-v4-preexecution-validation-20261008.json)记录恢复后354文件均正确、唯一runtime未创建、原接收器已停止；从该确定缺席边界用同一冻结接收器/O_EXCL补齐一次公共文件，180秒为准备传输观察边界，不改任何正式native/model/startup/GPU期限。取得670517字节/SHA回执后，独立重核两地355完整文件。原准备器退出1不改为0，没有重跑整个准备器、覆盖原文件、传送私有资料或消耗新题。

完整Mac3552/已知host339/tokenizer6/age、Linux分发21614/标准库960/libpython/解释器、基座14和adapter2独立重哈希通过；Linux环境536eac7d及原pip metadata缺项保留，独立检查未import torch，loader未初始化CUDA/模型。完整authority/budget只用未持久化的合成grant做CPU形状核验，不生成真实执行批准。两地state/grant/模型/Rhino/私有消费仍0。延长公共准备传输观察取得回执，不证明原超时唯一原因或未来五小时连接稳定。

当前只待最新发布双CI，再集中请求上述唯一spec/runtime两个完整哈希；旧v3批准不复用。本人应先准备唯一source-v4四行包装，但不Run；新精确批准后才本人TTY，看到zero-stage WAIT再单次Rhino arm。原20题承诺和封存不重发、不重做，正式最多五小时及10月9日16:39最晚入口/21:45停止/22:00到期不变。

下一步在这些准备项完成后集中给本人新两哈希；旧批准不能复用。无需新的开发研究/工程门、观察器扩展或E，不因续租直接消费正式20题、付款或合并PR。C5-7仍待实际完整证据；C4 NO-GO、v8 formal_quality_fail59/60、默认混合不变。
