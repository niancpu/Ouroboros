# Web API 协议总览

## 目标

定义后端推演系统与前端之间的 API 协议。前端只消费可展示数据和控制面状态，不参与 Agent 决策，不作为任何业务数据的唯一真理源。

前端访问路径固定为 Web API 层：REST 通过 API Gateway，实时事件通过 `FrontendRealtimeGateway`。前端不得直连内部 Redis、内部 Pub/Sub channel、Layer 0/1/2/3 模块接口或任何 Agent runtime。

## 协议范围

| 文档 | 覆盖范围 |
| :--- | :--- |
| [realtime_ws.md](realtime_ws.md) | WebSocket 实时推送：市场、盘口异动、账户快照、审计图、因果链、生命周期事件 |
| [control_rest.md](control_rest.md) | REST 控制接口：会话创建、启动、暂停、单步、快照查询 |
| [visibility_and_errors.md](visibility_and_errors.md) | 前端可见性边界、错误码、断线恢复规则 |

## 前端定位

前端是 Layer 4 展示层，只负责：

- 展示市场状态。
- 展示 Agent 公开画像、风险状态和脱敏审计图。
- 发起控制面操作，例如启动、暂停、单步推进。
- 查询当前会话快照。

前端不得：

- 写入 `Order_Input`。
- 写入 `UI_Audit`。
- 写入 `Forum_Rumors`。
- 修改 Agent 私有记忆。
- 修改 Layer 3 账本、持仓、冻结股或 LOB。
- 把 `Frontend_Audit_Graph` 回流给任何 Agent。
- 读取内部 Redis 或订阅内部频道。
- 读取 Agent 原始 payload、私有 `thought`、Prompt 或私有记忆。

## API 风格

| 类型 | 用途 | 说明 |
| :--- | :--- | :--- |
| REST | 控制命令、快照查询 | 请求必须幂等或带 `request_id` |
| WebSocket | 实时推送 | 后端主动推送，前端只发送订阅、心跳和 ack |

## 可见性映射

内部事件和 Web API 事件使用两套 visibility 枚举。转换只能由 Web API 层或 `FrontendRealtimeGateway` 完成，前端只看到 Web API visibility。

| 内部 visibility | Web API visibility | 说明 |
| :--- | :--- | :--- |
| `public` | `public` | 市场公开信息 |
| `agent_private` | `agent_private_snapshot` | 仅账户快照类数据可转为前端审计视图；Agent 侧仍只能收到本人快照 |
| `frontend_only` | `frontend_only` | 前端专用审计视图，禁止进入 Agent |
| `control_only` | `control_only_view` | 运行状态或错误摘要，不暴露内部原始 payload |

`Order_Input`、`UI_Audit`、Agent 原始 payload、`trade_batch`、`risk_result` 等内部原始事件不得直接转换为 Web API 事件。

## 通用字段

所有响应和推送事件必须包含：

```json
{
  "schema_version": "v1",
  "session_id": "sim_001",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "trace_id": "trace_abc",
  "server_time": "2024-01-02T14:02:01+08:00"
}
```

约束：

- `session_id` 标识一次推演会话。
- `tick_id` 是模拟时间，只能由 Meta-Orchestrator 推进。
- `server_time` 是真实服务器时间。
- `trace_id` 用于排错，不作为 Agent 输入。
- Web API 响应和推送不得包含原始 `thought`、Prompt、私有记忆、Agent 原始 payload 或内部频道原始消息。

## 数据来源映射

| 前端事件 | 后端来源 | 内部契约 |
| :--- | :--- | :--- |
| `market.price` | Layer 3 `Market_Price` | `order_and_clearing_contract.md` |
| `market.tape_alert` | ExchangeBroadcaster `Tape_Alerts` | `referee_publication_contract.md` |
| `market.end_of_day` | ExchangeBroadcaster `End_of_Day` | `referee_publication_contract.md` |
| `forum.post` | Meta-Orchestrator `Forum_Rumors` | `agent_payload_contract.md`、`channel_routing.md` |
| `agent.account_snapshot` | Layer 3 `Account_Snapshot` | `order_and_clearing_contract.md` |
| `audit.graph` | UIAuditOfficer `Frontend_Audit_Graph` | `referee_publication_contract.md` |
| `audit.causal_chain` | UIAuditOfficer `Frontend_Causal_Chain` | `referee_publication_contract.md` |
| `runtime.tick_state` | Meta-Orchestrator | `tick_lifecycle.md` |
| `runtime.agent_lifecycle` | Meta-Orchestrator | `tick_lifecycle.md` |

## 版本策略

- 当前协议版本为 `v1`。
- 新增字段必须向后兼容。
- 删除字段、改字段类型、改变枚举语义必须升级 `schema_version`。
- 前端必须忽略未知字段。
