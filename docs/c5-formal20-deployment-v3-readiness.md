# 正式20题部署修正 v3（field protocol v2，不是新实验）

> 当前优先：[批准后启动前窗口停止](#2026-10-08批准后的启动前窗口停止)。批准已收到，但16:39完整启动窗口已过；两地grant可恢复退休，正式零消费。旧入口不可运行，等本人实际新租期后再修订资源冻结。以下部署/批准过程保留相应历史时点。

2026-10-08。旧v2 spec9f27e0ad/runtime83f2f897虽已获本人精确批准，但在启动前对**实际部署根**运行公开承诺预检失败。[原始停止记录](../eval/c5/formal20-v2-pre-admission-dependency-stop-20261008.json)证明尚无zero/formal claim、key、模型或Rhino脚本/订阅/夹具，也没有私有20题或原80正文读取。两地仅新建的grant可恢复地改名保留；旧部署/冻结/批准及全部历史结论不改，旧入口不得运行。

已证实缺项是`final-holdout-commitment.json`、`dataset-v2-freeze-manifest.json`、`historical-exclusions.json`三份**公开、已由既有20题承诺绑定哈希**的JSON。原350文件字节核查只证明声明清单一致，不能证明传递依赖完整；旧40槽CPU测试注入了公开预检条件，完整Git根的预检也不能替代独立部署根。本发现是准备/部署问题，不是正式研究尝试或LoRA质量NO-GO。

## 最小修正和不变项

- [`PUBLIC_FILES`](../tools/run_c5_formal20_worker_v2.py)追加上述三个公开文件，不复制任何语料、答案、密文或认证材料。
- [准备器](../tools/prepare_c5_formal20_freeze_v2.py)在实际Mac部署根单独运行公开CLI预检，失败即不生成runtime；完整承诺仍为`41c92c72…ebaf4`。
- [Scope](../plugin/rhino_listener/c5_formal20_scope_v2.py)改用独立`formal20-source-v3` / `formal20-state-v3`、Linux对应v3和[spec-v3](../eval/c5/rhino-formal20-spec-v3.json)。协议仍v2、同一未消费study/20家族/40槽；不是通过换ID重跑。
- [六项公开部署回归](../eval/test_c5_formal20_deployed_public_dependencies.py)验证所有依赖入清单、实际隔离根正控、缺失各JSON负控、准备器确实针对部署根。19相关控制及全仓1026 passed/8 skipped通过；CPU不操作真实模型/Rhino或私有资料。
- 模型/revision/checkpoint132、契约/12工具/严格解析、顺序/评分、≥14/20/净胜≥3/安全与重复写/未核实清理0、有限host保证、normal2048/cleanup256/journal4096/3稳定60秒均不变。正式5/研究6/开发1/原16小时和10月8日21:45停止/22:00到期不扩大；最晚16:39开始，不自动续租或降低预算窗口。

源码双CI、窄清单新部署、实际部署公开预检/完整冻结与独立重哈希已完成，见[独立预执行核查](../eval/c5/formal20-v3-preexecution-validation-20261008.json)。冻结源码为`d27258f`，双CI37780147813/37780156280成功；337源码/15指定公开文件，加spec/runtime共354文件，Git/Mac/Linux人口与字节一致。3552 Mac外部、339已知可读host、6 tokenizer、age、21614 Linux分发、960标准库/libpython/解释器、14基座及两adapter已独立重哈希。GPU loader预检未初始化CUDA或加载模型；原pip metadata缺项不隐瞒或安装修补。

第一次准备在SSH边界中断；恢复后先只读证明远端新source/state均不存在，再从该确定边界继续首次部署，未重放整个准备器、覆盖文件或建立运行state。runtime传输取得精确长度/SHA回执，再独立核对完整字节。保活不证明五小时连接稳定；断线仍可能使唯一运行失败，不能因此补槽或重试。

冻结发布`5d629bc`双CI37787935070/37787943417成功。本人已直接确认[新spec/runtime两个精确哈希](../eval/c5/formal20-owner-approval-v3-20261008.json)，批准后两地354文件、完整环境/模型再次核对通过：

- [spec-v3](../eval/c5/rhino-formal20-spec-v3.json)规范化SHA-256：`5e11b001538768a05f2475a0f52722e0f78b985f2381926404af19e37e92a525`
- [runtime-v3](../eval/c5/rhino-formal20-runtime-freeze-v3.json)规范化SHA-256：`5ff14cf43a5cb7277ad27661e061c55b830a9e4ec9f51775624f8c6faac39bcf`

旧83f2批准不应用到新字节。新v3批准已经收到，两地state已各登记一份owner-approval.json，grant规范化SHA为`8cb21445e18e6d1ff45a1ca17c4b29f47f62c0be08b51e88abbce5adc4bcaef0`；没有claim/key/模型/Rhino或正式消费。批准前的freeze/独立核查中approval=false、state不存在保留当时原始事实，不修改冻结。当前现场仍显示两份旧source-v2包装，已请本人全选替换唯一source-v3四行，先核对、再本人TTY入口、看到WAIT才单次运行Rhino。超过16:39不启动原窗口，须先确认新资源边界；不因批准晚到而缩减五小时或自动续租。

## 2026-10-08批准后的启动前窗口停止

[停止原始记录](../eval/c5/formal20-v3-pre-admission-window-stop-20261008.json)：14:33:46 UTC观察到本人完整精确批准，运行前重哈希通过，两地grant登记成功；但唯一包装/本人TTY交接没有在冻结的16:39苏黎世前完成。14:39:41 UTC确认窗口已过，没有调用任何正式入口，无claim/key/模型/Rhino/夹具/订阅/私题读取或消费。不能仅因GPU租期仍在而压缩五小时或略去zero-stage余量。

两地仅一份批准文件可恢复地改名为`owner-approval.retired-window-expired.json`，并各写一份公开停止元数据；原批准与冻结/模型/公开承诺保留，不写失败质量分数、NO-GO或重复消费。旧v3包装不可运行；前面“批准收到/待包装”描述为此次对应历史时点。

当前必要输入仅为服务商显示的新GPU实际到期日期/时间/时区；代理不续租或付款。有效新租期后只修订未启动研究的资源/部署冻结（正式5/研究6/开发1/原16及完整zero-stage/900秒导出不缩减），保留原20题承诺/封存/模型/D工程证据，双CI后给新两哈希精确批准。不重新数据、工程门、观察器研究或新E。完整交付仍须实际40槽及本人私下审计/C5-7。

## 责任隔离与后续

本人仍唯一reviewer_1/独立保管人。代理只核验公开元数据及冻结字节，私有路径、解密、20题运行和证据审计仍由本人TTY入口完成；不请求重新封存或发送现有承诺，不加新开发题、不重读原80，不启动E。修复后保持一次消费/无重试；C5-7仍须实际完整证据，GO不切默认混合。C4 NO-GO、v8 formal_quality_fail59/60和R证据保留，整体Goal未完成。
