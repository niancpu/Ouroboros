# Visibility And Errors

## 目标

定义前端 API 的可见性边界、错误码和恢复规则。核心要求：前端可以看审计视图，但审计视图不得成为 Agent 输入。

前端访问路径固定为 Web API 层。REST 通过 API Gateway，实时事件通过 `FrontendRealtimeGateway`；前端不得直连内部 Redis、内部 Pub/Sub channel、Layer 0/1/2/3 模块接口或 Agent runtime。

## 可见性等级

Web API visibility 与内部 visibility 分开命名。前端只接收下表中的 Web API visibility：

| 值 | 说明 | 可进入前端 | 可进入 Agent |
| :--- | :--- | :--- | :--- |
| `public` | 市场公开信息 | 是 | 按权限可以 |
| `agent_private_snapshot` | 前端审计可见的账户快照 | 是 | 仅对应 Agent |
| `frontend_only` | 前端审计图和脱敏解释 | 是 | 否 |
| `control_only_view` | 控制面运行状态 | 是 | 否 |

内部 visibility 到 Web API visibility 的唯一映射：

| 内部 visibility | Web API visibility | 转换限制 |
| :--- | :--- | :--- |
| `public` | `public` | 仅可转换已按公开规则过滤的市场、论坛和披露事件 |
| `agent_private` | `agent_private_snapshot` | 仅 `Account_Snapshot` 等账户快照审计视图可转换；不得开放内部 `agent_private` channel |
| `frontend_only` | `frontend_only` | 仅 `Frontend_Audit_Graph`、`Frontend_Causal_Chain` 等前端专用脱敏事件 |
| `control_only` | `control_only_view` | 仅运行状态和错误摘要；不得暴露内部原始 payload |

转换只能由 Web API 层或 `FrontendRealtimeGateway` 完成。前端事件回放只能回放 Web API 事件，不得要求前端读取内部 Redis。

禁止通过 Web API 暴露：

- `Order_Input` 原始内部消息。
- `UI_Audit` 原始内部消息。
- Agent 原始 payload。
- Agent 私有记忆。
- 未脱敏原始 `thought`。
- `thought` 摘要、Prompt、未公开订单理由或内部 payload。
- Layer 3 底层 LOB 队列。
- Layer 0 未来事实。

## 前端展示边界

允许展示：

- `Market_Price` 聚合价格和 Level-2 快照。
- `Tape_Alerts` 匿名盘口异动。
- `End_of_Day` 盘后龙虎榜和收盘统计。
- `Forum_Rumors` 公开帖子。
- `Account_Snapshot` 的审计视图。
- `Frontend_Audit_Graph` 的脱敏拓扑边。
- `audit.causal_chain` 的脱敏因果链。
- Meta-Orchestrator 的 Tick 状态和 Agent 生命周期状态。
- 快照中的 `causal_chains` 恢复摘要。

默认不展示：

- 核心机构 Agent 原始 COT。
- 未脱敏 `thought`。
- `thought` 摘要。
- 订单背后的私有理由。
- Prompt、Agent 私有记忆和 Agent 原始 payload。

诊断通道说明：

- 普通 Web API 不提供原始 `thought` 调试例外。
- 如果后续需要沙盒外诊断通道，必须另起独立接口和独立权限，不得复用普通 `snapshot`、`events` 或 WebSocket 事件流。
- 诊断通道输出仍不得写入任何 Agent 可订阅频道。
- 诊断通道不得改变 Web API visibility 的含义。

## 错误响应格式

REST 错误：

```json
{
  "schema_version": "v1",
  "request_id": "req_001",
  "trace_id": "trace_abc",
  "server_time": "2024-01-02T14:02:01+08:00",
  "error": {
    "code": "SESSION_NOT_FOUND",
    "message": "session does not exist",
    "retryable": false,
    "details": {}
  }
}
```

WebSocket 错误：

```json
{
  "schema_version": "v1",
  "seq": 2049,
  "type": "system.error",
  "session_id": "sim_001",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "trace_id": "trace_abc",
  "server_time": "2024-01-02T14:02:01+08:00",
  "visibility": "control_only_view",
  "payload": {
    "code": "SNAPSHOT_REQUIRED",
    "message": "event buffer expired; request snapshot before resubscribe",
    "retryable": true,
    "details": {}
  }
}
```

## 错误码

| Code | HTTP | Retryable | 说明 |
| :--- | :--- | :--- | :--- |
| `BAD_REQUEST` | 400 | 否 | 请求 JSON 或参数非法 |
| `UNAUTHORIZED` | 401 | 否 | 未认证 |
| `FORBIDDEN` | 403 | 否 | 当前用户无权访问该会话 |
| `SESSION_NOT_FOUND` | 404 | 否 | 会话不存在 |
| `SESSION_STATE_CONFLICT` | 409 | 是 | 当前会话状态不允许该操作 |
| `SCHEMA_VERSION_UNSUPPORTED` | 422 | 否 | 协议版本不支持 |
| `RATE_LIMITED` | 429 | 是 | 请求过快 |
| `ORCHESTRATOR_BUSY` | 503 | 是 | 控制面忙 |
| `SNAPSHOT_REQUIRED` | 409 | 是 | WebSocket 事件缓冲已过期，需要先拉快照 |
| `WS_BACKPRESSURE` | 429 | 是 | 前端消费太慢 |
| `INTERNAL_ERROR` | 500 | 是 | 未分类服务端错误 |

## 状态冲突规则

| 操作 | 允许状态 | 冲突示例 |
| :--- | :--- | :--- |
| `start` | `created`、`paused` | 已经 `running` |
| `pause` | `running` | 已经 `completed` |
| `step` | `created`、`paused` | 正在 `running` |
| `stop` | `created`、`running`、`paused` | 已经 `completed` |
| `snapshot` | 任意存在状态 | 会话不存在 |

## 断线恢复

前端恢复顺序：

1. 调用 `GET /api/v1/sessions/{session_id}/snapshot`。
2. 使用快照重建当前 UI。
3. 用 `from_seq=snapshot.last_seq` 连接 WebSocket。
4. 如果服务端返回 `SNAPSHOT_REQUIRED`，重新获取快照。

快照响应应包含：

```json
{
  "last_seq": 1024,
  "current_tick_id": "2024-01-02T14:02:00+08:00"
}
```

## 实现检查项

- Web API 层必须过滤 `UI_Audit` 和 Agent 原始 payload。
- `frontend_only` 事件不得写入任何 Agent 可订阅频道。
- 因果链只能用于前端解释，不得成为 Agent 下一轮输入。
- REST 不提供下单、改账、改仓、注入 thought 的接口。
- 断线恢复不能要求前端访问内部 Redis。
- 错误响应不得泄露私有 `thought`、Prompt 或 Agent 私有记忆。
- `agent_private_snapshot` 只能来自允许转换的账户快照审计视图，不得作为通用私有数据透传通道。
- `control_only_view` 只能展示状态和错误摘要，不得携带内部 `control_only` 原始 payload。
