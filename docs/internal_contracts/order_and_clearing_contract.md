# Order And Clearing 内部契约

## 目标

定义 Layer 3 如何接收订单、维护 LOB、执行撮合清算、发布账户快照和市场快照。Layer 3 是资产中心，拥有 `Ledger`、`Positions`、`frozen_shares` 和 `LOB` 的唯一真理源。

## 模块拆分

| 子模块 | 职责 | 拥有数据 | 禁止事项 |
| :--- | :--- | :--- | :--- |
| `MatchingEngine` | 订单校验、LOB 维护、撮合、成交生成 | `LOB`、订单状态 | 读取 Agent 私有 `thought` |
| `ClearingHouse` | 资金扣划、持仓变更、T+1 冻结、费用、风险状态 | `Global Ledger`、`Positions`、`frozen_shares` | 接受 Agent 自报资产变更 |
| `MarketDataPublisher` | 生成合规 Level-2 快照和成交事件 | 脱敏市场快照缓存 | 发布底层队列或身份绑定意图 |

第一版可以把三个子模块放在同一 Python 包内，但测试和接口必须按职责拆开。

## `Order_Input` schema

```json
{
  "schema_version": "v1",
  "event_id": "order_001",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "trace_id": "trace_abc",
  "producer": "meta_orchestrator",
  "visibility": "control_only",
  "agent_id": "mutual_fund_a",
  "symbol": "demo_stock",
  "side": "sell",
  "order_type": "limit",
  "price": 15.2,
  "quantity": 500000,
  "time_in_force": "day",
  "client_order_id": "agent_order_001"
}
```

字段约束：

- `side`: `buy`、`sell`
- `order_type`: `limit`、`market`
- `quantity`: 正整数，单位为股或系统配置的最小交易单位。
- `price`: `limit` 必填，`market` 可为空。
- `client_order_id`: Agent 侧幂等 id，不能作为成交事实。
- `producer` 必须是 `meta_orchestrator` 或系统强平流程，Agent 不得绕过控制面直写 Layer 3。

禁止字段：

- `thought`
- `belief_shift`
- `reason`
- `expected_fill`
- `new_cash`
- `new_position`

## 订单校验顺序

```text
schema validation
  -> tick_id validation
  -> agent lifecycle validation
  -> symbol trading status validation
  -> price limit validation
  -> lot size validation
  -> cash / position / T+1 validation
  -> enqueue or reject
```

拒单必须返回结构化原因：

```json
{
  "schema_version": "v1",
  "event_id": "reject_001",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "order_event_id": "order_001",
  "agent_id": "mutual_fund_a",
  "status": "rejected",
  "reason_code": "insufficient_available_shares",
  "public": false
}
```

`reason_code` 取值：

- `invalid_schema`
- `stale_tick`
- `agent_suspended`
- `symbol_halted`
- `price_out_of_limit`
- `invalid_lot_size`
- `insufficient_available_cash`
- `insufficient_available_shares`
- `t_plus_one_restricted`

## 撮合规则

- 买单价格优先、时间优先。
- 卖单价格优先、时间优先。
- 成交价第一版采用被动挂单价格。
- 涨跌停边界由 `limit_up`、`limit_down` 硬约束。
- 部分成交后剩余数量继续留在 LOB，直到 `time_in_force` 失效或被撤单。

成交事件：

```json
{
  "schema_version": "v1",
  "event_id": "trade_001",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "trace_id": "trace_abc",
  "symbol": "demo_stock",
  "price": 15.2,
  "quantity": 1000,
  "buy_order_id": "order_b_001",
  "sell_order_id": "order_s_001",
  "trade_time": "2024-01-02T14:02:01+08:00"
}
```

成交事件进入 Layer 3 内部清算和脱敏市场数据链路。公共 `Market_Price` 不得暴露真实 `buy_order_id`、`sell_order_id` 或 Agent 身份。

## 清算规则

买入成交：

- 扣减买方现金。
- 增加买方持仓。
- 新增持仓写入 `frozen_shares`，当天不可卖。

卖出成交：

- 扣减卖方可用持仓。
- 增加卖方现金。
- 已卖出股数从 `available_shares` 扣除。

费用：

- 第一版可配置 `commission_rate` 和 `stamp_tax_rate`。
- 费用由 `ClearingHouse` 统一计算，Agent 不得自报费用。

T+1 解冻：

```text
COMMIT_TICK
  -> 如果进入下一交易日
  -> ClearingHouse 将上一交易日买入的 frozen_shares 转入 available_shares
```

## `Account_Snapshot` schema

```json
{
  "schema_version": "v1",
  "event_id": "acct_001",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "trace_id": "trace_abc",
  "producer": "clearing_house",
  "visibility": "agent_private",
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
  "market_value": 4560000.0,
  "equity": 5760000.0,
  "risk_state": "normal",
  "source": "layer3_global_ledger"
}
```

`risk_state` 取值：

- `normal`
- `warning`
- `margin_call`
- `liquidating`
- `terminated`

## `Market_Price` schema

```json
{
  "schema_version": "v1",
  "event_id": "mkt_001",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "trace_id": "trace_abc",
  "producer": "market_data_publisher",
  "visibility": "public",
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
```

约束：

- `Market_Price` 只展示聚合深度，不暴露底层订单 id。
- `level2` 深度第一版默认十档，可由配置调整。
- `limit_state`: `normal`、`limit_up`、`limit_down`、`halted`。

## 取舍与后果

- 第一版成交价采用被动挂单价。后果是实现简单且可解释；若后续追求更真实，可引入交易所级撮合细节。
- 强平由 Meta-Orchestrator 触发生命周期，但清算仍由 Layer 3 执行。后果是控制权和资产权分离，避免控制面直接改账。
- `Account_Snapshot` 可推送给前端审计视图，但 Agent 只能收到自己的快照。后果是演示可见性和沙盒隔离同时成立。

## 实现检查项

- `Order_Input` 出现私有字段时必须拒绝。
- Agent 绕过 Meta-Orchestrator 直写订单时必须拒绝。
- T+1 冻结测试覆盖：当日买入不可当日卖出。
- 涨跌停测试覆盖：越界报价被拒绝。
- 清算后只有 `ClearingHouse` 能发布 `Account_Snapshot`。
- `Market_Price` 不包含 Agent 身份、订单 id 或订单理由。
