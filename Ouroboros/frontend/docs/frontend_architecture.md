# Frontend Implementation Architecture

## 范围

本文描述 `Ouroboros/frontend` 第一版实现架构。根设计文档决定页面形态和交互要求；`docs\web_api` 决定 REST、WebSocket、错误码和字段 schema。本文只说明前端如何落地，不声明新协议能力。

## 第一版目标

- 桌面专业工具界面，目标宽度 `1440px` 及以上；`1280px` 到 `1439px` 保持可用；低于 `1280px` 保留横向滚动。
- 五个页面模块：初始化控制台、实时推演画板、智能体解剖室、时间轴剧本管理、最终判决与漏洞白皮书。
- REST 只通过 Web API client 访问；实时数据只通过 WebSocket client 访问。
- 首次进入运行态页面时使用 REST 快照初始化，再应用 WebSocket 增量事件。
- 断线、恢复、回放和错误状态在全局状态层统一表达。
- 图谱布局、剪枝和回放由前端确定性计算，结果不回传后端。
- 普通页面只展示脱敏审计摘要和可展示事件引用。

## 页面模块

### 初始化控制台

职责：

- 创建真实会话。
- 展示标的、场景、Tick 范围和节拍间隔表单。
- 展示 `agent_profile_set` 派生的阵营配平预览。
- 当本地配平和实际可提交参数不一致时显示 `LOCAL PROFILE PREVIEW ONLY`。

边界：

- 配平控件第一版只做本地草稿，不承诺写入后端。
- 不直接访问 Layer 0、Layer 3、Agent runtime、Redis 或内部 channel。
- 不写入 `Order_Input`、`Forum_Rumors`、`thought`。

### 实时推演画板

职责：

- 三栏布局：事件流、共识感染画布、盘口聚合。
- 展示 Tick 状态、公开事件、图谱、价格曲线、共识曲线和聚合盘口。
- 支持节点 Spotlight、Targeting Box、边高亮、当前 Tick 影响过滤和重置视图。
- 支持 Tick 刮擦回放；回放态显示 `REPLAY TICK`。

边界：

- 画布数据来自 Web API 快照、可展示事件和实时事件缓存。
- 不展示未来事实。
- 不展示底层真实订单 id、Agent 身份绑定意图、原始 `thought`、COT、Prompt 或私有记忆。

### 智能体解剖室

职责：

- 展示 Agent 名录、资产审计表、信念轨迹和脱敏审计流。
- 从图谱节点、资产表或列表选中同一 Agent。
- 没有公开因果链时显示 `NO PUBLIC CAUSAL CHAIN`。

边界：

- 第一版是普通审计视图，不做内部诊断角色。
- 只展示 Web API 允许的账户审计字段、公开原因、风险标签和事件引用。
- 原始 COT、私有记忆、Prompt 和 Agent 原始 payload 必须被 UI 层和数据映射层同时拒绝。

### 时间轴剧本管理

职责：

- 只读展示当前 Tick、历史事实轨、公开传闻轨和未来 Tick 占位。
- 页面标题区显示 `READ ONLY TIMELINE`。
- 可以展示本地草案预览，但必须标记 `LOCAL DRAFT`。

边界：

- 第一版不提供拖拽、删除、保存、发布按钮。
- 草案不写入 REST、WebSocket、Chronos SSOT 或内部 channel。
- 当前 Tick 之后的插桩只显示类型、释放 Tick 和可见性，不显示正文。

### 最终判决与漏洞白皮书

职责：

- 静态报告页，支持打印模式。
- 展示会话元信息、结论摘要、证据图、虚拟龙虎榜、风险排行和关键 Tick。
- 点击关键 Tick 或因果链标题时高亮本页对应证据。

边界：

- 崩塌概率只展示 Web API 或快照中已经存在的字段；没有字段时显示 `N/A`。
- 结论摘要如由前端模板整理，必须标记为前端展示摘要。
- 不把报告结论回流 Agent，不提供导出结论回写推演入口。

## 状态层

建议按职责拆分状态，不把全部数据堆进页面组件：

- `sessionState`：当前 `session_id`、会话状态、创建/启动/暂停/单步/停止命令状态。
- `snapshotState`：最近一次 REST 快照、`last_seq`、快照加载时间、恢复状态。
- `eventBuffer`：按 `seq` 和 `tick_id` 索引的可展示实时事件。
- `timelineState`：当前 Tick、回放 Tick、是否处于 `REPLAY TICK`。
- `graphState`：节点、边、布局坐标、剪枝结果、选中节点、Spotlight 目标、选中因果链。
- `inspectorState`：当前 Agent、资产审计字段、信念历史、公开因果链摘要。
- `uiState`：全局导航、工具栏开关、错误条、空态、loading、recovering、terminal。

状态原则：

- REST 快照是进入页面和断线恢复的基准。
- WebSocket 事件只做增量合并，不替代快照权威。
- 回放只读取本地缓存或 Web API 事件回放，不读取内部 Redis。
- 任何 payload 在进入页面状态前必须经过可见性过滤。

## Web API Client

