# Tick Lifecycle 内部契约

## 目标

定义一个 Tick 内控制面如何推进 Layer 0、Agent、Layer 3、Referee 和前端审计链路。系统时间轴只能由 Meta-Orchestrator 推进。

## Tick 状态机

```text
INIT_TICK
  -> RELEASE_FACTS
  -> PUBLISH_MARKET_VIEW
  -> AGENT_STEP
  -> BARRIER_WAIT
  -> PAYLOAD_SPLIT
  -> MATCH_AND_CLEAR
  -> RISK_AND_LIFECYCLE
  -> REFEREE_PUBLICATION
  -> COMMIT_TICK
```

## 状态定义

### `INIT_TICK`

Meta-Orchestrator 创建 `tick_id`、trace id、截止时间和当前活跃 Agent 列表。

### `RELEASE_FACTS`

Meta-Orchestrator 调用 Layer 0。Layer 0 只发布当前 Tick 允许可见的事实到 `Official_News`。

约束：

- Layer 0 不得释放未来 Tick 的事实。
- Agent 不得直接查询 Layer 0 全量历史库。

### `PUBLISH_MARKET_VIEW`

Meta-Orchestrator 调用 Layer 3 的 `MarketDataPublisher` 生成当前可见市场快照，并调用交易所数据播报员生成必要的前置匿名盘口异动。这里发布的是 Agent 决策前可见的市场视图，来源必须是上一已提交状态或当前 Tick 释放前已经公开的信息。发布责任固定为：

- `Market_Price`
- `MarketDataPublisher` 发布合规 Level-2 快照到 `Market_Price`。
- 交易所数据播报员读取 Layer 3 匿名市场输出，发布必要的 `Tape_Alerts`。

约束：

- 只发布匿名盘口和价格状态。
- 不发布底层 LOB 队列。
- 不发布订单身份绑定意图。
- 本阶段产生的 `Tape_Alerts` 可以进入当前 Tick 的 Agent 输入，因为它们只基于当前 Agent 决策前已经可见的市场状态。

### `AGENT_STEP`

Meta-Orchestrator 向所有活跃 Agent 发出 `agent.act(tick_context)`。

Agent 输入只能来自合法频道和自己的私有记忆：

- `Official_News`
- `Market_Price`
- `Account_Snapshot`
- `Tape_Alerts`
- `End_of_Day`，仅限已经发布的历史/上一收盘披露；盘中当前交易日披露必须为空
- `Forum_Rumors`
- 自己的 `Private Memory`

### `BARRIER_WAIT`

Meta-Orchestrator 等待全部活跃 Agent 返回，或等待超时。

超时策略必须显式配置：

| 策略 | 行为 | 后果 |
| :--- | :--- | :--- |
| `hold` | 生成空 action | 最安全，但会降低市场冲击 |
| `cancel_active_orders` | 撤销该 Agent 未成交挂单 | 更偏风控系统 |
| `forced_liquidation` | 触发强平流程 | 只适用于风险状态触发，不应用作普通超时默认值 |

默认策略：`hold`。

### `PAYLOAD_SPLIT`

Meta-Orchestrator 对每个 Agent payload 做字段级切割：

| 字段 | 目标 |
| :--- | :--- |
| `action` | Layer 3 / `Order_Input` |
| `thought` | `UI_Audit` |
| `belief_shift` | `UI_Audit` |
| `evidence_refs` | `UI_Audit` |
| `forum_post` | `Forum_Rumors`，仅允许有发帖权限的 Agent |

约束：

- Agent 原始 payload 不得写入公共 Redis 总线。
- `thought` 不得进入 Agent 合法输入频道。
- Meta-Orchestrator 不解释 payload 的金融含义，只做结构化路由。

### `MATCH_AND_CLEAR`

Layer 3 校验订单并执行撮合、清算、T+1 冻结、账户快照发布。

输出：

- 成交结果。
- 更新后的 `Global Ledger`。
- 对应 Agent 的 `Account_Snapshot`。
- 新的市场价格状态。

### `RISK_AND_LIFECYCLE`

Meta-Orchestrator 根据 Layer 3 风险结果处理生命周期：

- 正常存活。
- 禁止主动交易。
- 强制平仓。
- 终止 Agent。

Meta-Orchestrator 可以提交系统级 `forced_liquidation` action，但该 action 仍必须进入 Layer 3，由 Layer 3 执行清算。

### `REFEREE_PUBLICATION`

Meta-Orchestrator 调用 Referee 的两个隔离实体：

- 交易所数据播报员：读取 Layer 3 匿名市场输出，发布 `Tape_Alerts` 或 `End_of_Day`。
- UI 渲染审查官：读取 `UI_Audit`，发布 `Frontend_Audit_Graph` 和 `Frontend_Causal_Chain`。

约束：

- `Frontend_Audit_Graph` 和 `Frontend_Causal_Chain` 不得回流 Agent。
- 交易所数据播报员不得读取 Agent 私有 `thought`。
- 本阶段在 `MATCH_AND_CLEAR` 后生成的 `Tape_Alerts`、`End_of_Day` 和审计事件可以实时给前端展示，但最早只能进入下一 Tick 的 Agent 输入。
- `End_of_Day` 只能在收盘或模拟收盘阶段发布；发布前不得以空缺字段、预测字段或摘要形式进入当前 Tick Agent 上下文。

### `COMMIT_TICK`

Meta-Orchestrator 确认当前 Tick 的账本、事件日志、生命周期状态已落盘，然后推进到下一个 Tick。

## 一次完整 Tick 时序

```text
1. Meta-Orchestrator -> Layer 0: release(tick_id)
2. Layer 0 -> Official_News: publish current facts
3. Meta-Orchestrator -> MarketDataPublisher: publish_market_view(tick_id)
4. MarketDataPublisher -> Market_Price: publish Level-2 snapshot
5. Meta-Orchestrator -> Agent[*]: act(tick_id)
6. Agent[*] -> Meta-Orchestrator: payload(action, thought, belief_shift)
7. Meta-Orchestrator -> Order_Input: route action
8. Meta-Orchestrator -> UI_Audit: route thought/belief_shift
9. Meta-Orchestrator -> Layer 3: match_and_clear(tick_id)
10. Layer 3 -> Account_Snapshot: publish per-agent snapshots
11. Meta-Orchestrator -> Referee: publish Tape_Alerts / End_of_Day / audit graph
12. Meta-Orchestrator: commit tick and advance
```

## 实现检查项

- 系统中只有 Meta-Orchestrator 可以创建下一个 `tick_id`。
- Agent 不得自行调用 Layer 0 或 Layer 3 推进时间。
- Agent payload 原文不得进入公共频道。
- 超时 Agent 必须被记录，并按显式策略生成结果。
- `COMMIT_TICK` 前必须完成 Layer 3 账本更新。
