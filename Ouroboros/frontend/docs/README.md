# Frontend Implementation Docs

## 文档归属

本目录只记录前端工程实现侧文档，服务于 `Ouroboros/frontend` 内的代码实现、组件拆分、状态组织、错误恢复和验收检查。

- 根设计文档：`D:\WorkField\Projects\Ouroboros\docs\frontend\frontend_design.md`
- Web API 协议文档：`D:\WorkField\Projects\Ouroboros\docs\web_api`
- 前端实现侧文档：`D:\WorkField\Projects\Ouroboros\Ouroboros\frontend\docs`

## 权威来源

- 页面形态、视觉语言、交互需求和页面级数据需求，以根设计文档为准。
- REST、WebSocket、错误码、断线恢复和字段 schema，以 `docs\web_api` 为准。
- 本目录不得新增 Web API 字段、内部频道、长期状态归属或权限模型。
- 发现实现需要新字段时，先更新 Web API 文档，再同步本目录。

## 禁止复制协议定义

本目录可以引用 Web API 能力边界，但不得复制一份独立协议定义，避免实现文档和协议文档分叉。

允许记录：

- 前端如何组织 API client。
- 页面状态如何消费 REST 快照和 WebSocket 事件。
- 错误、恢复、回放和缓存的实现策略。
- UI 约束如何转成组件和 CSS token。

禁止记录为本目录权威：

- REST 请求/响应完整字段 schema。
- WebSocket 事件完整 payload。
- 错误码全集。
- 内部 channel、Redis key、Layer 0/1/2/3 数据结构。

## 第一版已决边界

- 第一版是桌面专业工具，不做移动端卡片流。
- 初始化配平只作为 `agent_profile_set` 可视化预览和本地草稿；除非 Web API 已定义字段，否则不影响真实创建请求。
- 时间轴第一版只读；本地草案不得保存、发布或写入 Chronos SSOT。
- 智能体解剖室是普通审计视图，不展示原始 COT。
- 白皮书崩塌概率只展示后端或快照已有字段；缺失时显示 `N/A`。
- 图谱布局由前端确定性计算，只服务展示，不回传后端。
- 普通前端严禁展示原始 `thought`、COT、Prompt、私有记忆或 Agent 原始 payload。

