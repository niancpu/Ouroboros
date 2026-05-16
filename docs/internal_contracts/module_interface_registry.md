# Module Interface Registry 内部契约

## 目标

把信息隔离架构拆成可实现、可测试、可替换的模块。本文只定义模块职责、调用方向和接口边界；具体字段 schema 分散在同目录的专项契约中。

## 模块总览

| 模块 | 层级 | 职责 | 拥有的数据 | 禁止事项 | 主要接口 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `MetaOrchestrator` | Control Plane | 推进 Tick、Agent 生命周期、并发屏障、payload 路由切割 | `tick_id`、运行状态、trace 日志 | 生成市场信号、改写账本、发布私有 payload | `release(tick_id)`、`act(tick_context)`、`match_and_clear(order_batch)` |
| `Chronos` | Layer 0 | 按 Tick 释放历史事实 | `Chronos Data`、历史事件索引 | 释放未来事实、让 Agent 直查全量库 | `release_facts(tick_id)` |
| `AgentRuntime` | Layer 1 | 维护 Agent 私有记忆、生成 action/thought | `Private Memory`、认知状态、只读资产快照 | 修改资产 SSOT、读取其他 Agent 记忆 | `act(tick_context)` |
| `LLMGateway` | Infra | API 路由、限流、模型供应商抽象 | 请求队列、限流状态 | 持久化业务事实、跨 Agent 拼接上下文 | `complete(agent_prompt)` |
| `RedisBus` | Layer 2 | 按权限转发事件与短期快照 | 可过期消息、订阅关系 | 成为业务 SSOT、承载私有 thought 公共广播 | Pub/Sub channels |
| `MatchingEngine` | Layer 3 | 维护 LOB、价格优先时间优先撮合 | `LOB`、订单状态 | 读取 Agent 私有 thought | `submit_orders(order_batch)`、`publish_market_view(tick_id)` |
| `ClearingHouse` | Layer 3 | 资金、持仓、冻结股、费用、风险状态 | `Global Ledger`、`Positions`、`frozen_shares` | 让 Agent 自行结算 | `settle(trades)`、`snapshot(agent_id)` |
| `ExchangeBroadcaster` | Referee/Public | 基于匿名市场输出生成盘口异动和盘后披露 | 脱敏市场事件缓存 | 读取或总结私有 thought | `build_tape_alerts(market_events)`、`build_eod_report(tick_id)` |
| `UIAuditOfficer` | Referee/UI | 基于私有审计材料生成前端拓扑图 | 审计事件缓存 | 输出给 Agent 可订阅频道 | `build_audit_graph(ui_audit_batch)` |
| `FrontendRealtimeGateway` | Layer 4 | 向前端推送市场视图和审计视图 | WebSocket 会话状态 | 作为 Agent 输入源 | WebSocket push |

## 调用拓扑

```text
MetaOrchestrator
  -> Chronos.release_facts(tick_id)
  -> MatchingEngine.publish_market_view(tick_id)
  -> AgentRuntime[*].act(tick_context)
  -> MatchingEngine.submit_orders(order_batch)
  -> ClearingHouse.settle(trades)
  -> ExchangeBroadcaster.build_tape_alerts(market_events)
  -> UIAuditOfficer.build_audit_graph(ui_audit_batch)
  -> commit tick
```

事件总线只负责模块间事件传递，不反向拥有业务状态：

```text
Chronos -> Official_News -> AgentRuntime
MatchingEngine -> Market_Price -> AgentRuntime / Frontend
ClearingHouse -> Account_Snapshot -> 对应 AgentRuntime / Frontend
ExchangeBroadcaster -> Tape_Alerts / End_of_Day -> AgentRuntime / Frontend
MetaOrchestrator -> Forum_Rumors -> 散户 AgentRuntime / Frontend
UIAuditOfficer -> Frontend_Audit_Graph -> Frontend only
```

说明：Agent 是 `Order_Input`、`UI_Audit`、`Forum_Rumors` 的语义来源，但实际频道发布者必须是 Meta-Orchestrator。Agent 原始 payload 不得绕过控制面直写公共频道。

## 接口形态

模块间接口分为两类：

| 类型 | 用途 | 示例 | 一致性要求 |
| :--- | :--- | :--- | :--- |
| 控制面调用 | 推进生命周期和同步屏障 | `release_facts`、`act`、`match_and_clear` | 必须返回明确成功、失败或超时 |
| 数据面事件 | 广播可见事实或审计材料 | Redis Pub/Sub channel payload | 必须带 `event_id`、`tick_id`、`schema_version` |

控制面调用可以用 Python 方法、RPC 或 LangGraph node 实现。第一版建议从进程内 Python 接口开始，等边界稳定后再拆成服务。

## 通用消息头

所有跨模块事件必须包含：

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
- `trace_id` 用于审计链路排错，不得作为 Agent 推理输入。

## 专项契约索引

| 契约 | 覆盖范围 |
| :--- | :--- |
| `agent_payload_contract.md` | Agent 输入上下文、输出 payload、字段级路由 |
| `agent_identity_permissions.md` | Agent 类型、频道订阅权限、发帖权限 |
| `chronos_release_contract.md` | Layer 0 历史事实释放、RAG 时间边界、官方新闻事件 |
| `order_and_clearing_contract.md` | 订单、撮合、成交、清算、T+1、账户快照 |
| `referee_publication_contract.md` | 盘口异动、龙虎榜、前端审计图发布规则 |
| `channel_routing.md` | Redis 频道权限、合法发布者和订阅者 |
| `state_ownership.md` | 数据所有权和 SSOT |
| `tick_lifecycle.md` | Tick 状态机和控制面推进顺序 |

## 取舍与后果

- `MatchingEngine` 和 `ClearingHouse` 在逻辑上拆分，但第一版可以同进程实现。后果是部署简单，但测试必须仍按两个职责分别覆盖。
- `LLMGateway` 是基础设施模块，不进入金融数据 SSOT。后果是它只能处理 prompt 和模型调用，不能缓存跨 Agent 的业务上下文。
- `FrontendRealtimeGateway` 只消费事件，不参与 Tick 推进。后果是前端掉线不能阻塞撮合和账本提交。

## 实现检查项

- 每个模块只能写入自己拥有的数据。
- 每个事件通道必须有固定发布者和订阅者白名单。
- 公共事件 schema 必须有自动校验，发现私有字段立即拒绝发布。
- 单元测试覆盖每个模块的禁止事项。
- 集成测试覆盖一次完整 Tick 的跨模块调用链。
