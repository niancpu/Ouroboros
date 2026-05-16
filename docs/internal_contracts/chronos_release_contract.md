# Chronos Release 内部契约

## 目标

定义 Layer 0 如何按 Tick 释放历史事实，防止 Agent 偷看未来数据或直接查询全量历史库。Layer 0 是事实中心，不是时钟推进者；系统 Tick 只能由 Meta-Orchestrator 创建和推进。

## 模块边界

| 项 | 说明 |
| :--- | :--- |
| 模块名 | `Chronos` |
| 所属层 | Layer 0 |
| SSOT | `Chronos Data`、历史新闻、公告、财报、监管函、历史量价、历史龙虎榜 |
| 调用方 | `MetaOrchestrator` |
| 发布频道 | `Official_News` |
| 禁止 | 释放未来事实、让 Agent 直查全量库、主动推进 Tick |

## 控制面接口

### `release_facts`

```json
{
  "schema_version": "v1",
  "command_id": "cmd_release_001",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "trace_id": "trace_abc",
  "symbol": "demo_stock",
  "release_window": {
    "from": "2024-01-02T13:57:00+08:00",
    "to": "2024-01-02T14:02:00+08:00"
  }
}
```

返回：

```json
{
  "schema_version": "v1",
  "command_id": "cmd_release_001",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "status": "ok",
  "published_event_ids": ["news_001", "news_002"],
  "withheld_future_count": 17
}
```

约束：

- `release_window.to` 不得晚于当前 `tick_id` 对应的历史时间。
- `withheld_future_count` 只进入控制面日志，不得广播给 Agent。
- Layer 0 不得自行决定下一个 `tick_id`。

## `Official_News` 事件 schema

```json
{
  "schema_version": "v1",
  "event_id": "news_001",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "trace_id": "trace_abc",
  "producer": "chronos",
  "visibility": "public",
  "created_at": "2024-01-02T14:02:01+08:00",
  "symbol": "demo_stock",
  "fact_time": "2024-01-02T14:00:00+08:00",
  "source_type": "announcement",
  "source_name": "exchange",
  "fact_id": "official_announcement_001",
  "title": "公开事实标题",
  "summary": "只包含当时已经公开的信息摘要",
  "confidence": "official",
  "permission_tags": ["institutional", "hot_money", "quant"]
}
```

`source_type` 取值：

- `announcement`
- `financial_report`
- `regulatory_notice`
- `macro`
- `news`
- `historical_dragon_tiger`
- `initial_market_seed`

## RAG 时间边界

Agent 可检索历史相似事件，但检索必须受 `tick_id` 截断。

允许：

```text
query_time <= current_tick_time
```

禁止：

```text
query_time > current_tick_time
```

RAG 返回必须只包含：

- 历史事件 id。
- 截止当前 Tick 可见的摘要。
- 来源类型。
- 发生时间。

RAG 返回不得包含：

- 未来价格走势标签。
- 未来龙虎榜结果。
- 未来公告。
- 由未来事实反推的解释。

## 初始市场种子

Layer 0 可以在推演启动时提供初始市场种子给 Layer 3。该流程只能在会话初始化阶段发生，由 Meta-Orchestrator 调用 Chronos 后转交 Layer 3，不经过 Agent 可订阅频道。

```json
{
  "schema_version": "v1",
  "seed_id": "seed_001",
  "symbol": "demo_stock",
  "previous_close": 15.0,
  "limit_up": 16.5,
  "limit_down": 13.5,
  "initial_l2_snapshot": {
    "bids": [["14.99", 10000]],
    "asks": [["15.01", 8000]]
  }
}
```

约束：

- `initial_market_seed` 只能由 Meta-Orchestrator 在 `create_session` 阶段请求。
- Chronos 不得直接向 Agent 发布初始种子。
- Layer 3 接收种子后生成第一份合规 `Market_Price` 快照，Agent 仍只能看到该快照。
- 初始 L2 种子只用于初始化 Layer 3 市场状态。
- Agent 仍只能通过 `Market_Price` 看到合规市场快照。
- 初始种子不得包含未来 Tick 的盘口变化。

返回：

```json
{
  "schema_version": "v1",
  "seed_id": "seed_001",
  "status": "accepted",
  "target": "layer3_market_init"
}
```

## 取舍与后果

- `Official_News` 用摘要而不是全文。后果是降低上下文成本，但需要保留 `fact_id` 方便审计回查。
- RAG 截断放在 Chronos 层实现。后果是 Agent 侧更简单，但 Chronos 必须承担时间过滤测试。
- `permission_tags` 允许不同 Agent 看到不同官方源。后果是真实度更高，但权限矩阵必须集中配置，避免散落在 Agent prompt 中。

## 实现检查项

- 集成测试覆盖：当前 Tick 无法检索未来 `fact_time`。
- 集成测试覆盖：Agent 不能直接访问 Chronos 全量库。
- 单元测试覆盖：`release_window.to` 晚于当前 Tick 时被拒绝。
- 审计日志记录已发布和被截留的事实数量，但截留数量不得广播给 Agent。
