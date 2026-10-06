# C5-6：公开承诺登记与实际现场阻塞（2026-10-06）

状态：`PUBLIC_COMMITMENT_REGISTERED_ACTUAL_RHINO_CLOSURE_BLOCKED_NOT_EXECUTION_AUTHORITY`。本轮完成登记、端口适配和只读诊断，**未完成新的现场工程门、正式冻结、正式执行或 C5-7 裁决**。完整无正文观察见[只读审计记录](../eval/c5/formal20-field-readonly-audit-20261006.json)。

## 已完成：保管人公开承诺登记

[公开 JSON](../eval/c5/rhino-formal20-public-commitment-v1.json)经原严格公开校验器验证，固定20家族/40路线槽、12/2/2/2/2分层、12核心工具各1家族、反平衡 seed `20261003`；草案已绑定承诺及顺序，不是可执行 spec。

- 规范化 SHA-256：`41c92c723df663782000a4e34934a371a2a552e5ef27d6052b7c6d07656ebaf4`。
- 原公开文件字节 SHA-256：`726ad282775568bd63472ea8fa164ab489996c8fd0cd47126585e1cf7eb40745`，登记文件保持相同字节。
- 家族根：`759fa83bb5e0f8c58f40b5ec0926e4be0f1ce25c24634859b7dacbc22f003791`；40槽顺序 SHA：`95f6d650c644bff34ef12df07266865cc1acc01db07c8fffd89598b11600580c`。
- 绑定历史补充清单 `f8343ca0…445d46`、440家族开发冻结、历史排除与原80公开承诺；公开字段未包含正文、答案、明文路径或密钥。

所有者已私下运行自动排除预检（20候选/440开发/80原集/1013额外，exact/numeric/0.92近重复为0），报告完成人工审核，并报告 `ROUNDTRIP_BYTE_IDENTICAL`。JSON中相应保管声明为true。**这些是保管人侧记录，不是代理读取私有包后独立重算的结论。**代理未打开密文、identity、候选或原80正文，也未验证密文与私有家族根的对应关系。正式入口未来须在新精确批准和不可覆盖 `started` 后，由保管人核对封存身份再解密；现在仍为零消费。

可直接重复运行的是以下**公开、无消费**校验，不需私有路径，也不要求保管人重新排除或重新封存：

```bash
cd /Users/xiongweiluo/.codex/worktrees/c5-engineering-gate/RhinoCoder
python tools/c5_formal20_public_preflight.py --commitment eval/c5/rhino-formal20-public-commitment-v1.json
python tools/c5_formal20_owner_run.py preflight
```

## 已完成：新端口与资源只读核对

当前端口 `175.155.64.171:22159` 的 ED25519 指纹与所有者此前从服务商实例核实的 `SHA256:PW+vIRRrOBl66FAaU0iN6WmbLuYt/wPhZxwMZpObjFI` 相同。使用仅含该端口的独立 known_hosts，未改全局 SSH 信任库；所有者在自己的 Mac 终端建立认证，密码不进入代理。未冻结的正式适配器/草案已改为新 socket/端口，检查 pin 文件 SHA 并维持 strict checking；旧 B 源码、授权和部署不修改。

远端只读核对 RTX3090 24576MiB，11MiB使用、0%利用率、驱动550.107.02；基座14文件/revision `c03e6d…e242` 的manifest与checkpoint132两adapter保持原身份（adapter `305d7270…dc22cae`）。检查的是**已退休 B 部署**的固定只读入口，不是新的正式部署或已加载依赖闭包。环境清单记录21614个distribution文件，但存在 `pip:../../../bin/pip3.13` 缺失metadata引用；不得据此把新环境冻结标为完整通过，也不擅自安装/升级依赖。

补充只读loader import核查通过：PyTorch2.10.0+cu126、CUDA未初始化、模型未加载、生成/holdout0，仍只绑定旧B部署及其环境身份；它不消除pip安装metadata缺项或证明新正式源码部署。Mac现有tokenizer的CPU预检覆盖3551个已加载环境文件、原B公开开发题的假设渲染最大1757/2048 tokens（无模型）；不是新开发题或正式20题的token/实际闭包证明。

