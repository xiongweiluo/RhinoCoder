# 将已准备的40题整理为私有评测输入

2026-10-30所有者确认：已有40道题目文本或表格；尚不是可直接封存的case包。租约截止更新为**2026-11-04 20:00 Europe/Zurich**（19:00 UTC），延期费用未知；代理未采购、续租或更换资源。固定9小时48分完整窗口不变，最迟须在11月4日10:12前启动并另外留出预检时间。这个时间绑定不是执行批准。

本页接续[第二阶段完整方案](lora-phase2-final-freeze-20261027.md)，只补充格式填写与新资源绑定。原模型、权重、original、B契约、评分、40家族80槽、分层、统计、停止规则及第一阶段选择摘要均不变。10月27日公开冻结记录保留，不能用其旧租期规格进行新封存。

## 现在先做一件事：在私有环境补齐case字段

题目和答案留在所有Git worktree及公开部署目录之外，不发到聊天，不让本代理或参评模型补写/筛选。保留原始文本/表格；整理只把原意转为原契约，不根据模型表现修改任务、答案或难度。每题必须属于一个独立家族，不是同一模板改数字凑40题。

复制[单题空白模板](../eval/lora-development/final-case-blank-template.json)到自己的私有目录，填写40项后放在一个JSON数组中，保存为`cases.json`（UTF-8）。模板刻意使用`null`，**未填完不能通过校验**；它不含题目或答案，也不构成新测试集。表格可作填写工作稿，但封存入口只接受JSON。不要为通过格式检查把未知评分改成空对象或零。

| 字段 | 本人填写内容 |
|---|---|
| `schema_version` | 固定1 |
| `family_id` / `template_family` | 各40个唯一标识；4–80个ASCII字母、数字、下划线、点或连字符，首字符字母或数字。不能复用历史家族/模板身份 |
| `stratum` / `primary_tool` | 按下表原分层；核心工具填对应工具名，其他层填`null` |
| `task_text` | 原题意的自然语言输入，非空、≤4096 UTF-8字节；使用场景别名，不含真实GUID。不要附加参考操作、答案或评分说明 |
| `fixture_recipe` | 执行前场景准备，0–8项，每项`{"operation":工具名,"arguments":参数对象}`。真正空场景才填`[]` |
| `initial_assertions` | 准备后的初始场景应满足什么；`read_result`固定`null` |
| `expected_operations` | 私有参考操作顺序，最多3项，每项`{"name":工具名,"arguments":参数对象,"read_result":读取期望或null}`；写入的`read_result`为`null`，读取必须有期望 |
| `max_steps` / `max_writes` / `max_reads` | 原契约的精确预算：步数=`max(1,参考操作数)`，写/读数分别等于参考序列中的写/读数量。不是统一填3 |
| `final_assertions` | 最终完整任务成功依据；在模型消费前固定，不能只检查模型自述或包围盒 |

| 分层 | 家族数 | 原契约 |
|---|---:|---|
| `core_tool` | 12 | 每个核心工具恰好1家族；1次对应操作、1步 |
| `multistep` | 8 | 2或3次参考操作，2或3步 |
| `error_recovery` | 8 | 题目/初始场景包含预置事实错误，1–3次参考操作；不是运行时故意注入新异常 |
| `clarification` | 6 | 应澄清，参考操作`[]`，1步、0写、0读 |
| `refusal` | 6 | 应拒绝，参考操作`[]`，1步、0写、0读 |

先检查现有40题是否自然满足这个已固定的分布。若不满足，只反馈各层数量和缺口，不发送题目，不把多余题随意改标签，也不改变冻结评分或规模。题目本身尚未证明独立：后续仍须本人完成历史排除及语义近重复核查。

### 场景与评分字段

所有场景单位为毫米。创建操作采用原生实现的固定位置：box在WorldXY原点沿正轴延伸，sphere球心为原点，cylinder基圆位于WorldXY原点；若题目需要其他位置，用夹具中的移动操作表达。新对象别名由每份隔离文档的全局递增计数产生（类型加序号），不是每种类型各自重新计数；种子和任务中的创建共用该计数。不要凭私有真实GUID填写别名。

