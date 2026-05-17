# Realtime WebSocket API

## 目标

定义后端向前端推送实时事件的 WebSocket 协议。WebSocket 只用于展示和控制面状态同步，不允许前端通过该连接写入市场业务数据。

WebSocket 连接由 `FrontendRealtimeGateway` 提供。前端不得直连内部 Redis、内部 Pub/Sub channel、`UI_Audit`、`Order_Input` 或任何 Agent runtime。

页面级消费需求见 [../frontend/frontend_design.md](../frontend/frontend_design.md)。本文是 WebSocket 入口、客户端消息、服务端事件信封和事件 payload 的权威来源。

## 连接

```text
GET /api/v1/sessions/{session_id}/ws
```

查询参数：

| 参数 | 必填 | 说明 |
| :--- | :--- | :--- |
| `client_id` | 是 | 前端实例 id，用于断线恢复和 ack |
| `from_seq` | 否 | 断线恢复起始序号，exclusive 语义；不传则从最新事件开始 |

`from_seq=1024` 表示服务端从 `seq > 1024` 的事件开始回放。前端从 REST 快照恢复时应使用 `from_seq=snapshot.last_seq`。

## 客户端消息

前端只能发送三类消息：

### `subscribe`

```json
{
  "type": "subscribe",
  "request_id": "req_001",
  "topics": [
    "runtime",
    "market",
    "agent",
    "audit"
  ]
}
```

`topics` 合法值：

- `runtime`
- `market`
- `agent`
- `audit`

订阅成功后，服务端返回连接控制消息 `subscribed`，并可立即回放符合 topic 且 `seq > from_seq` 的缓存事件。订阅失败必须返回错误控制消息或发送 `system.error`，并在 details 中回填客户端 `request_id`。

### `ack`

```json
{
  "type": "ack",
  "request_id": "req_002",
  "last_seq": 1024
}
```

### `ping`

```json
{
  "type": "ping",
  "request_id": "req_003",
  "client_time": "2024-01-02T14:02:01+08:00"
}
```

服务端收到合法 `ping` 后返回：

```json
{
  "type": "pong",
  "request_id": "req_003",
  "server_time": "2024-01-02T14:02:01+08:00"
}
```

`pong` 是连接控制消息，不进入事件回放缓冲，不占用 `seq`。

### 连接控制消息

连接控制消息只响应当前 WebSocket 客户端，不进入事件回放缓冲，不占用 `seq`。

订阅成功：

```json
{
  "schema_version": "v1",
  "request_id": "req_001",
  "server_time": "2024-01-02T14:02:01+08:00",
  "data": {
    "topics": ["runtime", "market"]
  }
}
```

Ack 确认：

```json
{
  "schema_version": "v1",
  "request_id": "req_002",
  "server_time": "2024-01-02T14:02:01+08:00",
  "data": {
    "last_seq": 1024
  }
}
```

客户端不得把连接控制消息写入事件时间线；前端状态恢复仍以 REST `snapshot` 和服务端事件信封为准。

禁止：

- 通过 WebSocket 提交订单。
- 通过 WebSocket 修改 Agent 状态。
- 通过 WebSocket 发布论坛消息。
- 通过 WebSocket 写入审计图。
- 通过 WebSocket 订阅内部 Redis channel。
- 通过 WebSocket 请求 `UI_Audit`、Agent 原始 payload、私有 `thought`、Prompt 或私有记忆。

## 服务端事件信封

所有服务端推送事件使用统一信封：

```json
{
  "schema_version": "v1",
  "seq": 1024,
  "type": "market.price",
  "session_id": "sim_001",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "trace_id": "trace_abc",
  "server_time": "2024-01-02T14:02:01+08:00",
  "visibility": "public",
  "payload": {}
}
```

字段约束：

- `seq` 在单个 `session_id` 内严格递增。
- `type` 使用 `domain.event` 命名。
- `visibility` 取值：`public`、`frontend_only`、`agent_private_snapshot`、`control_only_view`。
- `visibility` 是 Web API visibility，不是内部 visibility。内部枚举到 Web API 枚举的映射见 [visibility_and_errors.md](visibility_and_errors.md)。
- `payload` 只能包含前端协议字段，不得包含内部 Redis 原始消息、内部 channel payload、Agent 原始 payload 或任何私有字段。

## 事件类型

