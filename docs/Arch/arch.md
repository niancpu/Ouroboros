# Ouroboros 架构总览

## 目标

定义一个面向 A 股市场推演的多智能体系统架构。系统核心要求是信息隔离、资金与订单 SSOT 统一、时间轴仅由控制面推进。

## 设计原则

- 控制面与数据面分离。
- 私有思考不回流公共总线。
- 资金、持仓、订单簿、历史事实各有唯一真理源。
- 所有频道按白名单路由。
- Tick 只能由 Meta-Orchestrator 推进。

## 模块分层

### 1. Control Plane: Meta-Orchestrator

职责：

- 推进全局 Tick。
- 管理 Agent 生命周期。
- 执行并发屏障。
- 切割 Agent 返回体。
- 驱动 Layer 0、Layer 3、Referee。

边界：

- 可以收集完整 Agent 返回体用于路由。
- 不参与金融逻辑计算。
- 不生成市场信号。
- 不把任意 Agent 私有 payload 写入公共 Redis 总线。

依赖：

- 详细设计见 [meta_orchestrator.md](meta_orchestrator.md)
- 控制面接口见 [../internal_contracts/control_plane_contract.md](../internal_contracts/control_plane_contract.md)
- Tick 生命周期契约见 [../internal_contracts/tick_lifecycle.md](../internal_contracts/tick_lifecycle.md)

### 2. Layer 0: Chronos 历史时间轴与事实底座

职责：

- 提供真实外部刺激。
- 按 Tick 释放历史事实。
- 在会话初始化阶段提供初始市场种子。
- 维护 `Chronos Data` 的唯一真理源。

组件：

- 时间轴数据源：只响应 Meta-Orchestrator 的释放指令。
- 双轨数据泵：官方轨与量价轨。
- 向量记忆库：用于历史相似事件检索。

约束：

- Agent 不得一次性读取全量历史。
- Layer 0 不得自行推进系统 Tick。
- `initial_market_seed` 只能由 Meta-Orchestrator 请求，并只交给 Layer 3 初始化市场状态，不进入 Agent 可订阅频道。

### 3. Layer 1: 异构智能体矩阵

职责：

- 维护 24+ 个 Agent 的内部状态机与私有 Prompt。
- 管理 Agent Profile、Prompt Profile、私有记忆命名空间。
- 生成 `thought` 与 `action`。

状态边界：

- `thought` 只能进入 UI 审计链路。
- `action` 是唯一允许影响市场的输出。
- `memory_update` 只能写入本 Agent 私有记忆。
- 资金、持仓、可卖数量只允许保存 Layer 3 推送的只读副本。

Agent 编队：

- 游资大佬 x2：动量驱动，偏情绪和盘口。
- 公募机构 x2：偏基本面和研报。
- 量化游资 x2：规则驱动，偏微观结构。
- 散户群体 x16：高 FOMO，高损失厌恶。
- 国家队 x2：极端行情下提供流动性。

设定与 Prompt 契约见 [../internal_contracts/agent_profile_prompt_contract.md](../internal_contracts/agent_profile_prompt_contract.md)。权限矩阵见 [../internal_contracts/agent_identity_permissions.md](../internal_contracts/agent_identity_permissions.md)。

### 4. Layer 2: 异步信息流沙盒

职责：

- 按权限转发事件。
- 承载黑板式公开信息流。
- 为前端和 Agent 提供短期实时事件缓冲。

约束：

- 不拥有资金、持仓、订单簿、历史事实或 Agent 私有记忆。
- 不作为业务 SSOT。
- Redis key/channel 必须按会话隔离，缓存必须有 TTL。
- WebSocket `ack/replay` 只用于前端断线恢复和事件缓冲清理，不得改变账本、订单、私有记忆或 Tick 状态。
- `Forum_Rumors_Internal` 只做公开帖子校验和去重，不允许 Agent 订阅。

信息池：

- 官方公告板：财报、监管函、宏观数据。
- 谣言股吧：游资生成的小作文。

Referee 边界：

- 交易所数据播报员只读 Layer 3 匿名市场输出。
- UI 渲染审查官只向前端输出审计图。

详细边界见 [referee_design.md](referee_design.md) 与 [../internal_contracts/channel_routing.md](../internal_contracts/channel_routing.md)。

### 5. Layer 3: A 股特色反身性清算引擎

职责：

- 维护 `Ledger`、`Positions`、`frozen_shares`、`LOB`。
- 校验订单、撮合、清算、冻结与快照发布。
- 生成 `trade_batch`、`risk_result` 和合规 `Market_Price`。

