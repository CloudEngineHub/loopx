# RFC：小内核与运行时装配（v0）

- **RFC status:** Accepted, design acceptance takes effect on merge
- **替代 / 关闭：** 无
- **Delivery maturity:** Proposal
- **作者 / 负责人：** LoopX 维护者
- **创建日期：** 2026-10-29
- **最近规范修订：** 2026-10-29
- **实现基线：** `9cae3b28939f72fa4aadab5cfe49e19bcbdab372`
- **相关契约：** [发行拆分](monorepo-distribution-split-v0.zh-CN.md)、[Controller/Executor 统一契约](controller-executor-unified-contract-v0.zh-CN.md)、[Session 执行模式](agent-session-execution-modes-v0.zh-CN.md)、[总体路线图](loopx-overall-roadmap-v0.zh-CN.md)、[扩展机制](../../reference/extensions.md)
- **Language mirror:** [English](small-kernel-runtime-composition-v0.md)

## 文档地图与维护契约

第 1–11 节定义设计与验收契约，其中第 4 节记录指定实现基线的事实。
第 12 节记录未决事项，建议答案不代表批准。附录保存来源证据。
中英文是语义镜像。合并代表接受设计依据，不代表实现、性能、宿主资格或新默认值已经成立。
带日期的交付证据进入 [RFC ledger](ledger/README.md)。

## 1. 决策摘要

LoopX 应保留一个小型治理内核，装配成 **minimal** 与 **standard** 两种预设。
研究配置冻结某种装配及其实验改动，不产生第三套治理实现。

内核负责持久工作的准入与结算：Goal 要求、工作身份、claim/lease、预算、停止规则、
effect 身份、receipt 与恢复。宿主负责模型和工具执行。Capability 提供任务策略与领域行为。
前端通过同一套 owner 展示状态、提交操作。

“小”有四个独立维度：安装依赖、加载代码、激活服务、模型可见上下文。
安装 standard 不应让每条命令都加载或启动全部能力。Minimal 仍必须能完成真实的受治理
Turn，并在中断后恢复。

本 RFC 在既有发行拆分与统一工作契约下细化运行时装配，不重新命名它们的包，
不新增插件体系、Session 协议或路线图。现有默认行为、强制工作义务与 authority
持续生效，直到合格迁移明确改变它们。接受本设计不批准 benchmark 运行、设备操作或宿主晋级。

## 2. 问题与动机

简短的 CLI 读取不应初始化研究栈或 IM 服务。嵌入式 managed 任务不应依赖交互式 App Session。
Standard 产品用户仍需要可理解的进展、干预、恢复，以及把结果送回原请求。
Benchmark 需要测量同一份实现，同时避免引入无关产品服务或改变原生 evaluator。

只拆包无法满足这些要求：已安装依赖仍可能被提前导入，未使用服务仍可能轮询，
很小的二进制仍可能在每次模型调用发送过量上下文。单独的 loader 也无法提供 LoopX 的持久治理语义。

设计必须支持以下可观察旅程：

| 旅程 | 必须得到的结果 | 对装配的要求 |
| --- | --- | --- |
| 有界 managed 任务 | 无交互 App 也能启动、执行、结算并回读结果 | Minimal 包含一条合格宿主路径与持久 authority |
| 长程研究 | 先产出有用的首个结果，持续工作后有证据支持的修订或新成果 | 规划、研究、记忆策略按需；进展不能只是时间变长或重复总结 |
| 两三个 peer 协作 | 证据返回协调者，记录采纳，中断后恢复所有权 | 复用工作/租约 authority；peer 生命周期与结果采纳分离 |
| App 或 IM 请求 | 暂停、纠正、继续，并在原目的地收到已验收结果 | 前端与交付 provider 围绕同一工作身份装配 |
| 硬件或外部操作 | 完成多步任务，核对不确定副作用，并在对应边界验证停止 | 显式激活的 operation provider 负责回读、联锁与安全重试 |
| 可复现 benchmark | 用原生对照与完整成本比较合格产品装配 | 冻结实验输入；原生 runner、verifier 与评分保留各自所有权 |

这些是共享产品要求，不表示一次性交付所有旅程或组合。
内容、办公与工程能力使用同样的边界，无须成为强制启动依赖。

### 不变量

