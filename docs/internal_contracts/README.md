# Internal Contracts 总览

## 目标

把架构里的每个模块都落到可检查的接口文档上。架构文档说明“系统为什么这样拆”，本目录说明“模块之间怎么说话、谁能看什么、谁能改什么”。

## 阅读顺序

1. `module_interface_registry.md`：先看模块总表和调用方向。
2. `state_ownership.md`：确认每类数据的唯一真理源。
3. `channel_routing.md`：确认哪些事件能进 Agent，哪些只能进前端。
4. `tick_lifecycle.md`：确认一个 Tick 怎么推进。
5. 各专项契约：按模块继续看具体 schema。

## 模块到接口覆盖表

| 架构模块 | 核心接口文档 | 覆盖内容 |
| :--- | :--- | :--- |
| `MetaOrchestrator` | `control_plane_contract.md`、`tick_lifecycle.md` | 会话初始化、Tick 推进、Agent 屏障、payload 切割、生命周期处理 |
| `Chronos` | `chronos_release_contract.md` | 历史事实按 Tick 释放、RAG 时间截断、初始市场种子 |
| `AgentRuntime` | `agent_payload_contract.md`、`agent_profile_prompt_contract.md`、`agent_identity_permissions.md` | Agent 输入、输出、身份权限、提示词设定、私有记忆边界 |
| `LLMGateway` | `agent_profile_prompt_contract.md` | 模型调用输入、上下文拼装边界、禁止跨 Agent 拼接 |
| `RedisBus` | `channel_routing.md` | 频道发布者、订阅者、可见性等级、泄露拦截点 |
| `MatchingEngine` | `order_and_clearing_contract.md` | 订单输入、拒单、撮合、LOB 可见性 |
| `ClearingHouse` | `order_and_clearing_contract.md`、`state_ownership.md` | 资金、持仓、冻结股、账户快照、风险状态 |
| `ExchangeBroadcaster` | `referee_publication_contract.md` | 盘口异动、盘后龙虎榜、匿名市场播报 |
| `UIAuditOfficer` | `referee_publication_contract.md` | 前端拓扑图、脱敏因果链、审计隔离 |
| `FrontendRealtimeGateway` | `../web_api/realtime_ws.md`、`../web_api/control_rest.md` | 前端实时推送、会话控制、快照恢复 |

## 契约完整性标准

一份模块接口文档必须至少说明：

- 这个模块接收什么输入。
- 这个模块输出什么事件或返回值。
- 哪些字段是必填。
- 谁允许调用或订阅。
- 哪些数据绝对不能出现在输出里。
- 出错时怎么处理。
- 这个接口对应的唯一真理源在哪里。

## 当前固定边界

- `thought`、私有记忆、未公开意图不得进入任何 Agent 可订阅通道。
- `action` 是 Agent 影响市场的唯一入口。
- `Ledger`、`Positions`、`frozen_shares`、`LOB` 的唯一真理源在 Layer 3。
- `Chronos Data` 的唯一真理源在 Layer 0。
- Tick 只能由 `MetaOrchestrator` 推进。
- 前端可以看脱敏审计结果，但前端输出不得回流 Agent。

## 新增接口前的检查

- 如果接口会改变资金、持仓、订单或 Tick，先检查是否绕过了 `MetaOrchestrator` 或 Layer 3。
- 如果接口会展示因果链，先检查是否把原始 `thought` 泄露给了公共频道。
- 如果接口会给 Agent 增加输入，先检查 `agent_identity_permissions.md` 是否明确授权。
- 如果接口只是给前端展示，必须标记 `frontend_only` 或对应的前端可见性等级。
