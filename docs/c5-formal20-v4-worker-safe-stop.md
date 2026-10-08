# 原formal20孤立worker的单次安全停止准备

2026-10-09（Europe/Zurich）。**仅准备，未发送信号；完整runtime/双CI和新的两精确哈希批准未完成。**这不是新评测、恢复原20题、E或质量结论。

## 完整准备和独立复核

[runtime](../eval/c5/formal20-v4-worker-stop-runtime-20261009-a.json)与[独立核查](../eval/c5/formal20-v4-worker-stop-preexecution-validation-20261009-a.json)已形成。源码0366c46双CI37856617361/37856623340成功，本地全仓1060 passed/8 skipped、最终针对性27控制通过。三份实际部署文件与Git/本地字节一致，1341系统stdlib/12映像、解释器和真实入口inspect-runtime环境比对通过；UID/boot/start tick/固定公开argv/cwd/executable匹配，新的state/grant/admission缺席。独立检查器首次仅接受/usr的假设错在标准库链接到/etc/python3.10/sitecustomize.py；已重新核对解析后的实际人口及原冻结SHA，不改源码/spec/runtime或真正guard，也不加载site。没有打开pidfd或发送信号。

唯一spec规范化SHA `a555bbe8d3a921cd81ebc43b28a81de8d124c5453cc8473015ff9a0b2f4b9fef`、runtime规范化SHA `2e5386a3a51caad22bedd460984eec149eeb8f42ec4917c9b419252369f60dbc`；当前等待完整发布双CI后集中请求本人新精确批准。源码字节SHA76573dcb…d1ccbc1，旧正式v4批准不复用。本节不是执行授权或实际停止结果，02:00苏黎世截止仍严格有效。

只读恢复认证后，nvidia-smi显示原worker PID43776占18744 MiB、GPU利用率0%。固定公开argv/cwd、UID1000、boot_id、启动tick451535及解释器字节已核实；本地SSH255并不证明远端退出。原正式消费/失败/磁盘证据不改，不能重新发送bootstrap或模型请求。远端驻留时间必须纳入资源风险，不能只引用本地结算1512秒。

## 精确范围

[spec](../eval/c5/formal20-v4-worker-stop-spec-20261009-a.json)固定唯一PID及启动tick/boot/UID/argv/cwd/executable SHA，新独立安全收尾ID `C5SAFE-FORMAL20-V4-WORKER-20261009-A`。父PID18255是观察值而非身份保证，允许其自然退出/重托管，不允许PID重用或目标身份漂移。固定截止为10月9日02:00苏黎世（00:00 UTC），不扩张模型/租期预算。

[独立标准库入口](../tools/c5_formal20_worker_safe_stop.py)使用已安装`/usr/bin/python3.10 -I -S -B`（无user/site/PYTHONPATH加载），先校验新spec/runtime和真实owner grant，永久O_EXCL admission，再固定pidfd、核对真实身份、重新校验冻结/截止，永久signal-attempt后仅一次SIGTERM，等待同一pidfd最多30秒。不用裸PID kill、进程组、SIGKILL、私有stdin/模型协议、ctypes或自动重试；未知和失败不再次发送。首次admission若被拒绝，不伪造新result覆盖旧未知尝试。独立只读nvidia-smi/进程观察在之后核实GPU是否释放，不由producer自行追认完整清理。

训练Conda Python无pidfd接口，因此不使用不安全fallback；系统Python3.10实际能力探测支持两个接口。[Python pidfd_open](https://docs.python.org/3.10/library/os.html#os.pidfd_open)和[pidfd_send_signal](https://docs.python.org/3.10/library/signal.html#signal.pidfd_send_signal)按进程句柄管理目标，不把结构指纹当代码证明。runtime将冻结单一源码/spec、系统解释器、完整可读stdlib及已映射文件字节；仍明确信任Linux内核/opaque映像，不声称全OS代码字节闭包。30秒是pidfd退出等待，不声称能抢占冻结文件I/O或内核阻塞；持久admission确保观察超时不构成重跑权限。

不得读取私有题/答案/密文/identity/模型帧或原账本，不删除/重写任何原磁盘证据，不改C4/v8/R/默认混合。只在独立安全收尾目录追加grant/admission/信号尝试/结果。不证明目标内存清零、完整宿主委托缺席或Rhino清理；这些与保管人失败审计分开。PID身份若自然失效，零信号停止，不换PID执行。

## CPU与发布门

[CPU注入控制](../eval/test_c5_formal20_worker_safe_stop.py)覆盖成功单信号/固定fd、八类身份漂移/PID重用、scope/计数/截止字段、两次guard、已有admission、不确定syscall、等待超时、文件symlink/不可覆盖，以及AST无裸PID/进程组/子进程kill；CPU从不打开或发送真实进程信号。源码/最新完整冻结发布双CI后，集中提交新spec/runtime两完整SHA给本人；旧formal批准不复用。只读身份/接口/字节准备与真正SIGTERM分开，不把CPU正控当实际释放证据。
