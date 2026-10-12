# 嵌入式启动修复与独立开发候选B准备

本人要求继续完成离线修复及新冻结准备。原A的[单次启动失败](c5-reuse-development-startup-failure-20261012.md)、批准、源根与退休记录均保留；本轮没有再次Run、恢复A、模型加载、native派发或私题读取。B仅为待另批完整spec/runtime的独立公开8槽候选，不能借用原A两哈希或“继续”作为现场执行批准。

修复了准入和宿主会话两处顶层`plugin`绝对导入，全部留在临时包内解析；不注入顶层别名、不修改嵌入式sys.path。入口在导入Rhino之前解析完整准入/hub/session/CLR adapter/deferred barrier及标准库依赖，并再次查源；该阶段失败只移除本次临时包，不创建registry、文档、订阅或回调。宿主作用开始后的失败仍保留未知状态，不做猜测清理或重试。

新回归在`-I -S -B`独立解释器中运行实际`run_path`包装器、模块图、SQLite准入与返回屏障；只有批准取得、Rhino类型和CLR观察使用明确CPU替身。解释器不存在顶层plugin/training，禁止模型包导入。包含首Idle不派发、command期间等待、缺批准、缺依赖、黏性失败、两处旧错误再现和macOS实际Python3.9完整启动共8项。不能将其表述为真实Rhino现场PASS。

B固定study `C5DEV-REUSE-20261012-B`、instance `reuse-dev-20261012-b`、两端源根/状态及spec/plan/runtime独立命名。每次入口检查绑定A原失败及退休的完整字节，要求A原名grant缺席且保存的批准未漂移。共用原全局准入命名空间；公共部署只接受已有表的稳定0行/原schema/无tombstone，不删除、迁移或新建命名空间绕过已消费角色。17项CPU控制拒绝复活、非空、schema/字节漂移、权限、别名及硬链接；原A spec/runtime批准不能绑定B。

本人保管工具`tools/run_c5_reuse_owner_custody.py`仅在实际精确批准后由本人私下交互运行。ready先在原source guard下核对实际部署/资产回执，再等待controller实际host/worker输出，显示具体锚并要求本人输入“确认并保管”，才O_EXCL发布ready。final要求本人粘贴Rhino终端实际终止回执并与原始输出绑定，再独立保管controller/native/lifecycle/export锚。29项CPU控制覆盖错scope/锚、重复/不完整日志、非TTY/假producer拒绝、实际资产回执绑定；工具不产生分数、模型/宿主操作、信号或原始联合审计PASS。交互记录仍是本人声明，非密码学人类来源证明。

全仓本地**1833 passed／11 skipped，316.39秒**；Python3.9语法及完整隔离启动通过，secret scan、发布一致性与diff检查通过。首次全仓13项失败暴露审计器残留A环境计划文件名；改为当前固定PLAN常量后68项相关及最终全仓通过，首次失败不追认成功。见[机器验证记录](../eval/c5/reuse-bootstrap-repair-preparation-validation-20261012.json)。源码发布双CI和随后完整冻结发布双CI均需各自精确head实际成功，不复用A的绿灯。

资源沿用本人已确认的有限23小时修订（开发5＋正式18，含加载/idle/停止/释放观测）；不增加开发预算或转移余量，不追认历史16小时合规、平台余额或新续租。原模型/契约/顺序/TTL/180秒请求/120秒native ACK/60秒settlement/无parser repair不变。B完整材料须明确披露A未开始任何模型/native槽、记录计数0与独立物理生成总量null，并等待本人新完整两哈希批准。正式40槽及原20题消费仍依赖B完整工程门和另一份正式冻结/批准；原C5 NO-GO与默认混合不变。
