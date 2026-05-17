# Frontend Implementation Architecture

## 范围

本文描述 `Ouroboros/frontend` 第一版实现架构。根架构文档决定系统边界和 Agent 编队；`docs/web_api` 决定 REST、WebSocket、错误码和字段 schema。本文只说明前端如何组织代码、状态和数据流，不声明新协议能力。

## 权威来源

- 系统分层、Agent 编队和模块职责以 `docs/Arch/arch.md` 为准。
- REST、WebSocket、错误码、断线恢复和字段 schema 以 `docs/web_api` 为准。
- Agent 身份、权限和 Prompt 边界以 `docs/internal_contracts/agent_identity_permissions.md`、`docs/internal_contracts/agent_profile_prompt_contract.md` 为准。
- 前端实现文档不得新增 Web API 字段、内部 channel、长期状态归属或权限模型。

## 第一版目标

- 提供完整推演生命周期入口：初始化、实时监控、Agent 审计、时间轴查看和报告查看。
- 只通过 Web API 层访问后端能力。
- 使用 REST 快照作为页面初始化和恢复基准。
- 使用 WebSocket 事件作为增量更新来源。
- 在状态层统一表达创建、启动、暂停、单步、停止、恢复、错误和终止状态。
- 普通前端只展示 Web API 允许的脱敏审计字段和公开事件引用。

## Agent 编队展示

`default_24` 的前端预览必须与根架构文档一致：

- 公募机构 x2。
- 游资大佬 x2。
- 量化游资 x2。
- 国家队 x2。
- 散户群体 x16。

边界：

- 初始化控制台可以展示本地配平草稿。
- 第一版创建会话时仍只提交 `agent_profile_set`。
- 本地配平草稿不得绕过 Web API 写入真实 Agent 配置。
- 如果 Web API 尚未定义配平字段，前端不得伪造请求字段。

## 页面模块

### 初始化控制台

职责：

- 创建真实会话。
- 收集 `scenario_id`、`symbol`、`agent_profile_set`、`start_tick_id`、`end_tick_id`、`tick_interval`。
- 展示 `agent_profile_set` 派生的 24 Agent 编队预览。
- 标记本地草稿和真实提交参数的差异。

边界：

- 不直接初始化 Layer 0、Layer 3 或 Agent runtime。
- 不访问 Redis、内部 Pub/Sub 或内部 channel。
- 不写入订单、论坛消息、Agent 记忆或 Agent 状态。
- 创建成功只代表控制面会话已创建，不代表已经推进 Tick。

### 实时推演画板

职责：

- 展示会话运行状态、Tick 状态、公开事件、行情摘要、Agent 图谱和可展示因果链。
- 提供启动、暂停、单步和停止命令入口。
- 使用 REST 快照初始化运行态视图。
- 使用 WebSocket 事件增量更新视图。
- 支持本地回放和当前 Tick 过滤。

边界：

- 不展示未来事实。
- 不展示底层真实订单 id。
- 不展示原始 `thought`、COT、Prompt、私有记忆或 Agent 原始 payload。
- 不通过 WebSocket 提交订单、发帖、改账或改 Agent 状态。
- 图谱布局结果只服务展示，不回传后端。

### 智能体解剖室

职责：

- 展示 Agent 名录、生命周期状态、账户审计字段、风险状态、信念轨迹和脱敏审计链路。
- 从图谱节点、资产表或列表选中同一 Agent。
- 在缺少公开因果链时显示明确空态。

边界：

- 第一版是普通审计视图，不提供内部诊断角色。
- 只展示 Web API 允许的账户审计字段、公开原因、风险标签和事件引用。
- 不展示或缓存原始 `thought`、COT、Prompt、私有记忆、Agent 原始 payload、内部 `UI_Audit` 或内部 `Order_Input`。

### 时间轴剧本管理

职责：

- 只读展示当前 Tick、历史事实轨、公开传闻轨和未来 Tick 占位。
- 支持本地草案预览。
- 区分真实已发布事实和本地未提交草稿。

边界：

- 第一版不提供保存、发布、删除或拖拽改写能力。
- 本地草案不写入 REST、WebSocket、Chronos SSOT 或内部 channel。
- 当前 Tick 之后的插桩占位不得泄露未来正文。

### 最终判决与漏洞白皮书

职责：

- 展示会话元信息、结论摘要、证据链、虚拟龙虎榜、风险排行和关键 Tick。
- 支持从关键 Tick 或因果链标题定位到对应证据。

边界：

- 崩塌概率只展示 Web API 或快照中已经存在的字段；没有字段时显示 `N/A`。
- 如果结论摘要由前端模板整理，必须标记为前端展示摘要。
- 不把报告结论回流 Agent。
- 不提供导出结论回写推演入口。

## 状态层

建议按职责拆分状态：

