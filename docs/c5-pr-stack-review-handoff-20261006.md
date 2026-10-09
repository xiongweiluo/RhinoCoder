# C5/R PR依赖与所有者审核交接

## 2026-10-09正式失败及独立资源收尾后的审核快照（当前）

本次直接GitHub API核实main仍`01647f1cee38e2f09dd1d561289bfd42f103b9c5`，#2～#6 OPEN/非Draft，#7仍独立OPEN/Draft。实际base依赖main→#2→#3→#4→#5→#6；#7基于main，不作为LoRA结论替代。下方10月8日“未消费/等租期”是当时记录，不再作为当前状态。

| PR | 核查时head | 实际base |
| --- | --- | --- |
| #2 | c444f5f732e7d05dd81cded955dee712d1488383 | main |
| #3 | 86235f77185f8a557136cae5e8fd2be77ebd6d77 | codex/c5-contract-freeze |
| #4 | 19b44f36276cd0a0c7805da1b9851b93fa47e0b8 | codex/c5-dataset-v2 |
| #5 | da2fc6d8bef7b1c06ff63e73d7d6ff76fcad5bbb | codex/c5-holdout-gate |
| #6 | 1d3b226a325fb1f5e5f9f2e91cbb728a045ede71（本次文档发布前） | codex/c5-engineering-gate |
| #7 | ea85df0918147da13d58d5210269fed54f9876ef | main（Draft） |

#6在上述head的完整分页API人口368文件，94,359新增/13删除行；不是只看GitHub短files的前100项，也**不是已完成全部内容人工审核**。该head push37862239259/PR37862244090成功，独立审计源码d886452的两CI亦成功；本次只更新报告/状态文档，将产生新head及CI，不改已交接审计包的字节或SHA。审核合并仍需实际最新head，不能把旧CI自动当新head通过。

当前审核重点见[完整证据盘点](c5-research-evidence-and-decision-report.md)：原80离线门/D开发门通过与正式20题单次失败分别保留；缺外部锚、40槽和完整审计，质量不可估计。新精确批准的worker停止仅核实进程/GPU释放，不能追认Rhino安全PASS。唯一v3保管人部分核查已准备且两组双CI通过，尚待本人；代码/报告merge也不解除任何私有或现场门禁。

本人仍唯一reviewer_1。此前#2合并被执行审查要求精确PR/head确认、尚未执行，不能换接口绕过；最终C5-7/报告和实际head审核完成后，再按本人具体决定逐依赖合并及核对main CI。主工作区九份修改保持原样（diff SHA b407093a…8aa6c），不reset/pull覆盖，不打包认证、私有题目或整批R证据；#7不自动转Ready，不扩大产品UI/用户开放。

## 2026-10-08 v3批准与启动前停止后的当前审核快照

[v3冻结准备](c5-formal20-deployment-v3-readiness.md)源码`d27258f`/发布`5d629bc7a503e259fc32ea766c4a47bef0d18362`双CI成功；本人[精确确认两哈希](../eval/c5/formal20-owner-approval-v3-20261008.json)，两地grant登记及批准后完整重哈希通过。但16:39苏黎世窗口已过，[启动前停止](../eval/c5/formal20-v3-pre-admission-window-stop-20261008.json)核实入口/claim/key/模型/Rhino/正式消费均0，grant可恢复封存；不是研究失败、质量NO-GO或整体C5 GO。当前等实际新租期，不通过merge解除资源/现场/保管门禁。

完整分页GitHub文件人口与本地Git一致：#2 12、#3 18、#4 12、#5 10、#6 **336**、#7 63。GitHub短`files`只给#6前100项，不能当完整范围；这次核查覆盖全列表，不声称只凭文件名完成全部代码内容安全审核。真实祖先链main01647f1→#2 c444f5f→#3 86235f7→#4 19b44f3→#5 da2fc6d→#6 5d629bc成立，各head双CI成功；#7 ea85df0仍独立Draft。详情与完整SHA见[当时API/Git审核记录](https://github.com/xiongweiluo/RhinoCoder/pull/6#issuecomment-6061805185)。本次批准/停止文档发布会再次更新#6 head，merge前须核对实际新head/CI。

