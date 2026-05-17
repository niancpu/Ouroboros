# 2024-10 Ouroboros 历史案例设计草案

用途：把 `2024-10-08` 至 `2024-10-11` 的公开资料映射为 Ouroboros 可用的 Chronos 事件、agent 初始画像、信息等级和图谱边类型草案。本文只作为 source/design 输入，不定义最终剧情，不替代行情库复核。

资料输入：

- [docs/source/2024-10-policy-market-timeline.md](./2024-10-policy-market-timeline.md)：政策冲击、指数与成交、四日市场节奏、硬事实和推断边界。
- [docs/source/2024-10-targets-market-data.md](./2024-10-targets-market-data.md)：创业板 ETF、东方财富、同花顺的日线和部分分时公开资料。
- [docs/source/2024-10-retail-sentiment-personas.md](./2024-10-retail-sentiment-personas.md)：开户热、券商 APP/银证转账压力、散户叙事、论坛情绪等级。
- [docs/source/2024-10-institutional-fund-profiles.md](./2024-10-institutional-fund-profiles.md)：ETF、公募、两融、主力资金、政策型机构和 T+1 约束资料。

## 设计取舍

- 采用“事实事件 + 仿真参数”双层建模。指数、成交额、政策发布、ETF 申赎、融资余额等进入事实层；主体动机、情绪阈值、传播强度、承接能力进入仿真层。
- 不把公开成交额直接解释为某一类主体买入。散户、游资、公募、量化、政策型机构只能作为行为模型，不代表真实账户或真实机构。
- 不把论坛叙事升级为事实。forum_rumor 只能影响情绪传播、误判概率和注意力流向，不能直接写入市场硬状态。
- 不把 `national_team/institution` 设计成无限买盘。SFISF 是流动性互换便利，不是央行直接买股；可建模为“提升符合条件机构流动性与稳定意愿”。来源见 `2024-10-institutional-fund-profiles.md` 的“政策型机构与国家队相关工具”。

## 信息等级草案

| 等级 | 含义 | 可驱动系统模块 | 降权/限制 |
| --- | --- | --- | --- |
| `official_first_hand` | 央行、证监会、交易所、中国结算、中证金融、政府发布会等一手材料，或来源文档中明确引用的一手披露。 | Chronos 硬事件、政策状态、交易规则、融资余额基准。 | 若是事后报告，需标记披露日期和事件日期。 |
| `media_report` | 主流财经媒体对行情、发布会、券商采访、市场现象的报道。 | 市场背景、行为环境、agent 观察输入。 | 对数字口径保留来源，不跨口径相加。 |
| `market_signal` | 指数涨跌、成交额、涨跌家数、涨跌停、ETF/标的 OHLC、主力资金统计等市场数据。 | 行情 tick、风险偏好、流动性、波动率、拥挤度。 | 主力资金、涨跌停家数等需带数据口径。 |
| `institutional_flow` | ETF 申赎、融资融券、龙虎榜机构席位、公募仓位、SFISF 等资金或制度线索。 | mutual_fund、major-fund、quant_algo、national_team/institution 的参数输入。 | 不能等同为真实交易意图；多数是聚合或滞后数据。 |
| `forum_rumor` | 股吧、财富号、Reddit、媒体转述网友吐槽、社群截图式表达。 | forum_rumor、retail_cluster 的语言、情绪传播、FOMO/恐慌开关。 | `verified=false`；不得直接驱动事实判断。 |
| `analyst_inference` | 来源文档中明确标记为市场评论、推断、建模解释的内容。 | 叙事层、假设层、待验证情景分支。 | 必须带 `assumption=true` 或 `inference=true`。 |

建议事件字段：

```yaml
source_evidence:
  level: official_first_hand | media_report | market_signal | institutional_flow | forum_rumor | analyst_inference
  local_doc: docs/source/2024-10-*.md
  origin: url_or_named_source
  confidence: high | medium | low
  fact_status: fact | reported | inferred | assumption
```

## Chronos 事件草案

### 1. 10/8 狂热：节后补涨与交易拥挤