- `sessionState`：`session_id`、会话状态、创建/启动/暂停/单步/停止命令状态。
- `snapshotState`：最近一次 REST 快照、`last_seq`、加载时间、恢复状态。
- `eventBuffer`：按 `seq`、`tick_id`、`type`、`agent_id`、`reason_ref` 建索引的可展示事件缓存。
- `timelineState`：当前 Tick、回放 Tick、是否处于回放态。
- `graphState`：节点、边、布局坐标、剪枝结果、选中节点、选中因果链。
- `inspectorState`：当前 Agent、账户审计字段、信念历史、公开因果链摘要。
- `uiState`：全局导航、工具栏开关、错误条、空态、加载、恢复和终止状态。

状态原则：

- REST 快照是进入页面和断线恢复的基准。
- WebSocket 事件只做增量合并，不替代快照权威。
- 回放只读取本地缓存或 Web API 事件回放。
- 任何 payload 在进入页面状态前必须经过可见性过滤。
- 前端状态不得成为市场事实、账户资产、订单簿、Agent 记忆或 Agent 生命周期的 SSOT。

## Web API Client

REST client 职责：

- 统一 base URL、请求 id、认证上下文、超时、取消请求和错误映射。
- 封装会话创建、查询、启动、暂停、单步、停止、快照和事件读取。
- 不在实现层复制协议 schema；字段以 `docs/web_api` 为准。

WebSocket client 职责：

- 连接 Frontend Realtime Gateway。
- 发送协议允许的客户端消息。
- 按 `seq` 去重、排序和恢复。
- 识别断线、重连、快照要求和心跳超时。
- 把事件交给可见性过滤和事件缓存，不直接写页面组件状态。

错误映射：

- REST 命令失败进入对应命令状态和全局错误状态。
- `system.error` 进入实时事件流。
- 不可恢复错误占据当前模块主体，但不破坏全局导航。
- 错误文案只说明前端可见事实和下一步操作，不展示内部 payload。

## 实时事件缓存

缓存目标：

- 支撑实时画布增量更新。
- 支撑 Tick 回放。
- 支撑 Inspector 的 Agent 历史审计视图。
- 支撑断线恢复前后的事件去重。

索引建议：

- `bySeq`：用于去重和恢复。
- `byTick`：用于回放和时间轴。
- `byType`：用于事件流筛选。
- `byAgentId`：用于 Inspector 和图谱节点。
- `byReasonRef`：用于边、因果链和事件流互相定位。

缓存边界：

- 只缓存 Web API 允许展示的事件和字段。
- 不持久化私有 payload。
- 不把内部 channel 结构提升为前端状态模型。

## 图谱布局与剪枝

布局规则：

- 同一快照和同一事件序列必须得到稳定坐标。
- 如使用伪随机，种子必须来自会话和 Agent id 的稳定 hash。
- 节点位置由前端确定性计算，只服务展示。
- 节点、边、选中态、风险态和影响强度不得改变后端状态。

剪枝规则：

- 默认优先展示当前 Tick 的有效影响。
- 历史边只在回放、选中因果链或打开历史影响开关时显示。
- 低影响信息进入审计摘要或 tooltip，不默认画边。
- 24 个 Agent 默认不超过 48 条边；超出时按影响强度、当前 Tick 和选中链路优先级裁剪。

交互规则：

- Hover 节点只影响本地高亮。
- 点击节点同步 Inspector。
- 点击边定位关联事件引用。
- Tooltip 只展示脱敏字段和审计摘要。

## Tick 回放

回放目标：

- 在不影响运行态的前提下查看历史 Tick。
- 同步更新节点信念值、仓位信息、连线显隐、曲线区间和事件流高亮。

实现规则：

- 进入回放态后不得触发控制命令。
- 回到最新 Tick 后恢复 live、paused 或 terminal 状态。
- 回放只读取本地事件缓存、REST 快照或 Web API 事件回放。
- 回放状态不得请求内部数据源。

## Inspector 可见性

允许展示：

- `agent_id`、`agent_type`、`risk_state`、`lifecycle_state`。
- Web API 允许的账户审计字段。
- `belief_score` 历史。
- `public_reason`、审计因果链摘要、事件引用和风险标签。

禁止展示：

- 原始 `thought`。
- COT。
- Prompt。
- 私有记忆。
- Agent 原始 payload。
- 内部 `UI_Audit`。
- 内部 `Order_Input`。
- 内部 `trade_batch`。
- 内部 `risk_result`。

## 恢复流程

1. 首次进入页面先取 REST 快照。
2. 使用快照中的序列基准连接 WebSocket。
3. WebSocket 事件按 `seq` 去重合并。
4. 断线后进入恢复状态。
5. 收到需要快照的恢复信号后重新获取 REST 快照。
6. 快照恢复完成后再应用后续实时事件。

## 验收约束

- `default_24` 预览必须显示 24 个 Agent 的架构编队：2+2+2+2+16。
- 创建会话请求不得携带未在 Web API 定义的配平字段。
- 普通前端不得展示原始 `thought`、COT、Prompt、私有记忆或 Agent 原始 payload。
- WebSocket 不得成为写入订单、论坛、资产或 Agent 状态的通道。
- 时间轴草案不得写入 Chronos SSOT。
- 图谱布局不得回传后端。
- 缺失后端字段时不得由前端伪造正式分析结论。
