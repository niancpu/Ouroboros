# Agent Payload 内部契约

## 目标

定义 Agent 每个 Tick 能看到什么、能输出什么、输出如何被 Meta-Orchestrator 切割路由。核心原则：Agent 只能用合法公开输入和自己的私有记忆做决策；只有 `action` 可以影响市场。

## Agent 输入上下文

`AgentRuntime.act(tick_context)` 的输入必须由 Meta-Orchestrator 构造，Agent 不得自行拼接公共总线以外的数据源。

```json
{
  "schema_version": "v1",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "trace_id": "trace_abc",
  "agent_id": "retail_b",
  "agent_role": "retail",
  "public_inputs": {
    "official_news": [],
    "market_price": {},
    "tape_alerts": [],
    "end_of_day": [],
    "forum_rumors": []
  },
  "private_inputs": {
    "account_snapshot": {},
    "memory_refs": [],
    "memory_window": {
      "lookback_ticks": 20,
      "retrieved_memory_ids": ["mem_001"]
    }
  },
  "constraints": {
    "allowed_actions": ["buy", "sell", "cancel", "hold", "post_forum"],
    "deadline_ms": 30000,
    "can_post_forum": false
  }
}
```

允许输入：

- `Official_News`
- `Market_Price`
- `Account_Snapshot`，仅限本 Agent
- `Tape_Alerts`
- `End_of_Day`
- `Forum_Rumors`，按 Agent 权限过滤
- 本 Agent 的 `Private Memory`

## 私有记忆检索约束

Agent 的私有记忆检索必须由 Meta-Orchestrator 或 AgentRuntime 本地接口完成，不能直接从公共频道拼装。

允许返回的记忆项：

```json
{
  "memory_id": "mem_001",
  "memory_type": "past_trade",
  "summary": "曾在高波动行情追涨后回撤。",
  "source_refs": ["forum_post_123", "acct_001"],
  "created_tick_id": "2023-12-20T10:30:00+08:00"
}
```

约束：

- `summary` 必须是本 Agent 自己可见的摘要。
- `source_refs` 只能引用公开事件或本 Agent 自身历史。
- 检索结果不能包含其他 Agent 的私有内容。

禁止输入：

- 任意其他 Agent 的 `thought`
- `UI_Audit`
- `Frontend_Audit_Graph`
- Layer 3 底层 LOB
- Layer 0 未来 Tick 事实
- 其他 Agent 的账户快照和私有记忆

## Agent 输出 payload

Agent 必须返回结构化 JSON。无论 LLM 原始输出是什么，进入控制面的 payload 都必须先通过 schema 校验。

```json
{
  "schema_version": "v1",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "trace_id": "trace_abc",
  "agent_id": "retail_b",
  "action": {
    "action_type": "buy",
    "symbol": "demo_stock",
    "order_type": "limit",
    "price": 15.2,
    "quantity": 1000,
    "time_in_force": "day"
  },
  "thought": "private audit text, never routed back to agents",
  "belief_shift": {
    "confidence_delta": 0.34,
    "sentiment": "bullish",
    "risk_appetite_delta": 0.1
  },
  "evidence_refs": ["forum_post_123"],
  "forum_post": null,
  "memory_update": {
    "should_write": true,
    "summary": "受到盘口异动和股吧帖子影响，看多信念上升。"
  }
}
```

## 字段路由

| 字段 | 目标 | 可被 Agent 订阅 | 说明 |
| :--- | :--- | :--- | :--- |
| `action` | `Order_Input` | 否 | 只承载交易动作，不承载理由 |
| `thought` | `UI_Audit` | 否 | 私有审计材料 |
| `belief_shift` | `UI_Audit` | 否 | 用于前端拓扑和情绪可视化 |
| `evidence_refs` | `UI_Audit` | 否 | 只能引用已公开事件或本 Agent 记忆 id |
| `forum_post` | `Forum_Rumors` | 是 | 仅允许有发帖权限的 Agent 发布 |
| `memory_update` | `Agent Private Memory` | 否 | 仅写入本 Agent 私有记忆 |
| `trace_id` | 控制面日志 | 否 | 不进入 Agent 下一轮上下文 |

## `action` 约束

`action_type` 取值：

| 值 | 含义 | 进入 Layer 3 |
| :--- | :--- | :--- |
| `buy` | 买入限价或市价订单 | 是 |
| `sell` | 卖出限价或市价订单 | 是 |
| `cancel` | 撤销未成交订单 | 是 |
| `hold` | 本 Tick 无交易动作 | 可记录，不进 LOB |
| `post_forum` | 公开发帖 | 否，进入 `Forum_Rumors` |

约束：

- `buy`、`sell` 必须包含 `symbol`、`order_type`、`quantity`。
- `order_type=limit` 必须包含 `price`。
- Agent 不得提交结算结果、成交价格、扣款结果或持仓变更。
- Agent 可以表达想卖出数量，但是否可卖由 Layer 3 根据 `available_shares` 和 T+1 规则裁决。

## `forum_post` 约束

```json
{
  "post_id": "forum_post_123",
  "author_agent_id": "hot_money_a",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "text": "公开股吧内容",
  "stance": "bullish",
  "visibility": "public"
}
```

约束：

- 只有 `can_post_forum=true` 的 Agent 可以发布。
- `forum_post.text` 可以是公开观点，但不得携带该 Agent 的私有 `thought` 字段原文。
- `forum_post` 是市场公开内容，其他 Agent 可以在下一 Tick 看见。
- `memory_update` 只能进入本 Agent 私有记忆，不能回流给其他 Agent。

## 校验失败处理

| 失败类型 | 处理 |
| :--- | :--- |
| JSON 无法解析 | 生成 `hold`，记录 `payload_parse_error` |
| 缺少必填交易字段 | 拒绝 `action`，保留 `UI_Audit` 可解析部分 |
| `thought` 出现在 `action` 内 | 拒绝整份 payload，生成安全 `hold` |
| 未授权 Agent 发布 `forum_post` | 丢弃 `forum_post`，保留合法 `action` |
| `tick_id` 不匹配 | 拒绝 payload，记录控制面异常 |

## 取舍与后果

- 第一版允许 `thought` 进入 `UI_Audit`，但默认前端只展示脱敏摘要。后果是演示效果足够，信息泄露风险可控。
- `evidence_refs` 只保存引用 id，不保存证据全文。后果是链路更干净，但调试时需要额外查事件日志。
- 超时默认生成 `hold`。后果是安全，但会削弱极端行情中的同步恐慌，需要在压力测试时单独评估。

## 实现检查项

- Agent payload schema 校验发生在路由切割前。
- `action` 序列化进入 `Order_Input` 时不得包含 `thought`、`belief_shift`、`evidence_refs`。
- `UI_Audit` 写入后，任意 Agent 下一轮 `tick_context` 都不得出现该内容。
- 未授权发帖的 Agent 输出 `forum_post` 时必须被拒绝。
- `memory_update` 不得写入公共频道。
