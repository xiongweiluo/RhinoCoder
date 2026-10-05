# C5-6 正式 20 题：保管人侧准备规范（不含题目）

2026-10-05。此页只定义**私有候选包格式与预检方法**；仓库里没有新 20 题正文或答案。仓库所有者本人是唯一 `reviewer_1` 和独立保管人；不要把候选 JSONL、原 80 明文、答案、密钥、实际私有路径或替换了占位符的命令发送给代理、放进仓库/PR，或放到 GPU 开发目录。本页和[公开 draft](../eval/c5/rhino-formal20-spec-draft.json)均为 `execution_ready=false`，不能启动正式运行。

## 一份家族对应一行私有 JSONL

恰好 20 行，每行是独立 JSON 对象，字段必须恰为下列 13 项；不要加入物理 GUID、模型提示修补、可见答案标签或可选隐藏字段。

| 字段 | 私有准备规则 |
| --- | --- |
| `schema_version` | 整数 `1`。 |
| `family_id`, `template_family` | 各 4–80 位 ASCII 字母/数字/`_.-`，首位字母或数字；20 行内分别唯一，不复用训练/开发/历史家族或模板。 |
| `stratum` | `core_tool` 12、`multistep` 2、`clarification` 2、`refusal` 2、`error_recovery` 2。 |
| `primary_tool` | 仅 12 行 `core_tool` 各填一个不同的 C5 核心工具名；其余填 JSON `null`。不得改用 R 缩减 schema。 |
| `task_text` | 每家族唯一的原始自然语言意图，≤4096 UTF-8 字节；这是唯一进入模型提示的题目文本。不要写预期工具名、标准参数或评分答案。`error_recovery` 在这轮约定为**题面已经提供事实性的先前错误上下文**，不是运行中自动重试或注入新 oracle。 |
| `fixture_recipe` | 0–8 个 `{ "operation": ..., "arguments": ... }`，仅在独立未保存 headless 毫米夹具内、模型调用前执行；只允许原 schema 的创建、变换、颜色、图层或分组操作。不能对活动文档执行；种子步骤、实际别名和读回须另留证并审计。 |
| `initial_assertions` | 夹具播种后、首轮模型调用前的独立读回断言，结构严格为 `object_count`、`objects`、`unchanged`、`read_result`；最后一个必须为 `null`。每个被断言的实体至少包含真实 `volume`、`solid`、`face_count`，不能只靠 bbox。 |
| `max_steps`, `max_writes`, `max_reads` | 最多分别 3/3/3；`max_steps=max(1, expected_operations 的长度)`，写/读上限恰为预期序列中相应操作数。它们是安全上限，不向模型暴露答案。 |
| `expected_operations` | 私有、有序的 0–3 项 `{ "name": 核心工具名, "arguments": 原完整 schema 下的标准参数, "read_result": ... }`；写入的 `read_result` 为 `null`，只读填写真实预期结果。澄清与拒绝必须为 `[]`，零派发。核心工具题恰一项且与 `primary_tool` 一致；多步至少两项。 |
| `final_assertions` | 任务终态的同形独立断言；对几何/属性/未改变对象、只读结果和场景保持给出精确预期。评分器会把它与**实际 Rhino 原生读回**比较，不把这些字段发给模型。 |

上述结构由[私有 case 验证器](../training/c5_formal20_plan.py)机械检查。它只能证明形状、覆盖、预算与原生参数 schema，不证明题目语义正确、几何期望可达或与旧题不相似。保管人须在封存前人工检查题意、夹具、预期参数/结果、实际几何、模板族和语义近重复；不确定项换题于封存前，封存后不得补位。

20家族规范化JSON总大小须≤512KiB。夹具/预期调用中的图层和组标签使用公开合成名称：`Default`或`C5-`加1–64位ASCII字母/数字/下划线/短横线；不使用真实客户、文件路径或私有项目标签。拒绝题可描述危险操作意图，但不要加入真实凭证/个人信息或需要云端外传的敏感数据。结构预检不代替这项语义审核；新的研究隐私策略与现场验证边界见[工程准备](c5-rhino-formal20-engineering-readiness.md)。

## 私下排除及预检命令

准备完整的 A/B/native12 开发题与所有 R 已消费任务的额外排除 JSONL；每行至少需可比较的 `task_text`、`user_step`、`instruction` 或 `records[0].user_step`。工具无法证明这份额外清单完整，保管人须亲自核对。原 80 私有明文只由保管人本机读取，工具会与仓库公开 Merkle root 核对身份；**代理不运行下列命令或读取其输入。**

在仓库代码目录下，由你本人在私有终端运行；下面都是占位路径，不要把替换后的命令贴回聊天：

