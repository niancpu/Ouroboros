

---

### 一、 API 熔断与 RPM 爆炸的“高情商工程解法”

阵营划分（24个全量 LLM 驱动节点）：
游资大佬 (Hot Money) x 2：极度短视，动量驱动。提示词注入：“你只看情绪和盘面，喜欢在涨停板（Limit Up）上打板确认，不看基本面。你的目标是吸引散户接盘。”
公募机构 (Mutual Funds) x 2：看重基本面和研报，受合规限制。提示词注入：“你有严格的止损线，偏好左侧建仓，对‘小作文’免疫，只信官方财报（Fact-ID: Official）。”
量化游资 (Quant Algos) x 2：由 LLM 模拟的机器行为。提示词注入：“如果价格连续 3 个 Tick 下跌且跌破均线，你将无条件触发抛售。”
散户群体 (Retail Swarm) x 16：A股的核心燃料。提示词注入：“你极易受情绪感染（FOMO），极度厌恶损失。一旦价格逼近跌停（Limit Down），你会恐慌性抛售。你每天高强度刷雪球和股吧。”
国家队/平准基金 (National Team) x 2：隐藏 Boss。提示词注入：“当大盘或标的出现非理性暴跌（如单日跌幅>15%），你才下场注入流动性，不以盈利为目的。”

防止 24 个 Agent 瞬间并发导致 `429 Too Many Requests` 的核心策略是：**用金融逻辑解决工程问题（逻辑错峰 + 路由负载）**。

1.  **架构级错峰：信息级联 (Information Cascade)**
    *   **Tick 内部分层**：真实的 A 股是存在**“信息获取时差”**的。
        *   **T+0**: 2 个量化/公募 Agent 接收官方 API 资讯，发起 API 请求
        *   **T+1**: 2个游资大佬 Agent 观测到盘面异动或公募动作，发起 API 请求思考，并在黑板（股吧）生成“小作文”
        *   **T+3**: 16 个散户 Agent 才看到游资的“小作文”。
2.  **网关级负载：LiteLLM 多租户路由池**
    *   不要把请求砸向单一的 OpenAI API Key。
    *   部署 **LiteLLM Proxy Server**，后端挂载 3-5 个不同的 API 渠道（例如：2 个 Azure OpenAI 实例，2 个 Anthropic 官方 API，1 个 AWS Bedrock 实例）。
    *   LiteLLM 会自动进行 RPM 监控和轮询负载均衡（Round-Robin Load Balancing），彻底吃下所有的瞬发算力需求。

---

### 二、 Ouroboros 核心五层架构设计

#### 【Control Plane: Meta-Orchestrator 元编排器】
*   **职责**：推进全局 Tick、管理 Agent 生命周期、执行并发屏障、切割 Agent 返回体、驱动 Layer 0/Layer 3/Referee。
*   **控制边界**：Meta-Orchestrator 拥有最高调度权，但不参与金融逻辑计算，不生成市场信号，不把任意 Agent 的私有 payload 写入公共 Redis 总线。
*   **隔离法则**：Meta-Orchestrator 可以收集完整 Agent 返回体用于路由，但必须将 `action` 送往 Layer 3，将 `thought`/`belief_shift` 送往 UI 审计链路；不得把 Agent A 的私有字段放入 Agent B 的输入。
*   **时钟权威**：系统时间轴只能由 Meta-Orchestrator 推进。Layer 0、Layer 1、Layer 2、Layer 3、Layer 4 均不得自行推进 Tick。
*   详细设计见 `docs/Arch/meta_orchestrator.md`，Tick 生命周期契约见 `docs/internal_contracts/tick_lifecycle.md`。

#### 【Layer 0: Chronos 历史时间轴与事实底座】
*   **职责**：提供100%真实的外部刺激，杜绝系统性幻觉。
*   **数据归属**：Layer 0 是 `Chronos Data` 的唯一真理源，负责按 Tick 时间释放历史事实；Agent 不得一次性读取全量历史。
*   **组件**：
    *   **时间轴数据源**：提供历史真实时间戳步长（如 5分钟/Tick）；只响应 Meta-Orchestrator 的释放指令，不自行推进系统 Tick。
    *   **双轨数据泵**：
        *   *官方轨*：注入当时的真实新闻、财报、宏观数据。
        *   *量价轨*：注入真实的初始 LOB（订单薄）深度、昨收盘价、真实龙虎榜数据。
    *   **向量记忆库 (Milvus)**：存储该股票过去 5 年的重大历史事件。Agent 在推理前，通过 RAG 检索“历史相似 K 线与事件”，增加推理深度。

