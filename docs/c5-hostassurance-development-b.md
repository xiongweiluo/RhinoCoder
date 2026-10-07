# C5 独立开发 B：入口返回后封存（冻结已完成/待精确批准/未执行）

当前第2项研发延续：A是[FAIL/退休、安全停止已交叉核实](c5-hostassurance-development-a-result.md)，不重跑、不改判。B为独立ID `C5DEV-HOSTASSURANCE-20261007-B` 与全新源/状态，只修复实际诊断的**基线采样时序**；不是为了GO追加任务、调模型/提示或按名字隐藏来源。

## 最终可审阅冻结

**后续执行状态：**本人已批准上述最终两个哈希，B单次执行后因首请求远端回执未知而FAIL/永久退休；有限宿主连续性独立PASS，实际1次基座selector、0invocation/LoRA/工具/holdout，迟到结果只读保全，清理已核实。见[B结果](c5-hostassurance-development-b-result.md)。下文未批准/未执行状态仅为事前历史，不再索要B批准或复用B运行；当前只准备新C运输生命周期修复，仍需其独立两个精确哈希批准。

[spec](../eval/c5/hostassurance-development-spec-20261007-b.json)规范化SHA-256：`bf09d927c79ff1d36338e93fbf1d235c4d905cdce18353c017a916d854a50f7d`。

[runtime freeze](../eval/c5/hostassurance-development-runtime-freeze-20261007-b.json)规范化SHA-256：`241b72baf3fe0c72e684e7783fd3b5935aa24dc4fe2c1f33af6b8a9efe539d7d`。

[独立预执行复核](../eval/c5/hostassurance-development-preexecution-validation-20261007-b.json)：源码`aab4a5f`，279源码条目、339可读宿主文件、287部署文件；工作树/Mac/GPU全部源、配置、spec/runtime字节相同。Mac外部3552文件、上下文1767/2048、基座与checkpoint132、GPU环境/无CUDA初始化和pip唯一metadata缺项已核实。724 passed/8 skipped，23项B与时序专门正负控，secret/release/diff/文档链接通过；源码push/PR双CI `37613717586` / `37613723271`成功。最终发布head仍须双CI成功才集中请求新批准。

`execution_ready=true`仅表示冻结材料具备核对条件；**实际批准、执行状态、key、订阅、模型/夹具/工具调用均未建立**。B不是A的重跑或许可延长。当前驻留的退休研究模块/opaque宿主仍属于本人已接受的信任假设；未删除模块或伪称整个宿主属于这279文件，也不把可见结构指纹当代码字节证明。

## 单次生命周期

[B spec](../eval/c5/hostassurance-development-spec-20261007-b.json)冻结wrapper：只执行一次`runpy.run_path`，**返回后**明确调用返回字典中的`ENTRY_RETURN_BARRIER.release_after_entry_return()`。入口本身仅做已声明imports/types/一个空夹具读回与关闭、挂接hub、排队，不同步seal。callback在release前或Rhino仍InCommand时不得订阅、seal或派发；第一份非command Idle单次seal/publish ready，并直接return，不在同一callback派发请求。driver看到与两个哈希绑定的release/ready后才能启动模型。

[纯时序门](../plugin/rhino_listener/c5_deferred_baseline.py)用真实stdlib runpy与合成Idle正负控验证旧临时`__main__`对象恢复、延后采样、未release/command-active/失败/重复release阻断。**没有忽略`__main__`**；封存后任何新/变化module/instance/native artifact仍严格拒绝，不重封、不补白名单。未来真实晚加载是否还会触发守卫，必须如实等待新单次运行；合成PASS不替代工程门或完整字节证明。

release和ready具有独立不可覆盖文件，原始独立审计核对其值、所有host checkpoint/每请求关联/外部Command History回执，以及raw模型/许可/几何/账本/关闭/删钥。seal或release失败sticky且没有模型启动，保留实际owner/hook/keys；不猜测清理，必要时另请求精确reconcile批准。两条新entry-return操作只在新的B执行许可里成立，A许可不能复用。

## 不变化的实验与资源边界

同一4个已排除训练家族（原文复用，无新语义家族）、8槽交叉基座/LoRa、最多16生成阶段；同一base revision与checkpoint132、system/chat template/schema/严格解析/max2048、每槽一写或一读、其他0许可；最多2写/2读。一个空warmup夹具＋8独立模型夹具，不运行native12/旧B/原80/正式20题，不训练、不改默认路线，不修模型解析、不重试/补题。

有限保证仍为本人已接受的冻结源码/可读文件＋整个opaque宿主信任假设＋可见checkpoint连续性，不证明完整发射字节/因果来源/连续无瞬变/handler完全缺席。旧完整byte闭包字段仍false，原正式/默认守卫不改。pip3.13唯一metadata缺项显式保留，不安装/升级。

退休模型桥A+B340.027164秒＋本次Host A37.788497秒=累计开发377.815661秒，剩余3222.184339（取整**3222**），所有新预算/用量在freeze前重新核对。今日**2026-10-07 18:45 Europe/Zurich停止生成、19:00到期**、900秒导出、正式3/研究4/原累计16 GPU-hours不扩张，无自动续租。

源码传输仍只包含干净Git明确py/公开配置列表，不打包工作区。B采用gzip降低弱链路负担，禁Mac/xattrs并解析archive精确人口/普通文件，拒绝额外/重复/缺失/符号链接/硬链接；不因传输unknown自动覆盖或把不完整源当已冻结。

## 当前门禁

完整B source/environment/assets/public config/资源freeze已生成且独立复核；最终发布head双CI成功后，集中给本人上述两个新的精确哈希。现在仍只允许已授权代码/CPU、只读及公开冻结审核，批准前不能运行B。A的source/spec/runtime/raw结果保持历史不变。B通过独立实际工程门之后，才进入已登记20题正式冻结/另一份精确批准，不重复索取公开承诺、也不读私有正文。