```yaml
chronos_event:
  id: cn_a_2024_10_08_mania_open
  date: 2024-10-08
  phase: open_to_close
  event_type: mania_open
  replay_label: 10/8 狂热
  factual_triggers:
    - 沪指高开 10.13%，深成指高开 12.67%，创业板指高开 18.44%，收盘仍大涨。
    - 沪深两市成交额约 34519.39 亿元，沪深京三市约 34835 亿元。
    - 开盘后约 20 分钟沪深成交额破万亿，约 71 分钟破 2 万亿。
    - Wind 口径全 A 5024 只上涨、816 只涨停。
  market_ticks:
    - 159915.SZ 创业板ETF：涨停开盘、涨停收盘，成交额 474.86 亿元。
    - 300059.SZ 东方财富：20cm 涨停开盘/收盘，成交额 330.78 亿元。
    - 300033.SZ 同花顺：20cm 涨停开盘/收盘，成交额 56.71 亿元。
  agent_effects:
    retail_cluster:
      fomo: very_high
      source_discernment: low
      order_bias: chase_limit_up_or_high_open
    hot_money:
      narrative_push: brokerage_fintech_startup_board_beta
      exit_pressure: medium_high
    mutual_fund:
      etf_subscription_pressure: high
      tracking_liquidity_need: high
    quant_algo:
      volatility_filter: stressed
      liquidity_signal: extreme
  graph_tags:
    - policy_expectation_amplifies_fomo
    - hk_market_gap_maps_to_a_share_open
    - app_congestion_reinforces_mania
  evidence:
    - local_doc: docs/source/2024-10-policy-market-timeline.md
      origin: 每日经济新闻、新浪财经、财联社等行情报道
      level: market_signal
    - local_doc: docs/source/2024-10-targets-market-data.md
      origin: 东方财富 K 线接口、新浪财经
      level: market_signal
    - local_doc: docs/source/2024-10-retail-sentiment-personas.md
      origin: 第一财经、证券时报/界面新闻、财联社
      level: media_report
```

设计说明：10/8 不应只写“上涨日”。它是政策预期、假期香港/中概映射、新开户追涨、券商系统压力、ETF 巨量成交叠加后的流动性拥挤日。对 Chronos 来说，关键不是收盘涨幅，而是“高开买入后日内回落、T+1 无法纠错、次日形成惩罚”的状态转移。

### 2. 10/9 T+1 惩罚：高开追涨资金隔夜暴露

```yaml
chronos_event:
  id: cn_a_2024_10_09_t1_penalty
  date: 2024-10-09
  phase: open_to_close
  event_type: liquidity_stampede
  replay_label: 10/9 T+1 惩罚
  factual_triggers:
    - 上证指数跌 6.62%，深成指跌 8.15%，创业板指跌 10.59%。
    - 沪深两市成交额约 29398 亿元，较 10/8 缩量但仍极高。
    - 约 5000 只股票下跌，超 800 股跌停；东方财富成交额 900.38 亿元。
    - 10/1 至 10/8 提交申请的新开证券账户于 10/9 起可交易。
  market_ticks:
    - 159915.SZ：收跌 16.28%，成交额 385.85 亿元。
    - 300059.SZ：盘中高冲后收涨 2.22%，成交额 900.38 亿元，分歧极端。
    - 300033.SZ：盘中接近 +20% 后收跌 0.42%，成交额 143.04 亿元。
  agent_effects:
    retail_cluster:
      t1_frustration: very_high
      panic: high
      rule_confusion: high_for_new_accounts
    hot_money:
      narrative_shift: from_all_in_to_core_only_or_low_absorb
      distribution_probability: high
    major_fund:
      leverage_addition: still_positive_but_riskier
      stop_loss_pressure: medium_high
    quant_algo:
      gap_risk: high
      forced_deleveraging_signal: medium
  graph_tags:
    - t1_constraint_blocks_same_day_exit
    - forum_loss_story_accelerates_panic
    - limit_down_cluster_reduces_liquidity
  evidence:
    - local_doc: docs/source/2024-10-policy-market-timeline.md
      origin: 每日经济新闻、新浪财经、界面新闻
      level: market_signal
    - local_doc: docs/source/2024-10-retail-sentiment-personas.md
      origin: 经济观察网、新华财经/上海证券报、时代财经/新浪财经
      level: media_report
    - local_doc: docs/source/2024-10-institutional-fund-profiles.md
      origin: 第一财经、上海证券报、中证金融相关数据报道
      level: institutional_flow
```

