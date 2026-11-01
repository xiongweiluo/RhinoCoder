# 第二阶段保管：取消两份独立确认文件

2026-11-01，所有者明确确认已完成防止新旧题重复及核查记录，并要求不再准备 `exclusions.json`、`attestation.json`。该直接指令已记入[公开保管政策](../eval/lora-development/final-custody-policy-20261101.json)，替代10月27日方案中提交这两份文件的要求。无需再次批准这一规范调整。所有者此前返回的脱敏结果已通过40家族/80槽结构检查；这不等于机器验证几何正确性或独立性。

## 现在只准备两个私有文件

1. 已通过检查、由本人核查的 `cases.json`。
2. 当前这份 `cases.json` 的加密副本，格式为 `age-x25519` 或 `aes-256-gcm`。本人核实解密往返一致，密钥独立保管。

两文件留在所有Git worktree及公开部署目录之外。另选一个尚不存在的私有输出目录；不需要制作排除清单或确认表，也不需向代理交出旧题、新题、答案、路径或密钥。

材料齐备后，在macOS终端运行：

```bash
/opt/anaconda3/bin/python3.13 -I -S -B /Users/xiongweiluo/.rhinocoder-final/comparison-20261101-preflight/source/tools/seal_lora_final_owner.py
```

依次输入：case路径、加密副本路径、新输出目录、加密格式。路径不回显，不加外层引号。最后输入一次 `SEAL`，只确认本次文件对应已核查版本、密文已完成往返核对、密钥/明文未交给代理、当前题目未经模型或正式运行消费。此前已确认的查重与核查记录直接引用，不再逐项填写旧表。这一步绑定当前文件，不是新增模型执行批准。

工具生成 `runtime-package.json`、`scorer-cases.json` 和脱敏 `owner-receipt.json`，文件0600、目录0700；不覆盖原件或已有封存。仅返回屏幕打印的脱敏回执。没有加密副本时先完成加密，不用空文件或把明文改后缀替代。

## 封存失败时先做一次只读预检

本人报告旧入口返回通用封存失败；失败原因及已有输出是否部分写入未知，不能据此声称封存成功。现已补充阶段错误码，同一入口增加可选只读模式：

```bash
/opt/anaconda3/bin/python3.13 -I -S -B /Users/xiongweiluo/.rhinocoder-final/comparison-20261101-preflight/source/tools/seal_lora_final_owner.py --check-seal
```

沿用两文件和新输出目录的输入，不重新准备已取消的清单/确认表。`SEAL`在此模式仅确认当前文件绑定事实；`--check-seal`始终在写入之前返回，不创建目录、封存文件、claim或许可。成功状态为`seal_preflight_passed_not_sealed`，不是实际封存；也不会解密核实内容或证明实际写盘必然成功。

失败仅输出`stage/input/code`和本次是否可能已创建部分输出；不输出路径、任务、答案或原始异常。只读预检本次不会写文件，但不能据此判断上次输出状态。保留旧输出，不覆盖或删除。主要错误码：

| 错误码 | 含义与处理 |
|---|---|
| `path_has_outer_quote` / `empty_path` | 去掉路径外层引号，输入路径本身；不发送实际路径 |
| `output_directory_already_exists` | 指定一个尚不存在的新输出目录，保留旧目录；不要先手工创建末级目录 |
| `output_parent_missing` | 新输出目录的父目录必须已存在 |
| `input_file_missing_empty_or_over_size_limit` / `invalid_json_or_encoding` | 在本人环境核对输入文件及JSON；不发送文件内容 |
| `encrypted_file_missing_symlink_empty_or_over_10_MiB` | 密文须为非符号链接的普通文件，非空且不超过10MiB |
| `encryption_format_must_be_age_x25519_or_aes_256_gcm` | 填写实际使用的两种支持格式之一；不猜格式或以明文替代 |
| `current_file_binding_not_confirmed` | 当前文件/加密/未消费事实尚未确认；不自动填真 |
| `new_set_numeric_template_overlap` / `new_set_near_duplicate_overlap` | 新集内部重复检查拒绝；保留原文件，先核查重复机制，不据此修改评分或追分选题 |
| `published_historical_fingerprint_overlap` | 与已有公开历史指纹重合，需本人核查；未执行全量历史私有扫描 |
| `unexpected_error_details_withheld` | 返回阶段与错误码，保留未知；不要发送原始异常或私有材料 |

预检不会改原结构、重叠阈值、评分或两文件政策。通过后沿同一入口去掉`--check-seal`才会尝试实际封存；仅完整成功回执可用于后续精确最终执行审批。

## 回执如实区分证据来源

- v2回执自动记录本人本次指令、封存时间、case/顺序/runtime/密文及公开规格摘要，不再需要独立 `attestation.json`。
- 全量旧题查重改为**所有者已确认**的事实来源；新版入口不读取完整历史清单，不核对旧80行Merkle身份或历史清单数量，不再需要 `exclusions.json`。
- 仍保留无需旧私有文件的检查：新40题内部数字模板/近重复、已有公开历史指纹、原case契约、40/80及分层、核心工具覆盖、字节预算。原近重复阈值不改。这些不证明全量历史排除或语义独立。
- `exclusions`及全量`automated_overlap_count`为 `null`；`historical_inventory_machine_checked`为 `false`。不会把“未执行机器全量扫描”写成“机器发现0重叠”，也不会把本人概括确认展开为未逐项核实的旧八个布尔断言。
- 单独记录新集内部和公开指纹检查的实际通过状态。加密往返及未消费是本人对当前文件的绑定声明，工具不接收密钥或自行解密。

原v1函数与回执验证保留以解释历史证据和回归，新版本交互入口仅走v2。新旧规格、部署、失败和研究记录均保留；旧回执/旧许可不能冒用于新包。新版正式入口接受准确绑定的新回执后，仍必须另有所有者最终执行批准才会读取运行包和启动。

## 研究边界与接续

原11组选择摘要、基座＋checkpoint132、original、B契约、40家族80配对槽、评分、统计、时间/存储/停止规则不变。保管证据提交方式的变化单列，不伪称此前机器排除门已通过；原C4/C5 NO-GO、历史失败与未知及默认混合路线保持。

[新版公开准备记录](../eval/lora-development/final-public-freeze-20261101-preflight.json)绑定实际部署字节和CPU验证。当前仍没有实际新集封存回执或正式许可；目标Linux新版CPU准备和新提交CI另行核实，不继承旧版结果。未读取私有题目/答案，未进行模型、GPU、Rhino、训练或正式测试；不采购、续租、换资源或自动合并。租约仍按所有者报告至11月4日20:00 Europe/Zurich。

下一集合是在上述两文件流程中取得真实脱敏封存回执，结合新版公开包、目标环境和CI完成唯一精确最终执行方案，供所有者集中确认。研究主任务继续，不因本次文档或PR更新结束。
