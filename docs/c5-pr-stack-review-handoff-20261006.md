# C5/R PR依赖与所有者审核交接

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