设计说明：10/9 的核心机制是“前一日高位成交 + 普通股票 T+1 + 新股民首日交易 + 跌停流动性缺口”。它不是简单的均值回归，而是隔夜风险在制度约束下被放大的惩罚日。

### 3. 10/10 分化：指数修复不等于风险解除

```yaml
chronos_event:
  id: cn_a_2024_10_10_divergence
  date: 2024-10-10
  phase: full_day
  event_type: failed_stabilization
  replay_label: 10/10 分化
  factual_triggers:
    - 上证指数涨 1.32%，深成指跌 0.82%，创业板指跌 2.95%。
    - 沪深两市成交额约 21430 亿元；中证网口径 A 股成交额 2.16 万亿元，连续 4 个交易日超 2 万亿元。
    - 市场涨跌家数改善，但高 beta 金融科技和创业板方向继续释放风险。
    - 央行创设 SFISF，首期操作规模 5000 亿元。
  market_ticks:
    - 159915.SZ：收跌 3.03%，成交额 178.12 亿元。
    - 300059.SZ：收跌 17.47%，盘中接近跌停区间，成交额 519.73 亿元。
    - 300033.SZ：收跌 17.44%，金融科技高 beta 退潮。
  agent_effects:
    retail_cluster:
      hesitation: high
      dip_buy_conflict: medium_high
      panic_after_failed_rebound: medium
    mutual_fund:
      broad_based_etf_preference: medium_high
      sector_rotation_pressure: high
    national_team_institution:
      stability_signal: medium
      direct_purchase_assumption: forbidden
    quant_algo:
      dispersion_trade: high
      trend_signal_conflict: high
  graph_tags:
    - index_rebound_masks_sector_drawdown
    - policy_liquidity_tool_supports_stability_expectation
    - fintech_beta_switches_from_leader_to_risk_source
  evidence:
    - local_doc: docs/source/2024-10-policy-market-timeline.md
      origin: 新浪财经、中证网、中国金融信息网
      level: market_signal
    - local_doc: docs/source/2024-10-targets-market-data.md
      origin: 东方财富 K 线接口、新浪财经
      level: market_signal
    - local_doc: docs/source/2024-10-institutional-fund-profiles.md
      origin: 央视网、第一财经、中国经济网
      level: official_first_hand
```

设计说明：10/10 应建模为“分化修复失败”，不是全面企稳。上证指数修复与创业板/金融科技杀跌并存，适合测试 agent 是否会误把指数信号当成全市场安全信号。

### 4. 10/11 退潮：成交下台阶与普跌确认

```yaml
chronos_event:
  id: cn_a_2024_10_11_recede
  date: 2024-10-11
  phase: full_day
  event_type: post_mania_drawdown
  replay_label: 10/11 退潮
  factual_triggers:
    - 上证指数跌 2.55%，深成指跌 3.92%，创业板指跌 5.06%。
    - 沪深两市成交额约 15720 亿元，较上一交易日缩量约 5709-5710 亿元。
    - 新浪财经口径 4862 只股票下跌、442 只个股收红。
    - 两市融资余额较前一交易日减少约 78.09 亿元。
  market_ticks:
    - 159915.SZ：收跌 5.24%，成交额 151.84 亿元。
    - 300059.SZ：低开后收涨 1.46%，成交仍有 301.43 亿元，个股修复不代表整体退潮结束。
    - 300033.SZ：收跌 4.45%，继续回落。
  agent_effects:
    retail_cluster:
      regret: high
      forced_hold_or_cut_loss: high
      new_entry_probability: low_medium
    hot_money:
      attention_decay: high
      rotate_to_policy_or_defensive: medium
    major_fund:
      deleverage_probability: high
      liquidity_demand: high
    mutual_fund:
      redemption_awareness: medium
      etf_flow_cooling: high
  graph_tags:
    - turnover_step_down_confirms_cooling
    - deleveraging_pressure_increases
    - forum_narrative_turns_from_fomo_to_survival
  evidence:
    - local_doc: docs/source/2024-10-policy-market-timeline.md
      origin: 每日经济新闻、新浪财经、甬兴证券策略点评
      level: market_signal
    - local_doc: docs/source/2024-10-targets-market-data.md
      origin: 东方财富 K 线接口
      level: market_signal
    - local_doc: docs/source/2024-10-institutional-fund-profiles.md
      origin: 每日经济新闻融资余额报道、中国基金报/东方财富 ETF 资金报道
      level: institutional_flow
```

