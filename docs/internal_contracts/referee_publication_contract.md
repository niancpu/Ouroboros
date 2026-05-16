# Referee Publication 内部契约

## 目标

定义交易所数据播报员和 UI 渲染审查官的输入、输出和隔离规则。Referee 不是上帝广播器；它不能把私有思考转换为公共市场信号。

## 实体拆分

| 实体 | 输入 | 输出 | 可被 Agent 订阅 | 禁止事项 |
| :--- | :--- | :--- | :--- | :--- |
| `ExchangeBroadcaster` | Layer 3 匿名订单流、成交、Level-2 快照、盘后席位统计 | `Tape_Alerts`、`End_of_Day` | 是 | 读取私有 `thought`、广播身份绑定意图 |
| `UIAuditOfficer` | `UI_Audit`、公开事件引用、成交结果 | `Frontend_Audit_Graph`、`Frontend_Causal_Chain` | 否 | 写入 Agent 可订阅频道 |

## `Tape_Alerts` schema

```json
{
  "schema_version": "v1",
  "event_id": "tape_001",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "trace_id": "trace_abc",
  "producer": "exchange_broadcaster",
  "visibility": "public",
  "symbol": "demo_stock",
  "alert_type": "large_sell_pressure",
  "severity": "medium",
  "public_text": "该股遭遇连续千手大单砸盘，当前跌幅扩大至 5%，下方买盘承接乏力。",
  "source": "anonymous_order_flow",
  "metrics": {
    "price_change_pct": -3.0,
    "sell_volume": 500000,
    "bid_depth_change_pct": -35.0
  }
}
```

`alert_type` 取值：

- `large_sell_pressure`
- `large_buy_pressure`
- `limit_up_pressure`
- `limit_down_pressure`
- `liquidity_vacuum`
- `volume_spike`

约束：

- `public_text` 只能描述匿名盘口和价格状态。
- `metrics` 只能来自 Layer 3 匿名市场输出。
- 不得出现 Agent 身份、私有意图、未公开订单理由。

## `End_of_Day` schema

```json
{
  "schema_version": "v1",
  "event_id": "eod_001",
  "tick_id": "2024-01-02T15:00:00+08:00",
  "trace_id": "trace_abc",
  "producer": "exchange_broadcaster",
  "visibility": "public",
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
```

约束：

- 龙虎榜是盘后延迟披露，不能在盘中提前发布。
- `seat_name` 是脱敏席位或模拟席位，不等同于具体 Agent 私有身份。
- `net_amount` 来自 Layer 3 成交和清算统计，不来自 Agent `thought`。

## `Frontend_Audit_Graph` schema

```json
{
  "schema_version": "v1",
  "event_id": "audit_graph_001",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "trace_id": "trace_abc",
  "producer": "ui_audit_officer",
  "visibility": "frontend_only",
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
```

## `Frontend_Causal_Chain` schema

该事件用于前端展示脱敏因果链，例如：

```text
公开帖子 -> 散户信念上升 -> 买单增加 -> 价格上涨 -> 更多散户追涨
```

```json
{
  "schema_version": "v1",
  "event_id": "chain_001",
  "tick_id": "2024-01-02T14:03:00+08:00",
  "trace_id": "trace_abc",
  "producer": "ui_audit_officer",
  "visibility": "frontend_only",
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
      "public_text": "公开帖子被散户群体看到"
    },
    {
      "step_id": "step_002",
      "step_type": "belief_shift",
      "tick_id": "2024-01-02T14:02:00+08:00",
      "actor_id": "retail_cluster",
      "event_ref": "audit_graph_001",
      "public_text": "散户群体对上涨叙事的信任增强"
    },
    {
      "step_id": "step_003",
      "step_type": "order_flow",
      "tick_id": "2024-01-02T14:02:00+08:00",
      "actor_id": "market",
      "event_ref": "mkt_001",
      "public_text": "买盘增强并推高最新成交价"
    }
  ],
  "metrics": {
    "price_change_pct": 2.1,
    "affected_agent_count": 8,
    "confidence": 0.76
  }
}
```

约束：

- `public_text` 只能使用脱敏解释，不得包含原始 `thought`。
- `event_ref` 只能引用公开事件或前端专用审计事件。
- `confidence` 是审计官对链路强弱的估计，不是市场事实。
- `Frontend_Causal_Chain` 不得写入任何 Agent 可订阅频道。

普通前端和普通 Web API 不得展示原始 `thought`。如需沙盒外诊断能力，必须另行定义独立诊断通道，不复用 `Frontend_Audit_Graph`、`Frontend_Causal_Chain`、REST `snapshot` 或 WebSocket 普通事件流。

- 诊断通道必须有独立权限和独立审计日志。
- 诊断输出不得进入普通前端事件回放。
- 不写入任何 Agent 可订阅频道。
- 页面必须明确区分“沙盒外诊断视图”和“市场可见信息”。

## 发布阈值

第一版采用固定阈值：

| 异动 | 默认阈值 |
| :--- | :--- |
| 价格快速下跌 | 单 Tick 跌幅 >= 3% |
| 价格快速上涨 | 单 Tick 涨幅 >= 3% |
| 大单卖压 | 主动卖出量 >= 最近 5 Tick 均值 3 倍 |
| 大单买压 | 主动买入量 >= 最近 5 Tick 均值 3 倍 |
| 流动性断层 | 买一到买五总量下降 >= 30% |

后续可改为波动率自适应阈值，但必须保持输入只来自匿名市场输出。

## 实现检查项

- `ExchangeBroadcaster` 的构造函数不得接收 `UI_Audit` 或 Agent payload。
- `Tape_Alerts.public_text` 不得出现 Agent id、席位真实身份、`thought` 摘要。
- `End_of_Day` 只能在收盘或模拟收盘阶段发布。
- `Frontend_Audit_Graph` 和 `Frontend_Causal_Chain` 不得被 Agent runtime 订阅。
- 注入一条私有 `thought` 后，公共频道不得出现其原文或摘要。
