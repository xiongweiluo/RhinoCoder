# 未启动C的GPU boot修订与完整精确批准门

本人已批准原C spec/runtime两个完整哈希。恢复SSH后、登记任何grant前的无研究作用实际预检发现GPU重启，冻结boot `0a861fa3-31c9-4899-a022-c4f9cdb8dbfe`与实际 `77b495a6-c67c-4721-9038-e87c7fcc3fc6`不符。原GPU预检按守卫拒绝；[追加原批准与停止证据](../eval/c5/reuse-development-c-postapproval-boot-drift-20261012.json)保留原精确批准、发布head与最新观察，不将批准迁移到新runtime。

此时C两端均无state/grant/key/claim/custody，Mac prepare、Rhino wrapper、controller drive、模型加载/请求和槽启动均0。停止发生于只读准备复核，未消耗研究单次入口。保持同一未启动C身份和唯一一次固定公开8槽机会；不是失败后换ID或重跑，不恢复A/B。原批准完整副本保存在 `/private/tmp/rhinocoder-c5-reuse-development-c-freeze-20261012`，Git版本为 `84a0336ab32883c4f16cf7bca775421062387d0a`。

## 两个完整哈希

| 完整材料 | canonical SHA-256 |
| --- | --- |
| [C spec（字节不变）](../eval/c5/reuse-development-spec-20261012-c.json) | `10f821cacb0e5681c3b2f8286230eab7dfdd69102ed7ca3adf540f6cd2148446` |
| [C boot修订完整runtime](../eval/c5/reuse-development-runtime-freeze-20261012-c.json) | `160e74bb15497960d51d499f51bac6a8be67b38c0124af385296c1119ecedc24` |

覆盖整个JSON，sort_keys=true、紧凑separators、ensure_ascii=true、allow_nan=false；不是raw文件SHA。[完整plan](../eval/c5/reuse-field-environment-plan-20261012-c.json)只有 `gpu_process.boot_id` 一个叶子值变化。spec、全部Python/依赖契约源码、模型、环境、宿主接受、资源、停止/导出边界、A/B原失败和退休绑定均字节不变。307项source map仅plan的raw SHA改变，runtime由它重新规范化。新完整副本在 `/private/tmp/rhinocoder-c5-reuse-development-c-boot-revision-freeze-20261012`。

两端公共更新只能在原C state/grant/custody缺席、旧308文件人口及字节验证、A/B退休和原共享准入为空且保持不变的情况下调用既有 `--update-freeze`；不是入口重试，不清空准入或覆盖研究证据。更新完成后，重新检查两端308公共文件、独立完整哈希、实际固定解释器无grant预检及新boot/原GPU UUID/完整5小时窗口。传输尚未完成时代理提前发起过只读source和GPU preflight，两项见旧冻结而拒绝；失败记录保留，成功证据只采用明确部署完成后的复核。

## 当前验证和边界

原基座14、adapter2、非缓存分发21614、标准库960、两libpython、解释器、RTX3090 UUID/驱动/容量及Mac宿主339、控制器3552、tokenizer6重哈希匹配；实际GPU compute为空。相关CPU控制65 passed；原完整功能CPU 1852 passed/11 skipped与本次全部代码字节不变相对应，修订发布head仍要求双CI成功，不能用旧CI替代。[完整修订验证](../eval/c5/reuse-development-boot-revision-preexecution-validation-20261012-c.json)记录实际部署与无研究作用预检；CI以本PR最终精确head为准。

历史GPU累计仍未知，平台无小时额度。原有限修订开发5小时/正式18小时/研究23小时不变；租期2026-10-13 20:00 Europe/Zurich，19:45停止生成，900秒导出。开发最迟14:45完整准入，正式18小时另行验证窗口，不自动续租/付款或缩短预算。保证仍为可读文件冻结、opaque宿主信任及有限可见连续性；不追认完整字节闭包、人类来源、历史清理或内存擦除。原C5 NO-GO与默认混合保持。

原04caa runtime批准不批准本160e runtime。只有本人再次明确批准上述**两个完整哈希**且本次精确head双CI成功后，才可登记两端grant→使用 `require_escalated` 一次Mac prepare→本人私下TTY ready保管工具就绪→一次Rhino C wrapper→一次drive→固定8槽→退出/资格目标释放/导出→本人实际final保管与完整原始联合审计。Mac调用权限、120秒真实ready等待、原180秒模型/120秒native/60秒settlement、无补槽重发重试均不变。

本人保管操作及真正现场验收按[原C完整说明](c5-reuse-development-c-exact-freeze-review-20261012.md)执行；只有新完整工程门PASS才能准备正式40槽及另一份完整精确批准，代理不接触原私题。当前尚无修订精确执行批准，也没有现场研究PASS。
