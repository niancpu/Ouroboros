# Agent Profile 与 Prompt 内部契约

## 目标

定义 Agent 的身份设定、提示词、策略偏好和私有记忆如何配置。核心原则：Prompt 只能影响“怎么思考”，不能扩大“能看到什么”。

## 模块边界

| 项 | 说明 |
| :--- | :--- |
| 模块名 | `AgentRuntime` |
| 相关基础设施 | `LLMGateway`、Agent 私有 Memory Store |
| 拥有数据 | 本 Agent 的 `Private Memory`、性格设定、策略偏好、只读资产快照 |
| 输入来源 | Meta-Orchestrator 构造的 `tick_context` |
| 输出去向 | Meta-Orchestrator |
| 禁止 | 读取其他 Agent 记忆、直接查全量历史、直接改资产、把 Prompt 当作权限来源 |

## Agent Profile Set

一组 Agent 设定必须集中配置，不能散落在代码和 prompt 文本里。

```json
{
  "schema_version": "v1",
  "profile_set_id": "default_24",
  "agents": [
    {
      "agent_id": "hot_money_a",
      "agent_type": "hot_money",
      "display_name": "游资 A",
      "seat_alias": "宁波桑田路",
      "strategy_bias": ["momentum", "forum_narrative"],
      "risk_profile": {
        "risk_appetite": "high",
        "max_drawdown_pct": 50
      },
      "prompt_profile_ref": "prompt_hot_money_v1",
      "memory_namespace": "mem_hot_money_a",
      "permission_profile_ref": "perm_hot_money_default",
      "initial_asset_plan_ref": "asset_hot_money_a"
    }
  ]
}
```

字段说明：

- `agent_id` 是系统内唯一身份。
- `agent_type` 必须来自 `agent_identity_permissions.md`。
- `seat_alias` 只用于盘后席位风格或前端展示，不等于真实私有身份。
- `memory_namespace` 必须与其他 Agent 隔离。
- `permission_profile_ref` 指向权限配置，不能由 prompt 覆盖。
- `initial_asset_plan_ref` 只是初始化计划，实际落账仍由 Layer 3 完成。

## Prompt Profile

```json
{
  "schema_version": "v1",
  "prompt_profile_id": "prompt_hot_money_v1",
  "agent_type": "hot_money",
  "system_role": "你是一个偏短线情绪和盘口的 A 股游资 Agent。",
  "behavior_rules": [
    "关注盘口异动、股吧情绪和短线资金合力。",
    "可以发布公开股吧观点，但公开帖子不得复制私有 thought。",
    "只能基于 tick_context 和自己的私有记忆做判断。"
  ],
  "risk_rules": [
    "不得假设自己拥有未公开信息。",
    "不得自行修改现金、持仓或可卖数量。"
  ],
  "output_schema_ref": "agent_payload_contract.md",
  "forbidden_claims": [
    "我可以查看其他 Agent 的 thought",
    "我可以直接读取底层 LOB",
    "我可以知道未来价格"
  ]
}
```

约束：

- Prompt 中可以写人格、偏好、交易风格。
- Prompt 中不能写“你拥有某某数据权限”来绕过权限矩阵。
- Prompt 不得要求模型输出成交结果、清算结果或账户变更。
- Prompt 必须要求输出结构化 JSON，并符合 `agent_payload_contract.md`。

## Tick Context 拼装

Agent 每轮只能看到 Meta-Orchestrator 按权限拼好的 `tick_context`。

上下文组成：

```text
prompt_profile
  + permission-filtered public_inputs
  + own Account_Snapshot
  + own Private Memory refs
  + output schema
  + current constraints
```

禁止加入：

- 其他 Agent 的 `thought`。
- `UI_Audit`。
- `Frontend_Audit_Graph` 或 `Frontend_Causal_Chain`。
- Layer 3 底层 LOB。
- Chronos 未来事实。
- 其他 Agent 的账户快照。

## 私有记忆接口

### `memory_read`

请求：

```json
{
  "schema_version": "v1",
  "agent_id": "retail_b",
  "memory_namespace": "mem_retail_b",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "query": "当前行情和过去追高亏损经历是否相似",
  "limit": 5
}
```

返回：

```json
{
  "schema_version": "v1",
  "agent_id": "retail_b",
  "memory_refs": [
    {
      "memory_id": "mem_001",
      "memory_type": "past_trade",
      "summary": "曾在高波动行情追涨后回撤。",
      "created_tick_id": "2023-12-20T10:30:00+08:00"
    }
  ]
}
```

约束：

- `agent_id` 必须与 `memory_namespace` 绑定。
- 返回摘要不能包含其他 Agent 私有信息。
- 如果记忆来自公开事件，可以保留公开 `event_ref`。

### `memory_write`

请求：

```json
{
  "schema_version": "v1",
  "agent_id": "retail_b",
  "memory_namespace": "mem_retail_b",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "memory_type": "decision_trace",
  "summary": "受到股吧帖子影响，看多情绪上升。",
  "source_refs": ["forum_post_123", "acct_001"]
}
```

约束：

- 只能写入本 Agent 记忆空间。
- 可以记录私有决策摘要，但不得被其他 Agent 读取。
- 写入失败不得阻塞 Layer 3 清算，但必须记录审计错误。

## LLMGateway 调用边界

LLM 请求：

```json
{
  "schema_version": "v1",
  "request_id": "llm_req_001",
  "agent_id": "hot_money_a",
  "tick_id": "2024-01-02T14:02:00+08:00",
  "prompt_profile_id": "prompt_hot_money_v1",
  "messages": [],
  "output_schema_ref": "agent_payload_contract.md",
  "deadline_ms": 30000
}
```

约束：

- `LLMGateway` 只负责模型调用、限流和返回结构预检。
- `LLMGateway` 不得跨 Agent 合并上下文。
- `LLMGateway` 不得持久化业务事实作为新的 SSOT。
- 模型原始输出必须先转成候选 Agent payload，再交给 Meta-Orchestrator 做最终安全校验和路由。

## 权限与 Prompt 的关系

优先级固定为：

```text
系统硬边界 > 权限矩阵 > tick_context 实际输入 > Prompt 文字
```

后果：

- Prompt 说“你知道机构在出货”，但 `tick_context` 没有这个事实时，Agent 不能获得该信息。
- Prompt 说“你可以看全市场账户”，运行时仍只能给本 Agent 的 `Account_Snapshot`。
- Prompt 说“发布帖子”，也必须先通过 `forum_post` 发布权限校验。

## 实现检查项

- 每个 Agent 必须有唯一 `memory_namespace`。
- 构造 LLM messages 前必须完成频道权限过滤。
- Prompt 配置不得包含任何能扩大数据权限的字段。
- LLM 原始输出不得直接进入 Redis。
- `forum_post.text` 不得自动复制 `thought`。
- Agent 本地资产副本只能由 `Account_Snapshot` 更新。
