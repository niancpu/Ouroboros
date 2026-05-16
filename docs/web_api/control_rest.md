# Control REST API

## 目标

定义前端调用控制面的 REST 接口。REST 只用于会话管理、运行控制和快照查询，不允许前端直接修改市场业务状态。

## 基础路径

```text
/api/v1
```

## 通用请求头

| Header | 必填 | 说明 |
| :--- | :--- | :--- |
| `Content-Type: application/json` | 是 | JSON 请求体 |
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
- `single_tick`：只推进一个 Tick。

响应：

```json
{
  "data": {
    "session_id": "sim_001",
    "status": "running",
    "accepted": true
  }
}
```

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

## 获取当前快照

```text
GET /api/v1/sessions/{session_id}/snapshot
```

响应：

```json
{
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
    }
  }
}
```

约束：

- 快照用于前端恢复视图，不用于 Agent 输入。
- 快照中的 `audit_graph` 必须是脱敏结果。
- 快照不得包含原始 `thought`，除非后端显式开启沙盒外调试模式。

## 获取事件回放

```text
GET /api/v1/sessions/{session_id}/events?from_seq=1000&limit=500
```

响应：

```json
{
  "data": {
    "events": [
      {
        "seq": 1001,
        "type": "market.price",
        "tick_id": "2024-01-02T14:02:00+08:00",
        "payload": {}
      }
    ],
    "next_from_seq": 1501,
    "has_more": true
  }
}
```

约束：

- 只返回前端允许消费的事件。
- 不返回 `Order_Input`、`UI_Audit`、Agent 原始 payload。
- `limit` 必须有服务端上限。

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
  "data": {
    "session_id": "sim_001",
    "status": "completed"
  }
}
```

约束：

- 停止必须先完成当前安全点。
- 已停止会话不得继续推进 Tick。

## 禁止的 REST 能力

前端 REST API 不提供：

- 下单接口。
- 人工修改资金接口。
- 人工修改持仓接口。
- 人工注入 Agent `thought` 接口。
- 人工写入 `Forum_Rumors` 接口。
- 直接推进 Layer 0 或 Layer 3 的接口。
