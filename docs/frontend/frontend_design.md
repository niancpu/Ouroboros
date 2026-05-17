# Ouroboros 前端设计归档

## 文档边界

本文只定义前端页面、视觉语言、交互需求和页面级数据需求。

- 架构边界以 [../Arch/arch.md](../Arch/arch.md) 的 Layer 4 为准。
- REST、WebSocket、错误码和断线恢复以 [../web_api/README.md](../web_api/README.md)、[../web_api/control_rest.md](../web_api/control_rest.md)、[../web_api/realtime_ws.md](../web_api/realtime_ws.md)、[../web_api/visibility_and_errors.md](../web_api/visibility_and_errors.md) 为准。
- 内部频道来源和可见性转换以 [../internal_contracts/channel_routing.md](../internal_contracts/channel_routing.md) 和 [../internal_contracts/module_interface_registry.md](../internal_contracts/module_interface_registry.md) 为准。
- 本文不得新增 Web API 字段、内部频道或状态归属；发现页面需求缺字段时，先同步更新 Web API 文档。

## 目标

Ouroboros 前端定位为“昂贵、可审计的机构级金融沙盘推演工具”。前端不是营销站，也不是普通 SaaS 仪表盘；它应像彭博终端、工程蓝图和做空机构报告的混合体。

第一版前端按完整沙盘推演生命周期设计 5 个核心页面：

1. 沙盘初始化控制台
2. 实时推演画板
3. 智能体解剖室
4. 时间轴剧本管理
5. 最终判决与漏洞白皮书

前端访问路径固定为 Web API 层。REST 通过 `WebApiGateway`，实时事件通过 `FrontendRealtimeGateway`。前端不得直连 Redis、内部 Pub/Sub、Layer 0/1/2/3 或 Agent runtime。

普通前端不得展示原始 `thought`、Prompt、私有记忆或 Agent 原始 payload。若未来需要沙盒外诊断能力，必须独立设计权限、审计日志和接口，不复用普通页面。

## 总体风格

采用“瑞士国际主义排版 + 先锋金融终端风”：高对比工程化财经终端 + 报纸编辑部版式。

视觉目标：

- 严肃、冷静、昂贵、可审计。
- 像白底黑字的机构交易终端、工程图纸和财经报告，少量克莱因蓝形成高强度撞色。
- 信息密度高，但所有边界都由严格网格切割。
- 不用互联网产品常见的柔和卡片、渐变、玻璃拟态、圆角和投影。

基础色：

| 颜色 | 值 | 用途 |
| :--- | :--- | :--- |
| 纯白 | `#ffffff` | 页面主体、图表背景、报告纸面、高密度数据区 |
| 纯黑 | `#000000` | 主要文字、边框、表格线、下跌实体 |
| 克莱因蓝 | `#002fa7` | 小面积高强度强调：运行态、选中线、关键按钮、关键曲线、预警标记 |
| 警戒红 | `#dc2626` | 风险、失败、异常，仅小面积使用 |
| 增长绿 | `#10b981` | 正向状态，仅小面积使用 |

面积原则：

- 85% 以上屏幕面积应为纯白或白底黑线框。
- 克莱因蓝只小面积使用；不得铺满导航、页眉、整列侧栏或大块内容背景。
- 黑色用于字体、边框、表格线和金融语义，不做大面积背景。
- 白色用于承载高密度数据、图表和长文本阅读区。
- 红绿只服务金融语义，不做装饰。

字体分工：

| 用途 | 字体 | 使用范围 |
| :--- | :--- | :--- |
| 叙事标题 | Georgia, Times New Roman, SimSun, serif | Masthead、报告标题、页面主标题 |
| 数据与机器状态 | Courier New, JetBrains Mono, monospace | Tick、时间、价格、Agent id、错误码、事件流 |
| UI 控件与正文 | Helvetica Neue, Arial, sans-serif | 导航、按钮、标签、长文本、普通说明 |

页面军规：

1. 用边框代替间距。模块之间优先使用 `border-right`、`border-bottom` 切开。
2. 全系统默认 `border-radius: 0`。
3. 禁止阴影、发光、模糊、渐变、装饰性圆点。
4. 白底上使用纯黑 1px/2px 线；蓝底只用于小块区域，文字优先黑色。
5. Hover 只做瞬间颜色反转，不做弹跳、呼吸、漂浮动效。
6. 图表不使用默认主题，不使用面积渐变和灰色网格。

## 全局导航

导航像终端模块切换，而不是普通网站导航。

导航项：

- 初始化
- 实时推演
- 智能体
- 时间轴
- 白皮书