设计说明：10/11 是退潮确认，不是流动性枯竭。成交额仍高于常态，但从 3.45 万亿到 1.57 万亿的下台阶说明承接能力明显下降，适合触发 agent 的去杠杆、降低仓位、降低社媒追涨传播强度。

## Agent profile 草案

### `retail_cluster`

```yaml
agent_profile:
  id: retail_cluster
  role: 新开户、休眠账户重启、普通散户集合的仿真群体
  represents_real_entity: false
  initial_state:
    cash_scale: fragmented_small_to_mid
    leverage_access: none_to_margin_account_partial
    rule_literacy: low_to_medium
    source_discernment: low
    fomo_threshold: low
    loss_tolerance: low
    t1_constraint_awareness: uneven
  information_channels:
    - media_report
    - forum_rumor
    - app_push
    - friend_group
    - market_signal_headline
  behavior_rules:
    - 当成交额创新高、券商开户热、港股/中概先涨、政策标题共振时，提高追涨概率。
    - 当买入当日回撤且无法卖出时，提高发帖、抱怨、次日竞价卖出或补仓冲突概率。
    - 对 `forum_rumor` 赋予较高情绪权重，但交易事实判断应由系统层降权。
  calibrating_facts:
    - 国庆期间开户、两融开户、休眠账户激活明显升温。
    - 10/9 是 10/1 至 10/8 新开证券账户可交易首日。
    - 媒体记录新股民对 T+1、板块选择、后市调整存在困惑。
  sources:
    - docs/source/2024-10-retail-sentiment-personas.md: 第一财经、经济观察网、新华财经/上海证券报、羊城晚报、澎湃新闻
```

### `hot_money`

```yaml
agent_profile:
  id: hot_money
  role: 利用情绪和流动性窗口的短线资金仿真体
  represents_real_entity: false
  initial_state:
    cash_scale: mid_to_high_fragmented
    risk_appetite: high
    turnover: very_high
    holding_period_days: 1_to_3
    t1_constraint_awareness: high
    narrative_sensitivity: high
  information_channels:
    - market_signal
    - forum_rumor
    - media_report
    - financing_balance
    - hot_list
  behavior_rules:
    - 10/8 优先推高券商、金融科技、创业板 ETF、半导体等能承接 FOMO 的高弹性方向。
    - 10/9 在巨量分歧中提高换手和兑现概率，并把话术从“全面牛市”切换为“核心辨识度”。
    - 10/10 后降低后排题材暴露，转向防守、低吸或等待政策确认。
  calibrating_facts:
    - 东方财富、同花顺在 10/8 至 10/10 呈现涨停、巨量换手、接近跌停区间的高 beta 路径。
    - 论坛/财富号常见“主线、旗手、踏空资金、分歧转一致”等话术。
  sources:
    - docs/source/2024-10-targets-market-data.md: 东方财富 K 线接口、新浪财经
    - docs/source/2024-10-retail-sentiment-personas.md: hot_money / forum_rumor Chronos 草案
```

### `mutual_fund`

