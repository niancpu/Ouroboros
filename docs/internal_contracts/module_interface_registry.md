# Module Interface Registry 内部契约

## 目标

把信息隔离架构拆成可实现、可测试、可替换的模块。本文只定义模块职责、调用方向和接口边界；具体字段 schema 分散在同目录的专项契约中。

更完整的契约索引见 [README.md](README.md)。新增模块或新增跨模块通信时，必须同步更新本文和专项契约。

## 模块总览

| 模块 | 层级 | 职责 | 拥有的数据 | 禁止事项 | 主要接口 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `MetaOrchestrator` | Control Plane | 推进 Tick、Agent 生命周期、并发屏障、payload 路由切割 | `session_id`、`tick_id`、运行状态、trace 日志 | 生成市场信号、改写账本、发布私有 payload | `create_session(config)`、`run_tick(tick_id)`、`split_payload(payload)`、`handle_lifecycle(risk_result)` |
| `Chronos` | Layer 0 | 按 Tick 释放历史事实、提供初始化市场种子 | `Chronos Data`、历史事件索引 | 释放未来事实、让 Agent 直查全量库 | `release_facts(tick_id)`、`build_initial_market_seed(session_config)` |
| `AgentRuntime` | Layer 1 | 维护 Agent 私有记忆、生成 action/thought | `Private Memory`、认知状态、只读资产快照、Prompt Profile 引用 | 修改资产 SSOT、读取其他 Agent 记忆 | `act(tick_context)`、`memory_read(query)`、`memory_write(summary)` |
| `LLMGateway` | Infra | API 路由、限流、模型供应商抽象、模型输出格式预检 | 请求队列、限流状态 | 持久化业务事实、跨 Agent 拼接上下文、做最终安全路由判断 | `complete(agent_prompt)`、`precheck_structured_output(raw_output)` |
| `RedisBus` | Layer 2 | 按权限转发事件与短期快照 | 可过期消息、订阅关系 | 成为业务 SSOT、承载私有 thought 公共广播 | Pub/Sub channels |
| `MatchingEngine` | Layer 3 | 维护 LOB、价格优先时间优先撮合、生成成交批次 | `LOB`、订单状态 | 读取 Agent 私有 thought、直接发布公共市场快照 | `initialize_market(seed)`、`submit_orders(order_batch)`、`match_orders(tick_id)` |
| `ClearingHouse` | Layer 3 | 资金、持仓、冻结股、费用、风险状态 | `Global Ledger`、`Positions`、`frozen_shares` | 让 Agent 自行结算 | `settle(trades)`、`snapshot(agent_id)` |
| `MarketDataPublisher` | Layer 3 | 生成合规成交、价格和 Level-2 快照 | 脱敏市场快照缓存 | 发布底层 LOB、订单 id、身份绑定意图 | `publish_market_view(tick_id)`、`build_market_price(trades, lob_view)` |
| `ExchangeBroadcaster` | Referee/Public | 基于匿名市场输出生成盘口异动和盘后披露 | 脱敏市场事件缓存 | 读取或总结私有 thought | `build_tape_alerts(market_events)`、`build_eod_report(tick_id)` |
| `UIAuditOfficer` | Referee/UI | 基于私有审计材料生成前端拓扑图和因果链 | 审计事件缓存 | 输出给 Agent 可订阅频道 | `build_audit_graph(ui_audit_batch)`、`build_causal_chain(audit_context)` |
| `WebApiGateway` | Layer 4 | REST 会话控制、快照查询、事件回放、Web API visibility 转换 | HTTP 请求状态、幂等键、前端事件索引 | 绕过 Meta-Orchestrator 或 Layer 3 改业务状态、透传内部 payload | `/api/v1/sessions/*` |
| `FrontendRealtimeGateway` | Layer 4 | 向前端推送市场视图和审计视图 | WebSocket 会话状态 | 作为 Agent 输入源 | WebSocket push |

## 调用拓扑

```text
MetaOrchestrator
  -> create_session(config)
  -> Chronos.build_initial_market_seed(config)
  -> MatchingEngine.initialize_market(seed)
  -> Chronos.release_facts(tick_id)
  -> MarketDataPublisher.publish_market_view(tick_id)
  -> AgentRuntime[*].act(tick_context)
  -> split_agent_payload(payload)
  -> MatchingEngine.submit_orders(order_batch)
  -> ClearingHouse.settle(trades)
  -> MarketDataPublisher.build_market_price(trades, lob_view)
  -> handle_lifecycle(risk_result)
  -> ExchangeBroadcaster.build_tape_alerts(market_events)
  -> UIAuditOfficer.build_audit_graph(ui_audit_batch)
  -> commit tick
```

事件总线只负责模块间事件传递，不反向拥有业务状态：

```text
Chronos -> Official_News -> AgentRuntime
MarketDataPublisher -> Market_Price -> AgentRuntime / FrontendRealtimeGateway
ClearingHouse -> Account_Snapshot -> 对应 AgentRuntime / FrontendRealtimeGateway
ExchangeBroadcaster -> Tape_Alerts / End_of_Day -> AgentRuntime / FrontendRealtimeGateway
MetaOrchestrator -> Forum_Rumors(validated forum_post) -> 散户 AgentRuntime / FrontendRealtimeGateway
UIAuditOfficer -> Frontend_Audit_Graph / Frontend_Causal_Chain -> FrontendRealtimeGateway only
WebApiGateway -> MetaOrchestrator: create/start/pause/step/stop session commands
WebApiGateway -> Frontend: snapshot/events REST responses
FrontendRealtimeGateway -> Frontend: Web API event envelopes
```