导航规则：

- 顶部高度 72px。
- 白底，黑色字体，底部 2px 纯黑线。
- 左侧品牌使用 Georgia：`Ouroboros`
- 右侧模块名使用等宽字体或 Helvetica Bold。
- 当前页面底部用 3px 克莱因蓝线标记。

## 页面 1：沙盘初始化控制台

### 定位

推演开始前的参数配平中心。视觉上像飞行前检查清单、工程蓝图参数表和机构交易前风控单。

### 布局

```text
┌──────────────────────────────────────────────────────────────┐
│ [OUROBOROS // 新建推演]             标的 000001.SH  3021.44    │
├──────────────────────────┬───────────────────────────────────┤
│ 标的与环境 40%            │ 智能体配平 60%                     │
│                          │ ┌────────┬────────┬────────┐      │
│ 标的代码                 │ │ 公募   │ 游资   │ 散户   │      │
│ 时间锚点                 │ │ 雷达图 │ 雷达图 │ 雷达图 │      │
│ 场景编号                 │ │ 参数   │ 参数   │ 参数   │      │
├──────────────────────────┴───────────────────────────────────┤
│ [启动推演序列]                                                │
└──────────────────────────────────────────────────────────────┘
```

顶部：

- 高度约 15vh。
- 左侧 Georgia 大标题：`[OUROBOROS // 新建推演]`
- 右侧可使用小面积克莱因蓝数字块，黑色等宽字体展示真实市场指数或系统时间。

左侧列：标的与环境

- 宽度 40%。
- 白底，1px 黑线框出表单。
- 字段：
  - 标的代码
  - 场景编号
  - 时间锚点
  - 起始节拍
  - 结束节拍
  - 节拍间隔
- 输入框为直角黑框。
- Focus 时边框变 2px 克莱因蓝。

右侧列：智能体配平

- 宽度 60%。
- 三列等宽：
  - 公募机构
  - 游资
  - 散户
- 每个阵营包含：
  - 智能体数量步进器。
  - 资金权重步进器。
  - 信息敏感度步进器。
  - 风险厌恶度步进器。
  - 极简纯线条雷达图。

控件规则：

- 不使用传统 Slider。
- 数值调节使用输入框 + 步进器。
- 步进器按钮是硬边小方块，`-` 和 `+` 使用等宽字体。

雷达图规则：

- 图表框为正方形。
- 雷达网为纯黑 1px 多边形。
- 参数连线为 1px 克莱因蓝曲线或折线。
- 不使用填充面积，不使用渐变。

底部操作：

- 巨大按钮：`[启动推演序列]`
- 默认克莱因蓝底 + 黑字；按钮是页面内主要蓝色块，不再额外铺蓝色背景。
- Hover 变白底 + 黑字，并保留黑色边框。
- 点击后创建会话，但不直接绕过控制面；必须调用 Web API 会话创建接口。

### 数据来源

- REST `POST /api/v1/sessions`
- REST `GET /api/v1/sessions/{session_id}`
- 可选市场预览来自 WebSocket `market.price` 或 REST `GET /api/v1/sessions/{session_id}/snapshot`。

### 禁止

- 不直接初始化 Layer 0、Layer 3 或 Agent runtime。
- 不允许前端写入 `Order_Input`。
- 不允许前端注入 `Forum_Rumors` 或 `thought`。

## 页面 2：实时推演画板

### 定位

推演过程中的核心监控室。冷酷网格牢笼内，Agent、叙事和价格像粒子轨迹一样碰撞。

### 布局

```text
┌──────────────────────────────────────────────────────────────┐
│ Ouroboros 实时推演     会话 演示会话一     节拍 14     运行中  │
├──────────────┬───────────────────────────────────┬───────────┤
│ 时间轴事件流 │ 共识感染画布                         │ 盘口      │
│ 20% 蓝底      │ 上 60%: 拓扑图谱                   │ 20%       │
│              │ 下 40%: 价格 / 共识曲线             │           │
└──────────────┴───────────────────────────────────┴───────────┘
```

左侧栏：时间轴事件流

- 宽度 20%。
- 白底，黑色等宽字体；只用克莱因蓝左边线或事件编号标记运行态。
- 像报纸窄列，严格按 Tick 向下滚动。
- 展示：
  - `runtime.tick_state`
  - `market.tape_alert`
  - `forum.post`
  - 官方事实注入摘要
  - `system.error` 摘要
- 不展示未来事实。
- 不展示原始 `thought`。

中栏：画布

- 宽度 60%。
- 白底。
- 上 60%：共识感染拓扑图。
- 下 40%：价格走势和共识平均值。