两组断言均恰好包含：`object_count`（0–16）、`objects`（别名到属性期望的对象）、`unchanged`（要求整个对象读回记录不变的已有别名数组，包含几何与属性）、`read_result`。每个被断言对象至少包含`volume`、`solid`、`face_count`；可按题意增加`min/max/centroid/edge_count/vertices/layer/color/groups/geometry_sha256`。具体比较行为见原[scorer](../training/c5_rhino_scorer.py)，容差不改。未掌握的几何/拓扑期望先保留未知并核查，不能用`null`或删除断言假装已知；格式检查不会证明这些值正确。

操作参数直接遵循[原JSON schema](../eval/c5/rhino-runtime-schema-v1.json)和[原生参数验证](../plugin/rhino_listener/c5_research_native.py)，不引入另一套工具语言：

| 工具 | 参数名 |
|---|---|
| `create_box` | `width, depth, height` |
| `create_cylinder` | `radius, height` |
| `create_sphere` | `radius` |
| `move_object` | `object_id, translate_x, translate_y, translate_z` |
| `rotate_object` | `object_id, angle_degrees, axis, center_point`（后两项支持null） |
| `scale_object` | `object_id, scale_factor, center_point`（中心支持null；比例为三项数组） |
| `set_object_color` | `object_ids, r, g, b` |
| `set_object_layer` | `object_id, layer_name` |
| `group_objects` | `object_ids, group_name`（名称支持null） |
| `boolean_difference` | `input0_ids, input1_ids` |
| `get_bounding_box` | `object_id` |
| `get_scene_summary` | 空参数对象`{}` |

夹具只允许前三个创建、移动/旋转/缩放、颜色/图层/分组；不允许读取或布尔操作作为种子。仅`get_bounding_box/get_scene_summary`计为读取。所有几何与读取结果的具体值由本人独立填写，本页不提供新题答案。

## 本机格式检查：可选辅助，不增加审批层

本人填写后，在**macOS终端**运行下列命令；入口会不回显地询问私有`cases.json`路径，不要把路径写进命令或聊天。不能由代理代跑私有输入。

```bash
/opt/anaconda3/bin/python3.13 -I -S -B /Users/xiongweiluo/.rhinocoder-final/comparison-20261030/source/tools/seal_lora_final_owner.py --check-cases
```

这一模式复用原`validate_case/compile_cases`，不修数据、不写文件、不封存、不启动模型或Rhino，不创建正式claim。它只输出数组行号与白名单错误码、结构是否通过；不打印题文、身份、参数、答案、路径或原始异常。可以在任何模型消费前修正格式后重复检查，不消耗正式槽位；不构成新增研究步骤或逐项批准要求。

- `case_structure_passed_not_sealed`：40项结构、固定分层/核心工具覆盖、80槽编译与通道字节预算通过。**尚未完成独立性、排除、几何正确性、加密或封存**。
- `row`从1起对应JSON数组位置；每行报告最早结构错误。例如`dispatch_or_step_budget_differs_from_expected_sequence`表示读/写/步数未与参考序列一致。
- `private_case_check_failed_no_authority_created`：在本人环境检查JSON编码、路径位于所有worktree之外、公开部署完整性；不要发送原始文件或异常截图。

如果需要协助，只返回这段脱敏JSON或错误码。代理无法也不会由其判断私有答案是否正确。

## 随后完成一次封存、一次集中执行确认

接着按[已有四项输入与本人确认表](lora-phase2-final-freeze-20261027.md#所有者需在私有环境准备的四项输入)准备完整历史排除、本人确认及独立加密往返副本；不新增材料类别。四项齐备后使用同一新版入口，去掉`--check-cases`，完成一次私有CPU封存；仅返回工具输出的`owner-receipt`，不要返回runtime、scorer-cases、题文、答案或密钥。

新公开规格/本机检查见[10月30日准备记录](../eval/lora-development/final-public-freeze-20261030.json)。当前租期身份将进入回执，原10月27日部署和记录保留。目标Linux新版实际入口尚须恢复连接后CPU核验；这不妨碍本人整理输入，也不能据旧版CPU结果声称新版目标部署通过。新版完整CI亦以PR #31当前提交结果为准。

回执、源码/环境、最新CI齐备后，形成唯一精确最终执行方案供本人集中确认；确认前不启动模型、Rhino、训练或正式比较，不自动合并。原C4/C5 NO-GO、历史失败与未知、默认混合路线保留；本轮仅是同一第二阶段的准备接续。
