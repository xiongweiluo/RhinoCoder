# C5 PR #8～#26 集中合并审核材料

核查时点：2026-10-24T22:00:04.921637+00:00（Europe/Zurich已为2026-10-25）。建议把 **#8→#26连续依赖栈** 作为候选合并范围，按编号顺序逐个合并，并最后纳入本次描述性分析/审核补充PR。本材料只准备审核，不合并、不运行模型、不改变默认产品路线；仓库所有者是唯一必需审核人。

## 实际Git与依赖

main精确HEAD：`9d20bd70fb0367da9346f11e83bd78d347f443b8`。19个PR均为OPEN、Draft；查询时相对于各自base均为MERGEABLE/CLEAN，reviewDecision为空，**不能当作本人已批准**。本地已获取远端引用并核对head一致、base为head祖先、base分支及OID对应前一个PR。#8基于main，#9～#26分别基于前一项。#7为独立R路线，既非本栈前置也不纳入本次范围。

[机器可读现场快照](c5-analysis/pr-stack-8-26-snapshot-20261025.json)包含所有完整head/base OID、分支名、变更路径、CI/check结果和查询时点。快照是时点证据，后续任何head/base变化都须重新核对，不能沿用旧绿灯自动合并。

## 精确head与适用CI

下表CI均绑定该行精确head且已成功；“P/R”分别为push和pull_request事件。#8～#22沿用当时双事件CI；#23起工作流已去重为PR检查，分支无第二个push CI是设计行为。#23～#25五项impact/python/ui/release/validate均成功；#26文档diff仅impact/release/validate运行成功，Python/UI明确SKIPPED。