拓扑图规则：

- 允许圆和曲线，但必须是几何工程语言。
- 节点是绝对正圆。
- 圆形只允许：
  - 纯白填充 + 1px 纯黑描边。
  - 克莱因蓝描边。
  - 选中态克莱因蓝实心 + 白字。
- 禁止阴影、渐变、发光、呼吸动画。
- 标签用引线牵出，等宽字体标注，例如 `[散户乙] 活跃`。
- 连线使用 1px 纯黑或克莱因蓝贝塞尔曲线。
- 箭头使用锐利几何三角形，不使用圆角箭头。
- 曲线视觉隐喻是粒子碰撞轨迹，不是社交网络图。

曲线语义：

| 线型 | 含义 |
| :--- | :--- |
| 实线 | 已确认公开影响 |
| 虚线 | 审计推断链路 |
| 点划线 | 弱相关或低置信链路 |

行情曲线：

- 不使用面积图。
- 价格走势使用 2px 克莱因蓝实线。
- 共识平均值使用 1px 纯黑实线。
- 没有完整坐标轴，只保留极值点的悬浮等宽标签。

右侧栏：微观订单簿

- 宽度 20%。
- 白底。
- 横向切成大量 24px 高窄条。
- 卖盘用警戒红小面积文字。
- 买盘用纯黑或极小面积绿色。
- 数字全部等宽字体。
- 不展示底层真实订单 id 或 Agent 身份绑定意图；只展示 Web API 允许的聚合行情视图。

### 数据来源

- WebSocket `runtime.tick_state`
- WebSocket `runtime.agent_lifecycle`
- WebSocket `market.price`
- WebSocket `market.tape_alert`
- WebSocket `forum.post`
- WebSocket `audit.graph`
- WebSocket `audit.causal_chain`
- WebSocket `system.error`
- REST `GET /api/v1/sessions/{session_id}/snapshot` 用于断线恢复。

### 禁止

- 不显示 `Order_Input`、`UI_Audit`、`trade_batch`、`risk_result` 原始 payload。
- 不允许 WebSocket 提交订单、发帖、改账或改 Agent 状态。

## 页面 3：智能体解剖室

### 定位

审计单个智能体的状态、资产、信念轨迹和脱敏推理摘要。体现系统可解释性。

### 布局

```text
┌──────────────────────────────────────────────────────────────┐
│ 智能体解剖室     [散户乙]                                    │
├──────────────────┬───────────────────────────────────────────┤
│ 实体名录 25%     │ 四象限工作区 75%                          │
│                  │ ┌──────────────┬────────────────────────┐ │
│ [公募甲]         │ │ 资产表        │ 脱敏审计流              │ │
│ [散户乙]         │ ├──────────────┤                        │ │
│ ...              │ │ 信念轨迹      │                        │ │
│                  │ └──────────────┴────────────────────────┘ │
└──────────────────┴───────────────────────────────────────────┘
```

左侧：实体名录

- 宽度 25%。
- 像列车时刻表。
- 24 个智能体竖排：
  - `[公募甲]`
  - `[散户乙]`
  - `[国家队甲]`
- 默认白底黑字。
- 选中行白底黑字，左侧或底部用克莱因蓝短线标记。
- 高风险智能体行尾用小面积红色标记。

主工作区：四象限

左上：资产表

- 纯表格排版。
- 字段：
  - `cash`
  - `available_cash`
  - `positions`
  - `available_shares`
  - `frozen_shares`
  - `market_value`
  - `equity`
  - `risk_state`
- 数据来自 `agent.account_snapshot` 或 REST 快照。

左下：信念轨迹

- 白底。
- 1px 克莱因蓝曲线。
- 不使用面积填充。
- 标注关键 Tick，例如强平、发帖、盘口异动。

右侧贯穿：脱敏审计室

- 白底。
- 左侧一条 1px 克莱因蓝竖线贯穿到底。
- 展示脱敏审计摘要、公开原因、事件引用、风险标签。
- 字体使用 Helvetica，保证长文本可读。
- 关键逻辑词汇可用克莱因蓝高亮，例如“强平线”“恐慌”“流动性真空”。

### COT 边界

普通智能体解剖室不展示原始 `<thought>` 或 COT。它只能展示：

- 脱敏 `public_reason`
- `audit.causal_chain` 摘要
- 可展示事件引用
- 风险状态说明

若后续要展示原始 COT，必须新增沙盒外诊断能力，并满足：

- 独立权限。
- 独立审计日志。
- 不进入普通 Web API 事件回放。
- 不回流 Agent。