说明：Agent 是 `Order_Input`、`UI_Audit`、`Forum_Rumors` 的语义来源；Meta-Orchestrator 只负责校验和转发，不生成论坛内容。Agent 原始 payload 不得绕过控制面直写公共频道。

前端不得订阅内部 Redis channel。上图中的 Frontend 只表示经 `WebApiGateway` 或 `FrontendRealtimeGateway` 转换后的 Web API 协议出口。

## 接口形态

模块间接口分为两类：

| 类型 | 用途 | 示例 | 一致性要求 |
| :--- | :--- | :--- | :--- |
| 控制面调用 | 推进生命周期和同步屏障 | `release_facts`、`act`、`match_and_clear` | 必须返回明确成功、失败或超时 |
| 数据面事件 | 广播可见事实或审计材料 | Redis Pub/Sub channel payload | 必须带 `event_id`、`tick_id`、`schema_version` |

控制面调用可以用 Python 方法、RPC 或 LangGraph node 实现。第一版建议从进程内 Python 接口开始，等边界稳定后再拆成服务。

## 通用消息头

所有内部跨模块事件必须包含：

```json
{
  "schema_version": "v1",
  "event_id": "evt_001",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "trace_id": "trace_abc",
  "producer": "module_name",
  "visibility": "public|agent_private|frontend_only|control_only",
  "created_at": "2024-01-02T14:02:01+08:00"
}
```

约束：

- `visibility=public` 的事件不得包含 `thought`、私有记忆、未公开订单理由、身份绑定意图。
- `visibility=agent_private` 的事件必须绑定 `agent_id`，只能投递给对应 Agent。
- `visibility=frontend_only` 的事件不得被 Agent runtime 订阅。
- `visibility=control_only` 的事件只能在控制面和内部模块之间传递，不进入 Agent 或前端普通事件流。
- `trace_id` 用于审计链路排错，不得作为 Agent 推理输入。

## 内部与 Web API 可见性映射

内部事件和 Web API 事件使用两套枚举。转换只能由 `WebApiGateway` 或 `FrontendRealtimeGateway` 完成。

| 内部 visibility | Web API visibility | 说明 |
| :--- | :--- | :--- |
| `public` | `public` | 市场公开信息，可进入前端，也可按权限进入 Agent |
| `agent_private` | `agent_private_snapshot` | 仅账户快照类数据可转为前端审计视图；Agent 侧仍只能收到本人快照 |
| `frontend_only` | `frontend_only` | 只给前端展示，禁止进入 Agent |
| `control_only` | `control_only_view` | 只展示运行状态或错误摘要，不暴露内部原始 payload |

约束：

- `Order_Input`、`UI_Audit`、`trade_batch`、`risk_result` 等内部原始事件不得直接转换成 Web API 事件。
- Web API 层不得新增比内部 visibility 更宽的可见性。
- 前端事件回放只能回放 Web API visibility，不得要求前端读取内部 Redis。
- REST `snapshot` 和 `events` 只能返回 Web API 事件或快照字段，不得返回内部 channel payload。
- WebSocket `ack/replay` 只能影响 `FrontendRealtimeGateway` 的前端缓冲，不得改变账本、订单、私有记忆或 Tick 状态。

## 专项契约索引

| 契约 | 覆盖范围 |
| :--- | :--- |
| `README.md` | 模块到接口的覆盖矩阵、阅读顺序、契约完整性标准 |
| `control_plane_contract.md` | Meta-Orchestrator 会话初始化、Tick 推进、payload 切割、生命周期处理 |
| `agent_payload_contract.md` | Agent 输入上下文、输出 payload、字段级路由 |
| `agent_profile_prompt_contract.md` | Agent 设定、Prompt Profile、私有记忆接口、LLM 调用边界 |
| `agent_identity_permissions.md` | Agent 类型、频道订阅权限、发帖权限 |
| `chronos_release_contract.md` | Layer 0 历史事实释放、RAG 时间边界、官方新闻事件 |
| `order_and_clearing_contract.md` | 订单、撮合、成交、清算、T+1、账户快照 |
| `referee_publication_contract.md` | 盘口异动、龙虎榜、前端审计图发布规则 |
| `channel_routing.md` | Redis 频道权限、合法发布者和订阅者 |
| `state_ownership.md` | 数据所有权和 SSOT |
| `tick_lifecycle.md` | Tick 状态机和控制面推进顺序 |

## 取舍与后果

- `MatchingEngine`、`ClearingHouse` 和 `MarketDataPublisher` 在逻辑上拆分，但第一版可以同进程实现。后果是部署简单，但测试必须仍按三个职责分别覆盖。
- `LLMGateway` 是基础设施模块，不进入金融数据 SSOT。它只能做模型调用和格式预检；最终安全校验、权限判断和字段路由必须由 Meta-Orchestrator 完成。
- `FrontendRealtimeGateway` 只消费事件，不参与 Tick 推进。后果是前端掉线不能阻塞撮合和账本提交。
- `WebApiGateway` 和 `FrontendRealtimeGateway` 是协议适配层，不是新的业务 SSOT。后果是前端协议可以独立演进，但每个 Web API 字段都必须能追溯到内部契约来源。

## 实现检查项

- 每个模块只能写入自己拥有的数据。
- 每个事件通道必须有固定发布者和订阅者白名单。
- 公共事件 schema 必须有自动校验，发现私有字段立即拒绝发布。
- 单元测试覆盖每个模块的禁止事项。
- 集成测试覆盖一次完整 Tick 的跨模块调用链。
