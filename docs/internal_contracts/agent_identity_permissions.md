# Agent Identity Permissions 内部契约

## 目标

集中定义 Agent 类型、频道订阅权限、发帖权限和官方信息访问权限。权限不得散落在 prompt 中硬编码；Agent prompt 只能表达性格和策略偏好，不能扩大数据访问范围。

## Agent 类型

| 类型 | 示例 | 主要特征 | 默认是否调用 LLM |
| :--- | :--- | :--- | :--- |
| `mutual_fund` | 公募机构 | 基本面、研报、合规限制 | 是 |
| `hot_money` | 游资大佬 | 情绪、动量、股吧叙事 | 是 |
| `quant_algo` | 量化游资 | 规则驱动、微观结构反应 | 可选 |
| `retail` | 散户 | FOMO、损失厌恶、跟风 | 是 |
| `national_team` | 国家队/平准基金 | 极端行情下提供流动性 | 是 |

## 权限矩阵

| Channel | `mutual_fund` | `hot_money` | `quant_algo` | `retail` | `national_team` |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `Official_News` | 订阅 | 订阅 | 订阅 | 可配置 | 订阅 |
| `Market_Price` | 订阅 | 订阅 | 订阅 | 订阅 | 订阅 |
| `Account_Snapshot` | 仅本人 | 仅本人 | 仅本人 | 仅本人 | 仅本人 |
| `Tape_Alerts` | 订阅 | 订阅 | 订阅 | 订阅 | 订阅 |
| `End_of_Day` | 订阅 | 订阅 | 订阅 | 订阅 | 订阅 |
| `Forum_Rumors` | 可配置 | 订阅 | 可配置 | 订阅 | 可配置 |
| `UI_Audit` | 禁止 | 禁止 | 禁止 | 禁止 | 禁止 |
| `Frontend_Audit_Graph` | 禁止 | 禁止 | 禁止 | 禁止 | 禁止 |

## 发布权限

| 输出 | 默认允许类型 | 实际发布者 | 说明 |
| :--- | :--- | :--- | :--- |
| `action` -> `Order_Input` | 所有活跃 Agent | Meta-Orchestrator | Agent 是语义来源，控制面校验后路由 |
| `thought` -> `UI_Audit` | 所有活跃 Agent | Meta-Orchestrator | 私有审计材料，不可回流 |
| `forum_post` -> `Forum_Rumors` | `hot_money`，可配置扩展 | Meta-Orchestrator | 必须通过发帖权限校验 |

## 配置示例

```json
{
  "schema_version": "v1",
  "agent_id": "hot_money_a",
  "agent_type": "hot_money",
  "subscriptions": [
    "Official_News",
    "Market_Price",
    "Account_Snapshot:self",
    "Tape_Alerts",
    "End_of_Day",
    "Forum_Rumors"
  ],
  "publish_permissions": {
    "order_action": true,
    "ui_audit": true,
    "forum_post": true
  },
  "official_news_scope": ["announcement", "news", "regulatory_notice"]
}
```

## 约束

- `Account_Snapshot:self` 必须在运行时解析为当前 Agent 自己的私有快照。
- Agent 类型不能隐式获得频道权限，必须由权限矩阵或配置显式授权。
- Prompt 中出现“你可以查看其他账户”“你知道机构正在出货”等描述时，运行时不得因此扩大输入。
- 权限配置变更必须进入审计日志。

## 取舍与后果

- 散户默认不订阅 `Official_News` 或只订阅部分官方新闻。后果是更符合信息不对称，但评测场景可以通过配置打开。
- `hot_money` 默认可发布 `forum_post`。后果是叙事传播链路更强，但必须确保公开帖子和私有 `thought` 字段隔离。
- `quant_algo` 可以不调用 LLM。后果是降低 API 压力，也能保留市场微观结构行为。

## 实现检查项

- 构造 `tick_context` 前必须根据本文件权限矩阵过滤频道事件。
- 未授权 Agent 发布 `forum_post` 时必须拒绝。
- Agent runtime 永远不注册 `UI_Audit` 和 `Frontend_Audit_Graph`。
- 权限测试覆盖每种 Agent 类型的默认订阅集合。