| Type | Topic | 来源 | 说明 |
| :--- | :--- | :--- | :--- |
| `runtime.tick_state` | `runtime` | Meta-Orchestrator | Tick 状态机进度 |
| `runtime.agent_lifecycle` | `runtime` | Meta-Orchestrator | Agent 生命周期变化 |
| `market.price` | `market` | Layer 3 | 价格、成交量、Level-2 快照 |
| `market.tape_alert` | `market` | ExchangeBroadcaster | 匿名盘口异动 |
| `market.end_of_day` | `market` | ExchangeBroadcaster | 收盘统计和龙虎榜 |
| `forum.post` | `market` | Meta-Orchestrator | 公开论坛帖子 |
| `agent.account_snapshot` | `agent` | ClearingHouse | 前端审计视图用账户快照 |
| `audit.graph` | `audit` | UIAuditOfficer | 前端拓扑图和脱敏解释 |
| `audit.causal_chain` | `audit` | UIAuditOfficer | 前端因果链时间线 |
| `system.error` | `runtime` | WebApiGateway | 可恢复或不可恢复错误 |

## `runtime.tick_state`

```json
{
  "type": "runtime.tick_state",
  "visibility": "control_only_view",
  "payload": {
    "state": "MATCH_AND_CLEAR",
    "previous_state": "PAYLOAD_SPLIT",
    "active_agent_count": 24,
    "completed_agent_count": 24,
    "timeout_agent_count": 0,
    "can_advance": false
  }
}
```

`state` 取值与 `docs/internal_contracts/tick_lifecycle.md` 保持一致。

## `runtime.agent_lifecycle`

```json
{
  "type": "runtime.agent_lifecycle",
  "visibility": "control_only_view",
  "payload": {
    "agent_id": "retail_b",
    "agent_type": "retail",
    "lifecycle_state": "margin_call",
    "reason_code": "equity_drawdown_limit",
    "public_label": "已触发强平线"
  }
}
```

`lifecycle_state` 取值：

- `active`
- `suspended`
- `margin_call`
- `liquidating`
- `terminated`

## `market.price`

```json
{
  "type": "market.price",
  "visibility": "public",
  "payload": {
    "symbol": "demo_stock",
    "last_price": 15.2,
    "volume": 100000,
    "turnover": 1520000.0,
    "limit_up": 16.5,
    "limit_down": 13.5,
    "limit_state": "normal",
    "level2": {
      "bids": [["15.19", 12000], ["15.18", 9000]],
      "asks": [["15.21", 8000], ["15.22", 11000]]
    }
  }
}
```

约束：

- 不包含 Agent 身份。
- 不包含订单 id。
- 不包含订单理由。
- 不包含底层 LOB 队列。

## `market.tape_alert`

```json
{
  "type": "market.tape_alert",
  "visibility": "public",
  "payload": {
    "symbol": "demo_stock",
    "alert_type": "large_sell_pressure",
    "severity": "medium",
    "public_text": "该股遭遇连续千手大单砸盘，当前跌幅扩大至 5%，下方买盘承接乏力。",
    "metrics": {
      "price_change_pct": -3.0,
      "sell_volume": 500000,
      "bid_depth_change_pct": -35.0
    }
  }
}
```

约束：

- `public_text` 只能描述匿名市场状态。
- 不得出现 `thought` 原文或摘要。
- 不得出现“某机构正在出货”这类身份绑定意图。

## `market.end_of_day`

```json
{
  "type": "market.end_of_day",
  "visibility": "public",
  "payload": {
    "symbol": "demo_stock",
    "close_price": 15.2,
    "volume": 12000000,
    "turnover": 182400000.0,
    "dragon_tiger": {
      "buy_rank": [
        {
          "seat_name": "拉萨团结路",
          "seat_type": "retail_cluster",
          "buy_amount": 50000000.0,
          "sell_amount": 12000000.0,
          "net_amount": 38000000.0
        }
      ],
      "sell_rank": [
        {
          "seat_name": "机构专用",
          "seat_type": "institution",
          "buy_amount": 10000000.0,
          "sell_amount": 80000000.0,
          "net_amount": -70000000.0
        }
      ]
    }
  }
}
```

## `forum.post`

```json
{
  "type": "forum.post",
  "visibility": "public",
  "payload": {
    "post_id": "forum_post_123",
    "author_agent_id": "hot_money_a",
    "author_type": "hot_money",
    "text": "公开股吧内容",
    "stance": "bullish",
    "created_tick_id": "2024-01-02T14:02:00+08:00"
  }
}
```

约束：

- `text` 是公开帖子，不是 Agent 私有 `thought`。
- 前端可以展示作者类型和模拟作者 id，但不得把帖子反写到任何 Agent 输入通道。

## `agent.account_snapshot`

```json
{
  "type": "agent.account_snapshot",
  "visibility": "agent_private_snapshot",
  "payload": {
    "agent_id": "mutual_fund_a",
    "agent_type": "mutual_fund",
    "cash": 1200000.0,
    "available_cash": 1200000.0,
    "positions": {
      "demo_stock": 300000
    },
    "available_shares": {
      "demo_stock": 0
    },
    "frozen_shares": {
      "demo_stock": 300000
    },
    "market_value": 4560000.0,
    "equity": 5760000.0,
    "risk_state": "normal"
  }
}
```

说明：

