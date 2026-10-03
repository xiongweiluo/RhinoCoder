# C5 十二工具原生开发控制：事前冻结与单次实际结果

2026-10-03。`C5DEV-NATIVE12-20261003-A` 已在事前双CI通过、所有者对下列两个精确哈希直接批准后单次执行，并通过只读独立审计。**这是已消费的原生开发控制，不是正式20题、模型质量评测或整体C5 GO；禁止重跑。** 它与已经消费的 R B 不同，没有继承 B 的授权。[公开审计](../eval/c5/native12-development-audit-20261003.json)保留实际结论和私有原始证据的哈希。

[固定 spec](../eval/c5/native12-development-spec-20261003.json)限定新的独立、未保存 headless 毫米夹具，实际活动空白文档永不作为目标。固定全12工具每种一次：盒体/球/圆柱、位移/90度旋转/非均匀缩放、图层/RGB/分组、bbox/场景只读、圆柱减球 Boolean。最多十笔**有签名的变更请求**与两笔只读；group/Boolean 内可有多个原生对象改动，不伪装成仅十次底层对象变更。

十二步后只发送一份事前声明的无效 HMAC 负控。它必须在预留/派发前拒绝，返回冻结的 `handoff signature rejected`，使 Idle 桥阻断后续执行；仅允许随后签名关闭与 stop。stop 的 `had_failure=true` 必须保留，不能改写为无失败。审计同时检查无第十一行变更账本、无额外原始 execute 回执、关闭前完整几何仍等于第十二步终态。此计划内负控不是忽略真实失败：任何其它错误、缺失回执或错误拒绝原因都保持原 probe 失败并退休。

## 运行与审计边界

- 三道固定状态根永久屏障：admission、engine-started、driver-started；崩溃、换输出目录或重新启动客户端都不能重跑。状态根固定为 spec 所列本地私有路径，不接受 CLI 替换。
- [Mac 客户端](../tools/c5_native12_client.py)只提供 `prepare / drive / audit`。prepare 必须先取得新的实际所有者批准，生成私有600签名密钥；驱动最多40消息、300秒，每条最多25秒等待，不对未知回执重发或猜测清理。
- [Rhino ScriptEditor 入口](../tools/c5_rhino_native12_batch.py)使用新的私有模块包，核对完整源字节/实际 import、同一 spec/冻结/批准；engine claim 先于打开夹具。任何部分打开错误保留原始 fixture identity/私有记录供人工对账，不重复创建。
- Native 每步保留立即执行、SQLite 预留/结果及至少三个稳定 Idle 读回；没有下一次模型调用、参数修改或几何重试。未知、超时或不确定状态只能按已知安全关闭边界交接，不能宣称清理通过。
- 关闭回调前后活动内容哈希、实际 fixture registry 消失、关闭前完整 fixture 读回、精确密钥文件消失和 stop/unhook 都须原始交叉核对。密钥不归档、不输出；原 R 证据不清理。
- 独立审计核对所有27请求、原始/稳定回执、十行 done/两行 read/十份 consumed/四十事件/十二份 native-control 交接、每步几何/属性/非目标不变以及关闭。只读结果也按实际 bbox/语义场景评分，不能以“成功”布尔值替代。
- 几何断言事前固定：最终盒体 `[-64,33,68] → [-26,84,160]`、体积178296、6面、指定图层/RGB/组；圆柱减球体积 `67π/3`、bbox `[-3,-3,4] → [3,3,7]`、闭合3面，最终仅两个对象且组仅含盒体。中间三个实体与全部变换/属性步骤另有独立数学断言。

运行源码先提交，随后记录该不可变 revision 的完整 Python/固定 schema/spec 清单与 SHA-256；预执行文档/冻结提交的 CI 必须通过。**只有直接人类批准精确 spec 和 runtime freeze 两个哈希后，才可生成批准台账并启动。** 本文不是该批准，代理不代签。

事前源码已固定在 `3106ea461850775b64253ba2c938ff808f677e57`，完整203文件（201 Python及固定schema/spec）清单见[运行冻结](../eval/c5/native12-runtime-freeze-20261003.json)，inventory SHA-256 `29afc13e5ca121906ea80b511134b680c230429b1371a98aea072a62ac977916`。spec canonical SHA-256 `412091578b788a364397a0ac8165f8eaad9e4bfd60dea1431fa902c4b2185a3e`；runtime freeze canonical SHA-256 `8ea7df13c412df749f01aa162415f42e5e5c4cd9b46b4ca8bfb7d0d6540363aa`。Rhino8/内嵌Python3.9运行族被校验，实际build/version写入原始engine记录；这不是完整C5模型/依赖环境冻结。完整本地回归474 passed/8 skipped，release/secret/diff通过。原事前准备状态确实未生成批准文件/claim/密钥/夹具；随后预执行提交 `e5524f4955dd9b3f2a56041be0cbfb8d71a41a6c` 双CI分别在14:02:42Z/14:03:06Z通过，才取得新的直接人类批准并执行，没有事后改动 spec、断言或源码。

## 2026-10-03 单次实际执行与封存

所有者的实际回复为“以 repository_owner 身份批准上述 spec 和 runtime freeze 的单次原生开发控制”。据此登记精确批准台账及三道永久 claim，仅调用一次 prepare、一次官方 ScriptEditor 入口、一次 drive；只读 audit 不重新派发。实际 Rhino `8.21.25188.17002` / Python `3.9.10`，全12工具每步原始立即回执与至少三个稳定 Idle 样本均核对通过；中间实体、变换、属性、非目标不变、两个只读结果及最终 Boolean 的独立断言全部通过。

原始SQLite和回执交叉核对为十行 write done、两行 read done、十份 consumed 许可、四十事件和十二份 `c5_native_control_handoff`；没有伪造模型输出或使用模型交接表。第25请求无效HMAC返回 `handoff signature rejected`，没有 execute回执或新账本行；第26/27请求完成关闭、实际删除密钥和同回调停hook，保留 `stop.had_failure=true`，它表示预注册的拒绝负控而非未报告错误。活动文档身份及内容SHA-256 `de8fa7924ad4cf7fbeffdbe982f0b559a77eca7a8cf1f24175df642404ec6cfa`前后不变，独立fixture从registry消失。

74份原始JSON（含三道claim）及两份一致SQLite backup已私有封存，目录700/文件600，两个backup `quick_check=ok`且独立计数相符；逐文件哈希见公开审计。没有归档密钥、holdout正文或模型输出，删钥后不声称重新验证原HMAC。原状态根和证据继续保留，不因封存而解除单次屏障。所有模型/GPU/holdout调用均为0，完整C5工程门仍为false；原R A/B、原80家族消费结论与默认路线均不变。

## 与 C5 主线的关系

模型、GPU、原80家族、正式20题和任何 holdout 调用均为0；不得运行训练、原最终入口或旧 R 正式 run。该本地 native 开发门不消耗 GPU 配额，不延长租期。[GPU资源边界](../eval/c5/rhino-resource-boundary-20261002.json)仍仅批准开发≤1/正式≤3/合计≤4、原累计≤16 GPU-hours，沿用更早停止截止；没有完整门禁前不启动模型。

即使此次通过，也仅证明指定原生/许可/执行/读回/关闭正负控，**完整 C5 工程门仍需真实冻结模型调用运输和独立联合审计**。随后才冻结新的20题，由唯一人类所有者在私下排除原80及其它已消费族并批准，再进行40路线槽；C5-7与产品接入仍未裁决，默认混合路线不变。