#### 【Layer 1: 异构智能体矩阵 (高质量 API 驱动)】
*   **职责**：维护 24+ 个 Agent 的内部状态机与私有 Prompt。
*   **数据隔离法则**：Agent 输出必须拆分为 `thought` 与 `action` 两类字段。`thought` 属于私有审计材料，只能进入 UI 审计链路；`action` 是唯一允许影响市场的输出，只能通过订单输入通道进入 Layer 3。
*   **状态边界**：Agent 逻辑拥有自己的认知状态和私有记忆；资金、持仓、可卖数量只允许保存 Layer 3 推送的只读副本，Agent 不得自行改写资产状态。
*   **机构级 Agent (Smart Money)**：
    *   *模型分配*：用擅长长文本深度逻辑、代码与财报解析
    *   *特征*：拥有“大局观” Prompt，输出私有推理摘要、信念分、证据引用和交易动作；私有推理不得回流公共总线。
*   **散户/跟风 Agent (Dumb Money)**：
    *   *模型分配*：用较弱的
    *   *特征*：Prompt 注入极强的“损失厌恶”、“FOMO 情绪”。不看财报，只看盘面红绿和大 V 言论。
*   **微观结构维持者 (量化套利 Agent)**：纯 Python 脚本（不调大模型），基于 $\tanh$ 极值触发，专门在涨跌停板提供对手盘流动性。

#### 【Layer 2: 异步信息流沙盒 (Asynchronous Pub/Sub Sandbox)】
解决 20+ Agent 广播风暴的唯一解是引入**“黑板模式（Blackboard System）”**，模拟 A 股的资讯环境。
Layer 2 只负责按权限转发事件，不拥有资金、持仓、订单簿、历史事实或 Agent 私有记忆。
双轨信息池（The Dual-Track Feed）：
官方公告板 (Wind/CSRC)：只有高质量 Fact-ID（财报发布、监管函），公募和量化赋予极高权重。
谣言股吧 (Xueqiu/Eastmoney)：游资 Agent 故意生成的“小作文”（未经证实的利好/利空），散户 Agent 的主要信息源。
Referee 裁判节点（权限降级后）：
裁判节点不得监听并广播 Agent 私有 `thought`，不得把机构意图、未公开订单理由或私有记忆浓缩成公共信号。
将原裁判拆为两个物理隔离实体：**交易所数据播报员** 与 **UI 渲染审查官**。
交易所数据播报员只读取 Layer 3 撮合引擎的匿名物理输出，向 Agent 广播盘口异动、价格、盘后龙虎榜等市场可见信息。
UI 渲染审查官可以读取 Agent 私有 `thought` 与 `belief_shift`，但输出只能单向进入前端可视化通道，绝对不得回流给任何 Agent。
详细边界见 `docs/Arch/referee_design.md`，Redis 频道路由见 `docs/internal_contracts/channel_routing.md`。

#### 【Layer 3: A股特色反身性清算引擎 (核心量化层)】

*   **职责**：将 LLM 的文本情绪转化为绝对的数学执行。
*   **平滑信念更新方程 (引入 $\tanh$ 激活)**：
    $$ C_t = (1 - \lambda) \cdot C_{t-1} + \lambda \cdot \tanh\left( \alpha \cdot LLM\_Score + \beta \cdot f(\Delta Price) \right) $$
*   **交易指令映射**：基于 $C_t$ 和 T+1 真实可用资金，生成 Limit Order（限价单）。
*   **LOB 撮合机 (Limit Order Book)**：
    *   价格优先、时间优先撮合。
    *   **硬性物理约束**：$\pm 10\%$ 涨跌停板直接拒绝越界报价；如果某一方流动性耗尽，产生“无量一字板”，系统自动将“涨停板状态”通过 Layer 2 广播，触发反身性高潮。