- I1. 每个状态迁移与 effect 只有一个 authority；预设不能分叉它。
- I2. 未选择的可选组件不得初始化、注册 timer、联网、执行 hook 或注入模型指令。
- I3. 缺少执行前提时，dispatch 前给出可操作错误；不能降级到不受治理的执行路径。
- I4. 必需上下文保持完整、新鲜；缩短 prompt 不能成为删除要求、required reads 或停止条件的授权。
- I5. 重放先核对持久身份与外部证据，再决定重试；完成、结算、结果交付保持可区分。
- I6. 性能与成果声明必须注明所测装配、基线、环境及范围。Help 加速不能证明任务效果提升。

## 3. 范围与非目标

范围包括：运行时所有权、显式装配、按需加载、上下文边界、benchmark 保真，以及产品旅程的分阶段资格验证。

非目标：新模型 loop、capability catalog、scheduler、记忆数据库、benchmark 原生 runner、
存储迁移、设备抽象框架或微服务拆分。本提案不增加 CLI 参数、包或持久 schema，不删除存储字段。
具体配置语法由后续实现按现有扩展与发行契约确定。

## 4. 当前系统契约

指定基线的 [entrypoint.py](../../../loopx/entrypoint.py) 已有轻量 version 路径和部分
原生 scheduler 后续调用；[cli_runtime.py](../../../loopx/cli_runtime.py) 按所选命令分发，
其余命令仍走完整 parser。`performance-diagnosis` 无须 registry，但尚未进入 selected-command
集合。这提供了有界的首个加载接缝，不代表所有启动路径都已经延迟加载。

类型化领域 authority 正按 [TypeScript 迁移](typescript-control-plane-migration-v0.md)
集中到 [control_plane](../../../loopx/control_plane/)。Python 仍负责适配器和部分既有路径。
新装配工作必须复用现有 owner，迁移前先刻画旧行为；不能在另一门语言里悄悄重建规则。

发行 RFC 负责 `loopx-core`、`loopx-workspace` 与可选包。
[三层协议](../../reference/protocols/multi-agent-three-layer-minimality-v0.md) 的 “kernel”
指更宽的可复用层，包含 runner/展示设施。本文的 **治理内核** 指 authority 边界，
**启动依赖闭包** 指所选入口必需的代码。设施可以继续属于更宽的复用层，而不进入每个启动闭包。

Controller/Executor 统一 RFC 负责受治理工作契约。Session 模式负责 `managed_runtime`
与 `attached_host`。[DSH/Pi 选择 RFC](harness-selection-dsh-pi-v0.zh-CN.md) 负责宿主资格；
有界 headless adapter 与拥有 Session 的 runtime 职责不同。
[Benchmark toolkit](../../../loopx/capabilities/benchmark_toolkit/README.md) 负责通用的权限、
并发和完整性支持，[benchmark 政策](../../../benchmark/README.md) 把原生执行与评估留在 benchmark。
本 RFC 不恢复第二个 launcher。

## 5. 提议架构

### 5.1 所有权与放置

| 边界 | Owner 与职责 | 不承担的职责 |
| --- | --- | --- |
| Bootstrap | 现有 entrypoint/CLI 路由；解析命令与已安装装配元数据 | Goal 决策、发现阶段激活 provider |
| 治理内核 | 现有类型化 Goal、work、quota、runtime、coordination owner；准入、迁移、effect、结算、恢复规则 | LLM/tool loop、任务策略、UI、传输、benchmark 评分 |
| 宿主执行 | 已准入的 managed 或 attached host provider；模型调用、工具、Session 生命周期、执行观测 | 第二份工作账本或独立权限 authority |
| Capability 策略 | 最近的结果型 capability；规划、上下文选择、研究、召回、评审 | 覆盖强制迁移、租约、停止或预算 |
| Extension 生命周期 | 现有 manifest、registry、兼容与激活机制 | 另一套通用插件/容器框架 |
| 产品界面 | Workspace、CLI、IM 或交付 provider 消费公开安全投影并提交命令 | 从私有源文件或展示文字推断规范状态 |

放置理由：此处不引入新 capability id 或 provider id。核心治理属于 `control_plane`；
加载/生命周期机制属于现有入口与 `extensions`；benchmark 支持留在 `benchmark_toolkit`。
后续可选宿主/设备集成在现有结果型 owner 足够时复用它，独立发行的 provider 放在
`packages/<package-id>/`。新 capability 必须有真实、provider-neutral 的调用者契约，
不能仅因 bundle 可以安装就创建。