### 数据来源

- WebSocket `agent.account_snapshot`
- WebSocket `runtime.agent_lifecycle`
- WebSocket `audit.graph`
- WebSocket `audit.causal_chain`
- REST `GET /api/v1/sessions/{session_id}/snapshot` 中的 `agents`

## 页面 4：时间轴剧本管理

### 定位

展示和管理历史切片、官方事实轨、谣言轨和演示剧本。它证明系统不是黑箱，而是可复现实验沙盘。

### 权限边界

时间轴页面属于第一版五页范围，但第一版以只读展示和剧本草案预览为主。它涉及未来 Tick、事实释放和剧本插桩，写入或正式编辑能力必须后续另行设计权限和审计。

### 布局

```text
┌──────────────────────────────────────────────────────────────┐
│ 时间轴剧本管理                                               │
├──────────────────────────────────────────────────────────────┤
│ 时间线: ───○────○────●────△────○────○────────────────────── │
├──────────────────────────────┬───────────────────────────────┤
│ 官方事实轨                    │ 公开传闻轨                    │
│ 报纸式官方事件                 │ 电报式情绪消息                 │
└──────────────────────────────┴───────────────────────────────┘
```

顶部时间轴：

- 高度 20%。
- 一条 2px 黑线横穿屏幕。
- Tick 使用几何圆点。
- 当前 Tick 使用克莱因蓝实心圆。
- 未来插桩预警使用克莱因蓝三角形。

下半区：双轨瀑布流

左半区：官方事实轨

- 报纸头版排版。
- Georgia 大标题。
- 黑白强对比。
- 展示官方新闻、财报、监管函、宏观数据。

右半区：公开传闻轨

- 电报式消息堆叠。
- 等宽时间戳。
- 显示公开论坛消息、情绪指数、传播范围。

插桩规则：

- 若启用编辑能力，只能生成剧本草案，不能直接绕过 Meta-Orchestrator 或 Chronos 写入运行态。
- 每个插桩必须有：
  - `tick_id`
  - `event_type`
  - `visibility`
  - `source`
  - `audit_reason`
- 插桩不得泄露未来事实给当前 Tick Agent。

### 数据来源

- REST `GET /api/v1/sessions/{session_id}` 会话配置。
- Chronos 公开释放记录的 Web API 摘要。
- WebSocket `forum.post`
- WebSocket `market.tape_alert`

### 禁止

- 不允许普通用户直接改 Layer 0 SSOT。
- 不允许把未来 Tick 事实暴露给 Agent。
- 不允许把私有 `thought` 写成官方或谣言轨事件。

## 页面 5：最终判决与漏洞白皮书

### 定位

推演结束后的静态报告页。视觉上像可直接用黑白打印机打印的学术论文、做空机构报告或监管压力测试附件。

### 布局

```text
┌──────────────────────────────────────────────────────────────┐
│ 崩塌概率：87.4%                         2026-05-17 / 演示    │
├──────────────────┬──────────────────────┬───────────────────┤
│ 概述与定性        │ 图表证据              │ 虚拟龙虎榜 / 附录  │
│                  │ 桑基图 / 曲线         │ 表格              │
└──────────────────┴──────────────────────┴───────────────────┘
```

全局规则：

- 全屏白底。
- 不使用动画。
- 可以打印。
- 用经典报纸三列版式。
- 主要内容使用白底黑字和黑色表格线，克莱因蓝只标记关键证据路径。

页眉：

- 左上巨大 Georgia 标题。
- 示例：`崩塌概率：87.4%`
- 右上等宽字体：
  - `session_id`
  - `symbol`
  - `start_tick_id`
  - `end_tick_id`
  - `generated_at`

左栏：概述与定性

- 密集长文。
- 总结压力测试结论。
- 示例：`在第 7 个节拍，散户阵营发生不可逆踩踏。`
- 可使用 Drop Cap，但保持黑白。

中栏：图表证据

- 阵营瓦解路径图。
- 可使用桑基图，但必须保持克制：
  - 背景纯白。
  - 曲线为克莱因蓝或纯黑。
  - 不使用半透明渐变。
  - 节点为硬边矩形或几何圆。

右栏：表格与附录

- 虚拟龙虎榜。
- 智能体风险排行。
- 关键 Tick 列表。
- 只用 1px 黑色表格线。
- 无表头底色，最多用粗线区分表头。

### 数据来源

- REST `GET /api/v1/sessions/{session_id}/snapshot`
- REST `GET /api/v1/sessions/{session_id}/events`
- Web API 可展示事件归档
- WebSocket `audit.causal_chain`
- WebSocket `market.end_of_day`
- WebSocket `agent.account_snapshot` 审计视图