```yaml
agent_profile:
  id: mutual_fund
  role: 公募主动权益、指数基金、ETF 相关行为的仿真集合
  represents_real_entity: false
  initial_state:
    cash_scale: high
    position_bias: high_equity_or_index_tracking
    risk_appetite: medium_to_medium_high
    turnover: medium_for_active_high_for_etf_flow
    contract_constraints: high
    redemption_subscription_pressure: high
  information_channels:
    - official_first_hand
    - institutional_flow
    - market_signal
    - sell_side_research
    - etf_subscription_redemption
  behavior_rules:
    - ETF 子类对申购赎回和跟踪误差敏感，极端行情中被动承接成交。
    - 主动权益基金不应被设为无限追涨；仓位、合同、流动性和相对排名共同约束行为。
    - 创业板、沪深300、科创50/科创芯片方向可设较高关注权重。
  calibrating_facts:
    - 10/8 至 10/11 场内股票型 ETF 净申购金额约 1572.22 亿元，创业板 ETF 净申购金额居前。
    - 主动权益基金 2024Q3 股票仓位约 88.57%，调仓空间不是无限。
    - 部分新基金在市场快速上涨后面临建仓难。
  sources:
    - docs/source/2024-10-institutional-fund-profiles.md: 东方财富研究中心、中国基金报、开源证券、经济观察网
```

### `quant_algo`

```yaml
agent_profile:
  id: quant_algo
  role: 高成交、高波动环境下的量化/程序化策略仿真体
  represents_real_entity: false
  initial_state:
    cash_scale: medium_to_high
    risk_appetite: medium_high_with_strong_risk_control
    turnover: high
    liquidity_filter: strict
    volatility_limit: strict
    t1_constraint_awareness: high
  information_channels:
    - tick_or_bar_market_signal
    - order_book_proxy
    - etf_premium_discount
    - financing_balance
    - delayed_northbound_activity
    - news_event_flag
  behavior_rules:
    - 对极端成交额提高参与权重，但对跳空、跌停、T+1 和波动率上限提高风险折扣。
    - 对“主力资金”统计降权，因为来源文档显示不同口径可冲突。
    - 2024-08-19 后不使用旧口径实时北向净买入信号，只能使用成交总额、活跃股或滞后持仓估计。
  calibrating_facts:
    - 10/8 至 10/11 连续高成交和剧烈波动为量化策略提供流动性，但 10/9、10/11 的隔夜跳空和跌停集群提高尾部风险。
    - 北向资金披露机制已调整，实时净买入口径不可沿用。
  sources:
    - docs/source/2024-10-institutional-fund-profiles.md: 主力资金口径差异、沪深港通披露机制调整、T+1 规则
```

### `national_team/institution`

```yaml
agent_profile:
  id: national_team_institution
  role: 政策型稳定力量和大型合规机构的抽象仿真体
  represents_real_entity: false
  initial_state:
    cash_scale: very_high_but_constrained
    risk_appetite: stability_oriented
    turnover: low_to_medium
    target_preference:
      - broad_based_etf
      - csi300_components
      - high_liquidity_blue_chips
    direct_rescue_all_assets: false
  information_channels:
    - official_first_hand
    - policy_window
    - institutional_flow
    - broad_index_liquidity
    - systemic_risk_metric
  behavior_rules:
    - 可在政策窗口增强稳定预期和流动性支持，但不得被模拟为无条件买入所有股票。
    - 对小盘题材股、论坛热股、单一金融科技高 beta 标的设置低直接偏好。
    - SFISF 的影响先进入“机构流动性改善”和“风险承受力改善”，不直接生成央行买股订单。
  calibrating_facts:
    - 10/10 央行创设 SFISF，首期 5000 亿元，抵押品包括债券、股票 ETF、沪深300成分股等。
    - 来源文档明确该工具不是央行直接买股。
  sources:
    - docs/source/2024-10-institutional-fund-profiles.md: 央视网、第一财经、中国经济网关于 SFISF 的报道
```

## Graph edge 语义草案

### 节点类型

```yaml
node_types:
  policy_event: 政策、发布会、监管工具、会议表述
  market_index: 上证指数、深成指、创业板指等指数状态
  tradable_asset: ETF、股票、行业板块、风格篮子
  agent_cluster: retail_cluster、hot_money、mutual_fund、quant_algo、national_team_institution
  information_item: 新闻、公告、论坛帖、资金流统计、行情 tick
  constraint: T+1、涨跌停、融资保证金、披露制度断点
  liquidity_state: 成交额、涨跌停家数、ETF 申赎、融资余额、成交拥挤度
```

