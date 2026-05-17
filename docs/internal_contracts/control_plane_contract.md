# Control Plane 内部契约

## 目标

定义 `MetaOrchestrator` 对内如何调度各模块。它是系统时钟和生命周期管理者，但不是市场事实、资产、订单簿或 Agent 记忆的拥有者。

## 模块边界

| 项 | 说明 |
| :--- | :--- |
| 模块名 | `MetaOrchestrator` |
| 所属层 | Control Plane |
| 拥有数据 | `session_id`、`tick_id`、Tick 状态、Agent 生命周期状态、trace 日志 |
| 调用方 | Web API 控制层、系统启动入口 |
| 被调用模块 | `Chronos`、`AgentRuntime`、`MatchingEngine`、`ClearingHouse`、`ExchangeBroadcaster`、`UIAuditOfficer` |
| 禁止 | 改写账本、生成市场信号、解释 Agent 私有意图、把原始 payload 写入公共频道 |

## 会话初始化接口

### `create_session`

请求：

```json
{
  "schema_version": "v1",
  "command_id": "cmd_create_001",
  "scenario_id": "demo_a_share",
  "symbol": "demo_stock",
  "agent_profile_set": "default_24",
  "start_tick_id": "2024-01-02T09:30:00+08:00",
  "end_tick_id": "2024-01-02T15:00:00+08:00",
  "tick_interval": "5m"
}
```

返回：

```json
{
  "schema_version": "v1",
  "command_id": "cmd_create_001",
  "session_id": "sim_001",
  "status": "created",
  "current_tick_id": "2024-01-02T09:30:00+08:00",
  "agent_count": 24
}
```

约束：

- 只创建会话和运行状态，不自动推进 Tick。
- 不在 `create_session` 内完成 Chronos 初始市场种子构建、Layer 3 初始化或第一份 `Market_Price` 发布。
- 如果 `/start` 或 `/step` 从 `created` 状态进入运行，Meta-Orchestrator 必须先执行初始化屏障：请求 Chronos 初始市场种子、交给 Layer 3 初始化资产和市场状态、发布第一份合规 `Market_Price`，然后才能进入第一个 Agent Tick。
- Agent 初始资产配置只能作为初始化请求交给 Layer 3 落账。
- Chronos 初始市场种子只能交给 Layer 3 初始化市场状态，不能直接进入 Agent 上下文。

取舍与后果：

- `create_session` 保持轻量，只建立控制面元数据。后果是前端创建会话后可以先展示配置确认页；真正占用 Layer 0/3 初始化资源发生在首次运行命令。
- 从 `created` 调用 `/start` 或 `/step` 的延迟会更高，前端必须通过会话状态或 `runtime.tick_state` 展示初始化中状态。

## Tick 推进接口

### `run_tick`

请求：

```json
{
  "schema_version": "v1",
  "command_id": "cmd_tick_001",
  "session_id": "sim_001",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "trace_id": "trace_abc",
  "mode": "step"
}
```

`mode` 取值：

- `step`：由 REST `/step` 触发，只推进一个 Tick。
- `continuous`：由 REST `/start` 触发，由控制面持续调度多个 Tick。

返回：

```json
{
  "schema_version": "v1",
  "command_id": "cmd_tick_001",
  "session_id": "sim_001",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "status": "committed",
  "next_tick_id": "2024-01-02T14:07:00+08:00",
  "agent_results": {
    "completed": 24,
    "timeout": 0,
    "failed": 0
  },
  "published_event_ids": ["mkt_001", "tape_001", "audit_graph_001"]
}
```

约束：

- `run_tick` 必须按 `tick_lifecycle.md` 的状态机执行。
- `COMMIT_TICK` 前必须完成 Layer 3 清算。
- UI 审计可以异步完成，但审计事件必须绑定同一个 `tick_id` 和 `trace_id`。

## Agent Step 接口

Meta-Orchestrator 对每个活跃 Agent 下发 `Step` 指令。该指令不是公共广播。

```json
{
  "schema_version": "v1",
  "command_id": "cmd_agent_step_001",
  "session_id": "sim_001",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "trace_id": "trace_abc",
  "agent_id": "retail_b",
  "deadline_ms": 30000,
  "tick_context_ref": "ctx_retail_b_1402"
}
```

约束：

- `tick_context_ref` 指向已经按权限过滤好的上下文。
- Agent 不得自行从未授权频道补充上下文。
- 超时处理按 `tick_lifecycle.md`，默认生成 `hold`。

## Payload 切割接口

### `split_agent_payload`

输入来自 `AgentRuntime.act()` 的结构化 payload，schema 见 `agent_payload_contract.md`。`LLMGateway` 可以先做 JSON 与结构化输出格式预检，但最终安全校验、权限判断和字段级路由只能在这里完成。

