# State Ownership 与 SSOT 内部契约

## 目标

明确核心数据由谁逻辑拥有、由谁实际维护、谁是唯一真理源。任何实现不得让 Agent 自行改写资产、偷看全量历史或直接读取底层订单簿。

## 总览

| 数据资产 | 逻辑所有者 | 实际维护者 / SSOT | Agent 权限 | 关键约束 |
| :--- | :--- | :--- | :--- | :--- |
| 资金 `capital/cash` | 对应 Agent | Layer 3 Clearing House 的 `Global Ledger` | 只读副本 | Agent 不得自行加减现金 |
| 持仓 `positions` | 对应 Agent | Layer 3 Clearing House 的 `Global Ledger` | 只读副本 | 成交后由 Layer 3 更新 |
| 冻结股 `frozen_shares` | 对应 Agent | Layer 3 Clearing House | 只读副本 | 用于执行 A 股 T+1 可卖约束 |
| 订单簿 `LOB` | Layer 3 | Layer 3 Matching Engine | 不可直接读取 | Agent 只能看到 Level-2 快照 |
| 全局历史事实 `Chronos Data` | Layer 0 | Layer 0 Chronos / 历史数据库 / 向量库 | 按 Tick 接收 | 不得一次性读取未来数据 |
| 私有记忆 `Private Memory` | 对应 Agent | Agent 本地 Memory Store | 本 Agent 读写 | 不得跨 Agent 读取 |
| Tick 生命周期 | Meta-Orchestrator | Meta-Orchestrator 控制面 | Agent 被动接收 Step | 只有控制面能推进时间 |
| Redis 广播事件 | 事件发布者 | Layer 2 Redis 总线 | Agent 按频道权限订阅；前端只能经 Web API 层消费 | Redis 不作为业务 SSOT |

## 资金与持仓

资金和持仓的逻辑所有者是对应 Agent，但唯一真理源在 Layer 3 的 `Global Ledger`。

Agent 可以在本地保留：

- `cash_snapshot`
- `positions_snapshot`
- `available_cash_snapshot`
- `available_shares_snapshot`
- `frozen_shares_snapshot`

这些字段都是只读副本，只能由 Layer 3 通过 `Account_Snapshot` 推送更新。Agent 不得在本地执行扣款、加仓、减仓、解冻。

合法流程：

```text
Agent 生成 action
  -> 提交给 Meta-Orchestrator
  -> Meta-Orchestrator 校验并路由到 Order_Input
  -> Layer 3 校验资金、持仓、涨跌停、T+1
  -> Matching Engine 撮合
  -> Clearing House 更新 Global Ledger
  -> Layer 3 发布 Account_Snapshot
  -> Agent 更新只读副本
```

禁止：

- Agent 在本地修改 `cash_snapshot` 或 `positions_snapshot`。
- Agent 绕过 Layer 3 直接生成成交结果。
- Agent 根据私有意图改写 `frozen_shares` 来绕过 T+1。

## 订单簿

`LOB` 的绝对所有者和维护者是 Layer 3 Matching Engine。

底层结构可以是：

- 买单队列：价格优先、时间优先的 Max-Heap。
- 卖单队列：价格优先、时间优先的 Min-Heap。

Agent 无权直接读取底层队列。允许 Agent 看到的市场深度只能来自 Layer 3 发布的合规 `Market_Price` 快照和交易所数据播报员发布的匿名异动：

- 最新成交价。
- 成交量。
- 买卖十档行情。
- 涨跌停状态。
- 匿名盘口异动。

## 全局历史事实

`Chronos Data` 的唯一真理源是 Layer 0。

Layer 0 可以持有完整历史数据，例如：

- 新闻。
- 财报。
- 监管函。
- 宏观数据。
- 历史价格。
- 历史龙虎榜。
- 向量化历史事件。

Agent 只能通过当前 Tick 的事件注入获得历史事实。未来 Tick 的事实不得进入 Agent 上下文，也不得通过 RAG 检索泄漏。

## 私有记忆

私有记忆的所有者和维护者是对应 Agent。

每个 Agent 的记忆存储必须物理或逻辑隔离，可以采用：

- Memory Buffer。
- 私有 SQLite。
- 私有向量集合。
- 文件级隔离的本地存储。

机构 Agent 的私有记忆可以包含官方财报、宏观数据、历史分析摘要。散户 Agent 的私有记忆可以包含股吧帖子、亏损经历、交易历史。一个 Agent 不得读取另一个 Agent 的私有记忆。

`thought` 属于私有审计材料，可以进入 `UI_Audit`，但不得进入任意 Agent 的下一轮上下文。

## Redis 总线

Layer 2 Redis 总线不拥有业务数据。

Redis 的职责是：

- 按频道传递事件。
- 保存可过期的实时快照。
- 为 Agent runtime 提供权限隔离后的内部订阅入口。
- 为 `WebApiGateway` 和 `FrontendRealtimeGateway` 提供可展示事件输入，但不作为前端直连入口。

Redis 不得成为以下数据的 SSOT：

- 资金。
- 持仓。
- 冻结股。
- 底层 LOB。
- 全量历史事实。
- Agent 私有记忆。

前端只能通过 REST `snapshot`、REST `events` 和 WebSocket 前端事件信封消费数据。`ack`、`from_seq`、`last_seq` 只属于前端恢复协议，不得改变任何业务 SSOT。

## 五个数据中心

1. **控制中心**：Meta-Orchestrator，拥有 Tick 推进、生命周期管理和 payload 路由切割权。
2. **资产中心**：Layer 3，拥有 `Ledger`、`Positions`、`frozen_shares`、`LOB`。
3. **事实中心**：Layer 0，拥有 `Chronos Data` 和历史事实释放节奏。
4. **认知中心**：Layer 1 Agent 本地，拥有 `Private Memory`、偏好、信念状态、只读资产快照。
5. **广播中心**：Layer 2 Redis 总线，不拥有业务数据，只按频道权限传递事件。

## 实现检查项

- 单元测试覆盖：Agent 修改本地资产副本不会影响 Layer 3 Ledger。
- 集成测试覆盖：成交后只有 Layer 3 能发布新的 `Account_Snapshot`。
- 集成测试覆盖：Agent 不能订阅底层 LOB，只能订阅 `Market_Price`。
- 集成测试覆盖：未来 Tick 的 `Chronos Data` 不会进入 Agent 输入。
- 集成测试覆盖：Agent A 不能读取 Agent B 的私有记忆。
- 集成测试覆盖：只有 Meta-Orchestrator 可以推进 `tick_id`。
