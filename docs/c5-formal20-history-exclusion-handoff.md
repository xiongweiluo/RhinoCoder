# C5正式20题：历史补充排除清单交接

2026-10-06。所有者报告新20题已准备好；代理**未读取或校验其正文**，也未读取原80明文。本交付只生成历史补充清单和保管人预检入口，不冻结正式题、不创建消费账本、不运行模型/Rhino。

## 已生成的仓库外文件

私有目录 `/Users/xiongweiluo/Documents/rhinocoder_data/c5-history-exclusions-20261006`，目录0700、文件0600，不可覆盖生成：

- `extra-exclusion.jsonl`：1013条可比较排除记录、1002个不同文本，472127字节；SHA-256 `f8343ca0d2c65ed790aa032ca5d02d7141e8ccef321751c7b32674ae13445d46`。
- `coverage-report.json`：1860份历史来源的逐文件SHA、提取位置、表示类别与覆盖局限；来源清单SHA-256 `fc8c5bf3825e27e8eb1eae354cefc0e5c619de301c712fd66cfcc16b481a6491`。

正文清单不提交仓库/PR，也不打包原工作区大量未跟踪R证据。仓库只保存[生成器](../tools/build_c5_formal20_history_exclusions.py)、[私有终端入口](../tools/c5_formal20_owner_preflight_interactive.py)、合成测试和无正文交接说明。历史脚本仅用AST读取字面量/受限纯算术模板，绝不导入或执行。

来源包含：C5模型桥A/B的公开开发计划（失败或未执行也因开发可见而排除）、native12实际控制任务及12个明确标注的操作JSON代理、已冻结320/60/60开发文件的**全部user_step**、已经暴露的20个CPU合成家族；原工作区和R研究分支中的R题集、开发脚本、文档与现场JSON证据。R v6/v7/v8各60题均完整纳入，还静态展开了稳定性开发五组各12个写任务。重复文本保留不同历史身份和完整来源。

这是**本地可定位资料的保守超集**，不是“每条都被执行”或“整个R历史已证明完整”的声明。两条动态上下文是同一`consent_candidate.py`许可UI HTML模板在两个工作树的副本，经只读检查并非额外模型任务；生成器仍保留位置供审核。未归档终端/远端任务、自然语言与操作JSON的几何等价、语义近重复仍须所有者核对，不能自动填`full_r_exclusion_inventory_reviewed=true`。

## 可直接运行的保管人命令

在你自己的Mac终端运行，不在聊天或代理终端输入私有路径：

```bash
python /Users/xiongweiluo/.codex/worktrees/c5-engineering-gate/RhinoCoder/tools/c5_formal20_owner_preflight_interactive.py \
  --history-directory /Users/xiongweiluo/Documents/rhinocoder_data/c5-history-exclusions-20261006 \
  --development-root /Users/xiongweiluo/RhinoCoder/data/training/c5/v2/accepted
```

入口先核对补充清单SHA，随后分别询问**新20题JSONL**和**原80家族JSONL**的绝对路径，输入不回显，也不进入shell历史；不要把路径发给代理。没有真人终端时直接拒绝，不打开任何输入。两份文件必须在所有工作树外，且互不相同。三个现存开发split已按原冻结SHA核对，不需手工复制或改名。

仅保管人侧读取候选及原80：检查13字段schema/20题覆盖、原80Merkle身份、三份开发splitSHA、历史family/template身份、所有首步/后续user_step、数值模板及0.92近重复。补充清单和三份split重合是有意的覆盖增强，不是额外训练集。原历史hash文件/80承诺不修改。

终端只输出聚合状态或错误类别，不输出正文、路径、匹配任务或答案。成功应仍显示`formal_commitment_ready=false`、`formal_run_authorized=false`：自动排除不是完整人工审核、公开加密承诺、正式冻结或执行批准。只回传这份聚合结果即可；不要把新20题、原80、密钥或私有匹配项发给代理。后续人工审阅、age回读与公开承诺方法见[保管人规范](c5-rhino-formal20-owner-preparation.md)。

## 重生成与状态边界

生成器输入只有注册工作树中的固定C5开发文件、冻结开发split以及`r4`/`r_research`历史路径，**没有候选、原80或私有目录搜索参数**。如来源有更新，只能另选一个新的仓库外输出目录重生成，不覆盖本清单；未来公开承诺须绑定实际使用清单的新SHA。

原正式源码合成验证记录属于`ef3e0d7`的238源码快照；本轮新增预检工具改变当前源码清单，不能据旧快照授权现场运行。C5正式20题仍0消费，默认混合路由及所有历史失败结论不变。