输出：

```json
{
  "schema_version": "v1",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "trace_id": "trace_abc",
  "agent_id": "retail_b",
  "routes": [
    {
      "target": "Order_Input",
      "event_id": "order_001"
    },
    {
      "target": "UI_Audit",
      "event_id": "audit_input_001"
    }
  ],
  "dropped_fields": [],
  "validation_status": "ok"
}
```

路由规则：

| Payload 字段 | 目标 | 说明 |
| :--- | :--- | :--- |
| `action` | `Order_Input` | 只保留交易字段，不保留理由 |
| `thought` | `UI_Audit` | 仅供前端审计链路 |
| `belief_shift` | `UI_Audit` | 仅供前端审计链路 |
| `evidence_refs` | `UI_Audit` | 只能引用已公开事件或本 Agent 私有记忆 id |
| `forum_post` | `Forum_Rumors` | 必须先检查发帖权限 |

`action` 到 Layer 3 的字段映射：

| `action.action_type` | 控制面处理 | Layer 3 输入 |
| :--- | :--- | :--- |
| `buy` | 校验 `symbol`、`order_type`、`quantity`、`price/time_in_force/client_order_id` | 生成 `Order_Input`，`side=buy` |
| `sell` | 校验 `symbol`、`order_type`、`quantity`、`price/time_in_force/client_order_id` | 生成 `Order_Input`，`side=sell` |
| `hold` | 记录本 Tick 无交易动作 | 不生成 `Order_Input` |
| `post_forum` | 只处理 `forum_post` 权限和内容 | 不生成 `Order_Input` |
| `cancel` | 第一版默认不授权；如出现在 payload 中，按未授权 action 拒绝并生成安全 `hold` | 不生成 `Order_Input` |

`cancel` 后续如需启用，必须新增 Layer 3 撤单契约，至少定义被撤订单 id、撤单权限、部分成交后的剩余数量处理和事件回放字段；不得复用当前买卖 `Order_Input` schema 暗传撤单。

拒绝条件：

- `action` 内出现 `thought`、`reason`、`belief_shift` 等私有解释字段。
- `tick_id` 与当前 Tick 不一致。
- 未授权 Agent 发布 `forum_post`。
- 第一版收到未授权 `cancel`。
- payload 不是合法 JSON 或不符合 schema。
- `LLMGateway` 预检通过但字段安全规则不通过。

## 生命周期接口

### `handle_lifecycle`

输入来自 Layer 3 的风险状态：

```json
{
  "schema_version": "v1",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "agent_id": "retail_b",
  "risk_state": "margin_call",
  "equity": 480000.0,
  "drawdown_pct": 52.0,
  "reason_code": "equity_drawdown_limit"
}
```

返回：

```json
{
  "schema_version": "v1",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "agent_id": "retail_b",
  "lifecycle_state": "liquidating",
  "decision": "forced_liquidation",
  "order_event_id": "forced_liq_001"
}
```

约束：

- Meta-Orchestrator 可以决定暂停 Agent 主动交易权。
- 强平动作仍必须作为系统订单进入 Layer 3，由 Layer 3 校验和清算。
- Meta-Orchestrator 不得直接改现金、持仓或冻结股。

## 运行状态事件

Meta-Orchestrator 可以产出内部 `control_only` 运行状态事件：

```json
{
  "schema_version": "v1",
  "event_id": "runtime_001",
  "session_id": "sim_001",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "trace_id": "trace_abc",
  "producer": "meta_orchestrator",
  "visibility": "control_only",
  "state": "MATCH_AND_CLEAR",
  "active_agent_count": 24,
  "completed_agent_count": 24,
  "timeout_agent_count": 0
}
```

约束：

- 运行状态只能经 `WebApiGateway` 或 `FrontendRealtimeGateway` 转换为 `runtime.tick_state`、`runtime.agent_lifecycle` 或 REST 会话状态后给前端展示。
- 运行状态不得包含 Agent 原始 payload、`thought`、私有记忆或未公开意图。
- 运行状态不得作为 Agent 下一轮输入。
- Web API 转换规则见 [../web_api/realtime_ws.md](../web_api/realtime_ws.md) 和 [../web_api/visibility_and_errors.md](../web_api/visibility_and_errors.md)。

## 实现检查项

- 只有 Meta-Orchestrator 可以创建下一个 `tick_id`。
- 所有 Agent payload 进入 `Order_Input` 或 `UI_Audit` 前必须经过 Meta-Orchestrator 最终安全校验。
- Meta-Orchestrator 日志可以记录 trace，但不得把 trace 内容暴露给 Agent 推理。
- 会话暂停和停止必须在安全点生效，不得中断 Layer 3 半提交。
