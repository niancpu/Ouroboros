# 2024-10 信息等级分层证据资料

用途：为 2024-09-24 至 2024-10-11 A 股政策行情案例提供信息源分层证据。本文只做资料搜集和候选标签整理，不做架构决策，不定义长期状态归属。

候选来源标签：`official_first_hand`、`exchange_notice`、`market_data`、`mainstream_media`、`broker_view`、`forum_rumor/social_sentiment`。

## 口径说明

- 时间窗口：2024-09-24 至 2024-10-11。若 10 月 12 日财政部发布会被提及，只作为 10 月 9-11 日期间市场预期的外部信息，不把 10 月 12 日内容计入本窗口事实。
- “延迟”指信息从真实事件发生到普通市场参与者可见的大致时间差，不是系统技术延迟。
- “可信度”只评价事实源可靠性，不评价政策效果、行情方向预测是否正确。
- 股吧、财富号、Reddit、微博转述、朋友圈截图、媒体引用网民留言均按低可信情绪样本处理，不作为行情或政策事实。
- 成交额口径必须区分：沪深两市、沪深京/北三市、同花顺全 A、交易所单市场成交额不能混算。

## 信息等级表

| 候选标签 | 典型来源 | 可见延迟 | 可信度 | 可用于 belief 的内容 | 主要风险 |
| --- | --- | --- | --- | --- | --- |
| `official_first_hand` | 国新办、中国政府网、央行、证监会、发改委、财政部 | 实时到数小时；正式公告可晚于发布会 | 高 | 政策是否真实存在、工具规模、发布主体、监管态度 | 不能直接推出市场效果；发布会措辞常被二次解读放大 |
| `exchange_notice` | 上交所、深交所、中国结算、交易所技术通知 | 数小时到 1 日 | 高 | 交易/开户/测试/指定交易等制度和运维事实 | 不等于市场方向信号；有些原公告后续废止或迁移 |
| `market_data` | 交易所行情、东方财富/同花顺/Wind/iFinD、主流媒体引用行情 | 实时到收盘后数分钟 | 高到中 | 指数、成交额、涨跌家数、涨跌停、个股/ETF OHLC | 第三方口径可能不同；盘中数据需保留时间戳 |
| `mainstream_media` | 新华社、上海证券报、证券时报、每日经济新闻、界面、澎湃、财联社、新浪转载 | 分钟到数小时 | 中到高 | 市场状态概括、采访、系统拥堵、开户热、券商营业部现场 | 标题会强化情绪；采访和估计需降权 |
| `broker_view` | 中金、国泰君安、招商、中信建投、天风等研报/晨会 | 数小时到数日 | 中 | 机构解释框架、配置建议、风险提示、行情持续性判断 | 观点不是事实；容易形成追涨/踏空叙事 |
| `forum_rumor/social_sentiment` | 东方财富财富号/股吧、雪球、微博、Reddit、媒体转述网民留言 | 实时到数小时 | 低 | FOMO、踏空、被套、T+1 困惑、系统卡顿归因、谣言传播 | 匿名、样本偏差、夸张表达；只能作为情绪输入 |

## 关键事件信息源链

### 2024-09-24：金融政策组合拳发布

