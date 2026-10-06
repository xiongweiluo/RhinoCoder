# C5 可信宿主与动态来源审计方案：设计稿

2026-10-06。所有者明确同意**设计及合成验证，现行门禁保持封锁**。状态为 `DESIGN_AND_SYNTHETIC_NEGATIVE_CONTROLS_ONLY`；不是运行时冻结、真实来源证明、模型/Rhino执行批准或正式20题授权。实际阻塞/公开承诺/预算见[现场登记记录](c5-formal20-public-registration-and-field-blockers.md)。

## 不变量变化必须明确，不偷换原证明

现有守卫要求所有Python/CLR来源可对应文件字节；当前进程的`CLR/clr=unknown`与四个动态程序集不满足它。[原守卫](../plugin/rhino_listener/c5_formal20_environment.py)和[正式批准入口](../plugin/rhino_listener/c5_formal20_scope.py)继续执行原规则，不增名称白名单、不忽略unknown，不把部分文件库存标成完整闭包。

候选方案假设**冻结并信任研究专用Rhino、.NET、Python/Python.NET宿主及生成器**；动态代码可作为显式、不具文件字节证明的宿主信任边界。程序集名称、MVID、结构哈希、`AssemblyLoad`事件或调用栈都不是其代码安全性或唯一因果来源的密码学证明。此方案只能提供冻结宿主及受控进程状态连续性的证据，不能声称完整发射字节冻结、抵御同进程恶意代码或已证明CLR生成器因果来源。

只有所有者接受上述**较弱且不同的溯源保证**、真实观察可验证、负控有效，并另行批准新完整spec/runtime后，才可能选用新策略。现有精确批准不能迁移到此策略；如果真实来源不可核实、完整事件监听不可实现或生成状态持续变化无法封存，应保留阻塞，而非继续增加例外。此设计不改变默认产品的隐私/许可/安全执行，不改变模型prompt/schema/权重、20题分母或统计门槛。

## 威胁模型和不覆盖范围

研究要检出：源码/宿主/生成器文件漂移，外来project origin，Python模块重绑定，新增或同名替换程序集、动态类型/可观察结构变化，缺失/未归属加载事件，越界发送模型输入，以及封存后未经批准的运行变更。任何一项未知均在工具许可前停住；已发生或回执未知的动作不重试。

明确假设：机器和冻结宿主本身可信、无同进程攻击者/本地恶意注入，操作者不在研究进程执行其他脚本或安装插件，模型文本仅作为数据严格解析，不能送入eval/exec/ScriptEditor。签名许可、独立headless夹具、预算/账本和清理控制仍独立存在；它们减少执行影响，却不能证明不透明宿主代码无漏洞。无法证明此前遗留代码来源的当前ScriptEditor进程，不直接追认为受控基线。

## 实施前的实际证据要求（尚未完成）

1. **专用干净宿主**：由所有者准备新的研究Rhino进程/空白活动文档，保留现有进程与证据；不强制终止或重启用户工作。启动方式、插件加载、研究入口和无其他脚本运行边界须记录。不能把当前进程全部已有动态代码仅按名字认作可信。
2. **宿主/生成器文件库存**：冻结实际Rhino可执行及加载native images、.NET与Python运行时、Python.NET文件程序集、全部研究源码及依赖。身份来源必须是真实绝对文件与哈希，不从module名称猜路径。CPU候选验证器只验证记录结构，不证明库存完备或文件真实。
3. **只读观察器原型**：实现独立于工具hub的Python module binding、CLR assembly/native image及生命周期观察；验证真实Rhino能力及事件覆盖。各程序集记录name、实例/MVID、file-backed身份或明确opaque分类，以及可观察类型/方法结构。记录reflection不可见内容；若不能区分变更或无法证明事件完整，停止，不将缺项填true。
4. **事前限定warmup**：在新的开发spec中声明允许的纯类型绑定/构造及必要fixture操作范围，获得对应批准后才执行有影响动作。所有所需生成状态须在基线封存前完成；封存后新类型、新结构或新实例一律拒绝，即使名称相同且功能看似正常。未知的合法懒生成也按运营停止处理，不现场追加白名单或重放。
5. **基线封存与连续性**：固定process identity、研究项目文件、CLR/clr对象绑定、所有程序集结构和native image库存，记录完整监听起点；在每次许可前、动作后和shutdown独立核对。原始事件及快照不可覆盖、可独立复算。汇总bool不能替代完整原始日志；读取记录作独立审计，不信hub自报pass。
6. **未知Python绑定**：CLR/clr只能在受控进程中按明确Python.NET宿主假设登记，同时冻结实际生成器文件/模块对象实例；此绑定不是从`unknown`推导的真实文件来源证明。不满足来源、实例连续性或受控启动条件仍拒绝。

现场订阅/.NET反射及真实动态指纹的可实现性**尚未验证**。本轮未附加AssemblyLoad/Idle hook、未启动新Rhino进程、未构建夹具，也未运行warmup。339文件的现有部分库存只作为设计输入。

## 本轮合成验证交付

[纯数据候选验证器](../training/c5_host_provenance_candidate.py)无文件、进程、CLR、网络、模型或运行器访问，无CLI、不被任何现行执行入口调用。它只验证**事前manifest和合成observation的声明结构/精确连续性**；输入记录可以伪造，因此正控不能称为实际审计通过。策略标识`c5-trusted-host-opaque-baseline-design-v1`明确带design，非可执行策略。

正控输出固定：`execution_ready=false`、`formal_admission_supported=false`、`legacy_byte_closure_verified=false`、`actual_runtime_evidence_verified=false`、`emitted_bytecode_or_causal_generator_origin_proven=false`。Opaque记录必须注明`structure_only_not_code_bytes`，不能伪装file byte proof。

[合成测试](../eval/test_c5_host_provenance_candidate.py)覆盖21项：完整声明正控；不同process、项目文件/native inventory漂移；origin重绑定；warmup/基线未封存；日志缺失/未归属事件；模型输入不是数据；同名换实例、新动态程序集、同实例结构变化（即使重算库存哈希仍拒绝）；删信任边界、伪称字节证明、缺生成器及试图启用执行等负控。实际reflection或监听绕过尚未被这些纯数据测试证明可检出。

```bash
cd /Users/xiongweiluo/.codex/worktrees/c5-engineering-gate/RhinoCoder
python -m pytest -q -p no:cacheprovider eval/test_c5_host_provenance_candidate.py eval/test_c5_field_readonly_preflight.py
```

## 后续门禁与交付验收

下一交付应仅做独立观察器原型、受控宿主准备规范及CPU/合成篡改审计，并核实是否能产生完整实际记录。若可行，再制定**新的**执行策略版本，显式记录opaque宿主假设和真实审计范围。不能把新策略通过填入旧`actual_mac_rhino_gpu_import_closure_verified`字段冒充原证明；需要新增分离字段/严格版本分支并由所有者评审，旧版本与历史授权不修改。

再后才准备独立新开发ID、合成题/40槽链路范围、source/model/Mac/Rhino/GPU/observer完整freeze、租期/原累计预算及双CI，取两个新精确哈希批准；合成开发题与封存20题重合由保管人私下排除。单次现场开发门和原始独立审计都通过，才能冻结正式20题新spec/runtime并取**单独**批准。新开发warmup/observer/model/fixture运行均不由本设计确认授权。

本方案失败、不可实施或超预算时应真实报告现场工程阻塞；不能提前给整体C5 `NO-GO`质量裁决，也不能把它当作LoRA又失败。C4、v8、原80、R/B/native12历史裁决及默认混合路由保持原样。