### 禁止

- 不展示原始 COT。
- 不展示 Agent 原始 payload。
- 不展示内部 `UI_Audit`、`Order_Input`、`trade_batch`、`risk_result`。
- 不把报告结论回流 Agent。

## 图谱与曲线规范

### 几何圆节点

允许圆形节点，但必须满足：

- 正圆。
- 纯白填充 + 1px 纯黑描边，或克莱因蓝描边。
- 选中态使用克莱因蓝实心。
- 不使用阴影、渐变、发光、呼吸动画。
- 标签不塞满圆内，使用引线标注。
- 标签格式示例：`[散户乙] 活跃`

### 手术刀贝塞尔曲线

允许曲线，但必须满足：

- 线宽 1px。
- 颜色只用纯黑或克莱因蓝。
- 箭头是尖锐几何三角形。
- 不使用粗线、光束、圆角箭头。
- 曲线交叉可以存在，但必须像粒子轨迹或数学图。

### 行情和信念曲线

- 不使用面积图。
- 不使用默认灰色网格。
- 坐标轴实线默认隐藏。
- 数值标签悬浮，使用等宽字体。
- 多线对比使用实线、虚线、点划线，而不是多彩色系。

### K 线图

推荐传统报纸印法：

- 上涨：白色实体 + 黑色描边。
- 下跌：黑色实心。
- 涨跌停或异常：小面积红色标记。
- 背景纯白。
- 不使用圆角蜡烛、阴影、渐变。

## Web API 对齐

前端页面只能消费 Web API 事件和 REST 响应：

- `market.price`
- `market.tape_alert`
- `market.end_of_day`
- `forum.post`
- `agent.account_snapshot`
- `audit.graph`
- `audit.causal_chain`
- `runtime.tick_state`
- `runtime.agent_lifecycle`
- `system.error`
- REST `POST /api/v1/sessions`
- REST `GET /api/v1/sessions/{session_id}`
- REST `POST /api/v1/sessions/{session_id}/start`
- REST `POST /api/v1/sessions/{session_id}/pause`
- REST `POST /api/v1/sessions/{session_id}/step`
- REST `POST /api/v1/sessions/{session_id}/stop`
- REST `GET /api/v1/sessions/{session_id}/snapshot`
- REST `GET /api/v1/sessions/{session_id}/events`

字段归属：

| 页面需求 | Web API 来源 | 内部来源 |
| :--- | :--- | :--- |
| 行情、盘口聚合 | `market.price`、`snapshot.market` | `Market_Price` |
| 盘口异动和盘后披露 | `market.tape_alert`、`market.end_of_day` | `Tape_Alerts`、`End_of_Day` |
| 公开论坛消息 | `forum.post` | `Forum_Rumors` |
| Agent 资产审计视图 | `agent.account_snapshot`、`snapshot.agents` | `Account_Snapshot` |
| 拓扑图和因果链 | `audit.graph`、`audit.causal_chain`、`snapshot.audit_graph`、`snapshot.causal_chains` | `Frontend_Audit_Graph`、`Frontend_Causal_Chain` |
| 运行状态 | `runtime.tick_state`、`runtime.agent_lifecycle`、会话状态响应 | Meta-Orchestrator `control_only` 状态摘要 |

恢复规则：

- 首次进入运行页时先取 REST `GET /api/v1/sessions/{session_id}/snapshot`，再用 `from_seq=snapshot.last_seq` 连接 WebSocket。
- WebSocket 只发送 `subscribe`、`ack`、`ping` 三类客户端消息。
- 收到 `SNAPSHOT_REQUIRED` 后必须重新获取快照，不读取内部 Redis。

前端禁止：

- 下单。
- 改账。
- 改仓。
- 改冻结股。
- 注入 `thought`。
- 写入 `Forum_Rumors`。
- 读取内部 Redis。
- 读取内部 channel。
- 展示原始 `thought`、Prompt、私有记忆、Agent 原始 payload。

## 未决问题

- 沙盘初始化控制台第一版是否允许创建真实会话，还是只生成本地草稿后交由 API 确认。
- 时间轴剧本管理第一版是否允许保存本地剧本草案；正式写入 Chronos SSOT 必须后置。
- 智能体解剖室是否需要角色权限区分，例如普通演示视图和内部审计视图。
- 漏洞白皮书的崩塌概率由后端计算还是前端只展示后端字段。
- 图谱布局使用固定几何坐标、力导向冻结坐标，还是后端直接返回布局坐标。
