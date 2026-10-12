# 独立开发候选B完整冻结与精确批准入口

B是A单次启动失败后的独立公开8槽开发候选。A的原批准、冻结、源根、失败和退休保持；B每次入口验证A退休字节，使用原全局准入表，不恢复A或复用其批准。本文及材料不授予现场执行、正式消费或PR merge；只有本人直接批准下表两个完整哈希后才可启动B一次。

| 完整材料 | canonical SHA-256 |
| --- | --- |
| [B development spec](../eval/c5/reuse-development-spec-20261012-b.json) | `cdd2571e63f040fd145b56d6b322fb7914c0d63816b53eca762001f632131488` |
| [B complete runtime freeze](../eval/c5/reuse-development-runtime-freeze-20261012-b.json) | `8b2243663e571113b8912174835fe0adde169ac451706f2829af7299fcbee1b4` |

哈希是整个JSON按sort_keys、紧凑separators、ensure_ascii=true、allow_nan=false规范化的字节。原始文件SHA、全部305清单文件及模型/环境/宿主/资源/前序关系由runtime与[完整environment plan](../eval/c5/reuse-field-environment-plan-20261012-b.json)绑定。新spec/runtime material-ready字段不是本人批准或现场PASS；独立审阅与执行记录始终区分。

## 修复及原失败保留

[嵌入式修复](c5-reuse-embedded-bootstrap-repair-20261012.md)修复准入和宿主会话绝对导入，完整惰性依赖在导入Rhino之前解析/查源。不得注入全局plugin别名或修改嵌入式sys.path。8个独立解释器实际run_path回归含Python3.9、两处旧错再现、返回/首Idle及失败停止；17个前序/共享表控制、29个本人保管控制。CPU通过不能证明真实CLR/Rhino或模型/几何质量。

A原recorded model requests/slots started/completed为0，独立物理生成总量仍null。B plan按SHA钉住A原失败和两端退休记录；A原名grant若恢复或记录漂移即拒绝。Mac原全局准入表只读完整性/schema/稳定0行核查，原lock/db保留；任何tombstone/非空/未知/别名都阻断公共部署，没有清空或改换准入命名空间。GPU原表未存在。A准备密钥仍私下保留，不声称全宿主清理或内存擦除。

## 实际完整材料

两端B源根分别为`/Users/xiongweiluo/RhinoCoder/data/training/c5/reuse-dev-20261012-b-source`和`/data/reuse-dev-20261012-b-source`；同一305个清单文件＋runtime，各306个公共文件，payload 3,311,921字节。完整可读副本在`/private/tmp/rhinocoder-c5-reuse-development-b-freeze-20261012`。实际部署/逐文件人口/闭包及资产的完成证据以[独立核查记录](../eval/c5/reuse-development-complete-preexecution-validation-20261012-b.json)为准，不能用准备器自报替代独立核实。

原GPU基座14/adapter2、非缓存分发21614/stdlib960/两libpython、驱动/解释器/原GPU UUID与boot及UID1000保留。Mac宿主339/controller3552/tokenizer6匹配原模型资产。Rhino为已接受PID44652/UID501/UTC启动2026-10-11T16:14:32Z与boot-session UUID F873EC8A-960B-4B86-B35E-65A973D84E99。B接受依据是此前本人三项确认与当前相同进程的只读重核，不制造新的本人声明。真正入口仍在warmup/订阅之前要求主线程和空白；未来实际基线尚未封存。

保证范围仍为可读文件冻结＋opaque宿主信任＋有限可见检查点，不保证全部执行字节闭包、隐藏handler缺席、检查点间无瞬变、密码学人类/物理来源或内存擦除。原pip metadata缺项与缓存字节码观察保留，不归零历史用量。

## 资源及门

沿用本人已确认的额外23小时有限修订：开发5小时、正式18小时，含加载/idle/停止/保守释放观察，开发余量不转给正式。历史累计未知，原16小时合规不追认；不是平台余额，没有新续租/付款。实际租期2026-10-13 20:00 Europe/Zurich（UTC+2）、19:45生成截止、900秒导出。完整5小时准入最迟10月13日14:45；正式18小时及两阶段等待须另行符合实际租期，不能静默截短或增加预算。

B只允许原固定公开8槽单次，原模型/契约/顺序/TTL/180秒模型请求/120秒native ACK/60秒settlement/无parser repair不改。未知永久退休，不重发、不补槽、不重试；预算到界按冻结策略停止和如实报告，不保证强抢占、物理释放或完整完成。B工程门要求全部8槽完整原始联合审计、至少一笔模型导出的合法写和读、关键违规/重复派发/未核实清理0及有限连续性通过；质量分槽披露，不强制八槽全对、不降低正式14/20、净胜3、安全0门。

## 本人保管与批准后唯一操作顺序

本人新两哈希批准→独立字节/宿主/余量复核→B两端一次登记批准→Mac一次prepare→本人先在私下交互终端启动保管工具ready→代理核对并只Run一次B冻结wrapper→controller一次drive并私有记录stdout→本人实时ready确认→八槽/退出/清理/qualified target释放观察/导出→本人实际Rhino终止回执及final custody→原始联合审计。ready等待仅120秒，保管终端必须先就绪，代理不能代签确认。

ready命令（仅在批准、prepare和独立实际部署回执齐全后由本人运行）：

```sh
/opt/anaconda3/bin/python3.13 -I -B /Users/xiongweiluo/RhinoCoder/data/training/c5/reuse-dev-20261012-b-source/tools/run_c5_reuse_owner_custody.py --ready
```

controller stdout必须在本次state的`controller-output.log`以O_EXCL/0600创建，不覆盖旧日志。工具等待实际`C5_REUSE_EXTERNAL_READINESS_REQUIRED`完整一行，显示host/worker锚并要求本人输入“确认并保管”；代理不执行该交互或创建ready/final声明。controller结束后本人使用同一工具`--final`，粘贴Rhino实际`C5_HOST_CONTINUITY_EXTERNAL_RECEIPT`完整一行并确认保管。该步骤只绑定外部声明，不自证原始联合审计或质量PASS。

本人在私下入口执行独立原始审计：

```sh
/opt/anaconda3/bin/python3.13 -I -B /Users/xiongweiluo/RhinoCoder/data/training/c5/reuse-dev-20261012-b-source/tools/audit_c5_reuse_field_eight.py
```

B失败/未知/证据不足不自动再生成候选或改后重跑。只有B完整工程门PASS，才准备另外的正式40槽完整冻结与另一份两哈希批准；原20题仅由本人私下消费和审计，代理只接收脱敏摘要。原C5 NO-GO与原正式失败保留，不自动切产品/默认路线或merge。

## 本次验证

源码`31f7cf5649e9a92ffaa50f890e9c304836fc3b97` push38191591974／PR38191594635双CI均SUCCESS，各Linux1834 passed／10 skipped，浏览器端到端与secret/release检查通过。本地1833 passed／11 skipped；两端实际公共部署与305逐文件/精确人口/闭包、部署后完整原资产及宿主/退休/空表复核均通过。本文完整发布head的双CI以PR当前实际结果为准；本记录是发布前证据，不追认尚未观察的新head绿灯。
