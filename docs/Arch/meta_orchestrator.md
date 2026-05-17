# Meta-Orchestrator 控制面设计

## 目标

Meta-Orchestrator 是 Ouroboros 的控制面。它负责全局 Agent 管理、时间推进、生命周期调度和返回体路由切割，但不参与金融逻辑计算，也不拥有业务数据的唯一真理源。

## 职责范围

- 推进 Tick。
- 管理 Agent 生命周期。
- 执行并发屏障。
- 接收 Agent payload 并做字段级路由。
- 驱动 Layer 0、Layer 3、Referee。

## 平面边界

| 平面 | 组件 | 职责 | 禁止事项 |
| :--- | :--- | :--- | :--- |
| Control Plane | Meta-Orchestrator | Tick 推进、生命周期管理、并发屏障、payload 路由切割 | 生成市场信号、改写账本、发布私有信息 |
| Data Plane | Layer 0 | 释放历史事实 | 跳过 Tick 暴露未来事实 |
| Data Plane | Layer 1 Agent | 生成私有思考和交易动作 | 修改资产 SSOT、读取其他 Agent 私有记忆 |
| Data Plane | Layer 2 Redis | 按权限传递事件 | 成为业务 SSOT |
| Data Plane | Layer 3 | 撮合、清算、维护账本和 LOB | 读取 Agent 私有 `thought` |
| Data Plane | Referee | 播报市场可见事实、生成前端审计图 | 把 UI 审计结果回流 Agent |
| Adapter | Web API 层 | REST 会话控制、快照查询、事件回放、前端 WebSocket 推送 | 绕过控制面改业务状态、透传内部事件 payload |

Web API 层是前端唯一入口。REST 命令只能由 `WebApiGateway` 转换为控制面允许的会话操作；实时推送只能由 `FrontendRealtimeGateway` 将内部可展示事件转换为 Web API 事件后发送给前端。

## 生命周期管理

推演开始时：

- 读取配置。
- 请求 Chronos 生成 `initial_market_seed`。
- 实例化 Agent 进程或协程。
- 调用 Layer 3 初始化资金池、初始持仓和初始市场状态。

前端创建会话时调用 `POST /api/v1/sessions`。`WebApiGateway` 只负责鉴权、幂等和 schema 校验，然后调用 Meta-Orchestrator 的 `create_session`；不得直接初始化 Layer 0、Layer 3 或 Agent runtime。

初始化流程：

```text
Meta-Orchestrator 读取 session_config
  -> Chronos.build_initial_market_seed(config)
  -> Layer 3 initialize_market(seed)
  -> Layer 3 发布第一份合规 Market_Price
  -> Agent 只能通过 Market_Price 看到初始市场
```

每个 Tick 结束后：

- 读取 Layer 3 的账户快照或风险结果。
- 处理强平、停用、恢复等生命周期动作。

强平流程：

```text
Layer 3 产出风险状态
  -> Meta-Orchestrator 判断触发强平线
  -> Meta-Orchestrator 停止该 Agent 主动 act 权限
  -> Meta-Orchestrator 向 Layer 3 提交 forced_liquidation action
  -> Layer 3 校验并执行清算
  -> UI 标记该 Agent 为已爆仓/已终止
```

## Tick 屏障

Meta-Orchestrator 是唯一时钟权威。它向所有活跃 Agent 发出 `Step(Tick_N)` 后，等待所有 Agent 返回，或等待超时策略触发。

推进 `Tick_N+1` 的前置条件：

- Layer 0 已完成当前 Tick 的事实释放。
- Layer 3 已完成当前可见市场快照发布。
- 所有活跃 Agent 已返回 payload，或被超时策略处理。
- Layer 3 已完成订单撮合与清算。
- UI 审计链路已接收当前 Tick 的审计材料，允许异步渲染但不得阻塞账本一致性。

## 路由切割

Meta-Orchestrator 统一接收 Agent payload，并只做字段级路由，不做市场含义解释。

示例输入：

```json
{
  "agent_id": "retail_b",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "action": {
    "side": "buy",
    "price": 15.2,
    "quantity": 1000,
    "order_type": "limit"
  },
  "thought": "private, never routed back to agents",
  "belief_shift": -0.5
}
```

路由规则：

- `action` -> Layer 3 `Order_Input`。
- `thought`、`belief_shift`、`evidence_refs` -> `UI_Audit`。
- `forum_post` -> 权限校验后进入 `Forum_Rumors`。
- `memory_update` -> 仅写入该 Agent 私有记忆。
- `agent_id`、`tick_id`、`trace_id` -> 控制面日志。

绝对禁止：

- 把任意 Agent payload 原样写入公共 Redis 总线。
- 把 `thought`、私有记忆、未公开意图放进 `Official_News`、`Market_Price`、`Tape_Alerts`、`Forum_Rumors`。
- 把 `memory_update` 写入公共频道或其他 Agent 记忆。
- 用 Meta-Orchestrator 代替 Agent 或 Layer 3 做金融判断。

## 驱动外部环境

Meta-Orchestrator 决定何时调用：

- Layer 0：释放当前 Tick 的官方事实与历史事件。
- Layer 3：发布 Level-2 快照、执行撮合与清算、产出风险状态。
- LLMGateway：只做模型调用、限流和结构化输出格式预检，不拥有业务事实；最终安全校验由 Meta-Orchestrator 执行。
- Referee 数据播报员：生成盘口异动、盘后龙虎榜。
- UI 审计官：生成前端拓扑边与脱敏说明。

Meta-Orchestrator 不直接向浏览器发送内部事件。运行状态、Agent 生命周期和 Tick 状态先作为内部 `control_only` 事件产出，再由 Web API 层转换成 `runtime.tick_state`、`runtime.agent_lifecycle` 或 REST 响应中的前端字段。

## 权力边界

Meta-Orchestrator 有最高调度权，但没有业务数据所有权。

它不拥有：

- 资金和持仓 SSOT。
- 底层 LOB。
- Agent 私有记忆。
- Chronos 全量事实库。
- 公共市场事实解释权。

它拥有：

- Tick 推进权。
- Agent 生命周期管理权。
- 超时和失败处理权。
- Agent 返回体字段级路由权。
- 系统级 trace 和审计日志写入权。

## 未决取舍

- 超时 Agent 的默认动作：`HOLD` 最安全，但会弱化恐慌行情；`cancel_active_orders` 更偏风控；保留上一 Tick 意图风险最高。
- 强平阈值：固定亏损比例易实现，按 Agent 类型配置更真实。
- UI 审计是否阻塞 Tick：建议不阻塞账本推进，只保证审计事件最终到达前端。

## 已定 API 对齐决策

- REST `/start` 和 `/step` 如果从 `created` 状态进入运行，必须先完成初始化流程并发布第一份合规 `Market_Price`，再推进 Agent Tick。
- REST `/step` 调度一个 Tick 时可短暂进入 `running`，到达 `COMMIT_TICK` 后必须自动回到 `paused`。
- REST 端点、WebSocket 事件和恢复语义以 [../web_api/README.md](../web_api/README.md) 为准；前端页面需求以 [../frontend/frontend_design.md](../frontend/frontend_design.md) 为准。