治理是逻辑边界，不要求把全部规则移入一个文件。保留内聚的类型化领域。
Planner 可以建议工作或 stride，只有所属迁移规则决定准入与义务。
替换策略不能把机器强制的 `must_attempt_work` 变成文字 guidance。
改变此类默认值必须单独披露契约变化。

### 5.2 预设与独立维度

| 装配 | 必需内容 | 显式可选内容 |
| --- | --- | --- |
| Minimal | Bootstrap、现有治理实现、一个受支持的 authority provider、一条合格执行路径、紧凑状态/结果回读与恢复 | 任务能力、持久召回、observer、connector、workspace UI |
| Standard | 同一内核与面向普通使用的兼容产品装配 | 只为所选工作流激活 capability、宿主集成、UI/IM 服务与外部 connector |
| 研究配置 | 固定版本的 minimal 或 standard 装配及声明过的实验 overlay | 实验设计中明确列出的 instrumentation 或 ablation |

Minimal 是受支持的完整执行装配，不是在已全部初始化的 standard 上加关闭开关。
Kernel library 可以不带宿主做只读嵌入，但这不构成可执行 minimal 预设的资格。
Standard 是便利装配，安装本身不授予激活或权限。发行 RFC 的迁移门槛通过前，安装行为保持现状。

以下维度保持独立：装配、managed/attached 模式、宿主 provider、一个/两个模型 Session、
存储 provider、benchmark arm。尤其 minimal 不等于 attached，standard 不要求双模型 Session，
research 不等于不受治理。只发布已测组合。遵守 Session 模式 RFC 的默认值与显式准入；
改变装配不能静默改变 binding 的执行 owner。

### 5.3 解析、加载、激活、提供上下文

1. **解析：** 读取 build/install 或显式 extension 注册时生成的本地版本化元数据。
   顶层 help、命令列表与未知命令拒绝不能扫描仓库、导入所有 provider 或联网。
   重复注册、过期或不兼容元数据必须可见；优先级显式确定，不能依赖导入顺序。
2. **加载：** 导入所选命令及其依赖闭包。详细命令 help 可以加载自身 parser，但不能激活执行服务。
   可选导入留在所属路由之后，fallback 路径也须遵守。
3. **激活：** 校验 installed/enabled/ready 状态及作用域权限，再经现有生命周期 owner 启动所需服务。
   可选代码缺失时说明如何安装/启用；必需 authority 或 runtime 缺失时 fail closed。
   Kernel 导入/help 不要求 Node；有副作用命令保留发行 RFC 的类型化 `node_unavailable` 边界。
4. **提供上下文：** 为所选工作和 executor 渲染现有受治理工作契约，复用统一 Controller/Executor
   设计的首次完整、后续差量与恢复语义。Required reads 和来源完整性仍有约束力。

相关来源/要求版本变化、Session generation 变化、compaction 或 ACK 丢失时，必须使上下文复用失效。
不能因为 packet 更小，就认为 executor 已掌握前文。连续性未知时走所属契约的恢复路径。
Capability 指令仅在适用时提供；authority 不能从 prompt 文字推导。

可选 observer 消费已提交事件或有界投影。除非现有契约明确要求它的 receipt，
其延迟不能进入准入/结算事务。只批处理尽力而为的 telemetry；不能为满足时间目标而延迟
authority receipt 持久化、弱化 fsync/事务保证，或缓存过期权限/租约决策。

### 5.4 持久生命周期与外部副作用

通过统一工作契约使用既有 Goal/Agent/work/Turn 身份、revision、lease、effect id 与 receipt。
解析装配，校验要求和 authority，准入工作，经绑定宿主执行，验证并持久化证据，结算一次，
再经所属 channel 交付/回读。各步骤使用既有合法迁移与重放规则；这段描述不新增竞争的 status enum
或事务协调者。

Executor 崩溃、effect ACK 丢失、结果交付 ACK 丢失是不同恢复情形。
Operation provider 必须说明某个 effect 能否核对、能否安全重试。
外部状态未知时，后续依赖操作须等待回读或人工干预；“未观测到”不等于“未执行”。
设备幂等、物理联锁与补偿归 provider 负责，不能虚构为内核保证。