- 前端可以用于展示和审计。
- Agent 仍只能收到自己的 `Account_Snapshot`。
- 前端显示全量账户快照不改变 Agent 信息权限。
- `agent_private_snapshot` 只用于 Web API 审计视图，不等同于内部 `agent_private` 频道开放给前端直连。

## `audit.graph`

```json
{
  "type": "audit.graph",
  "visibility": "frontend_only",
  "payload": {
    "nodes": [
      {
        "agent_id": "retail_b",
        "agent_type": "retail",
        "belief_score": 0.42,
        "position_value": 152000.0,
        "risk_state": "normal"
      }
    ],
    "edges": [
      {
        "source": "hot_money_a",
        "target": "retail_b",
        "weight": 0.34,
        "reason_ref": "forum_post_123",
        "public_reason": "散户 B 受公开股吧帖子影响后信念上升"
      }
    ]
  }
}
```

约束：

- 不包含原始 `thought`、`thought` 摘要、Prompt、私有记忆或 Agent 原始 payload。
- `public_reason` 必须是脱敏解释。
- `visibility=frontend_only` 的事件不得进入 Agent runtime。

## `audit.causal_chain`

用于前端展示一条可读的因果链，例如：

```text
公开帖子 -> 散户信念上升 -> 买单增加 -> 价格上涨 -> 更多散户追涨
```

事件示例：

```json
{
  "type": "audit.causal_chain",
  "visibility": "frontend_only",
  "payload": {
    "chain_id": "chain_001",
    "title": "游资帖子触发散户追涨",
    "summary": "公开股吧帖子推动散户信念上升，随后买单增加并抬高价格。",
    "steps": [
      {
        "step_id": "step_001",
        "step_type": "public_message",
        "tick_id": "2024-01-02T14:00:00+08:00",
        "actor_id": "hot_money_a",
        "event_ref": "forum_post_123",
        "label": "游资发布看多帖子",
        "public_text": "公开帖子被散户群体看到"
      },
      {
        "step_id": "step_002",
        "step_type": "belief_shift",
        "tick_id": "2024-01-02T14:02:00+08:00",
        "actor_id": "retail_b",
        "event_ref": "audit_graph_001",
        "label": "散户信念上升",
        "public_text": "散户 B 对上涨叙事的信任增强"
      },
      {
        "step_id": "step_003",
        "step_type": "order_flow",
        "tick_id": "2024-01-02T14:02:00+08:00",
        "actor_id": "retail_cluster",
        "event_ref": "mkt_001",
        "label": "买单增加",
        "public_text": "散户方向买入意愿增强，盘口买盘变厚"
      },
      {
        "step_id": "step_004",
        "step_type": "price_move",
        "tick_id": "2024-01-02T14:03:00+08:00",
        "actor_id": "market",
        "event_ref": "mkt_002",
        "label": "价格上涨",
        "public_text": "最新价上行并触发更多关注"
      }
    ],
    "metrics": {
      "price_change_pct": 2.1,
      "affected_agent_count": 8,
      "confidence": 0.76
    }
  }
}
```

`step_type` 取值：

- `official_news`
- `public_message`
- `tape_alert`
- `belief_shift`
- `order_flow`
- `price_move`
- `risk_event`
- `end_of_day_disclosure`

约束：

- 只展示脱敏因果解释。
- `public_text` 不得包含原始 `thought`、`thought` 摘要、Prompt、私有记忆或 Agent 原始 payload。
- `event_ref` 只能引用可展示事件或前端专用审计事件。
- `confidence` 表示审计官对链路强弱的估计，不是市场事实。
- `visibility=frontend_only`，不得回流 Agent。

## `system.error`

```json
{
  "type": "system.error",
  "visibility": "control_only_view",
  "payload": {
    "code": "WS_BACKPRESSURE",
    "message": "client is consuming events too slowly",
    "retryable": true,
    "details": {
      "dropped_after_seq": 2048
    }
  }
}
```

错误码见 [visibility_and_errors.md](visibility_and_errors.md)。

## 背压与断线恢复

- 服务端为每个 `client_id` 保留最近 N 条事件，N 由配置决定。
- 前端重连时携带 `from_seq`，服务端返回 `seq > from_seq` 的事件。
- 如果 `from_seq` 已过期，服务端返回 `SNAPSHOT_REQUIRED`，前端必须先调用 REST 快照接口再重新订阅。
- 如果连接握手阶段已经能确认 `from_seq` 过期，服务端可以直接拒绝连接并返回 HTTP 409 + REST 错误体；如果 WebSocket 已建立，则发送 `system.error` 后关闭或等待客户端重连。
- 前端必须定期发送 `ack`，服务端可根据 `last_seq` 清理缓冲。
- 断线恢复只使用 REST `snapshot` 和 `FrontendRealtimeGateway` 回放缓冲，不要求也不允许前端读取内部 Redis。