| 时间 | 来源等级 | 来源 | 关键事实/信息 | 延迟 | 对 belief 的可能影响 |
| --- | --- | --- | --- | --- | --- |
| 上午 | `official_first_hand` | 中国政府网/国新办：[国务院新闻办举行发布会 介绍金融支持经济高质量发展有关情况](https://www.gov.cn/lianbo/fabu/202409/content_6976186.htm) | 央行、金融监管总局、证监会负责人介绍金融支持经济高质量发展举措；涉及降准、降息、存量房贷、资本市场支持工具、中长期资金等。 | 实时/当日 | 政策可信度直接上升；“政策底/监管支持资本市场”belief 增强。 |
| 2024-09-24 | `official_first_hand` | 证监会：[《关于深化上市公司并购重组市场改革的意见》](https://www.csrc.gov.cn/csrc/c100028/c7508366/content.shtml) | 证监会当日发布“并购六条”，支持上市公司向新质生产力方向转型升级、鼓励产业整合、提高监管包容度等。 | 当日 | 对并购重组、央国企、科技资产注入等主题 belief 增强。 |
| 15:02 | `mainstream_media` + `market_data` | 界面新闻/新浪财经：[沪指涨 4.15%，两市成交额 9713 亿元](https://finance.sina.com.cn/jjxw/2024-09-24/doc-incqfwyt1295722.shtml) | 上证指数涨 4.15%，深成指涨 4.36%，创业板指涨 5.54%；两市成交额 9713 亿元，5167 股上涨。 | 收盘后分钟级 | “政策即时有效/增量资金进场”belief 上升；散户 FOMO 开始发酵。 |
| 2024-09-24 | `broker_view` | 国泰君安策略快评转存：[9.24 金融政策组合拳下的投资策略分析](https://www.fxbaogao.com/detail/4516720) | 观点称政策组合拳有助于推动无风险利率下降与短期风险评价下调，推动股指阶段性反弹；重点在低估值蓝筹。 | 当日/次日传播 | 机构 agent 可能提高低估值蓝筹、破净央国企、非银等方向权重；但这是观点不是事实。 |

### 2024-09-26 至 2024-09-27：政策背书与落地细则

| 时间 | 来源等级 | 来源 | 关键事实/信息 | 延迟 | 对 belief 的可能影响 |
| --- | --- | --- | --- | --- | --- |
| 2024-09-26 | `official_first_hand` | 证监会：[中央金融办、中国证监会联合印发《关于推动中长期资金入市的指导意见》](https://www.csrc.gov.cn/csrc/c100028/c7508981/content.shtml) | 明确落实 9 月 26 日中央政治局会议部署，引导中长期资金入市，打通社保、保险、理财等资金入市堵点。 | 当日 | “长钱入市”可信度上升；中长期资金 agent 的买盘预期增强。 |
| 2024-09-27 08:00 | `official_first_hand` | 中国人民银行：[下调金融机构存款准备金率](https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/2025092212554238383/index.html) | 自 2024-09-27 起下调金融机构存款准备金率 0.5 个百分点；下调后加权平均存款准备金率约 6.6%。 | 公告即刻 | 货币宽松从发布会预期转为落地事实；提高流动性宽松 belief。 |
| 2024-09-27 | `mainstream_media` + `broker_view` | 中证网/经济参考报：[政策组合拳提振信心，A股估值有望迎修复](https://www.cs.com.cn/xwzx/hg/202409/t20240927_6442714.html) | 媒体综合政策与券商观点，称流动性面临反转过程，政策落地进展将影响行情节奏。 | 1-3 日 | 机构/媒体 agent 形成“估值修复”叙事；需和官方事实区分。 |

### 2024-09-30：节前交易狂热和成交纪录

| 时间 | 来源等级 | 来源 | 关键事实/信息 | 延迟 | 对 belief 的可能影响 |
| --- | --- | --- | --- | --- | --- |
| 15:42 | `mainstream_media` + `market_data` | 每日经济新闻/新浪财经：[沪指涨 8.06%，成交 2.59 万亿元](https://finance.sina.com.cn/roll/2024-09-30/doc-incqxmqu2903371.shtml) | 开盘后 35 分钟沪深两市成交额突破 1 万亿元；收盘沪指涨 8.06%，深成指涨 10.67%，创业板指涨 15.36%，沪深两市成交额超 2.59 万亿元。 | 收盘后分钟级 | “成交额破纪录/行情已启动”belief 大幅增强；踏空焦虑显著上升。 |
| 2024-10-01 至 10-07 | `forum_rumor/social_sentiment` | Reddit 转述 VOA：[A 股国庆前创成交纪录](https://www.reddit.com/r/4832/comments/1ftt4eh)；Reddit 转述 BBC：[中国经济刺激组合拳](https://www.reddit.com/r/LiberalGooseGroup/comments/1fus2qy) | 海外中文社区转述“救市”“牛市”“短期奏效”等叙事。 | 1 日到数日 | 海外/社媒 agent 可见市场情绪扩散；不能作为政策事实源。 |

### 2024-10-06 至 2024-10-07：交易和开户基础设施准备

| 时间 | 来源等级 | 来源 | 关键事实/信息 | 延迟 | 对 belief 的可能影响 |
| --- | --- | --- | --- | --- | --- |
| 2024-09-26 发布，10-07 测试 | `exchange_notice` | 深交所：[关于 2024 年 10 月 7 日开展深市交易系统连通性测试的通知](https://www.szse.cn/marketServices/technicalservice/notice/t20240926_609627.html) | 深交所定于 2024-10-07 提供深市交易系统连通性测试环境，检验长假后技术系统准备情况。 | 提前 11 日公告 | 运维/交易通道 agent 可见“节后交易压力准备”信号；不代表行情方向。 |
| 2024-10-06 | `exchange_notice` | 上交所后续通知提及已废止文件：[2024-10-06《延长接受指定交易申报指令时间的通知》](https://www.sse.com.cn/lawandrules/guide/stock/jyglywznylc/zn/c/c_20250523_10779856.shtml) | 上交所 2025 年指南通知明确 2024-10-06 曾发布上证函〔2024〕2639 号，后于 2025-06-23 废止。原文链接需另查。 | 当日；现仅能间接确认 | 可作为上交所为开户/指定交易处理做临时安排的证据；因原公告未定位，标为“间接确认”。 |
| 2024-10-07 | `mainstream_media` + `exchange_notice` | 新华财经/中国金融信息网：[中国结算恢复统一账户平台并延长开户身份复核时间](https://www.cnfin.com/yw-lb/detail/20241007/4114730_1.html) | 报道称中国结算 10 月 7 日恢复开放统一账户平台和身份信息核查系统等渠道权限，支持网上开户审核；10 月 1-8 日提交的新开证券账户，10 月 9 日起可用于交易。 | 当日 | 对新股民 agent 可见性很高；解释 10 月 9 日“新开户首日交易”现象。 |

### 2024-10-08：节后首日极端高开、天量成交、政策发布会承接预期

| 时间 | 来源等级 | 来源 | 关键事实/信息 | 延迟 | 对 belief 的可能影响 |
| --- | --- | --- | --- | --- | --- |
| 09:30 | `market_data` + `mainstream_media` | 每日经济新闻：[三大指数节后首日大幅高开](https://www.nbd.com.cn/articles/2024-10-08/3580175.html) | 沪指高开 10.13%，深成指高开 12.67%，创业板指高开 18.44%。同文汇总券商晨会和中金观点。 | 分钟级 | FOMO 极强；追涨 agent 认为“买不到/不能踏空”；风险控制 agent 看到开盘即透支。 |
| 10:00 | `official_first_hand` | 中国政府网/国新办：[推动经济持续回升向好，我国加力推出一揽子增量政策](https://www.gov.cn/lianbo/bumen/202410/content_6978753.htm)；国家发改委图文：[新闻发布会 | 介绍“系统落实一揽子增量政策 扎实推动经济向上结构向优、发展态势持续向好”有关情况](https://www.ndrc.gov.cn/fzggw/wld/zb/zyhd/202410/t20241008_1393508_ext.html) | 发改委介绍围绕逆周期调节、扩大需求、助企帮扶、房地产止跌回稳、提振资本市场等五方面加力推出增量政策。 | 实时/当日 | 官方政策链继续延伸；若市场预期更高，媒体/论坛可能产生“低于预期”解释。 |
| 15:00 后 | `market_data` + `mainstream_media` | 每日经济新闻：[成交 3.4835 万亿元创纪录](https://www.nbd.com.cn/articles/2024-10-08/3582077.html) | 沪指收 3489.78 点涨 4.59%，深成指涨 9.17%，创业板指涨 17.25%；同花顺全 A 口径成交 3.4835 万亿元；超过 1700 只个股涨超 10%。 | 收盘后分钟级 | “牛市确认/成交额确认”belief 达峰；也暴露高位震荡和系统拥堵风险。 |
| 2024-10-08 | `mainstream_media` | 每日经济新闻同文；财联社/证券时报关于券商 App、银证转账拥堵报道见本仓库既有资料 | 多家券商 App 卡顿、银证转账不顺畅、成交激增。 | 当日 | 对 retail agent 形成“买不进去/转不进钱/系统出问题”感知；事实可信度中等，具体故障归因需谨慎。 |
| 2024-10-08 | `broker_view` | 每经：[券商晨会精选](https://www.nbd.com.cn/articles/2024-10-08/3579983.html)；新浪：[中金称节后 A 股短线上行趋势有望延续](https://finance.sina.com.cn/roll/2024-10-08/doc-incruvpi0722950.shtml) | 券商观点中出现“信心重估牛”“节后短线上行趋势有望延续”“中期大底条件仍在完善”等判断。 | 开盘前到当日 | 机构观点强化追涨和配置叙事；同时中金保留“大底条件仍在完善”约束，可降低盲目乐观权重。 |
| 2024-10-08 | `forum_rumor/social_sentiment` | Reddit 讨论：[中国央行 5000 亿元互换机制](https://www.reddit.com/r/China_irl/comments/1g09hjy)；媒体转述朋友圈/游资表达见每日经济新闻同文 | 社媒出现“没满仓很难受”“10%涨停像亏”等表达。 | 实时到当日 | 只用于 FOMO 和相对收益焦虑；不得作为交易账户或资金来源事实。 |

### 2024-10-09：新开户首日交易叠加急跌

| 时间 | 来源等级 | 来源 | 关键事实/信息 | 延迟 | 对 belief 的可能影响 |
| --- | --- | --- | --- | --- | --- |
| 15:00 | `market_data` + `mainstream_media` | 东方财富/新浪财经：[沪指跌 6.62%，创业板指跌 10.59%，成交接近三万亿](https://finance.sina.com.cn/roll/2024-10-09/doc-incrxvru9879702.shtml) | 沪指收 3258.86 点跌 6.62%，深成指跌 8.15%，创业板指跌 10.59%；两市成交额约 2.94 万亿元。 | 收盘后分钟级 | “狂热后踩踏/高位追涨被套”belief 增强；风险厌恶和流动性撤退预期上升。 |
| 2024-10-09 | `mainstream_media` + `forum_rumor/social_sentiment` | 经济观察网：[新股民入场首日即交学费](https://www.eeo.com.cn/2024/1009/690431.shtml) | 报道称 10 月 1-8 日提交申请的新开证券账户 10 月 9 日起可交易，并转述新股民被套、T+1 不能卖等网络吐槽。 | 当日 | 新手 agent 的“规则困惑/T+1 恐慌”belief 上升；吐槽内容只按二手情绪样本处理。 |
| 2024-10-09 | `forum_rumor/social_sentiment` | Reddit：[real_China_irl 讨论串](https://www.reddit.com/r/real_China_irl/comments/1fypmq7) | 匿名评论中出现“跑步进场”“开盘买入后麻了”等嘲讽或自嘲表达。 | 实时/数小时 | 可用于论坛话术和情绪极化；不能推断真实交易规模。 |

### 2024-10-10：互换便利公告与市场分化

| 时间 | 来源等级 | 来源 | 关键事实/信息 | 延迟 | 对 belief 的可能影响 |
| --- | --- | --- | --- | --- | --- |
| 上午 | `official_first_hand` | 中国政府网/新华社：[我国首个支持资本市场的货币政策工具落地](https://www.gov.cn/lianbo/bumen/202410/content_6979049.htm) | 央行发布公告，即日起接受符合条件的证券、基金、保险公司申报 SFISF；首期 5000 亿元，可视情扩大。 | 当日 | 官方流动性工具从预告转为落地；机构流动性 belief 上升，但不等于当日券商股必涨。 |
| 15:00 后 | `market_data` + `mainstream_media` | 界面/新浪财经：[沪指涨 1.32%，两市成交 21430 亿元](https://finance.sina.com.cn/jjxw/2024-10-10/doc-incrzyqw8631755.shtml) | 上证指数涨 1.32%，深成指跌 0.82%，创业板指跌 2.95%；两市成交额 21430 亿元，较上日缩量约 7964 亿元。 | 收盘后分钟级 | 市场从全线狂热转为分化；“政策托底”与“高位退潮”belief 并存。 |
| 2024-10-10 | `broker_view` | 中新经纬/新浪收评引用招商证券观点：[沪指收涨 1.32%](https://finance.sina.com.cn/roll/2024-10-10/doc-incsaeww5291517.shtml) | 招商证券观点称随着 9 月指数大涨确认中期低点，未来整体方向以上行趋势为主。 | 当日 | 提供乐观机构锚；和市场缩量、创业板回调形成信息冲突。 |

### 2024-10-11：继续普跌，成交降温

| 时间 | 来源等级 | 来源 | 关键事实/信息 | 延迟 | 对 belief 的可能影响 |
| --- | --- | --- | --- | --- | --- |
| 15:24 | `market_data` + `mainstream_media` | 澎湃/新浪财经：[A 股震荡下行，沪指跌 2.55%](https://finance.sina.com.cn/jjxw/2024-10-11/doc-incseivz5186491.shtml) | 沪指跌 2.55%，深成指跌 3.92%，创业板指跌 5.06%；沪深两市成交总额 15720 亿元，较前一日减少 5710 亿元。 | 收盘后分钟级 | “成交退潮/踩踏延续”belief 增强；短线资金 agent 降低风险偏好。 |
| 2024-10-11 | `mainstream_media` | 中新经纬/新浪财经：[沪深两市全天成交额 1.57 万亿元，全市场约 4900 股下跌](https://finance.sina.com.cn/roll/2024-10-11/doc-incseiwf1486426.shtml) | 市场普跌，成交额较 10 月 8 日峰值显著回落但仍高于 9 月中旬常态。 | 收盘后分钟级 | 低位承接和风险释放两种解释并存；不宜直接写成“政策失败”。 |
| 2024-10-11 | `broker_view` | 招商策略后续复盘：[调整之后 A 股怎么看](https://finance.sina.com.cn/stock/roll/2024-10-13/doc-incsmaiy9221165.shtml) | 10 月 13 日复盘把 10 月 8 日发改委发布会、10 月 12 日财政发布会预期等列为本周影响因素。 | 事后 2 日 | 只能作为后验机构解释，用于复盘 agent，不适合做 10 月 11 日实时可见信息。 |

## 不同 agent 可见性候选

此表只描述资料可见性，不决定系统实现。

| agent 类型候选 | 高优先可见标签 | 低优先/降权标签 | 典型 belief 变化 |
| --- | --- | --- | --- |
| 政策/宏观 agent | `official_first_hand`、`broker_view`、部分 `market_data` | `forum_rumor/social_sentiment` | 根据国新办、央行、证监会、发改委公告提高政策支持强度；对市场反应保留滞后验证。 |
| 交易所/基础设施 agent | `exchange_notice`、`market_data`、媒体系统拥堵报道 | 论坛抱怨 | 关注连通性测试、指定交易、开户审核、成交额激增、App/银证转账拥堵。 |
| 机构投资者 agent | `official_first_hand`、`market_data`、`broker_view` | 匿名社媒 | 先从政策和成交额确认风险偏好，再用研报形成行业/风格倾向；对过热和拥挤度更敏感。 |
| 媒体传播 agent | `official_first_hand`、`market_data`、`mainstream_media`、`broker_view` | 社媒可作为素材但需标注 | 把官方事实、行情数字和券商观点组合成“政策组合拳/信心重估/踩踏回撤”等叙事。 |
| 新股民/散户 agent | `mainstream_media`、`forum_rumor/social_sentiment`、券商 App 体验、简单行情数据 | 正式公告原文 | 对涨跌幅、热搜、朋友群、开户和 T+1 体验敏感；容易把二手信息当事实。 |
| 股吧/传言 agent | `forum_rumor/social_sentiment`、媒体标题、盘中涨跌 | 官方原文仅作为被再解释材料 | 传播“牛市来了”“踏空”“被套”“系统卡顿”“政策不及预期”等情绪，不验证事实。 |

## 可转成 input event 的字段候选

以下字段仅为资料结构化候选，不代表最终接口或架构。

| 字段 | 含义 | 示例 |
| --- | --- | --- |
| `event_id` | 稳定事件编号 | `cn_a_2024_09_24_policy_package_press_conf` |
| `occurred_at` | 事件发生时间，带时区或交易日 | `2024-09-24T10:00:00+08:00` |
| `published_at` | 信息源发布时间 | `2024-09-24T15:02:00+08:00` |
| `source_tier` | 候选来源标签 | `official_first_hand` |
| `source_name` | 来源名称 | `中国政府网/国新办` |
| `source_url` | 来源链接 | `https://www.gov.cn/lianbo/fabu/202409/content_6976186.htm` |
| `fact_claim` | 可核验事实或观点摘要 | `央行宣布将创设支持资本市场的新货币政策工具` |
| `claim_type` | `fact` / `market_data` / `view` / `rumor` / `sentiment` | `fact` |
| `latency_bucket` | 可见延迟 | `real_time`、`same_day`、`T+1`、`post_hoc` |
| `confidence` | 事实可信度 | `high`、`medium`、`low` |
| `visibility` | 候选可见 agent | `policy_agent,institutional_agent,media_agent` |
| `belief_delta_hint` | 对 belief 的方向提示 | `policy_support_up,risk_appetite_up` |
| `market_context` | 可选行情上下文 | `沪指涨4.15%; 两市成交9713亿元` |
| `notes` | 口径/限制 | `成交额为沪深两市口径；不含北交所` |

## 可结构化的事件样本

| event_id | occurred_at | source_tier | claim_type | confidence | visibility | belief_delta_hint | 来源 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `policy_20240924_financial_package` | 2024-09-24 上午 | `official_first_hand` | `fact` | high | policy, institutional, media | `policy_support_up` | [中国政府网](https://www.gov.cn/lianbo/fabu/202409/content_6976186.htm) |
| `market_20240924_close_surge` | 2024-09-24 15:00 | `market_data` | `market_data` | high | all market agents | `risk_appetite_up,fomo_up` | [新浪财经/界面](https://finance.sina.com.cn/jjxw/2024-09-24/doc-incqfwyt1295722.shtml) |
| `policy_20240926_long_term_funds` | 2024-09-26 | `official_first_hand` | `fact` | high | policy, institutional | `long_term_fund_expectation_up` | [证监会](https://www.csrc.gov.cn/csrc/c100028/c7508981/content.shtml) |
| `exchange_20241007_szse_connectivity_test` | 2024-10-07 | `exchange_notice` | `fact` | high | infrastructure, institutional | `infra_preparedness_up` | [深交所](https://www.szse.cn/marketServices/technicalservice/notice/t20240926_609627.html) |
| `market_20241008_open_gap` | 2024-10-08 09:30 | `market_data` | `market_data` | high | all market agents | `fomo_up,overheat_risk_up` | [每日经济新闻](https://www.nbd.com.cn/articles/2024-10-08/3580175.html) |
| `policy_20241008_ndrc_incremental_package` | 2024-10-08 10:00 | `official_first_hand` | `fact` | high | policy, institutional, media | `policy_continuity_up` | [中国政府网](https://www.gov.cn/lianbo/bumen/202410/content_6978753.htm) |
| `market_20241008_record_turnover` | 2024-10-08 15:00 | `market_data` | `market_data` | high | all market agents | `mania_up,liquidity_up` | [每日经济新闻](https://www.nbd.com.cn/articles/2024-10-08/3582077.html) |
| `sentiment_20241009_new_retail_trapped` | 2024-10-09 | `forum_rumor/social_sentiment` | `sentiment` | low | retail, forum, media | `panic_up,tplus1_confusion_up` | [经济观察网](https://www.eeo.com.cn/2024/1009/690431.shtml) |
| `policy_20241010_sfisf_launch` | 2024-10-10 上午 | `official_first_hand` | `fact` | high | policy, institutional | `liquidity_tool_confirmed` | [中国政府网/新华社](https://www.gov.cn/lianbo/bumen/202410/content_6979049.htm) |
| `market_20241011_turnover_cooldown` | 2024-10-11 15:00 | `market_data` | `market_data` | high | all market agents | `risk_appetite_down,liquidity_cooldown` | [澎湃/新浪](https://finance.sina.com.cn/jjxw/2024-10-11/doc-incseivz5186491.shtml) |

## 不可确认项 / 需降权项

- “国庆期间新开户千万级”：多见于媒体转述券商人士测算或市场传闻，未找到中国结算官方精确发布。可作为开户热情绪强度，不可作为官方账户数量。
- “10 月 8 日成交额会到 4 万亿元”：见媒体或市场人士预测，不是事实。可作为盘前预期，不可写入实际成交。
- “发改委 10 月 8 日发布会导致盘中回落”：这是市场解释，不能从时间相关性直接推出因果。可作为 `mainstream_media` 或 `broker_view` 的观点输入。
- “券商 App 宕机/银证转账拥堵的具体责任方”：公开报道能确认投资者反馈和部分券商/业内人士说法，但无法确认每家机构的精确故障原因和影响范围。
- “游资朋友圈、股吧截图、Reddit 评论里的盈亏金额”：只能作为语言风格和情绪样本，不作为真实盈亏或交易数据。
- “上交所 2024-10-06 延长接受指定交易申报指令时间原公告”：当前通过上交所 2025-05-23 指南通知可间接确认该文件存在并已废止，但原公告正文链接未定位；使用时标注为间接证据。
- “10 月 12 日财政部发布会内容”：超出本窗口。窗口内只可记录 10 月 9-11 日市场已知的发布会预告或期待，不提前赋予后续政策事实。

## 来源索引

- 中国政府网，2024-09-24，三部门金融支持政策发布会：https://www.gov.cn/lianbo/fabu/202409/content_6976186.htm
- 中国证监会，2024-09-24，并购六条：https://www.csrc.gov.cn/csrc/c100028/c7508366/content.shtml
- 中国证监会，2024-09-26，中长期资金入市指导意见：https://www.csrc.gov.cn/csrc/c100028/c7508981/content.shtml
- 中国人民银行，2024-09-27，降准公告：https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/2025092212554238383/index.html
- 深交所，2024-09-26/10-07，深市交易系统连通性测试：https://www.szse.cn/marketServices/technicalservice/notice/t20240926_609627.html
- 上交所，2025-05-23，间接确认 2024-10-06 指定交易通知：https://www.sse.com.cn/lawandrules/guide/stock/jyglywznylc/zn/c/c_20250523_10779856.shtml
- 新华财经/中国金融信息网，2024-10-07，中国结算开户审核安排：https://www.cnfin.com/yw-lb/detail/20241007/4114730_1.html
- 中国政府网，2024-10-08，发改委一揽子增量政策发布会：https://www.gov.cn/lianbo/bumen/202410/content_6978753.htm
- 中国政府网，2024-10-10，央行 SFISF 新工具落地：https://www.gov.cn/lianbo/bumen/202410/content_6979049.htm
- 新浪财经/界面，2024-09-24，A 股收评：https://finance.sina.com.cn/jjxw/2024-09-24/doc-incqfwyt1295722.shtml
- 新浪财经/每日经济新闻，2024-09-30，A 股收评：https://finance.sina.com.cn/roll/2024-09-30/doc-incqxmqu2903371.shtml
- 每日经济新闻，2024-10-08，开盘高开与券商观点：https://www.nbd.com.cn/articles/2024-10-08/3580175.html
- 每日经济新闻，2024-10-08，成交 3.4835 万亿元：https://www.nbd.com.cn/articles/2024-10-08/3582077.html
- 新浪财经/东方财富，2024-10-09，A 股收评：https://finance.sina.com.cn/roll/2024-10-09/doc-incrxvru9879702.shtml
- 新浪财经/界面，2024-10-10，A 股收评：https://finance.sina.com.cn/jjxw/2024-10-10/doc-incrzyqw8631755.shtml
- 新浪财经/澎湃，2024-10-11，A 股收评：https://finance.sina.com.cn/jjxw/2024-10-11/doc-incseivz5186491.shtml
- 每日经济新闻，2024-10-08，券商晨会精选：https://www.nbd.com.cn/articles/2024-10-08/3579983.html
- 新浪财经，2024-10-08，中金节后观点：https://finance.sina.com.cn/roll/2024-10-08/doc-incruvpi0722950.shtml
- 发现报告，国泰君安 2024-09-24 策略快评转存：https://www.fxbaogao.com/detail/4516720
- 经济观察网，2024-10-09，新股民入场首日：https://www.eeo.com.cn/2024/1009/690431.shtml
- Reddit r/China_irl，2024-09-24 国新办发布会讨论：https://www.reddit.com/r/China_irl/comments/1fna6ap
- Reddit r/real_China_irl，2024-10-08 A 股讨论：https://www.reddit.com/r/real_China_irl/comments/1fypmq7
- Reddit r/4832，2024-10-01 VOA 转述 A 股行情：https://www.reddit.com/r/4832/comments/1ftt4eh