```bash
python tools/c5_rhino_formal20_owner_exclusion.py \
  --candidate /owner-private/new-rhino-20.jsonl \
  --original80 /owner-private/original-c5-80.jsonl \
  --development /owner-private/frozen/train.jsonl \
  --development /owner-private/frozen/validation.jsonl \
  --development /owner-private/frozen/development.jsonl \
  --extra-exclusion-jsonl /owner-private/all-consumed-development-and-r-tasks.jsonl
```

预检会先校验上述完整 case 结构和 12/2/2/2/2 覆盖，再验证 440 开发文件冻结 SHA、原 80 Merkle 身份、候选与旧题的 ID/数值模板/0.92 文本近重复。终端只输出无题目正文的聚合状态或错误类别。成功状态仍固定为 `formal_commitment_ready=false`，因为完整 R 清单、语义审阅、实际夹具/评分验证和加密封存不能由文本近重复算法代替。**不要只发送“预检通过”就让代理运行。**

## 私有审阅、加密与公开承诺

私有包通过人工审阅后，本次现场入口请选择 **`age-x25519`**，并在私有环境完成**解密回读与原候选逐字节一致**的核对。公开承诺构建器历史上也接受`aes-256-gcm`元数据，但当前现场入口未实现AES解密，不得据此宣称可执行。候选、密文、identity各为普通非符号链接文件、权限`0600`，父目录在所有工作树外且`0700`；age可执行文件及其SHA须纳入新冻结。不要把密钥、解密命令或明文放进仓库、PR、聊天或 GPU 开发目录。公开承诺构建器不能替你证明密文确实对应候选，因此要求你对回读、完整 R 清单、语义近重复与实际夹具/评分断言作出真实的私有声明；不能机械把这些布尔值填为 `true`。

私有声明 JSON 的字段必须恰为 `actor`=`repository_owner`、`sealed_at_utc`（以 `Z` 结尾的有效 UTC 时间），以及五个审核布尔项：`full_r_exclusion_inventory_reviewed`、`semantic_near_duplicate_review_passed`、`fixture_and_expected_geometry_reviewed`、`encryption_roundtrip_verified`、`keys_not_shared_with_development_agent`。确认每项真实完成后，在保管人控制的、仓库外权限 `0700` 的目录中存放此声明、候选和密文。下列命令也只由保管人运行，且不会启动模型、Rhino 或正式 run：

```bash
python tools/c5_formal20_owner_commitment.py \
  --candidate /owner-private/new-rhino-20.jsonl \
  --original80 /owner-private/original-c5-80.jsonl \
  --development /owner-private/frozen/train.jsonl \
  --development /owner-private/frozen/validation.jsonl \
  --development /owner-private/frozen/development.jsonl \
  --extra-exclusion-jsonl /owner-private/all-consumed-development-and-r-tasks.jsonl \
  --encrypted-artifact /owner-private/new-rhino-20.jsonl.age \
  --encrypted-format age-x25519 \
  --owner-attestation /owner-private/manual-review.json \
  --output /owner-private/c5-rhino-formal20-public-commitment.json
```

输出使用不可覆盖创建；成功时终端只给出无正文的承诺 SHA 与计数。只把**生成的公开承诺 JSON**交回，且交回前自行确认其中没有正文、答案、私有路径或密钥；不要把候选/密文/声明/原80发给代理。公开承诺只包含密文 SHA/字节数/格式、20 家族 Merkle root、分层/工具覆盖、反平衡顺序哈希、排除输入身份哈希、零重合声明和签署时间，仍固定 `execution_ready=false`。它经开发侧只读验证、真实适配器和独立原始证据审计准备完成、完整 spec/runtime 两个**新**哈希冻结并获你单独精确批准后，才可能登记一次性 `started` 并解密执行。B 的批准和八槽结果均不能替代该门。[整体边界](c5-rhino-formal20-handoff.md)继续适用。

开发侧收到**仅此公开 JSON**后，可运行以下只读预检；本轮因为尚未收到承诺，没有对真实公开承诺运行：

```bash
python tools/c5_formal20_public_preflight.py \
  --commitment /safe-public-handoff/c5-rhino-formal20-public-commitment.json
```

它只核对固定字段、20/40分母、原80公开身份与既有冻结文件哈希、保管人声明和禁止私有字段，返回承诺 SHA；不会定位/打开加密 artifact、读取20题明文、申请 GPU 或建立消费 claim。通过也不等于正式批准。

也可在代码目录运行 `python tools/c5_formal20_owner_run.py preflight`：仅检查公开冻结准备，故意输出`execution_ready=false`和剩余缺项，不接受私有输入。正式执行命令应在现场合成工程门、完整spec/runtime新哈希和你的精确批准全部就绪后再交付；本轮不提供立即执行正式20题的指令。`formal20.started`一旦建立即禁止重复消费，解密/连接失败也不能改run ID重跑；不完整研究保留证据并另行裁决。正式后`audit`只读取既有私有状态，完整报告保留在保管人本机，对外只发布审核过的聚合结果。