模型取消、进程终止、设备确认停止是不同事实。模型停止不能在缺少设备证据时生成
“设备已停止”声明。需要持续监督的 provider，在 effect 尚未解决时不能卸载。
结果验收、传输交付、用户回读也必须保留现有的不同证据。

### 5.5 Benchmark 使用产品实现

遵守 [长程研究计划](long-horizon-harness-benchmark-research-program-v0.zh-CN.md)：
native/plain 对照、被动观测、受治理执行与 ablation 具有明确身份。
原生对照不接受 LoopX 指令或 hook。被动观测须验证无干扰。
受治理实验臂使用与产品任务相同的合格装配与迁移；改变治理的 ablation 必须作为具名实验变体，
不能成为产品默认行为。

冻结产品/宿主版本、解析后的装配、模型与采样设置、skills/tools、初始状态、预算、
checkpoint/恢复策略、数据集与 verifier 版本。按 run/arm 隔离记忆，禁止跨实验臂污染。
除了任务结果，还要报告 controller、executor、compaction、retry、recovery 与人工干预成本。
原生 runner/verifier 保留任务语义与评分。性能工作不能跳过 toolkit 的权限/完整性检查，
也不能把原始任务、trajectory 或 verifier 日志作为公开产品证据发布。

长程产品资格还要求证明：后续工作改善了已经有用的初始结果，或改变了决策。
故意削弱首个结果、增加文字或运行更久都不算进展。

## 6. 替代方案与设计选择

| 方案 | 决策与取舍 |
| --- | --- |
| 只拆包或加 lazy import | 可作为首批切片，但不足以定义激活、authority 和上下文边界 |
| Minimal 与 standard 各自一套引擎 | 拒绝：重复状态迁移，破坏产品/benchmark 一致性 |
| 所有规则都插件化 | 拒绝：预算、停止、租约、结算可能随预设消失 |
| 用上游 agent runtime 替代 LoopX 内核 | 拒绝：上游模型执行可以是 provider，但不能替代 LoopX 工作 authority |
| 强制统一 daemon 或远端服务 | 不要求：给有界本地使用增加生命周期与部署成本；daemon 仍按其现有 RFC 演进 |

Pi 展示了小型 agent core、工具/事件执行，以及与 coding 产品分离的显式上下文转换。
DSH 展示了同一 runtime 的多预设装配与自包含的最小 SDK bundle。
在固定版本中，DSH web minimal 与 standard 使用相同 agent-preset 包、不同 plugin 列表；
minimal 包含持久 shell、图像读取与 compaction。SDK minimal 还提供工作目录状态、持久化，
并按配置提供可选 MCP 资源。这些是装配范例，不能据此声称 DSH 恰好有两套引擎，
或把 LoopX headless adapter 与 DSH plugin 分别当成这两种预设。
借鉴显式边界，不引入 Cordis、上游权限默认值或新的 LoopX 模型 loop。固定来源见附录 A。

## 7. 安全、隐私与兼容

装配不能把现有权限或强制门槛变成可选项。宿主可用、extension 已安装、runtime capability
声明都是观测，不是授权。每次 provider 调用保留 Goal、Agent、workspace 与 delivery 作用域；
凭据通过现有 provider 边界解析。公开投影排除私有源内容和本地工件。

不提议删除 schema/字段。按既有兼容窗口保留已知 reader/writer 和外部 import。
未迁移 CLI 路由保留现有 fallback，直到替代路径通过命令一致性验证。
不支持的版本/provider 组合在 dispatch 前拒绝；不能为了让混合版本看似可用而让一个 binding
同时存在两个 writer。

## 8. 迁移与回滚

先刻画 CLI parsing、输出、错误、required reads 与 effect 行为。
一次迁移一个内聚路由并更新活跃调用者；真实调用者迁完后再删除内部 bridge。
加载优化不能顺带迁移存储或降低持久性。

可执行 minimal 以 opt-in 引入，必须能显式回读解析后的装配。
切换活跃 binding 前先检查兼容性，让其 owner 静止，并核对未完成 effect。
恢复前验证新 owner 与回读；不能跨活跃 lease 热切换。
回滚到旧的合格装配也先做同样核对，保留持久状态。
后续任何不可逆数据变化都需要单独的迁移/导出门槛。

