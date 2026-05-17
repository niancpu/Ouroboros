# 2024-10 标的层面真实行情资料

数据用途：供 Ouroboros agent 回放 2024-10-08 至 2024-10-11 的创业板风险偏好、券商/金融科技情绪和高波动成交状态。

## 标的选择

- 创业板 ETF 选用 `159915.SZ`（创业板ETF易方达）。理由：其为常用、成交活跃的创业板宽基 ETF；新浪财经 2024-10-08 报道其开盘后不到半小时成交额已超 156 亿元，且当天收盘成交额约 474.86 亿元，适合作为创业板风险偏好的流动性载体。[来源：新浪财经 2024-10-08](https://finance.sina.com.cn/stock/bxjj/2024-10-08/doc-incruzvf0647121.shtml)，[来源：东方财富历史 K 线接口](https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=0.159915&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=0&beg=20241008&end=20241011)
- 东方财富 `300059.SZ`：创业板上市的互联网券商/金融信息平台标的，兼具券商 beta、金融科技交易活跃度和散户风险偏好代理属性。2024-10-08 半日成交额位居 A 股第一。[来源：新浪财经 2024-10-08](https://finance.sina.com.cn/stock/bxjj/2024-10-08/doc-incrvhce7351205.shtml)，[来源：东方财富 2024 半年度报告摘要](https://static.cninfo.com.cn/finalpage/2024-08-10/1220834734.PDF)
- 同花顺 `300033.SZ`：创业板上市的金融信息服务/交易工具链标的，是金融科技情绪和市场交易活跃度的高弹性代理。2024-10-08 市场复盘将同花顺列入金融科技涨停股。[来源：新浪财经 2024-10-08 涨停复盘](https://finance.sina.com.cn/roll/2024-10-08/doc-incrvssx0387764.shtml)，[来源：同花顺 2024 半年度报告摘要检索页](https://www.cninfo.com.cn/new/disclosure/stock?stockCode=300033&orgId=9900008340)

口径说明：

- 日线行情采用东方财富 `push2his` 历史 K 线接口，不复权 `fqt=0`。字段顺序按 `fields2=f51...f61` 解析为：日期、开盘、收盘、最高、最低、成交量、成交额、振幅、涨跌幅、涨跌额、换手率。
- 成交量单位按接口常见口径记为“手”。成交额单位在表内折算为“亿元”。
- 创业板股票和深市相关 20% 涨跌幅限制按交易规则理解；ETF `159915` 在公开行情和新闻中也按 20% 涨停表现记录。未取得交易所逐笔/分钟级官方数据时，不把“炸板”作为已确认事实，只标注“日线可见触及涨跌停/盘中大幅回落”。

## 日线行情表

| 日期 | 标的 | 开高低收 | 涨跌幅 | 成交额/量 | 现象标签 | 来源 |
|---|---|---:|---:|---:|---|---|
| 2024-10-08 | 创业板ETF易方达 `159915` | O 2.678 / H 2.678 / L 2.290 / C 2.678 | +19.98% | 474.86 亿元 / 185,677,265 手 | 涨停开盘、涨停收盘；日内低点显示大幅回落后回封；新浪报道 10:00 前后成交超 156 亿元、盘中涨幅一度收窄至 12% | [东方财富 K 线](https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=0.159915&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=0&beg=20241008&end=20241011)、[新浪](https://finance.sina.com.cn/stock/bxjj/2024-10-08/doc-incruzvf0647121.shtml) |
| 2024-10-09 | 创业板ETF易方达 `159915` | O 2.410 / H 2.478 / L 2.238 / C 2.242 | -16.28% | 385.85 亿元 / 164,618,813 手 | 前一日涨停后剧烈回撤；收盘接近日内低位 | [东方财富 K 线](https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=0.159915&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=0&beg=20241008&end=20241011) |
| 2024-10-10 | 创业板ETF易方达 `159915` | O 2.241 / H 2.297 / L 2.137 / C 2.174 | -3.03% | 178.12 亿元 / 80,625,516 手 | 高波动延续但成交降温；弱收盘 | [东方财富 K 线](https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=0.159915&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=0&beg=20241008&end=20241011) |
| 2024-10-11 | 创业板ETF易方达 `159915` | O 2.134 / H 2.152 / L 2.026 / C 2.060 | -5.24% | 151.84 亿元 / 72,995,288 手 | 连续回落；风险偏好退潮 | [东方财富 K 线](https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=0.159915&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=0&beg=20241008&end=20241011) |
| 2024-10-08 | 东方财富 `300059` | O 24.36 / H 24.36 / L 22.77 / C 24.36 | +20.00% | 330.78 亿元 / 13,667,678 手 | 20cm 涨停开盘、涨停收盘；日内低点显示曾明显打开/回落；新浪报道半日成交 311 亿元、A 股成交额第一 | [东方财富 K 线](https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=0.300059&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=0&beg=20241008&end=20241011)、[新浪](https://finance.sina.com.cn/stock/bxjj/2024-10-08/doc-incrvhce7351205.shtml) |
| 2024-10-09 | 东方财富 `300059` | O 24.00 / H 29.00 / L 22.61 / C 24.90 | +2.22% | 900.38 亿元 / 34,623,506 手 | 巨量成交；盘中从接近 +19% 冲高回落至小涨；情绪分歧极大 | [东方财富 K 线](https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=0.300059&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=0&beg=20241008&end=20241011) |
| 2024-10-10 | 东方财富 `300059` | O 24.10 / H 24.56 / L 19.92 / C 20.55 | -17.47% | 519.73 亿元 / 23,863,267 手 | 日内触及约 -20% 跌停价后回拉；新浪午间报道半日成交 341.03 亿元、仍居市场首位 | [东方财富 K 线](https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=0.300059&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=0&beg=20241008&end=20241011)、[新浪](https://finance.sina.com.cn/roll/2024-10-10/doc-incrzyqy5387294.shtml) |
| 2024-10-11 | 东方财富 `300059` | O 19.51 / H 21.50 / L 19.51 / C 20.85 | +1.46% | 301.43 亿元 / 14,583,066 手 | 低开后修复；成交仍高但较 10-09 峰值收缩 | [东方财富 K 线](https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=0.300059&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=0&beg=20241008&end=20241011) |
| 2024-10-08 | 同花顺 `300033` | O 231.97 / H 231.97 / L 214.97 / C 231.97 | +20.00% | 56.71 亿元 / 247,019 手 | 20cm 涨停开盘、涨停收盘；日内低点显示曾明显打开/回落；复盘列入金融科技涨停股 | [东方财富 K 线](https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=0.300033&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=0&beg=20241008&end=20241011)、[新浪](https://finance.sina.com.cn/roll/2024-10-08/doc-incrvssx0387764.shtml) |
| 2024-10-09 | 同花顺 `300033` | O 220.00 / H 277.38 / L 202.00 / C 230.99 | -0.42% | 143.04 亿元 / 601,243 手 | 巨幅震荡；盘中最高接近 +20%，收盘转为微跌；冲高大幅回落 | [东方财富 K 线](https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=0.300033&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=0&beg=20241008&end=20241011) |
| 2024-10-10 | 同花顺 `300033` | O 227.83 / H 227.83 / L 185.00 / C 190.70 | -17.44% | 81.35 亿元 / 407,275 手 | 高开即弱；接近跌停区间后弱收盘；金融科技高 beta 退潮 | [东方财富 K 线](https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=0.300033&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=0&beg=20241008&end=20241011) |
| 2024-10-11 | 同花顺 `300033` | O 185.00 / H 193.80 / L 176.11 / C 182.22 | -4.45% | 52.83 亿元 / 283,383 手 | 继续回落；波动收敛但风险偏好仍弱 | [东方财富 K 线](https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=0.300033&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=0&beg=20241008&end=20241011) |

## 分时级公开资料

- `159915`：可确认 2024-10-08 10:00 前后信息。新浪财经援引格隆汇称，开盘后不到半小时成交额超 156 亿元，早间涨停开盘，盘中涨幅一度收窄至 12%。[来源](https://finance.sina.com.cn/stock/bxjj/2024-10-08/doc-incruzvf0647121.shtml)
- `300059`：可确认 2024-10-08 11:58 前后，东方财富 20cm 涨停，报 24.36 元，半日成交 311 亿元，位居 A 股成交额第一。[来源](https://finance.sina.com.cn/stock/bxjj/2024-10-08/doc-incrvhce7351205.shtml)
- `300059`：可确认 2024-10-10 午间，东方财富半日成交额 341.03 亿元，仍居市场首位。[来源](https://finance.sina.com.cn/roll/2024-10-10/doc-incrzyqy5387294.shtml)
- `300033`：未找到可稳定引用的逐分钟公开资料。只能由日线 OHLC 判断 2024-10-08 曾涨停收盘、2024-10-09 盘中接近涨停后回落。是否“封板后炸板”需要逐笔、分钟 K 或盘口封单数据确认。
- 全市场背景：2024-10-08 午间财联社/新浪报道个股炸板率超 80%，说明当日高开、回落、再承接的波动结构具有市场普遍性。[来源](https://finance.sina.com.cn/jjxw/2024-10-08/doc-incrvhaz0931238.shtml)

## 与券商/金融科技/创业板风险偏好的关系

- `159915` 代表创业板整体风险偏好。2024-10-08 创业板指大涨、ETF 涨停并放出 474.86 亿元成交额，适合作为“风险偏好突然升温”的宽基输入；10-09 至 10-11 连续回落，适合作为“情绪从一致转分歧、再到退潮”的回放主线。[来源：东方财富 K 线](https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=0.159915&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=0&beg=20241008&end=20241011)
- `300059` 是券商交易活跃度和互联网金融情绪的合成代理。其 10-08 涨停、10-09 900.38 亿元成交、10-10 触及跌停区间，表明市场对券商/金融科技 beta 的定价在极短时间内从一致追涨切换为巨量换手和风险释放。[来源：东方财富 K 线](https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=0.300059&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=0&beg=20241008&end=20241011)、[东方财富 2024 半年度报告摘要](https://static.cninfo.com.cn/finalpage/2024-08-10/1220834734.PDF)
- `300033` 是金融信息服务/交易软件情绪代理。10-08 涨停、10-09 成交额放大到 143.04 亿元并冲高回落，说明交易工具链标的对活跃市场预期高度敏感，但回撤也更剧烈。[来源：东方财富 K 线](https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=0.300033&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=0&beg=20241008&end=20241011)

## 可回放市场数据草案

建议每个 tick 使用统一字段：

```yaml
market_tick:
  date: YYYY-MM-DD
  phase: open | midday | close | post_close
  symbol: string
  name: string
  open: number
  high_so_far: number
  low_so_far: number
  last: number
  pct_change: number
  turnover_amount_cny: number
  volume_hands: number
  amplitude_pct: number
  limit_state: none | limit_up | limit_down | touched_limit_up | touched_limit_down | opened_limit
  phenomenon_tags: [string]
  source_confidence: observed_daily | public_intraday_report | inferred_from_ohlc
  source_urls: [string]
  agent_hint:
    risk_preference: euphoric | divergent | cooling | panic | repair
    sector_link: startup_board | brokerage | fintech
    narrative: string
```

示例 tick 种子：

| 日期 | phase | 标的 | 建议状态 | 建议字段重点 |
|---|---|---|---|---|
| 2024-10-08 | open | `159915` / `300059` / `300033` | 一致性高开涨停 | `limit_state=limit_up`，`risk_preference=euphoric`，记录开盘价等于最高价/收盘价但低点明显低于涨停价 |
| 2024-10-08 | midday | `159915` | 涨停打开/涨幅收窄 | 用公开报道填 `last_pct_change≈12%`、`turnover_amount_cny>15.6e9`、`source_confidence=public_intraday_report` |
| 2024-10-08 | midday | `300059` | 20cm 涨停且半日成交第一 | `last=24.36`、`pct_change=20.00`、`turnover_amount_cny≈31.1e9` |
| 2024-10-08 | close | 三标的 | 涨停收盘、成交天量 | 使用日线收盘价、成交额、成交量；`risk_preference=euphoric` |
| 2024-10-08 | post_close | 三标的 | 复盘：金融科技和券商强势，炸板率高 | 写入全市场背景标签：`market_breadth_high`、`failed_limit_rate_high`、`volatility_warning` |
| 2024-10-09 | open | 三标的 | 分歧开盘 | `159915`、`300059`、`300033` 均不再封涨停；保留前日涨停惯性与获利盘压力 |
| 2024-10-09 | close | 三标的 | 巨量分歧 | `300059` 成交额 900.38 亿元；`300033` 冲高回落至微跌；`risk_preference=divergent` |
| 2024-10-10 | midday | `300059` | 巨量仍在但价格转弱 | 用新浪午间 341.03 亿元成交额；`risk_preference=panic` 或 `cooling` |
| 2024-10-10 | close | 三标的 | 风险释放 | `300059` 低点触及跌停价附近，`300033` 接近跌停区间，`159915` 继续下跌 |
| 2024-10-11 | close | 三标的 | 退潮后修复/分化 | `300059` 小涨修复；`159915`、`300033` 继续回落；`risk_preference=cooling` |

## 未确认点

- 未取得交易所逐笔成交、分钟 K 或盘口封单数据，因此“炸板”只能在 `159915`、`300059`、`300033` 的 2024-10-08 日线中按“开高收均为涨停价但日内低点明显低于涨停价”推断为“涨停曾打开/大幅回落”，不能确认具体打开时间、封单金额和打开次数。
- `300033` 2024-10-09 最高价接近但未等于按前收估算的 20% 涨停价；不能标为已触及涨停。
- ETF 的精确涨跌停制度、盘中 IOPV/申赎影响未在本文件展开；当前仅按行情表现和公开报道记录其 2024-10-08 涨停开盘/收盘事实。