main未变，未merge/retarget。本人唯一reviewer_1；#2仍等此前执行安全审查所要求的精确PR/head决定，不绕过，不打包九份主工作区修改、认证或私有证据。以下旧head/待批准/无grant均为历史，由本节和后续实际发布CI记录覆盖；冻结源码字节仍为d27258f，不随批准/停止文档发布改变。

## 2026-10-08当前续接

正式[完整冻结与独立准备复核](c5-formal20-v2-execution-preparation.md)已完成；执行源码5399281的push37702904130/PR37702910598成功，现发布runtime/独立核查材料，最新发布head双CI另需核实。两地正式run/grant不存在，没有模型/Rhino/题目消费，不把准备冻结合并解释为执行批准。main和下方PR依赖未改变；第6项收口仍需所有者的精确merge决定，不覆盖脏主工作区。下方“准备代码继续更新”等对应上一阶段。

PR6已发布D完整PASS和容量准备`29ab4b7d0a7a651966b323e32dc42fd55059aea8`，push37691392268/PR37691397782成功；[formal v2](c5-formal20-v2-execution-preparation.md)实现/CPU材料继续更新。本人接受提案81b799b1仅准备，不是正式执行或质量裁决。新正式两哈希、本人单次40槽、私有审计/C5-7仍未完成。#2～#6 OPEN、#7独立Draft、main01647f1不变；#2精确merge仍待安全审查要求的本人确认，不换接口绕过。以下旧SHA/“新工程门尚缺”均为历史核查；D实际完整PASS并未自动赋予正式批准。

## 2026-10-07本人扩大合并授权与执行安全审查

本人明确“正式20题、E、续租和PR合并也确认在此批准范围内”，[直接授权记录](../eval/c5/continuation-expanded-owner-authorization-20261007.json)优先于下方未授权历史。当前#2～#6仍OPEN，#7独立Draft；实际base/head与全部双CI已再次核实，#6当前发布为`cbc5f3dc6220aea658ef1869d9fe7dfa3c5435b4`（37674926137/37674935702成功）。本人仍唯一reviewer_1，代理不代签。

首次尝试以精确head `c444f5f732e7d05dd81cded955dee712d1488383`、merge commit合并#2，被执行安全审查在命令启动前拒绝，要求对精确PR/head提供直接确认；**没有发生合并、retarget或main变更**。已向本人提出该单一确认，不换接口绕过审查。获确认后仍逐依赖检查真实base/head和合并后CI；不要把当前扩大路线授权记录当成实际MERGED证据。

正式20题/E运行仍须新完整冻结及另外两个精确哈希；PR合并准备代码不自动解除现场/私有消费门禁。续租尚缺时长/费用上限，不自动付款。以下表格与未获授权描述保留对应核查时点，由本节覆盖当前授权事实。

后续资源说明（2026-10-07）：本人纠正实际租期并要求继续准备，[v6边界](../eval/c5/rhino-resource-boundary-v6-20261007.json)更新为10月8日22:00苏黎世/21:45停止生成；GPU-hours和运行/合并门禁不变。[C只读时序诊断](c5-retired-c-lifecycle-timing-diagnosis.md)完成但没有新工程PASS或后继执行授权。下文“租期结束/等待路线选择”保留为此前状态，不以此断言当前服务商停租。

## 2026-10-07 后续核查与当前审核边界

以下10月6日表格保留历史；本节优先。API和本地Git共同核实：main仍`01647f1cee38e2f09dd1d561289bfd42f103b9c5`，#2～#6均OPEN/非Draft，#7 OPEN/Draft。GitHub当前均报告MERGEABLE，但这只是当时合并可计算性，不能替代本人审核或合并授权。本人仍为唯一reviewer_1，代理不代签。