Standard 采用须通过下述产品旅程验收。
只有全部受支持命令迁移，且 global options、help、错误、exit code 保持兼容后，才能移除完整 parser
fallback。默认值变化需要 release notes 与明确 owner 决策；本 RFC 不改变默认值。

## 9. 验证与验收

以下是拟定验收条件，不是已通过声明。确定性 fixture 根据语义独立设计，不能从当前实现输出反推期望。
Live、性能和晋级证据分别记录。

| Id / 声明 | 测试或证据 | 必须得到的结果 | 边界 |
| --- | --- | --- | --- |
| A1 / 按需加载 | 两种预设下对 import、help、列表、未知命令、所选路由做导入/进程/网络追踪 | 只加载声明过的依赖闭包；无可选激活 | 不证明执行性能 |
| A2 / authority 一致性 | 对要求、过期 claim、停止、预算、重放、结算做刻画与负例测试 | 两种预设具有相同合法/非法迁移，只结算一次 | Minimal 不得绕过 authority |
| A3 / CLI 兼容 | 受支持命令的差分语料，含 fallback、Node/provider 缺失 | Parsing、输出契约、exit code 稳定，失败可操作 | 明确列出未迁移路由 |
| A4 / managed minimal | 一个真实 managed 任务、注入中断、重启、证据验证与结果回读 | 身份相同，effect 已核对，无重复工作或计费，已验收结果可获取 | 初期一个合格宿主即可；纯 mock 执行不够 |
| A5 / 上下文连续性 | 首次上下文、无变化续行、来源修订、compaction、ACK 丢失 | 必需上下文完整或明确恢复；拒绝过期上下文 | 单独测 token 减少 |
| A6 / standard 旅程 | 原始 App/IM 请求、纠正/暂停、继续、完成与返回 | 一个执行 owner；已验收结果和成本可见；目的地不静默改变 | 每个前端/provider 分别合格 |
| A7 / 研究与 peers | 有用首个结果后的证据性改善；owner 恢复后的 peer 结果返回与采纳 | 新成果或有理由的决策修订，并有可归属证据 | 更多时间、peer 或文字本身不能通过 |
| A8 / benchmark 保真 | 固定的匹配实验、native/passive/governed 边界、记忆隔离、完整成本账本 | 原生语义完整；C0–C4 证据遵守研究/诊断 owner | 本 RFC 不声称分数或因果收益 |
| A9 / 物理副作用 | 模拟器/故障注入，再做显式授权的 provider 专属 live 验证 | 核对丢失 ACK；在保证范围内防重复动作；独立确认设备停止 | 不承诺通用 exactly-once 或紧急停止 |
| A10 / 开销 | 指定环境中重复、成对测量冷进程与热路径 | 报告 median/p95、RSS、模块数、文件 I/O、Node 启动/IPC、字节与模型 token；持久性无退化 | M0 确定数字预算；CLI 基线无须付费任务运行 |

本地开发候选目标为 p95：import 低于 50 ms、顶层 help 低于 100 ms、所选命令 help 低于 200 ms。
它们是 D3 的建议，不是已验证结果或跨机器 CI 阈值。
采用前要定义解释器启动、缓存条件、样本数、机器/runtime 版本。
真实 status/admission/settlement 延迟须在有代表性的小/大状态上单独测量，包含 SQLite 竞争和恢复；
不能把 CLI-help 目标套在这些操作上，也不能减掉其必需 I/O。

## 10. 运维契约

回读应解释：解析后的装配及版本、所选宿主和 Session 模式、必需/可选 provider、激活/readiness，
以及加载某组件的原因。复用现有诊断/投影 owner，不新增状态数据库。
前提缺失、元数据不兼容、authority 过期、effect 不确定必须保持可区分。

启动开销与 Turn 开销分别记录。可选 observer 故障应可见，但不能改写已提交执行结果；
强制 delivery 或证据 receipt 失败继续由所属 owner 治理。
容量限制、背压归既有 work/host/provider 契约。运维恢复先核对持久 receipt 与 provider 回读，再继续执行。

## 11. 规范交付计划

以下切片归入既有路线图的 runtime、发行与产品工作流，不建立平行项目，
也不要求全仓重写后才能交付局部性能改善。

