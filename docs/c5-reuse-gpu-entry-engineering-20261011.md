# 新开发 GPU 入口、已有 SSH 接线与独立原始审计

本交付依赖 #12 的 `c02f82ab29623f93efd67030155aba268a54cf77`，包含此前本地入口准备 `b99c5af`。这是**当前第1项的源码子交付**，六项主线仍未完成；main 没有包含这些 Draft 分支。实际新 spec/runtime/environment plan、部署根、批准记录、研究状态或运行尚未创建。

## 已实现的接线

- `tools/run_c5_reuse_gpu_entry.py` 只接受固定新开发源根及 `--serve`/`--stop`。仓库 checkout、旧源根、缺失完整冻结或旧批准在任何状态写入、模型导入、stdin、fork、信号前拒绝。
- 全局 worker 准入先于启动；Linux supervisor 在单线程且未导入 torch 时 fork 一个自身子进程。子进程必须等待门管道；父进程以 pidfd 和 PID/UID/boot/start-ticks/解释器/argv/cwd/亲子关系核实，持久化加载前资格后才放行。独立停止从这份原始资格重新核实，不伪称当前重新取得“加载前”资格。
- 新源根的原公共 config、固定14基座文件及两 adapter、当前专用环境/UUID在加载前及加载后检查，后者完成后才发布ready。懒加载保持原 tokenizer、seed、NF4/BF16、原 `prepare_model_for_kbit_training`、同一 PEFT base `disable_adapter`、checkpoint-132 和原两阶段 generation/parser，不训练、不修复输出、不读任何 split/正式题。
- watchdog 独立覆盖启动/空闲及整个模型请求，selector/invoker之间不得重置180秒完整请求期限，最多112阶段和固定8个请求；新开发墙钟预约包含加载和等待，并预留60秒停止余量。SIGTERM最多一次、pidfd精确子进程、最多30秒退出等待；没有名字搜杀、SIGKILL、重连或重试。退出和资源观察即便停止失败也尽量持久化；未知或超预约不得认定完成。退出观察不能代替真实 GPU 释放检查。
- worker 使用固定公开八槽顺序，开始前要求匹配外部 readiness 记录；半帧、EOF、重复/额外帧、错误顺序拒绝，不补槽。完成八槽后仍须显式 close，模型原始 journal 与加载/ready/close/lifetime control journal 分开保留。
- SSH 接线只复用 `/private/tmp/c5-reuse-24151.control`，固定175.155.64.171:24151、已核实 known-host pin、SSH二进制、配置及新入口。`ControlMaster=no` 加 `ProxyCommand=/usr/bin/false` 阻止共享连接丢失后的自动新连接。Mac controller 的准入先于 SSH 启动；传递外部 ready、close和独立stop均不把匹配记录当人工来源证明。
- 独立入口审计不 import launcher/loader/generator；重算冻结 plan 字节、来源/停止策略、原始生成语义、加载资格、固定八槽顺序、close/head对应、退出及完整墙钟。`complete_eight_slot_entry_records` 仅表示这些记录闭合；返回的 `whole_field_pass=false`、人工来源未验证、真实 GPU 释放未知及 native/geometry/cleanup未验证均保留。

同一 journal 的第二个 peer/controller即使在首个请求之前也被拒绝，避免各自新的 spent 集合重复生成/发送。原字段 `remaining_gpu_seconds` 在新环境 plan 中强制解释为**研究预约，非平台余额**；[本人澄清](../eval/c5/reuse-platform-resource-owner-clarification-20261011.json)说明平台没有小时额度，不再要求其提供不存在的余额。原16小时累计边界未自动扩大；历史保守上界尚未核实，不填成0或沿用旧计数。

## 验证范围

入口/懒加载/独立审计/原入口guards的最终CPU控制及2项Linux专属自身CPU子进程资格/退出/一次SIGTERM控制，以[本次验证记录](../eval/c5/reuse-gpu-entry-cpu-validation-20261011.json)实际结果为准；Linux控制在Mac跳过，由发布CI核实。生成、field transport、原签名许可/native交接的联合回归另行通过。Python3.9的Rhino侧scope纯导入通过，未导入training。精确发布head双CI以PR实际状态为准，不能凭计划填写成功。

所有模型/八槽/raw审计正负控均是公开CPU夹具，包含合法但错误的几何输出，验证保留失败而非修复。重新哈希的亲子关系、加载前声明、无intent信号、墙钟预约、布尔计数、训练开关、close/head、外部ready和冻结plan篡改均拒绝；缺close只能得到不完整结果。实际 Mac/GPU研究入口、模型加载/生成、Rhino脚本/订阅/warmup/几何、私题或正式claim均为0。CI仅对新CPU子进程的真实信号测试不计作实际GPU现场信号。

## 第1项仍未闭合的内容

新 Rhino hub/ScriptEditor/deferred-baseline 完整入口、实际控制器的native调用/夹具/settlement/SQLite备份/退出清理、外部ready/final保管流程，以及覆盖整个八槽工程门的独立原始联合审计仍须实现。当前GPU入口和SSH helper不代替这些组成部分，也不能把旧D入口的冻结、实例或资格移植过来。

这些源码完成后，须重新核实新宿主实际PID/接受范围、两端当前完整可读环境/模型/source及资源事实，形成可审阅完整spec/runtime，独立逐字节复核与双CI。本人本轮概括“持续推进、均可通过和批准”支持继续源码交付，尚未指向未生成的完整两哈希；不得创建虚构精确批准记录或据此开始现场。后续保持开发单次现场独立PASS→正式40槽另一次完整冻结/批准→本人私下单次原20题消费/审计→披露式追加报告的顺序，原C5 NO-GO和默认路线不改，不自动merge。