*   **资产 SSOT**：Layer 3 是 `Ledger`、`Positions`、`frozen_shares` 与 `LOB` 的唯一真理源。Agent 只能提交订单，成交、扣款、持仓变更、T+1 冻结和账户快照均由 Layer 3 统一维护。
*   **订单簿隔离**：Agent 不得直接读取底层 LOB。交易所数据播报员只能基于 LOB 生成合规 Level-2 快照和匿名盘口异动广播。

#### 【Layer 4: 流式可视化与研报输出】
*   **职责**：向评委/客户展示极具震撼力的视觉与风控数据。
*   **前端赛博华尔街 (WebSockets + ECharts)**：
    *   实时渲染 24 个节点的**力导向图 (Force-Directed Graph)**。
    *   节点颜色随 $C_t$ 实时渐变（深红至深绿），节点大小代表实时持仓市值。
    *   屏幕侧边栏只展示经过脱敏的公开理由、证据引用、信念变化和拓扑影响；不得展示核心机构 Agent 的私有 COT。
*   **《反身性压力测试白皮书》生成器**：
    *   推演结束后，汇总所有 Tick 数据，生成 PDF。包含“阵营瓦解时序图”、“叙事承压极限点位”以及虚拟龙虎榜。

---

### 三、 推荐技术选型表 (Technology Stack)

为了确保架构的高并发、高稳定性与极佳的演示效果，建议严格按照以下现代栈进行开发：

| 模块类别           | 推荐技术/框架              | 选择理由 / 优势                                              |
| :----------------- | :------------------------- | :----------------------------------------------------------- |
| **控制编排层**   | **LangGraph** (Python)     | 支持循环图（Cyclic Graphs）和状态机（State Machine），适合作为 Meta-Orchestrator 的 Tick 状态机与容错重试骨架。 |
| **API 路由与限流** | **LiteLLM Proxy** + Redis  | 能够统一定义 OpenAI/Anthropic 接口，多 API Keys 轮询，自带 RPM/TPM 队列控制，完美解决 API 并发爆炸问题。 |
| **并发与异步**     | `asyncio` + `FastAPI`      | Python 的异步 IO 是处理高频 API 请求的唯一解，FastAPI 能极快地提供 WebSocket 接口给前端。 |
| **状态/事件总线**  | **Redis** (Pub/Sub & JSON) | 极速的内存级读写。Pub/Sub 用于 Layer 2 的黑板信息广播；RedisJSON 仅缓存 Layer 3 推送的只读账户快照，不作为资金与持仓 SSOT。 |
| **向量记忆库**     | **Milvus** (或 Qdrant)     | 云原生的高性能向量数据库，用于 Layer 0 存储股票的历史相似事件与 K 线形态，供机构 Agent RAG 检索。 |
| **撮合引擎引擎**   | 自研 Python 脚本 (`heapq`) | 不需要上 C++。用 Python 内置的优先队列维护买卖限价单薄（LOB）即可，加入 A 股 T+1 和 $\pm10\%$ 熔断逻辑，轻量且极度可控。 |
| **前端图谱渲染**   | **ECharts** (Graph 关系图) | 渲染 100 个节点以内的力导向图极其丝滑，支持节点颜色渐变、动态连线效果（Edge moving dots），演示视觉冲击力极强。 |
| **实时通信通道**   | **WebSockets**             | 保持后端推演引擎与前端 UI 的长连接。后端每撮合完一个 Tick，直接 PUSH 最新盘面价格和拓扑图谱的 JSON 到前端，实现丝滑动画。 |

---

### 四、 数据归属与唯一真理源

系统核心数据归属见 `docs/internal_contracts/state_ownership.md`。

五个数据中心：

1. **控制中心**（Control Plane）：Meta-Orchestrator 拥有 Tick 推进、生命周期管理和路由切割权。
2. **资产中心**（Layer 3）：拥有 `Ledger`、`Positions`、`frozen_shares` 和 `LOB`，负责资金、筹码、订单的绝对结算。
3. **事实中心**（Layer 0）：拥有 `Chronos Data`，负责客观历史事实的时间释放。
4. **认知中心**（Layer 1 Agent 本地）：拥有 `Private Memory` 和认知状态，只持有资产只读副本。
5. **广播中心**（Layer 2 Redis 总线）：不拥有业务数据，只按权限频道传递事件。

