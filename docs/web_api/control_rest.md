# Control REST API

## 目标

定义前端调用控制面的 REST 接口。REST 只用于会话管理、运行控制和快照查询，不允许前端直接修改市场业务状态。

REST 访问路径固定为 Web API 层 `WebApiGateway`。前端不得通过 REST 直连内部 Redis、内部 Pub/Sub channel、Layer 0/1/2/3 模块接口或 Agent runtime。

页面级消费需求见 [../frontend/frontend_design.md](../frontend/frontend_design.md)。本文是 REST 端点、请求、响应和状态语义的权威来源。当前代码中的 `ControlRestApi` 是 `WebApiGateway` 的 framework-free 核心适配器；是否外包 FastAPI 只属于部署封装选择，不改变本文协议。

## 基础路径

```text
/api/v1
```

## 通用请求头

| Header | 必填 | 说明 |
| :--- | :--- | :--- |
| `Content-Type: application/json` | 有 JSON 请求体时必填 | `GET` 等无请求体请求不要求 |
| `X-Request-Id` | 是 | 幂等与审计 id |

## 通用响应

成功：

```json
{
  "schema_version": "v1",
  "request_id": "req_001",
  "session_id": "sim_001",
  "trace_id": "trace_abc",
  "server_time": "2024-01-02T14:02:01+08:00",
  "data": {}
}
```

失败：

```json
{
  "schema_version": "v1",
  "request_id": "req_001",
  "trace_id": "trace_abc",
  "server_time": "2024-01-02T14:02:01+08:00",
  "error": {
    "code": "SESSION_NOT_FOUND",
    "message": "session does not exist",
    "retryable": false
  }
}
```

## 创建会话

```text
POST /api/v1/sessions
```

请求：

```json
{
  "scenario_id": "demo_a_share",
  "symbol": "demo_stock",
  "agent_profile_set": "default_24",
  "start_tick_id": "2024-01-02T09:30:00+08:00",
  "end_tick_id": "2024-01-02T15:00:00+08:00",
  "tick_interval": "5m"
}
```

响应：

```json
{
  "schema_version": "v1",
  "request_id": "req_001",
  "session_id": "sim_001",
  "trace_id": "trace_abc",
  "server_time": "2024-01-02T09:29:30+08:00",
  "data": {
    "session_id": "sim_001",
    "status": "created",
    "current_tick_id": "2024-01-02T09:30:00+08:00",
    "websocket_url": "/api/v1/sessions/sim_001/ws"
  }
}
```

约束：

- 创建会话只初始化控制面，不自动推进 Tick。
- 初始资金、持仓和 LOB 仍由 Layer 3 初始化。

## 获取会话

```text
GET /api/v1/sessions/{session_id}
```

响应：

```json
{
  "schema_version": "v1",
  "request_id": "req_001",
  "session_id": "sim_001",
  "trace_id": "trace_abc",
  "server_time": "2024-01-02T14:02:01+08:00",
  "data": {
    "session_id": "sim_001",
    "status": "running",
    "current_tick_id": "2024-01-02T14:02:00+08:00",
    "tick_state": "AGENT_STEP",
    "agent_count": 24,
    "active_agent_count": 23,
    "created_at": "2024-01-02T09:29:30+08:00"
  }
}
```

`status` 取值：

- `created`
- `running`
- `paused`
- `completed`
- `failed`

## 启动会话

```text
POST /api/v1/sessions/{session_id}/start
```

请求：

```json
{
  "mode": "continuous"
}
```

`mode` 取值：

- `continuous`：持续推进到暂停、失败或结束。

响应：

```json
{
  "schema_version": "v1",
  "request_id": "req_001",
  "session_id": "sim_001",
  "trace_id": "trace_abc",
  "server_time": "2024-01-02T14:02:01+08:00",
  "data": {
    "session_id": "sim_001",
    "status": "running",
    "accepted": true
  }
}
```

说明：REST `/events` 返回完整 Web API event envelope，字段与 [realtime_ws.md](realtime_ws.md) 的服务端事件信封一致；示例 payload 可为空对象，但事件信封字段不得省略。

约束：

- `start` 只负责把 `created` 或 `paused` 会话切到连续运行。
- 单步推进统一使用 `/step`，避免与 `start` 语义重叠。
- 如果会话仍处于 `created`，启动前必须先完成初始化流程并发布第一份合规 `Market_Price`；不得跳过 Chronos 初始种子和 Layer 3 初始化。

## 暂停会话

```text
POST /api/v1/sessions/{session_id}/pause
```

请求：

```json
{
  "reason": "operator_pause"
}
```

响应：

```json
{
  "schema_version": "v1",
  "request_id": "req_001",
  "session_id": "sim_001",
  "trace_id": "trace_abc",
  "server_time": "2024-01-02T14:02:01+08:00",
  "data": {
    "session_id": "sim_001",
    "status": "paused",
    "pause_after_state": "COMMIT_TICK"
  }
}
```

约束：

- 暂停应在安全点生效。
- 默认安全点为 `COMMIT_TICK` 后。
- 不得在 Layer 3 清算中间强停导致账本半提交。
- 第一版 `pause` 响应表示暂停已经在安全点提交完成；如果实现选择异步接受暂停请求，必须返回 `accepted: true`、`status: running` 和目标安全点，不能伪装成已暂停。

