# D 一次公开开发：本人 ready 门拒绝、有限收尾及永久退休

2026-10-12。本人明确批准完整 spec 62e6a66c77604858a0b0109003af1cff74f3ffbdb2ae33b8756c76951746e1d6、runtime af589bebd37a6786a01843275ec3add7b868edcc9e6a495fa989d67b93842f67 后，唯一 D 开发实际启动，但**没有进入任何槽位，完整 8 槽工程门未通过**。两端批准现已封存，D 永久退休，不重试、补槽、转移批准或创建替代研究身份；正式 40 槽条件未满足。见[完整公开失败记录](../eval/c5/reuse-followup-development-readiness-failure-20261012-d.json)。

## 实际过程与错误边界

批准对象发布 head 为 96e4fb3b83d5903f6296e4b381e4186bdf2cf3ad，push/PR 双 CI 均为 1958 passed、11 skipped。批准后再次完成两端无 grant 实际预检及独立 338 文件字节、环境、原消费历史/三次退休和完整 5 小时窗口复核。两端各登记一次 grant，Mac prepare 一次成功；本人私下 ready 保管终端就绪后，Rhino 包装入口和 Mac controller 各运行一次。UI Run 调用返回 timeout，但已观察到 durable entry-return release 和宿主基线，未重复 Run。

原生 pidfd 子进程资格屏障通过，模型加载及实际 worker ready 记录出现。两端 ready 原始记录交叉匹配，ready 前模型请求/生成阶段均为 0；准备完成或 ready 不等于工程门 PASS。

本人随后贴回实际保管终端报错：在输入“确认并保管”后，confirm() 的交互条件拒绝，抛出 reuse_owner_interactive_confirmation_required，未到 guard() 或写入 owner-readiness.json。本人报告“已确认”及“已保管 D 失败回执”，均保留；实际文件最终仍缺席。控制器 120 秒窗口结束时因 reuse_missing_external_readiness_no_retry 退出。不能把它写成本人没有输入或没有批准，也不能从渲染后的粘贴文本猜定空格、不可见字符或 TTY 为唯一原因；原始输入字节未取得。

controller/worker 原始链均无 external begin、模型请求、生成意图或槽位开始/完成记录，全部 8 槽未启动；质量和物理生成总量保持 null，不写成模型质量 0 分。

## 一次停止和首次已知宿主收尾

controller 仅发出一次独立 stop。原始资格链、完整 argv/解释器/boot/UID/cwd、原父子关系及资格锚复算通过；对该 pidfd 子进程记录一次 SIGTERM，独立 stop 返回 0、退出已观察。监督器 reap 原子进程，wait status 为 SIGTERM；只读观察确认原资格目标及父进程缺席、同一 GPU 计算进程为空、显存 11 MiB。完整原始链与有限目标释放观察有效，物理来源密码学认证仍为 false。

监督器随后在自身 finally 中再次领取已消费的全局 stop 角色，被 O_EXCL 拒绝，原 stderr 有 FileExistsError。它留下 unknown/no-retry 的 0 信号结果，serve 退出 1；不能把独立 stop 返回 0 改写为监督器正常完成，不能再发 stop 或声称第二次信号。

首次已知 hub stop 完成，HMAC 签名和服务端/客户端两份时序原始材料独立复算通过。opened slots 为空，hub key 和 8 份未用派发 key 缺席；实际 Rhino 外部 terminal receipt 与磁盘 9 条连续性链/封印匹配，本人已私下保管失败回执。此处只核实已知 hub 收尾及有限可见连续性，不声称完整宿主字节、隐藏 handler 缺席或内存擦除。

## 原始证据、资源及分支

serve stdout 412 字节、stderr 97124 字节，均观察 EOF/退出 1，无截断、捕获错误或协议尾；stop 两流为空、EOF/退出 0。每份原始流均与 journal 的 observed/retained 字节 SHA 重新核对。原始捕获完整不代表正常执行或 8 槽联合 PASS；正常 ready/final 本人文件和正常 GPU export 缺席，不伪造补齐。

两端完整公共源各 338 文件、A/B/C 三次退休和原 Mac v1 四文件/两行在失败后再次独立检查不变。原同一全局根保留导入的非空历史以及 D Mac controller/host、GPU worker/stop 四份永久消费文件；没有删除行、空表替换、重建命名空间或重置角色。D 封存 grant raw SHA 为 0d4e4eb088be82b2a955d10640cd0eaa53fe8ab348d660eeccb3b0add34ac0b8，两端退休记录 raw SHA 同为 7dcb6371e303d4a7a4bc4e726873271f6901e351fe4debe66505a8e2889e3826，活动 grant 均缺席。

本次 supervisor 最终有限账本为约 431.95 秒；保守计算到独立原始释放观察约 774.12 秒，均落在开发 18000 秒新预约内。历史累计仍未知，原累计 16 小时合规不追认，没有续租/付款或返还旧预算。正常正式消费未授权。

本失败记录分支基于未合并的 D 准备 PR #17，冻结现场源码/spec/runtime 没有修改，main 与原九份 WIP 不自动改变。当前收口为原始失败披露、作品集状态同步及本人 PR/main 审核；保留原 C5 NO-GO、原正式失败、同题复用披露和默认混合路线，不自动进入正式冻结、产品接入或后续研究。
