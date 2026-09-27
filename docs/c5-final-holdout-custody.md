# C5-1c：最终 holdout 独立保管与单次消费交接

日期：2026-09-27。状态：**开发侧实现、公开模板和自动测试已完成；等待 `repository_owner` 在代理不可访问的环境中生成、审计并加密 80 个全新家族，再只交回公开 commitment JSON。当前 `final_holdout_rows_read=0`，不授权 GPU、训练或最终评测。**

公开实现哈希和门禁状态见 [`eval/c5/final-holdout-gate-readiness.json`](../eval/c5/final-holdout-gate-readiness.json)；它明确保持 `owner_commitment_registered=false`、`training_authorized=false`。

## 1. 职责边界

- `repository_owner` 是唯一最终 holdout 保管人、唯一 `reviewer_1`；不要求 `reviewer_2`。
- 开发/训练代理不得创建、定位、打开、解密或看到 80 个家族的正文、明文路径或密钥。
- 仓库只接收公开 commitment：加密 artifact 的 SHA-256/字节数/格式、分层计数、工具覆盖、三个 Merkle root、排除清单哈希和保管人声明。
- 模板、preflight 和验证命令不寻找或打开 holdout。只有最终正式评测的 `claim` 在 append-only `started` 事件落盘并 `fsync` 后才首次打开**加密字节**；该 gate 本身不解密明文。
- 第一次 claim 无论后续哈希失败、基础设施中断或结果好坏，都永久阻止第二个新 run。恢复策略必须另行绑定同一 `run_id`、代码、adapter、阈值和 commitment，不能重置台账。

## 2. 冻结结构

最终 holdout 固定为 80 个不可拆分家族：

| 分层 | 家族数 |
| --- | ---: |
| 单步合法调用 | 40 |
| 澄清 | 12 |
| 拒绝或无工具 | 12 |
| 多步 | 8 |
| 错误恢复 | 8 |

12 个核心 invocation 工具各至少覆盖 3 个家族。正文必须使用 `rhinocoder-c5-dataset-v2`、契约 `qwen25-v4-selector-v3-json-invoker-c5-v1`，每个家族增加 `holdout_stratum`；所有内容的 `source_kind` 为 `repository_owner_holdout`。严禁复用 A5、P2、R 已消费题、C5 开发 440 家族及其数字模板或 0.92 以上近重复。

## 3. 保管人侧操作

以下命令只能由仓库所有者在代理无法访问的独立目录执行。明文 JSONL、加密 artifact、私钥和命令历史不得放入仓库、PR、聊天或训练主机的开发目录。

1. 独立撰写 80 家族 JSONL，并在本地完成加密。加密格式只接受 `age-x25519` 或 `aes-256-gcm`；密钥不交给开发代理。
2. 使用已冻结代码和本地 tokenizer 运行 owner-only 构建器。三个 `--development` 参数分别指向正式冻结的 train/validation/development JSONL：

```bash
python tools/c5_holdout_custodian.py \
  --plaintext-holdout /owner-private/c5-final-holdout.jsonl \
  --encrypted-artifact /owner-private/c5-final-holdout.jsonl.age \
  --encrypted-format age-x25519 \
  --tokenizer-snapshot /Users/xiongweiluo/RhinoCoder/data/training/tokenizer-cache/models--Qwen--Qwen2.5-Coder-7B-Instruct/snapshots/c03e6d358207e414f1eca0bb1891e29f1db0e242 \
  --development /Users/xiongweiluo/RhinoCoder/data/training/c5/v2/accepted/train.jsonl \
  --development /Users/xiongweiluo/RhinoCoder/data/training/c5/v2/accepted/validation.jsonl \
  --development /Users/xiongweiluo/RhinoCoder/data/training/c5/v2/accepted/development.jsonl \
  --output /owner-private/c5-final-holdout-public-commitment.json
```

构建器会执行同契约 render/parse、schema、2,048-token、敏感信息、组内形状、近重复、开发集与历史排除、分层和每工具覆盖检查。它拒绝把明文、加密 artifact 或 commitment 暂存到仓库内。

3. 只把 `c5-final-holdout-public-commitment.json` 交回。不要提供其他路径、正文或密钥。可对照[公开字段模板](../eval/c5/final-holdout-commitment-template.json)，但不要手工把占位符冒充有效摘要。

## 4. 开发侧登记和零读取 preflight

收到公开 JSON 后：

```bash
python tools/c5_holdout_gate.py verify-commitment \
  --commitment /safe-handoff/c5-final-holdout-public-commitment.json

python tools/c5_holdout_gate.py register \
  --input /safe-handoff/c5-final-holdout-public-commitment.json

python tools/c5_holdout_gate.py preflight
```

`register` 使用不可覆盖创建；一旦 `eval/c5/final-holdout-commitment.json` 存在，任何修改都必须升新实验版本，不能覆盖。preflight 只验证公开元数据和消费台账，必须返回：

- `plaintext_opened=false`
- `encrypted_artifact_opened=false`
- `final_holdout_rows_read=0`
- `new_run_allowed=true`

只有上述状态、C5-2/3 的正式 adapter 与代码、统计阈值和最终运行清单全部冻结后，才能为 C5-4 明确授权一次 `claim`。本阶段不会执行该命令。

## 5. 一次性 claim 与统计边界

正式运行时必须显式传入 commitment、代码、adapter 和阈值哈希。gate 先持有独占锁并 append+fsync `started`，随后才校验加密 artifact；成功后将一次性 decryption permit 写入 Git 忽略、权限 `0600` 的私有文件，终端不打印 permit。

最终原始结果应只包含每家族的 base/LoRA 配对结构化判分和必要运行证据。`statistics` 对 80 对结果机械计算 parse/tool/arguments/sequence exact、净胜、双侧 exact McNemar、固定种子 10,000 次 paired bootstrap、澄清/拒绝正确率和关键安全错误：

```bash
python tools/c5_holdout_gate.py statistics \
  --input data/training/c5/final/raw-scored-results.jsonl \
  --output data/training/c5/final/offline-summary.json
```

即使 `offline_gate_passed=true`，输出也固定为 `overall_c5_decision=not_authorized_by_offline_gate_alone`。它只允许继续 C5-5 控制器兼容性；不能自动判 `GO`、运行 Rhino、切换默认路线或修改 C4/v8 历史结论。

## 6. 当前未满足项

当前尚无 owner commitment，因此 C5-1c 未完成。其后仍依次需要：C5-2 CPU/有界 GPU 工程门、C5-3 唯一正式训练、C5-4 一次性离线评测、C5-5 控制器兼容性；只有前述离线门通过，R 的最小研究收尾和 C5-6 真实 Rhino 小门才变为当前依赖。