规则：

- 价格优先、时间优先撮合。
- `±10%` 涨跌停板硬约束。
- T+1 冻结必须由 Layer 3 统一执行。
- Agent 只能提交订单，不能直接读取底层 LOB。
- `forced_liquidation` 由 Meta-Orchestrator 触发，但仍由 Layer 3 校验和清算。
- `trade_batch`、`risk_result` 是 Layer 3 内部接口，不进入 Agent 可订阅频道。

子模块：

- `MatchingEngine`：维护 LOB，执行订单校验、撮合和成交生成。
- `ClearingHouse`：维护资金、持仓、冻结股和风险状态。
- `MarketDataPublisher`：接收撮合和订单簿脱敏视图，发布成交、价格和 Level-2 快照；MatchingEngine 不直接发布公共市场快照。

### 6. Layer 4: 流式可视化与研报输出

职责：

- 向前端展示市场状态与审计结果。
- 渲染拓扑图、持仓变化、公开信念变化。
- 渲染前端因果链，并在断线恢复快照中保留 `causal_chains` 摘要。

约束：

- 不展示核心机构 Agent 的私有 COT。
- 只消费脱敏后的公共事件和前端专用审计数据。
- 前端因果链只用于解释展示，不得回流 Agent。

### 基础设施: LLMGateway

职责：

- 统一模型调用、限流和结构化输出校验。
- 执行 Agent Prompt 调用，但不拥有任何金融业务事实。

约束：

- 不得跨 Agent 拼接上下文。
- 不得缓存资金、持仓、订单簿、私有记忆或历史事实作为 SSOT。
- 只做模型输出格式预检；最终安全校验、权限判断和字段路由必须由 Meta-Orchestrator 完成。

## 数据归属

系统核心数据归属见 [../internal_contracts/state_ownership.md](../internal_contracts/state_ownership.md)。

五个数据中心：

1. 控制中心：Meta-Orchestrator，拥有 Tick 推进、生命周期管理和路由切割权。
2. 资产中心：Layer 3，拥有 `Ledger`、`Positions`、`frozen_shares` 和 `LOB`。
3. 事实中心：Layer 0，拥有 `Chronos Data`。
4. 认知中心：Layer 1 Agent 本地，拥有 `Private Memory` 和认知状态。
5. 广播中心：Layer 2 Redis 总线，只按权限频道传递事件。

## 推荐技术栈

| 模块类别 | 推荐技术/框架 | 说明 |
| :--- | :--- | :--- |
| 控制编排层 | LangGraph (Python) | 适合作为 Meta-Orchestrator 的 Tick 状态机骨架。 |
| API 路由与限流 | LiteLLM Proxy + Redis | 统一模型接口，多 Key 轮询，吸收并发压力。 |
| 并发与异步 | `asyncio` + `FastAPI` | 处理高频 API 请求和 WebSocket 推送。 |
| 状态/事件总线 | Redis (Pub/Sub & JSON) | Pub/Sub 用于 Layer 2 广播，RedisJSON 仅缓存只读账户快照。 |
| 向量记忆库 | Milvus / Qdrant | 存储历史相似事件与 K 线形态。 |
| 撮合引擎 | Python `heapq` | 维护限价单薄，加入 T+1 与涨跌停逻辑。 |
| 前端图谱渲染 | ECharts Graph | 渲染力导向图与动态连线。 |
| 实时通信通道 | WebSockets | 后端推演完一个 Tick 后向前端 PUSH JSON。 |

## 依赖契约

- [../internal_contracts/README.md](../internal_contracts/README.md)
- [../internal_contracts/control_plane_contract.md](../internal_contracts/control_plane_contract.md)
- [../internal_contracts/agent_profile_prompt_contract.md](../internal_contracts/agent_profile_prompt_contract.md)
- [meta_orchestrator.md](meta_orchestrator.md)
- [referee_design.md](referee_design.md)
- [../internal_contracts/module_interface_registry.md](../internal_contracts/module_interface_registry.md)
- [../internal_contracts/channel_routing.md](../internal_contracts/channel_routing.md)
- [../internal_contracts/state_ownership.md](../internal_contracts/state_ownership.md)
- [../internal_contracts/tick_lifecycle.md](../internal_contracts/tick_lifecycle.md)

## 未决取舍

- 超时 Agent 的默认动作是 `HOLD`。
- 强平阈值是否按 Agent 类型配置，后续再定。
- UI 审计默认不阻塞 Tick 推进。