只读核对 A/B 原结算分别17.613689741992857/322.4134741070011秒，合计340.027163848994秒，均为停止且禁止重放；远端正式20题状态目录不存在。此次未加载模型、调用生成或重跑任何旧研究。GPU空闲是观察时状态，执行前仍需新鲜核对。

[v5资源边界](../eval/c5/rhino-resource-boundary-v5-20261006.json)登记所有者报告：**2026-10-07 19:00 Europe/Zurich（17:00 UTC）到期，18:45（16:45 UTC）前停止生成，留至少900秒导出**。服务商到期尚未独立验证。开发≤3600、正式≤10800、研究合计≤14400、原累计≤57600秒不变；剩余开发上限约3259.973秒还需扣除任何新增用量。旧v2/v3/v4期限保留为历史，续租不是新执行批准。

## 实际阻塞：严格嵌入式运行时闭包

[只读诊断入口](../tools/c5_field_rhino_readonly_preflight.py)在当前 Rhino 8.21.25188.17002 / Python3.9.10 内执行三次递进只读诊断（首个错误、来源列表、全缺项列表）；三份本地报告均不可覆盖保存，并在公开审计登记各自SHA。没有fixture、Idle hook、工具派发、模型或题目读取；活动文档0对象、serial268435457、前后内容摘要相同，无活跃研究namespace。

当前严格[环境守卫](../plugin/rhino_listener/c5_formal20_environment.py)实际拒绝：

- Python `CLR` 与 `clr` 的 `__file__` 都为 `unknown`，不是可哈希的绝对文件。
- 四个非文件动态程序集：`Anonymously Hosted DynamicMethods Assembly`、`__Python_Runtime_Generated_Assembly0`、`Snippets`、`Snippets.scripting`。

诊断额外收集339个文件型Python/CLR/宿主来源的字节哈希，但这是**部分库存，不是完整闭包**。严格库存因拒绝而为空；其空对象SHA不能作证明。当前守卫保持原样，不按程序集名称放行、不把动态对象假称字节冻结，不设置 `actual_mac_rhino_gpu_import_closure_verified=true` 或现场探针通过。此观察不是已消费实验失败，也不影响 A/B、C4、v8 或原80裁决。

## 当前可交付边界与后续顺序

1. **已完成**公开承诺、期限和新端口登记；保管人不需再次发送私有材料。
2. **阻塞**新的仅合成现场工程门：所有者已同意仅设计/合成验证“冻结宿主/生成器＋动态来源审计”。[设计稿与21项合成正负控](c5-host-provenance-design.md)已交付，明确宿主信任假设、无法证明发射字节/因果来源的限制、拒绝条件和下一观察器交付；原守卫/正式门禁未放宽。设计许可不批准实施到真实执行链路、warmup或新运行；另一选择是保留原不变量并寻找可满足它的宿主，当前尚无该证据。
3. 新方案可核实后，另建独立开发ID/入口和完整 spec/runtime、实际Mac/tokenizer/GPU依赖/资产/预算证据，双CI及所有者对两个新精确哈希批准，才运行单次合成探针并独立审计。旧B/native12授权不得复用；新公开开发题须由保管人私下排除与封存20题重合，代理不获得正式正文。现在尚无可诚实请求批准的完整开发freeze。
4. 现场门通过后，另行冻结正式20题执行的完整spec/runtime（不是现在的draft）、40槽顺序、评分器、资源与停止规则，再取单独精确批准。正式入口不允许提前探题、补题、修解析、重试或更换run。
5. 正式单次运行/联合审计完成后才进入C5-7裁决和作品集报告。门槛保持LoRA≥14/20、净胜≥3、关键安全/重复写/未核实清理0；整体GO不自动切默认混合路线。
6. PR收口可并行，但仅由所有者reviewer_1决定merge；本轮不合并、不打包脏主工作区或全部R证据。完整产品UI/开放、P2b、精简D继续延期。

“全部完成”的持续请求不替代新的精确执行批准，也不能为赶租期把真实阻塞写成PASS。