实现侧应有统一 API client，而不是页面直接拼 URL。

REST client 职责：

- 统一 base URL、认证上下文、超时、取消请求和错误映射。
- 封装会话创建、查询、启动、暂停、单步、停止、快照和事件读取。
- 不在实现文档内复制字段 schema；字段以 `docs\web_api` 为准。

WebSocket client 职责：

- 连接实时 gateway。
- 发送协议允许的客户端消息，例如订阅、ack、ping。
- 按 `seq` 去重和排序。
- 识别断线、重连、`SNAPSHOT_REQUIRED` 和心跳超时。
- 把事件交给可见性过滤和事件缓存，不直接写页面组件状态。

错误映射：

- REST 命令失败显示在操作按钮上方硬边错误条。
- `system.error` 必须进入实时推演页事件流。
- 不可恢复错误占据当前模块主体，但不破坏全局导航。
- 错误文案只说明事实和下一步操作，不展示内部 payload。

## 实时事件缓存

缓存目标：

- 支撑实时画布增量更新。
- 支撑 Tick 刮擦回放。
- 支撑 Inspector 的 Agent 历史审计视图。
- 支撑断线恢复前后的事件去重。

索引建议：

- `bySeq`：用于去重和恢复。
- `byTick`：用于 `REPLAY TICK` 和时间轴。
- `byType`：用于事件流筛选。
- `byAgentId`：用于 Inspector 和图谱节点。
- `byReasonRef`：用于边、因果链和事件流互相定位。

缓存边界：

- 只缓存 Web API 允许展示的事件和字段。
- 不持久化私有 payload。
- 不把低层内部 channel 结构提升为前端状态模型。

## 图谱布局与剪枝

第一版由前端确定性计算布局，布局结果只服务展示。

布局规则：

- 同一快照和同一事件序列必须得到稳定坐标。
- 不依赖随机布局；如必须使用伪随机，种子来自会话和 Agent id 的稳定 hash。
- 节点大小固定在设计允许范围内，不用大圆表达重要性。
- 选中、风险和影响强度通过描边、短线、线型、显隐优先级表达。

剪枝规则：

- 默认只显示当前 Tick 的有效影响。
- 上一 Tick 影响降为 10% 透明度或点状极细虚线。
- 历史边只在回放、选中因果链或打开历史影响开关时显示。
- 低影响读取进入审计摘要或 tooltip，不默认画边。
- 24 个 Agent 默认不超过 48 条边；超出时按影响强度、当前 Tick 和选中链路优先级裁剪。

交互规则：

- Hover 节点进入 Spotlight Isolation。
- 点击节点同步 Inspector。
- 选中节点显示静态方形虚线 Targeting Box。
- 点击边定位 `reason_ref` 或 `public_reason` 关联事件。
- Tooltip 只展示脱敏字段和审计摘要。

## Tick 回放

回放目标：

- 在不影响运行态的前提下查看历史 Tick。
- 同步更新节点信念值、仓位进度条、连线显隐、曲线区间和事件流高亮。

实现规则：

- 拖动 Tick 刻度时进入 `REPLAY TICK`。
- 回到最新 Tick 后恢复 live/paused/terminal 状态。
- 回放只读取本地事件缓存、REST 快照或 Web API 事件回放。
- 回放状态不得触发控制命令，不得请求内部数据源。

## Inspector

Inspector 是普通审计视图，不是内部调试器。

允许展示：

- `agent_id`、`agent_type`、`risk_state`。
- Web API 允许的账户审计字段。
- `belief_score` 历史。
- `public_reason`、`audit.causal_chain` 摘要、事件引用和风险标签。

禁止展示：

- 原始 `thought`。
- COT。
- Prompt。
- 私有记忆。
- Agent 原始 payload。
- 内部 `UI_Audit`、`Order_Input`、`trade_batch`、`risk_result`。

## 错误与恢复状态

全局状态必须统一命名和视觉：

- `empty`：白底黑框，等宽短句。
- `loading`：保留最终布局骨架，黑线占位，不使用灰块动画。
- `live`：模块边缘克莱因蓝短线。
- `paused`：白底状态栏，等宽黑字。
- `recovering`：显示 `RECOVERING SNAPSHOT`。
- `error`：事件流记录错误，操作区显示红色硬边错误条。
- `terminal`：停止动画和实时刷新，顶部显示完成原因。

恢复流程：

1. 首次进入页面先取 REST 快照。
2. 使用快照中的序列基准连接 WebSocket。
3. WebSocket 事件按 `seq` 去重合并。
4. 断线后进入 `RECOVERING SNAPSHOT`。
5. 收到需要快照的恢复信号后重新获取 REST 快照。
6. 快照恢复完成后再应用后续实时事件。

## 后置条件

以下能力不是第一版既有能力，不能在 UI 中伪装为已支持：

- 配平控件真实影响会话创建。
- 保存或正式发布时间轴插桩。
- 内部诊断角色查看原始 COT。
- 后端未提供字段时由前端计算正式崩塌概率。
- 移动端信息架构和卡片流重排。
- 图谱布局结果回传后端或进入 Agent。

