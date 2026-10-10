# C5-4/5 独立保管人单次交接

> **2026-10-02：原run已完成并消费，本文入口现在禁止再次执行。**公开证据已完整回收和独立审计，C5-4/5通过，见[最终报告](c5-final-evaluation-report.md)。以下说明只保留为当时交接协议，不是恢复或重跑命令；原账本和run目录不可重置。

状态（2026-10-01）：C5-3完整训练/登记/73文件逐字节导出核验、最终代码冻结和真实零读取preflight全部通过，**已可交给所有者单次执行**。本文不是最终消费收据，不表示 C5-4/5 已通过。

最终冻结：[清单](../eval/c5/c5-final-evaluation-freeze.json)，canonical SHA-256 `9a57c1672e5d49d6b1ce8c23ee36c1fa6cf0b4570d08d9030df1c7bd2860a5d8`；绑定源码 `ced0de9`、checkpoint132 / adapter `305d7270…2cae`、28个直接源码/依赖及导出证明、原门槛与commitment。[真实preflight](../eval/c5/final-preflight-ready-20261001.json)返回ready、最多14400秒、claim/rows为0。初次隔离部署缺失requirements.txt的[失败记录](../eval/c5/final-preflight-deployment-failure-20261001.json)保留；只补齐既定哈希文件，未重生成或修改冻结清单。

仓库所有者是唯一 `reviewer_1` 与最终 holdout 独立保管人；不需要第二个人。开发代理完成训练和零读取 preflight，但不代替保管人解密、打开原始输出或触发最终消费。公开 commitment 是 `4fe1796cc1e5b19f7d81b79fdf883463d7bb77d6af012d9aa1900208ec35ebaa`；不更换文件、任务或门槛来重试。

## 执行前必须全部成立

- C5-2 两个真实工程 run 通过，C5-3 唯一正式 run 完整结束并登记固定 adapter；远端/本地逐文件导出审计一致。
- `tools/freeze_c5_final_evaluation.py` 以实际 formal result/registry 生成不可覆盖的最终冻结记录，绑定 checkpoint、adapter、代码、阈值和 commitment；远端部署精确匹配。
- 开发代理只运行远端 `--preflight`：`ready=true`、`final_holdout_rows_read=0`、`consumption_claim_executed=false`。这不打开加密文件、不加载模型权重、不创建 final run。
- 保管人自己知道原来封存的 age 加密 artifact 与 identity 文件；二者不交给代理，不放到仓库或聊天，不为运行重新生成 holdout。
- 明确唯一的私有状态目录（仓库外，0700）。若以前已经 claim，必须使用原权威台账并停止；不能换目录、删除或重置账本来取得第二次机会。

## 保管人自己的交互式终端

使用已通过冻结检查的 checkout 和 Python 环境，把示例中的 checkout/私有状态目录/已验证 SSH host/port 换成实际值。实例地址不固定在公开源代码中。密钥及加密 artifact 的路径会以隐藏输入提示读取，不放在命令参数、shell 历史、公开文档或聊天中。

```bash
python /verified-checkout/tools/run_c5_owner_final.py \
  --owner-state-dir /owner-private/c5-final-state \
  --final-freeze /verified-checkout/eval/c5/c5-final-evaluation-freeze.json \
  --ssh-host linux@VERIFIED_HOST \
  --ssh-port VERIFIED_PORT
```

若现有认证 master 仍有效，可另加 `--ssh-control /operator-private/ssh-control`。严格 known_hosts/ED25519 检查保持开启；不通过时先停止，不能临时关闭主机校验。

依次输入隐藏的加密文件路径、隐藏的 age identity 路径，然后逐字输入完整公开 commitment SHA-256。客户端先完成真实远端 preflight，随后 append+fsync 权威台账的 claim，才解密至保管进程内存并校验三个 Merkle root。只有私有 stdin 传给认证 GPU；不写明文数据文件，不传 identity/密钥。

整个最终 run 只运行一次：冻结基座/唯一 LoRA 同输入、同确定性解码，家族随机顺序、基座/LoRA 次序 counterbalanced，不修复、不重试、不用黄金选择强制 invocation。训练主机独占创建 `final` 目录；失败也不会允许换 run ID 再跑。原始生成仅保留为 owner-private 证据，开发代理不得读取。

数值加载也与正式 validation 对齐：NF4/double quant/BF16 matmul，使用相同 k-bit preparation 将非量化 embedding/head/norm 保持 FP32；最终进程不启用梯度 checkpoint/backward。两路共享同一基座 tensor，只 disable/enable 固定 adapter；不把标准 BF16 非量化层的另一个加载方式偷偷混入比较。

冻结统计的关键安全计数要求 **base 与 LoRA 两路合计为 0**，不是只核对 LoRA；拒绝分层中选出工具会保守计为关键预测错误，即使本入口没有实际 dispatch。报告同时提供分路计数以区分归因，但不能在看到最终结果后把合计门改成仅 LoRA 门。

## 回传与停止规则

只回传客户端输出的聚合报告（或私有状态目录中的 `c5-public-final-report.json`）；不要回传明文、密钥、加密文件路径、raw generations 或含任务正文的错误栈。开发侧可以再核对公开哈希化收据，不用结果调参。

- claim 前的检查失败：没有消费，修复明确的基础设施/部署问题后才能再次 preflight；不自动修改实验设计。
- claim 后任何解密/网络/模型/预算失败：保留原台账与 `c5-failed-consumption.json`，不自动再消费。程序只打印通用失败类型，避免泄露私有路径；保管人独立核实证据后决定后续流程。
- C5-4 离线必要门失败：C5-5 状态为 `blocked_by_offline_gate`，保留所有结果，不靠解析修复或降低门槛放行。不能自动运行 Rhino。
- C5-4 通过且 C5-5 严格兼容性通过：只解锁后续条件式 R 最小研究收尾/C5-6 预注册。仍不是总 `GO`，不改默认混合路线、不改 C4 `NO-GO` 或 v8 59/60 `formal_quality_fail`。

相关：[GPU 执行包](c5-gpu-execution.md)、[保管历史冻结](c5-final-holdout-custody.md)、[owner client](../tools/run_c5_owner_final.py)、[最终 GPU 入口](../tools/run_c5_final_remote.py)。