## 单步推进

```text
POST /api/v1/sessions/{session_id}/step
```

请求：

```json
{
  "ticks": 1
}
```

响应：

```json
{
  "schema_version": "v1",
  "request_id": "req_001",
  "session_id": "sim_001",
  "trace_id": "trace_abc",
  "server_time": "2024-01-02T14:02:01+08:00",
  "data": {
    "session_id": "sim_001",
    "status": "running",
    "scheduled_ticks": 1
  }
}
```

约束：

- `ticks` 第一版只允许 `1`。
- 只有 `created` 或 `paused` 状态允许单步。
- `step` 响应表示单步 Tick 已被调度，返回时会话短暂处于 `running`。
- 该 Tick 到达 `COMMIT_TICK` 后，会话必须自动回到 `paused`；前端通过 `runtime.tick_state` 或会话查询确认完成。
- 如果会话仍处于 `created`，单步前必须先完成初始化流程并发布第一份合规 `Market_Price`。

## 获取当前快照

```text
GET /api/v1/sessions/{session_id}/snapshot
```

响应：

```json
{
  "schema_version": "v1",
  "request_id": "req_001",
  "session_id": "sim_001",
  "trace_id": "trace_abc",
  "server_time": "2024-01-02T14:02:01+08:00",
  "data": {
    "session_id": "sim_001",
    "last_seq": 1024,
    "current_tick_id": "2024-01-02T14:02:00+08:00",
    "tick_state": "COMMIT_TICK",
    "market": {
      "symbol": "demo_stock",
      "last_price": 15.2,
      "volume": 100000,
      "limit_state": "normal",
      "level2": {
        "bids": [["15.19", 12000]],
        "asks": [["15.21", 8000]]
      }
    },
    "agents": [
      {
        "agent_id": "retail_b",
        "agent_type": "retail",
        "lifecycle_state": "active",
        "risk_state": "normal",
        "equity": 5760000.0,
        "position_value": 152000.0
      }
    ],
    "audit_graph": {
      "nodes": [],
      "edges": []
    },
    "causal_chains": [
      {
        "chain_id": "chain_001",
        "title": "游资帖子触发散户追涨",
        "summary": "公开股吧帖子推动散户信念上升，随后买单增加并抬高价格。",
        "last_event_ref": "mkt_002"
      }
    ]
  }
}
```

约束：

- 快照用于前端恢复视图，不用于 Agent 输入。
- 快照中的 `audit_graph` 必须是脱敏结果。
- 快照中的 `causal_chains` 只保存可恢复摘要和最近状态，不保存原始 `thought`。
- 快照不得包含原始 `thought`、`thought` 摘要、Prompt、私有记忆、Agent 原始 payload、`UI_Audit` 或内部 channel payload。

## 获取事件回放

```text
GET /api/v1/sessions/{session_id}/events?from_seq=1000&limit=500
```

`from_seq` 使用 exclusive 语义：返回 `seq > from_seq` 的事件。前端从快照恢复时应传 `from_seq=snapshot.last_seq`。

响应：

```json
{
  "schema_version": "v1",
  "request_id": "req_001",
  "session_id": "sim_001",
  "trace_id": "trace_abc",
  "server_time": "2024-01-02T14:02:01+08:00",
  "data": {
    "events": [
      {
        "seq": 1001,
        "type": "market.price",
        "tick_id": "2024-01-02T14:02:00+08:00",
        "payload": {}
      }
    ],
    "next_from_seq": 1500,
    "has_more": true
  }
}
```

约束：

- 只返回前端允许消费的事件。
- 不返回 `Order_Input`、`UI_Audit`、Agent 原始 payload。
- 不返回内部 Redis 原始消息、内部 channel payload、私有 `thought`、Prompt 或私有记忆。
- `limit` 必须有服务端上限。
- `next_from_seq` 是本批次最后一个事件的 `seq`，供下一次请求继续作为 `from_seq` 传入；如果本批次为空，则等于请求的 `from_seq`。

## 停止会话

```text
POST /api/v1/sessions/{session_id}/stop
```

请求：

```json
{
  "reason": "operator_stop"
}
```

响应：

```json
{
  "schema_version": "v1",
  "request_id": "req_001",
  "session_id": "sim_001",
  "trace_id": "trace_abc",
  "server_time": "2024-01-02T14:02:01+08:00",
  "data": {
    "session_id": "sim_001",
    "status": "completed",
    "completion_reason": "operator_stop"
  }
}
```

约束：

- 停止必须先完成当前安全点。
- 已停止会话不得继续推进 Tick。
- `created` 状态下没有运行中的 Tick，`stop` 可直接把会话置为 `completed`。
- `completed` 是终态；用 `completion_reason` 区分 `operator_stop`、`natural_end` 或 `failed_after_stop`，不新增 `stopped` 状态。

## 禁止的 REST 能力

前端 REST API 不提供：

- 下单接口。
- 人工修改资金接口。
- 人工修改持仓接口。
- 人工注入 Agent `thought` 接口。
- 人工写入 `Forum_Rumors` 接口。
- 直接推进 Layer 0 或 Layer 3 的接口。
- 读取内部 Redis 或内部 channel 的接口。
- 读取 `UI_Audit`、Agent 原始 payload、Prompt 或私有记忆的接口。