| 里程碑 | 交付行为 | 进入条件 | 退出证据 | 回滚 |
| --- | --- | --- | --- | --- |
| M0 / 一个加载接缝 | `performance-diagnosis` selected route 与实测加载边界 | 现有路由刻画；owner/依赖图；D3 测量决策 | 本路由的 A1/A3、A10 基线，无无关导入或行为变化 | 撤回路由提取 |
| M1 / 可执行 minimal | 一条合格 managed 受治理任务，含持久重启/结果回读 | D1 装配内容、D2 宿主/provider 选择；既有 authority 契约 | 此受支持组合的 A1–A5、A10 | 显式返回旧的合格装配 |
| M2 / standard 旅程 | Standard 解析同一内核，只激活所选产品工作流 | M1；现有 Session/前端准入 | A2/A5/A6/A10，含冷安装与功能关闭一致性 | 关闭 opt-in 装配并保留状态 |
| M3 / 研究资格 | 匹配的产品路径实验，以及一个长程/peer 旅程 | 所选界面的 M1 或 M2；冻结设计与单独运行授权 | A7/A8、完整成本与隐私检查、既有 C0–C4 门槛 | 停用实验 overlay，保留有界证据 |
| M4 / 外部操作 provider | 一个真实调用者，具备 provider 专属 effect 核对与停止证据 | D4；具名设备/操作 owner 与显式操作授权 | A9 加继承的治理门槛 | 停用前先静止并核对 provider |

M0 不代表内核合格。M3、M4 是可选资格分支，不必阻塞已合格的 CLI 或 managed 任务。
真实调用者出现前，不加入闲置 provider、配置字段、框架或通用测试矩阵。
每个 PR 记录考虑、应用或推迟的有界重构及兼容证据。

## 12. 未决事项

| Id / owner | 选项与建议 | 所需证据 / 决策点 |
| --- | --- | --- |
| D1 / 发行与 runtime 维护者 | 将预设映射到已接受的发行方案；建议 minimal 先 opt-in，standard 最终承接兼容装配，当前不选择新默认值 | M1 打包前给出精确安装/加载/激活闭包及升级/回读契约 |
| D2 / 宿主与 authority 维护者 | 从既有 provider 选择首个 managed 宿主与受支持存储组合；建议最小且已满足资格的路径，DSH/Pi 仍按既有选择 RFC 评估 | M1 退出前给出 A4 宿主/Session 连续性与 authority 恢复证据；不声称所有宿主合格 |
| D3 / 性能维护者 | 采用机器相关 p95 预算或相对回归界限；建议候选预算加明确测量条件 | M0 退出前提供可复现基线；真实 Turn 预算独立推导 |
| D4 / operation-provider owner | 选择一个具体外部操作调用者，或推迟物理资格；建议真实调用者出现前不做通用设备框架 | M4 前确定范围、幂等/回读/停止契约及授权 |

批准必须经相应评审决策记录；建议、实现进展或沉默都不能关闭未决事项。

## 附录 A：来源证据（非规范）

| 证据 | 固定来源 | 支持的声明与限制 |
| --- | --- | --- |
| E1 / LoopX | 上述实现基线；第 4 节链接的入口、CLI 与所属契约 | 仅证明现有接缝与所有权；没有新性能测量 |
| E2 / DSH | [`minimal.patch.yml`](https://github.com/deepseek-ai/deepseek-harness/blob/f3803c96974ad4a94195fb97e5c637e9c2a3afe3/packages/bundle/web-app/presets/minimal.patch.yml)、[`standard.patch.yml`](https://github.com/deepseek-ai/deepseek-harness/blob/f3803c96974ad4a94195fb97e5c637e9c2a3afe3/packages/bundle/web-app/presets/standard.patch.yml)、[`sdk-minimal`](https://github.com/deepseek-ai/deepseek-harness/blob/f3803c96974ad4a94195fb97e5c637e9c2a3afe3/packages/bundle/sdk-minimal/README.md) | 共享预设装配与自包含 SDK bundle；不代表 LoopX 宿主资格或权限建议 |
| E3 / Pi | [`agent` core](https://github.com/badlogic/pi-mono/blob/f14813e96510a7cf7562a120e809c6a134af073d/packages/agent/README.md) | Agent/tool/event core，以及 `transformContext`、`convertToLlm`、`prepareRequest`、`finishTurn` 接缝；无 LoopX authority 或性能声明 |

本提案没有执行 live benchmark 或硬件操作。