### 边类型

| edge_type | 方向 | 语义 | 典型来源等级 | 例子 |
| --- | --- | --- | --- | --- |
| `anchors_expectation` | `policy_event -> agent_cluster` | 政策或会议表述提高主体对风险资产的预期。 | official_first_hand / media_report | 9/26 政治局会议“提振资本市场”提高 retail 和 mutual_fund 的乐观预期。 |
| `amplifies_fomo` | `information_item -> agent_cluster` | 信息刺激追涨、开户、加仓、踏空焦虑。 | media_report / forum_rumor | “券商开户排队”“节后开门红”增强 retail_cluster FOMO。 |
| `raises_attention` | `market_signal -> tradable_asset` | 成交额、涨停、热榜提高某资产关注度。 | market_signal | 东方财富 10/8 涨停与巨量成交提高金融科技关注。 |
| `transmits_risk_appetite` | `tradable_asset -> agent_cluster` | 宽基或高 beta 标的表现影响主体风险偏好。 | market_signal | 创业板 ETF 10/8 涨停提高风险偏好，10/9 大跌触发恐慌。 |
| `creates_liquidity_pressure` | `agent_cluster -> liquidity_state` | 群体下单、赎回、融资、止损改变成交和流动性。 | institutional_flow / market_signal | 两融余额 10/8、10/9 增加，随后 10/11 回落。 |
| `constrains_action` | `constraint -> agent_cluster` | 制度约束限制 agent 可选动作。 | official_first_hand | T+1 使 10/8 追入的普通股票买方无法当日卖出。 |
| `blocks_exit` | `constraint -> tradable_asset` | 跌停、T+1、流动性枯竭限制退出。 | market_signal / official_first_hand | 10/9 超 800 股跌停降低止损成交概率。 |
| `validates_or_refutes` | `market_signal -> information_item` | 后续行情验证或削弱先前叙事。 | market_signal | 10/9 普跌削弱“无脑牛市”叙事，强化“交学费”叙事。 |
| `stabilizes_expectation` | `policy_event -> liquidity_state` | 政策工具改善流动性预期或风险承受能力。 | official_first_hand | SFISF 改善机构流动性预期，但不等于直接买股。 |
| `causes_narrative_shift` | `market_signal -> information_item` | 市场变化促使论坛/媒体叙事切换。 | media_report / forum_rumor | 10/8 “跑步入场”切到 10/9 “T+1 不能卖”。 |
| `口径冲突` | `information_item -> information_item` | 两个数据源描述同一概念但统计口径不同。 | media_report / institutional_flow | 股票 ETF 10/8 净流入 1017.98 亿与 1093.94 亿口径并存。 |

### 边字段建议

```yaml
graph_edge:
  from: node_id
  to: node_id
  edge_type: string
  direction: positive | negative | mixed
  strength: 0.0_to_1.0
  lag: intraday | t_plus_1 | multi_day | delayed_disclosure
  evidence_level: official_first_hand | media_report | market_signal | institutional_flow | forum_rumor | analyst_inference
  fact_status: fact | reported | inferred | assumption
  local_doc: docs/source/2024-10-*.md
  source_note: string
  simulation_only: boolean
```

## 四日回放结构

