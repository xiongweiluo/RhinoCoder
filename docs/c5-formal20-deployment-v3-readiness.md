# 正式20题部署修正 v3（field protocol v2，不是新实验）

2026-10-08。旧v2 spec9f27e0ad/runtime83f2f897虽已获本人精确批准，但在启动前对**实际部署根**运行公开承诺预检失败。[原始停止记录](../eval/c5/formal20-v2-pre-admission-dependency-stop-20261008.json)证明尚无zero/formal claim、key、模型或Rhino脚本/订阅/夹具，也没有私有20题或原80正文读取。两地仅新建的grant可恢复地改名保留；旧部署/冻结/批准及全部历史结论不改，旧入口不得运行。

已证实缺项是`final-holdout-commitment.json`、`dataset-v2-freeze-manifest.json`、`historical-exclusions.json`三份**公开、已由既有20题承诺绑定哈希**的JSON。原350文件字节核查只证明声明清单一致，不能证明传递依赖完整；旧40槽CPU测试注入了公开预检条件，完整Git根的预检也不能替代独立部署根。本发现是准备/部署问题，不是正式研究尝试或LoRA质量NO-GO。

## 最小修正和不变项

- [`PUBLIC_FILES`](../tools/run_c5_formal20_worker_v2.py)追加上述三个公开文件，不复制任何语料、答案、密文或认证材料。
- [准备器](../tools/prepare_c5_formal20_freeze_v2.py)在实际Mac部署根单独运行公开CLI预检，失败即不生成runtime；完整承诺仍为`41c92c72…ebaf4`。
- [Scope](../plugin/rhino_listener/c5_formal20_scope_v2.py)改用独立`formal20-source-v3` / `formal20-state-v3`、Linux对应v3和[spec-v3](../eval/c5/rhino-formal20-spec-v3.json)。协议仍v2、同一未消费study/20家族/40槽；不是通过换ID重跑。
- [六项公开部署回归](../eval/test_c5_formal20_deployed_public_dependencies.py)验证所有依赖入清单、实际隔离根正控、缺失各JSON负控、准备器确实针对部署根。19相关控制及全仓1026 passed/8 skipped通过；CPU不操作真实模型/Rhino或私有资料。
- 模型/revision/checkpoint132、契约/12工具/严格解析、顺序/评分、≥14/20/净胜≥3/安全与重复写/未核实清理0、有限host保证、normal2048/cleanup256/journal4096/3稳定60秒均不变。正式5/研究6/开发1/原16小时和10月8日21:45停止/22:00到期不扩大；最晚16:39开始，不自动续租或降低预算窗口。

当前仅准备修正部署：源码双CI→窄清单新部署→实际部署公开预检/完整冻结与独立重哈希→发布双CI→**新spec/runtime两个精确哈希批准**。旧83f2批准不能自动应用到新的字节；v3未授权运行、未创建运行state。包装路径将改为source-v3，不能运行目前Rhino缓冲区内旧source-v2包装；待新精确批准后再核对唯一四行。

## 责任隔离与后续

本人仍唯一reviewer_1/独立保管人。代理只核验公开元数据及冻结字节，私有路径、解密、20题运行和证据审计仍由本人TTY入口完成；不请求重新封存或发送现有承诺，不加新开发题、不重读原80，不启动E。修复后保持一次消费/无重试；C5-7仍须实际完整证据，GO不切默认混合。C4 NO-GO、v8 formal_quality_fail59/60和R证据保留，整体Goal未完成。