| PR / 依赖 | 精确head SHA-1 | 适用成功CI |
| --- | --- | --- |
| [#8](https://github.com/xiongweiluo/RhinoCoder/pull/8) ← main | `ef98aed6713bfbb8f254a87b4069a129da11661e` | [P 38096420444](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38096420444) / [R 38096457134](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38096457134) |
| [#9](https://github.com/xiongweiluo/RhinoCoder/pull/9) ← #8 | `c91b9a607bf24899572b18fc096e0a8788e9d273` | [P 38104027841](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38104027841) / [R 38104030013](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38104030013) |
| [#10](https://github.com/xiongweiluo/RhinoCoder/pull/10) ← #9 | `ad9f7ae9dcfe39be309cbb75c4e77af9d0349c75` | [P 38145273336](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38145273336) / [R 38145291362](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38145291362) |
| [#11](https://github.com/xiongweiluo/RhinoCoder/pull/11) ← #10 | `ff98a9edf06e63278ad1d2ea28c0329ead4ba249` | [P 38151946505](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38151946505) / [R 38151960744](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38151960744) |
| [#12](https://github.com/xiongweiluo/RhinoCoder/pull/12) ← #11 | `c02f82ab29623f93efd67030155aba268a54cf77` | [P 38156100266](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38156100266) / [R 38156401991](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38156401991) |
| [#13](https://github.com/xiongweiluo/RhinoCoder/pull/13) ← #12 | `ef36e208c332fe3c0a19b2e8470515d823696b70` | [P 38162981578](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38162981578) / [R 38162999158](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38162999158) |
| [#14](https://github.com/xiongweiluo/RhinoCoder/pull/14) ← #13 | `03302f95580bdc0d10953920cd394424148bc081` | [P 38197244754](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38197244754) / [R 38197249401](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38197249401) |
| [#15](https://github.com/xiongweiluo/RhinoCoder/pull/15) ← #14 | `abe63120b07bb5614b669b1bae512e6418856c9c` | [P 38273750373](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38273750373) / [R 38273757891](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38273757891) |
| [#16](https://github.com/xiongweiluo/RhinoCoder/pull/16) ← #15 | `8a9436cd33a9a3b4dc56eab5acb9eb55b8f4c039` | [P 38279664189](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38279664189) / [R 38279716736](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38279716736) |
| [#17](https://github.com/xiongweiluo/RhinoCoder/pull/17) ← #16 | `96e4fb3b83d5903f6296e4b381e4186bdf2cf3ad` | [P 38292633328](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38292633328) / [R 38292706371](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38292706371) |
| [#18](https://github.com/xiongweiluo/RhinoCoder/pull/18) ← #17 | `82fdf3954244b957da70353a8adc185bf08291cc` | [P 38303284834](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38303284834) / [R 38303332335](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38303332335) |
| [#19](https://github.com/xiongweiluo/RhinoCoder/pull/19) ← #18 | `9fdcec36d44953067f75d9c8e94bd016b2522081` | [P 38414492651](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38414492651) / [R 38414616746](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38414616746) |
| [#20](https://github.com/xiongweiluo/RhinoCoder/pull/20) ← #19 | `f6c204116389f1f2a6ef661d8f61753f2e2da9ca` | [P 38440186898](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38440186898) / [R 38440196656](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38440196656) |
| [#21](https://github.com/xiongweiluo/RhinoCoder/pull/21) ← #20 | `47631d2c4ec14976d28382b66751b8ca07deb4c0` | [P 38585661638](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38585661638) / [R 38585686786](https://github.com/xiongweiluo/RhinoCoder/actions/runs/38585686786) |
| [#22](https://github.com/xiongweiluo/RhinoCoder/pull/22) ← #21 | `16693dc7b5000c7dbb63c1c61ce7a024d098b45d` | [P 39835165373](https://github.com/xiongweiluo/RhinoCoder/actions/runs/39835165373) / [R 39835171919](https://github.com/xiongweiluo/RhinoCoder/actions/runs/39835171919) |
| [#23](https://github.com/xiongweiluo/RhinoCoder/pull/23) ← #22 | `189d0cc2e523c6c89c5dc1a79e874b4d102951ea` | [R 39995977951](https://github.com/xiongweiluo/RhinoCoder/actions/runs/39995977951) |
| [#24](https://github.com/xiongweiluo/RhinoCoder/pull/24) ← #23 | `ef0ee558f436b3e69d21463292f2ca9ac05ac227` | [R 40096500219](https://github.com/xiongweiluo/RhinoCoder/actions/runs/40096500219) |
| [#25](https://github.com/xiongweiluo/RhinoCoder/pull/25) ← #24 | `f73ed58cbcef659ee09800123112cb472168a720` | [R 40124063773](https://github.com/xiongweiluo/RhinoCoder/actions/runs/40124063773) |
| [#26](https://github.com/xiongweiluo/RhinoCoder/pull/26) ← #25 | `0ac86c2a07955646319ac9ba9675bac5869cb3be` | [R 40131958878](https://github.com/xiongweiluo/RhinoCoder/actions/runs/40131958878) |

这些CI检查各自历史head及当时base关系；不是未来main合并提交的检查，也不是逐行人工安全审查、原研究全部审核通过或运行授权。后续改变base必须核对实际diff和所选检查；不能为凑“双CI”重复运行等价作业。

## 建议范围与审核重点

| 依赖组 | 交付内容 | 审核重点 |
| --- | --- | --- |
| #8～#13 | 原20题复用协议、CPU传输/审计、现场准入 | 私题隔离、精确批准、权限转交和原始证据约束 |
| #14～#18 | A～D准备/启动兼容修复与退休历史 | 旧失败、消费与退休不可覆盖；当时规则保持时点含义 |
| #19～#21 | 有限预曝光恢复、公开8槽、追加只读审核 | 保留原计时和审核拒绝，不能用追加审核追认旧门通过 |
| #22～#25 | 正式包、统一入口、局部失败继续、r3/r4和TTL/停止修复 | 已曝光题边界、失败落盘、有限恢复、清理及原NO-GO |
| #26 | 分阶段研究报告及作品集 | 首次/r3/r4分别呈现，不能拼成首次完整通过 |
| 本次补充PR（基于#26） | 只读脱敏评分、逐题差异与本审核清单 | 描述性2/20对13/20；固定分母、工程失败、原门和来源限制 |

main到#26的净差异覆盖440个文件：docs 39、eval 203、plugin 37、tools 59、training 98、工作流1、计划1、中英文README各1。没有agent目录变更；这不等于所有共享原生权限/研究执行逻辑无需审查。其历史跨度与可执行变更应作为完整工程栈审核，不能只挑成功结果文件合并。现有CPU/CI及现场证据按各包复用，本次不重跑未受影响的模型或私有审计。

所有冻结的历史spec/runtime、原件指纹、失败、账本、首次计时和C5 NO-GO保留。追加评分来源和限制见[描述性分析](c5-descriptive-score-analysis-20261025.md)，阶段事实见[原报告](c5-reuse-phased-research-report-20261024.md)。合并历史材料不代表选择其所有历史“下一步”或重启退休包。

## 推荐合并方法与顺序（尚未执行）

1. 本人决定是否接受#8～#26整体范围及本次文档补充；可按上表分组审核/交付，但每组仍依赖已合并前缀，不跳过中间代码依赖。Draft需在本人决定后转为可合并；不新增第二审核人。
2. 推荐保留原head的 **merge commit** 方法。仓库当前允许merge/squash/rebase，且不自动删分支；squash/rebase会改写main上的祖先关系，需要重新计算后续栈diff/引用及验证，不能当作等价的一键替换。保留冻结引用和历史分支，不force-push重写历史。
3. 从#8开始，将每个后续PR在其前置合并后指向main（仅在获准合并阶段操作），核对完整head仍等于本表、预期新增diff、可合并状态和适用CI。base变化引起的新检查完成后再合并；合并后的main CI也须通过才继续下一项。顺序为#8→#9→…→#26→本次补充PR。
4. 任一head漂移、冲突、意外diff、CI失败或历史证据变化即停止合并流程，给出差异；不自动压掉失败或启动模型。最后核实main含所有获准head、公开链接/发布检查通过；合并不自动发布Release/网站或切换默认路由。

CI的main push按既有规则选择全量检查，成本会高于文档PR；这是整合验证，不是新增模型运行。对本次文档补充只执行公开数据一致性、链接、保密扫描、发布一致性和原NO-GO核验，适用CI沿用既有选择器。

## 需要本人决定的事项

- **范围：** 是否接受完整#8～#26顺序栈及本次文档补充，或先合并哪一个连续前缀。不能把“报告接受”默认为“代码栈合并批准”。
- **方式：** 是否采用上述merge commit、保留历史引用、逐项复核并等待main CI的合并方案。当前请求只准备材料；只有另行明确授权才实施合并。

没有需要重批的预算/模型运行包；也没有新增模型执行或产品路由决定。本材料不以CI绿灯替代本人审核。未对440个文件重新做完整逐行审计，私有原件不在本次访问范围，历史被拒绝的原始门仍被拒绝。


## 本次材料验证与交付

已复算40行、20配对、分阶段/分类及重叠失败信号，归档源字节与用户文件一致，三个阶段spec/runtime指纹与冻结公开文件相符；19个PR的完整head、依赖与CI成功绑定一致。来源、NULL评分及旧审核拒绝保持。原C5裁决指纹仍为 `09392d883ca147c547e292384837cefe2dc84b10b1fcd9c9423da84e2725ec19`。

公开文档本地链接/折叠区、`check_release_consistency.py`、`check_secrets.py`、`audit_c5_final_decision.py`和`git diff --check`通过。修改仅限文档和其脱敏数据附件，运行代码、原eval证据、运行包及账本没有修改，主工作目录原有改动保持。无需为文档变化重跑模型或不受影响的CPU研究套件。

本补充分支为 `codex/c5-results-merge-review`，基于#26的精确head `0ac86c2a07955646319ac9ba9675bac5869cb3be`，不改#8～#26任何head。最终CI以补充PR对应提交为准：沿用现有工作流的impact/release/validate，Python/UI依文档影响跳过。仓库main与全部待合并Draft状态保持；本页不是自动合并指令。