| 日期 | 回放阶段 | 事实锚点 | 系统状态 | Agent 行为重点 |
| --- | --- | --- | --- | --- |
| 2024-10-08 | 狂热 | 三大指数大涨，沪深成交约 3.45 万亿，创业板/金融科技高 beta 标的涨停或巨量成交。 | `mania=true`，`liquidity=extreme`，`fomo=extreme`，`slippage=high`。 | retail 追涨；hot_money 推动和分发；ETF 被动承接；quant 提高风控。 |
| 2024-10-09 | T+1 惩罚 | 三大指数大跌，超 5000 股下跌，超 800 股跌停，新开户首日交易叙事出现。 | `panic=high`，`exit_blocked=true`，`limit_down_cluster=true`。 | retail 因 T+1 恐慌；hot_money 分歧兑现；融资仍有增量但风险升高。 |
| 2024-10-10 | 分化 | 上证涨、深成指/创业板跌，成交继续缩量但仍超 2 万亿，SFISF 发布。 | `divergence=high`，`index_signal_conflict=true`，`policy_stability_signal=medium`。 | mutual_fund 偏宽基；national_team/institution 提供稳定预期；quant 做分化过滤。 |
| 2024-10-11 | 退潮 | 三大指数再跌，成交降至约 1.57 万亿，普跌，融资余额回落。 | `cooling=true`，`deleveraging=true`，`attention_decay=high`。 | retail 犹豫/止损；major-fund 去杠杆；forum 从 FOMO 转为亏损与求生叙事。 |

## 事实/假设边界

### 可以作为事实层输入

- 9/24、9/26、10/8、10/10 等政策、会议和发布会事件，以及其正式表述。来源：`2024-10-policy-market-timeline.md`、`2024-10-institutional-fund-profiles.md`。
- 10/8 至 10/11 的指数涨跌、成交额、涨跌家数、涨跌停家数、标的 OHLC 和成交额。来源：`2024-10-policy-market-timeline.md`、`2024-10-targets-market-data.md`。
- 10/8 至 10/11 ETF 申赎、融资余额变化、部分主力资金和龙虎榜统计，但需保留统计口径。来源：`2024-10-institutional-fund-profiles.md`。
- 国庆开户热、券商 APP/银证转账压力、新股民困惑等主流媒体采访描述。来源：`2024-10-retail-sentiment-personas.md`。
- T+1 规则、北向资金披露机制调整、SFISF 工具性质。来源：`2024-10-institutional-fund-profiles.md`。

### 只能作为仿真假设

- `retail_cluster` 的年龄结构、风险阈值、FOMO 强度、规则理解弱等参数，只能由媒体样本映射，不代表真实全体散户。
- `hot_money` 的推高、兑现、话术切换是行为模型，不代表某个真实席位或账户。
- `mutual_fund` 的申赎压力、建仓难、宽基偏好是公开资金流到仿真参数的映射，不等于单只基金真实买卖。
- `quant_algo` 的风控、流动性过滤、对冲行为是策略假设，公开资料没有给出私有量化模型。
- `national_team/institution` 的稳定倾向来自政策工具和市场角色抽象，不得写成“国家队在某日买入某股”。
- 10/8 发改委发布会与盘中回落之间的因果强度只能作为 `analyst_inference`，不能作为硬事实。

### 不应采用的表述

- 不写“3.45 万亿全市场成交额”。应写“沪深两市约 3.45 万亿元；沪深京三市约 3.48 万亿元”。
- 不写“交易所宕机”。来源文档只支持券商 APP、银证转账、银行端或流量控制等压力描述。
- 不写“散户主导全部买入”“机构全部出货”“国家队托底所有股票”。公开资料无法支持这些结论。
- 不把股吧、Reddit、财富号留言当作事实，只能作为 forum_rumor 语言和情绪样本。
- 不混用 ETF 净流入口径、主力资金口径、沪深/沪深京成交额口径。

## 未确认点

- 缺少交易所逐笔、分钟 K、盘口封单数据；`159915`、`300059`、`300033` 的“涨停打开/炸板”只能从日线 OHLC 和部分公开分时报道推断，不能确认具体次数和封单金额。
- 新开户数量、年轻投资者占比、行业累计开户需求多数来自媒体转述或券商人士估计，未取得统一官方日度数据。
- 10/8 发改委发布会与盘中回落的因果关系需要分钟行情、新闻时点和舆情数据复核。
- 主力资金、ETF 流、北向资金均存在口径或披露制度差异，后续实现必须在数据 schema 中保留 `source_scope`。
- 融资资金能确认杠杆余额变化，但不能识别融资账户身份；不要把融资余额直接映射为散户、机构或游资单一主体。
