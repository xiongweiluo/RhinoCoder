# C5 独立溯源观察器：单次能力探针与研究宿主规范

2026-10-06。持续Goal覆盖六项终点，目前处于第1项；下文只是待批准的观察能力探针，**不是整体交付完成、现场工程门通过或正式20题授权**。原设计和保证边界见[溯源设计](c5-host-provenance-design.md)。

## 已实现，尚未执行

- [注入式记录器](../plugin/rhino_listener/c5_host_observer.py)：固定ID `C5OBS-HOSTPROV-20261006-A`，永久started、不可覆盖原始记录、序号/单调时间/前向SHA链与不可覆盖seal；外部终端receipt绑定seal，避免只靠可整体重写的本地hash链。
- [真实CLR/macOS适配器](../plugin/rhino_listener/c5_host_observer_clr.py)：导入本身只涉及stdlib；精确批准与claim后才构造真实后端。以CLR对象ReferenceEquals登记实例，不按名称合并；记录MVID、文件身份、可见类型/签名、Python origin/object binding、native image及不可验证项。不读取方法源代码、常量、模块值、题目、答案或密钥。路径与文件读取限制在声明代码根/后缀，拒绝私有JSON或symlink escape；未知来源仅哈希元数据、没有内容读取。
- [独立原始审计](../training/c5_host_observer_audit.py)：重算全部record与CLR surface指纹、实际控制实例、前后类型变化、事件唯一性及detach后回调静默，拒绝额外/丢失/重排记录。不信producer的通过bool；要求终端外部sealSHA。
- [冻结部署工具](../tools/freeze_c5_host_observer.py)：只复制新提交的六个源码目录中的tracked `.py`、本spec和runtime；不复制整个脏工作区、大批R原始证据、私有数据或SSH材料。独立source目录与manifest均不可覆盖，后续工作树更新不改变批准对象。
- [精确授权入口](../tools/c5_rhino_host_observer_probe.py)：fresh私有package namespace避免运行旧ScriptEditor模块；先核对所有者两个精确哈希及所有冻结源码/已知host字节，再写固定state的永久claim，然后才订阅。设计许可/B/native12/正式承诺均不能代替该批准。

## 将请求批准的完整现场范围

本探针仅在**当前已有的空白Rhino宿主**做能力测量，不把该进程追认为clean baseline，不要求关闭用户文档或禁用插件。固定Rhino8.21.25188.17002、Python3.9；须空白活动文档、UI主线程，前后serial/内容摘要不变。

一次执行依次：一次AssemblyLoad订阅→baseline→第一份空动态程序集→空表面快照→在同实例增加一个空public type（不调用它）→类型表面快照→解除精确delegate→第二份空动态程序集作为detach负控→快照/回调静默核对→封存/无正文receipt。两份canary均为非收集`Run`程序集，在宿主自然退出前保留；不强制restart、不卸载、不删除。创建/类型定义是必须明确批准的宿主操作，**本轮未执行**。

模型加载/生成、GPU、RhinoDoc创建、几何/工具派发、holdout读取/消费均为0；无Idle hook、无密钥。逻辑测量上限180秒，在步骤间检查；**不能声称抢占阻塞中的CLR调用**。若调用阻塞需所有者安全停止；若未知回执、source漂移、失败/溢出或detach不能核实，此ID消费并退休、不重放。保留delegate引用供另获精确批准的安全reconcile；不得自动改成新ID再跑。

正式批准材料为[spec](../eval/c5/host-observer-spec-20261006-a.json)及生成的runtime freeze；提交/部署manifest、CPU全仓测试、两个CI通过后集中请求其规范化SHA。未收到该批准，不创建observer state/claim，不订阅、不生成canary；目前只有可审阅代码/spec。

## 探针正控通过也不提供的保证

AssemblyLoad并不覆盖既有程序集内修改；结构快照也不能排除两次快照之间的瞬时变更，或证明隐藏DynamicMethods、发射字节、因果生成器来源。native shared-cache映像可能没有可哈希磁盘文件，反射也可能有不可见内容；逐项保留缺口，不能名字白名单放行。API语义核对依据[Microsoft AssemblyBuilder](https://learn.microsoft.com/en-us/dotnet/api/system.reflection.emit.assemblybuilder.definedynamicassembly?view=net-8.0)与[AssemblyLoad](https://learn.microsoft.com/en-us/dotnet/api/system.appdomain.assemblyload?view=net-8.0)。

能力审计的最高结论仅是`observer_capability_raw_audit_verified_with_limits`。`complete_event_coverage_proven`、`code_bytes_or_causal_origin_proven`、`clean_host_baseline_verified`、`legacy_byte_closure_verified`及`formal_execution_ready`始终false；当前执行门禁没有放宽。

## 研究专用宿主的准备规范（后续必要批准，非本次能力探针）

1. 保留当前Rhino与R/A/B证据；由所有者准备新的研究专用进程和未保存毫米空白活动文档，记录启动/插件/版本。不能杀当前进程、删除文档或把既有Snippets/Fologram/rhinomcp-mod追认为可信研究代码。
2. 对第三方插件/启动脚本给出固定允许/拒绝列表、实际身份及必要性。任何禁用、启动方式、订阅或warmup操作都先写明影响及恢复方案、再取得对应批准；不擅自改全局插件设置，不凭未核实命令行flag启动。
3. 只加载独立冻结source中的入口及声明host/generator；warmup范围限定原12工具所需类型/夹具/清理路径，真实操作须纳入新的开发spec/精确批准。源码不触及正式题，新增开发任务与封存20题的排除只由保管人私下完成。
4. 核实所有可观测origin/instance/native image，冻结受控baseline及原始记录。若事件覆盖/反射无法达成预定保证，明确修改保证并另获批准或停止；绝不填原完整byte-closure字段为true。
5. 再冻结新的开发工程门source/model/Mac/Rhino/GPU/预算/observer与双CI，取得两个新哈希批准；单次全链路和独立审计通过后，才冻结正式20题并单独批准。

## 无正文公开进度接口已准备

[聚合发布器](../training/c5_formal20_public_progress.py)和保管入口的`progress`模式仅输出计数/冻结哈希/阶段，不读私有题、密文、key或原始生成。正式started之前不能发布进度，不能建立消费。started后元数据缺失返回**UNKNOWN/no-replay**，不把缺失误作零生成。进度历史不可覆盖、current原子更新；它不是评分、安全审计或执行授权。

```bash
python /Users/xiongweiluo/.codex/worktrees/c5-engineering-gate/RhinoCoder/tools/c5_formal20_owner_run.py progress
```

该命令现在可只读确认正式尚未started；真正私有解密/执行/审计命令只在完整正式冻结和单独批准后交付。新20题公开承诺不重做，原80/B/native12不重跑。