| PR | 当前head SHA | 相对实际base的文件数 | 最新push / PR CI |
| --- | --- | ---: | --- |
| [#2](https://github.com/xiongweiluo/RhinoCoder/pull/2) | `c444f5f732e7d05dd81cded955dee712d1488383` | 12 | 36332148093 / 36332152068，均成功 |
| [#3](https://github.com/xiongweiluo/RhinoCoder/pull/3) | `86235f77185f8a557136cae5e8fd2be77ebd6d77` | 18 | 36335147587 / 36335150394，均成功 |
| [#4](https://github.com/xiongweiluo/RhinoCoder/pull/4) | `19b44f36276cd0a0c7805da1b9851b93fa47e0b8` | 12 | 36468014557 / 36468021473，均成功 |
| [#5](https://github.com/xiongweiluo/RhinoCoder/pull/5) | `da2fc6d8bef7b1c06ff63e73d7d6ff76fcad5bbb` | 10 | 36470807851 / 36470814691，均成功 |
| [#6](https://github.com/xiongweiluo/RhinoCoder/pull/6) | `5fff62f07ccca30f0afede55470681168116d37f`（本次材料更新前） | 269 | 37657212922 / 37657224517，均成功 |
| [#7](https://github.com/xiongweiluo/RhinoCoder/pull/7) | `ea85df0918147da13d58d5210269fed54f9876ef` | 63 | 37062250892 / 37062259596，均成功 |

上述真实base均为head祖先，顺序是main→#2→#3→#4→#5→#6；#7独立基于main，不是正式LoRA结论的替代或必要合并依赖。文件名核查未发现key/socket/known_hosts路径，无`agent/`或CI workflow改动；这不是全部内容安全审核。#6当前API计64561新增行、13删除行，范围大，不能仅凭CI将所有运行/审计代码视为已人工审阅。所有者应按以下证据层分组审核，任何未审代码保留不确定性。

### 审核证据层与不能顺带授权的事项

1. 合同/数据/工程层（#2～#5）：核对[C5计划](c5-contract-aligned-qlora-plan.md)、[dataset v2](c5-dataset-v2-draft-report.md)、[C5工程门](c5-engineering-gate.md)及相应机器契约；既有冻结/批准不因merge而修改，最终holdout职责隔离仍保留。
2. 已运行训练/离线层（#6）：核对[正式训练](c5-formal-training-report.md)、[80家族单次结果](c5-final-evaluation-report.md)及公开独立统计；checkpoint132、77/80对20/80和唯一消费是已验证证据，不能重读原80或外推整体GO。
3. 实际宿主/现场失败层（#6）：观察能力探针完成、较弱宿主保证已由本人接受；新HOSTASSURANCE A/B/C均失败退休。[C失败](c5-hostassurance-development-c-result.md)、[收尾A失败](c5-hostassurance-c-cleanup-attempt-a-result.md)、[只读诊断](c5-retired-c-live-diagnosis-result.md)和[收尾B独立审计](c5-retired-c-cleanup-b-result.md)须一起看，不只保留成功清理。有限安全关闭不证明完整handler absence、隐藏发射字节或全过程连续性。
4. 未运行正式层（#6）：[已登记20题公开承诺](c5-formal20-public-registration-and-field-blockers.md)、[正式CPU工程准备](c5-rhino-formal20-engineering-readiness.md)仅为准备证据。新完整八槽工程门尚缺，正式40槽/独立私有审计/C5-7未完成；正式spec草案不是执行授权，不能读题验证或调用owner消费入口。
5. R层（#7）：只审核其独立安全证据/条件式最小交接，不把Draft转Ready或扩大UI/用户开放。R与C4/C5结论独立，v8 formal_quality_fail59/60不改判。

CI仅执行已检查workflow中的CPU/合成、构建、浏览器和静态模板审计；它没有调用owner私有消费入口或现场研究入口。合并准备代码、失败报告和较弱保证说明，不应被解释为产品默认门禁放宽、模型运行或holdout批准。C4 NO-GO/默认混合继续不变。

### 收口操作方案：准备就绪，但未获执行合并许可

- 仓库API显示merge-commit/squash/rebase均允许，delete_branch_on_merge=false。**建议保留merge commit**以保留已冻结提交祖先与堆叠关系；这是待本人确认的方案，不自动选择或执行。若本人选squash/rebase，先解释对堆叠祖先和冻结可追溯性的影响，不能重写冻结字节或默默force-push。
- 本人决定须指定PR范围及实际待合并head（本次公开材料提交会更新#6 head，应重新核对）。此前运行批准、一般“可以批准”和推送许可都不能替代本次明确merge决定。
- 获批后按依赖顺序逐个合并，每次核实真实base/head、自动retarget及main CI；如果GitHub自动retarget不符合既定顺序，先调整获批依赖并验证该head CI，再继续。发生冲突/未知CI/无权访问时停在该项，不跳过，不强推。
- main收口用干净隔离checkout做核查，不pull/reset覆盖主工作区九份tracked修改，不删除冻结分支或打包认证/私有证据。本节没有授权merge，#7仍独立Draft。

整体持续Goal未完成。当前现场路线必须由本人选择且新租期/研究边界未建立；原18:45生成停止/19:00苏黎世到期已结束，不自动准备D或正式评测。PR审核准备可独立推进，不要求为了merge先消费20题，也不通过merge追认C5-6/C5-7成功。

2026-10-06只读核查；这些是分支/PR状态，**不是main已接入**。所有者唯一reviewer_1，无reviewer_2；可推送/更新PR，不自动merge。持续Goal第6项尚未完成，当前先提供可审阅材料。

| PR | base | 核查时head | 状态/CI |
| --- | --- | --- | --- |
| [#2](https://github.com/xiongweiluo/RhinoCoder/pull/2) | main | c444f5f | OPEN，双CI成功 |
| [#3](https://github.com/xiongweiluo/RhinoCoder/pull/3) | codex/c5-contract-freeze | 86235f7 | OPEN，双CI成功 |
| [#4](https://github.com/xiongweiluo/RhinoCoder/pull/4) | codex/c5-dataset-v2 | 19b44f3 | OPEN，双CI成功 |
| [#5](https://github.com/xiongweiluo/RhinoCoder/pull/5) | codex/c5-holdout-gate | da2fc6d | OPEN，双CI成功 |
| [#6](https://github.com/xiongweiluo/RhinoCoder/pull/6) | codex/c5-engineering-gate | eeb499a（本轮继续更新） | OPEN，该核查SHA双CI成功；后续SHA须重新核实 |
| [#7](https://github.com/xiongweiluo/RhinoCoder/pull/7) | main | ea85df0 | Draft，双CI成功；独立R路线 |

远端main仍为`01647f1cee38e2f09dd1d561289bfd42f103b9c5`。C5顺序应先审#2→#3→#4→#5→#6；#7不是模型结论依赖，审核其独立安全证据与最小收尾边界即可。不因#7成功或LoRA离线77/80把整体C5标GO。

## 合并前要点

- 对每个**实际待合并head SHA**核对owner决定、diff范围、父依赖、CI、版本/链接/秘密检查。GitHub账号不能自我approve时，保留所有者明确人工审核/合并决定；代理或CI不代签reviewer_1。
- 第1～5项的观察/开发/正式运行批准与PR merge是不同权限。合并准备代码不批准模型或私有消费；批准运行也不批准merge。
- #6源码、旧冻结构件及公开元数据可审，私有20题/原80/identity/SSH socket和整批R原始证据不进入PR。当前dirty主工作区的9个tracked修改不打包、不checkout/reset覆盖。
- 审阅中要能辨别：C5-0～5已完成；正式20题仅公开承诺已登记；host动态来源方案只有设计/合成验证；新observer和开发门须各自明确批准；GO不能从未运行或mock结果导出。

## 所有者明确决定合并后才执行

先按其具体授权合并对应PR；每次之后重新核对GitHub真实base/head及堆叠自动retarget行为，必要时只做获授权的依赖调整，重新跑该SHA的CI和main合并后CI。不会为抹平依赖进行force-push/改写历史冻结、自动合并整个栈或往脏主工作区拉取覆盖。

如merge冲突涉及不相关用户变更或现存冻结字节，应停在具体冲突/选择点，不擅自取ours/theirs。当前未收到此六个PR的最新SHA合并决定，因此本轮不执行merge。
