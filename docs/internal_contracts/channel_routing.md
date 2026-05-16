# Channel Routing 内部契约

## 目标

用频道路由从工程上封死信息泄露路径。Agent 的私有思考只能进入 UI 审计通道，不能进入任何 Agent 可订阅频道；Agent 对市场的影响只能通过订单动作进入撮合引擎。

## 频道总览

| Channel | 发布者 | 订阅者 | 是否可被 Agent 订阅 | 用途 |
| :--- | :--- | :--- | :--- | :--- |
| `Order_Input` | Meta-Orchestrator | Layer 3 撮合引擎 | 否 | Agent 交易动作经控制面切割后的订单输入 |
| `UI_Audit` | Meta-Orchestrator | UI 渲染审查官 | 否 | Agent 私有 `thought`、`belief_shift` 经控制面切割后的审计输入 |
| `Official_News` | Layer 0 | 机构、游资、可配置 Agent | 是 | 官方事实、公告、财报、监管函 |
| `Market_Price` | Layer 3 撮合引擎 | 全员、前端 | 是 | 价格、成交、盘口快照 |
| `Account_Snapshot` | Layer 3 清算引擎 | 对应 Agent、前端审计视图 | 仅对应 Agent | 成交后的资金、持仓、冻结股只读副本 |
| `Tape_Alerts` | 交易所数据播报员 | 全员、前端 | 是 | 匿名盘口异动播报 |
| `End_of_Day` | 交易所数据播报员 | 全员、前端 | 是 | 收盘统计、龙虎榜延迟披露 |
| `Forum_Rumors` | Meta-Orchestrator | 散户、可配置 Agent、前端 | 是 | 允许发帖 Agent 的公开小作文，经控制面校验后发布 |
| `Frontend_Audit_Graph` | UI 渲染审查官 | 前端 | 否 | 拓扑连线、脱敏解释、审计可视化 |
| `Frontend_Causal_Chain` | UI 渲染审查官 | 前端 | 否 | 脱敏因果链时间线 |

## 控制面约束

Meta-Orchestrator 可以接收 Agent 完整 payload，但它不是公共消息总线。

约束：

- Meta-Orchestrator 只能做字段级路由切割，不得把 Agent 原始 payload 写入公共 Redis 频道。
- `action` 只能被路由到 `Order_Input`。
- `thought`、`belief_shift`、`evidence_refs` 只能被路由到 `UI_Audit`。
- Tick 推进和 Agent 生命周期事件不通过 Agent 可订阅公共频道传播私有内容。

## Agent 内部输出路由

```text
Agent N ===(payload)===> Meta-Orchestrator ===(action)===> [Channel: Order_Input] ===> Layer 3 撮合引擎
Agent N ===(payload)===> Meta-Orchestrator ===(thought)==> [Channel: UI_Audit]    ===> UI 渲染审查官 ===> 前端大屏
```

约束：

- `Order_Input` 只允许承载订单动作，不允许携带 `thought`、私有推理、未公开意图。
- `UI_Audit` 可以承载私有审计材料，但任何 Agent 都不得订阅。
- `Frontend_Audit_Graph` 和 `Frontend_Causal_Chain` 只能被前端订阅，不得被 Agent runtime、撮合引擎、策略调度器订阅。

## Agent 合法输入路由

```text
Layer 0 真实数据 =======> [Channel: Official_News] ==> 机构/游资/可配置 Agent
Layer 3 撮合引擎 =======> [Channel: Market_Price]  ==> 全员
Layer 3 清算引擎 =======> [Channel: Account_Snapshot] ==> 对应 Agent
交易所数据播报员 ======> [Channel: Tape_Alerts]   ==> 全员
交易所数据播报员 ======> [Channel: End_of_Day]    ==> 全员
Meta-Orchestrator ===> [Channel: Forum_Rumors]  ==> 散户/可配置 Agent
```

约束：

- Agent 的下一轮决策输入只能来自上表中的合法输入频道。
- UI 审计通道和前端审计图不得作为 Agent 上下文。
- `Account_Snapshot` 在 Agent 侧只能进入对应 Agent 的本地只读副本；前端只能通过 Web API 审计视图消费，不得作为全市场广播或 Agent 输入。
- 盘中广播只能描述匿名订单流和市场物理状态；身份级、动机级信息只能在盘后延迟披露中以席位统计形式出现。

## 最小消息字段

### `Order_Input`

```json
{
  "schema_version": "v1",
  "event_id": "evt_001",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "producer": "meta_orchestrator",
  "agent_id": "mutual_fund_a",
  "side": "sell",
  "price": 15.2,
  "quantity": 500000,
  "order_type": "limit"
}
```

### `UI_Audit`

```json
{
  "schema_version": "v1",
  "event_id": "evt_002",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "producer": "meta_orchestrator",
  "agent_id": "retail_b",
  "thought": "private, never routed back to agents",
  "belief_shift": 0.34,
  "evidence_refs": ["forum_post_123"]
}
```

### `Tape_Alerts`

```json
{
  "schema_version": "v1",
  "event_id": "evt_003",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "producer": "exchange_broadcaster",
  "alert_type": "large_sell_pressure",
  "symbol": "demo_stock",
  "public_text": "该股遭遇连续千手大单砸盘，当前跌幅扩大至 5%，下方买盘承接乏力。",
  "source": "anonymous_order_flow"
}
```

### `Account_Snapshot`

```json
{
  "schema_version": "v1",
  "event_id": "evt_005",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "producer": "clearing_house",
  "agent_id": "mutual_fund_a",
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
  "source": "layer3_global_ledger"
}
```

### `Frontend_Audit_Graph`

```json
{
  "schema_version": "v1",
  "event_id": "evt_004",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "producer": "ui_audit_officer",
  "edge": {
    "source": "hot_money_a",
    "target": "retail_b",
    "weight": 0.34,
    "reason_ref": "forum_post_123"
  },
  "visibility": "frontend_only"
}
```

### `Frontend_Causal_Chain`

```json
{
  "schema_version": "v1",
  "event_id": "chain_001",
  "tick_id": "2024-01-02T14:03:00+08:00",
  "producer": "ui_audit_officer",
  "chain_id": "chain_001",
  "title": "游资帖子触发散户追涨",
  "steps": [
    {
      "step_id": "step_001",
      "step_type": "public_message",
      "event_ref": "forum_post_123",
      "public_text": "公开帖子被散户群体看到"
    },
    {
      "step_id": "step_002",
      "step_type": "belief_shift",
      "event_ref": "audit_graph_001",
      "public_text": "散户信念上升"
    }
  ],
  "visibility": "frontend_only"
}
```

## 实现检查项

- Agent runtime 不注册 `UI_Audit`、`Frontend_Audit_Graph` 和 `Frontend_Causal_Chain` 订阅。
- 撮合引擎不读取 `thought`。
- 交易所数据播报员不读取 Agent 私有输出。
- UI 渲染审查官的输出不写入 Agent 可订阅频道。
- `Account_Snapshot` 只能由 Layer 3 发布；Agent 侧只能被对应 Agent 消费，前端侧只能作为审计视图消费。
- 集成测试必须覆盖：向 `UI_Audit` 写入私有 thought 后，任意 Agent 合法输入中都不能出现该内容。
