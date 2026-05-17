import type { DemoSeed } from "../types/demo";
import type {
  AgentSummary,
  AuditGraphEdge,
  AuditGraphNode,
} from "../types/api";

const sessionId = "sim_001";
const symbol = "demo_stock";
const tickId = "2024-01-02T14:02:00+08:00";

const tickOpen = "2024-01-02T09:30:00+08:00";
const tickMid = "2024-01-02T10:30:00+08:00";
const tickPreNoon = "2024-01-02T11:30:00+08:00";
const tickEarlyAfternoon = "2024-01-02T14:00:00+08:00";
const tickAlert = tickId;
const tickClose = "2024-01-02T15:00:00+08:00";

const agentRoster: AgentSummary[] = [
  // mutual_fund: 4 agents (a/b/c active+normal, d suspended+normal)
  {
    agent_id: "mutual_fund_a",
    agent_type: "mutual_fund",
    lifecycle_state: "active",
    risk_state: "normal",
    equity: 7800000,
    position_value: 5600000,
  },
  {
    agent_id: "mutual_fund_b",
    agent_type: "mutual_fund",
    lifecycle_state: "active",
    risk_state: "normal",
    equity: 6200000,
    position_value: 4800000,
  },
  {
    agent_id: "mutual_fund_c",
    agent_type: "mutual_fund",
    lifecycle_state: "active",
    risk_state: "normal",
    equity: 5400000,
    position_value: 3900000,
  },
  {
    agent_id: "mutual_fund_d",
    agent_type: "mutual_fund",
    lifecycle_state: "suspended",
    risk_state: "normal",
    equity: 4100000,
    position_value: 3200000,
  },
  // hot_money: 5 agents (a-d warning, e normal)
  {
    agent_id: "hot_money_a",
    agent_type: "hot_money",
    lifecycle_state: "active",
    risk_state: "warning",
    equity: 2850000,
    position_value: 2400000,
  },
  {
    agent_id: "hot_money_b",
    agent_type: "hot_money",
    lifecycle_state: "active",
    risk_state: "warning",
    equity: 2480000,
    position_value: 2100000,
  },
  {
    agent_id: "hot_money_c",
    agent_type: "hot_money",
    lifecycle_state: "active",
    risk_state: "warning",
    equity: 2120000,
    position_value: 1750000,
  },
  {
    agent_id: "hot_money_d",
    agent_type: "hot_money",
    lifecycle_state: "active",
    risk_state: "warning",
    equity: 1820000,
    position_value: 1500000,
  },
  {
    agent_id: "hot_money_e",
    agent_type: "hot_money",
    lifecycle_state: "active",
    risk_state: "normal",
    equity: 1620000,
    position_value: 1180000,
  },
  // retail: 14 agents - a..i normal, j/k warning, l margin_call, m liquidating, n terminated
  {
    agent_id: "retail_a",
    agent_type: "retail",
    lifecycle_state: "active",
    risk_state: "normal",
    equity: 480000,
    position_value: 360000,
  },
  {
    agent_id: "retail_b",
    agent_type: "retail",
    lifecycle_state: "active",
    risk_state: "normal",
    equity: 420000,
    position_value: 320000,
  },
  {
    agent_id: "retail_c",
    agent_type: "retail",
    lifecycle_state: "active",
    risk_state: "normal",
    equity: 360000,
    position_value: 280000,
  },
  {
    agent_id: "retail_d",
    agent_type: "retail",
    lifecycle_state: "active",
    risk_state: "normal",
    equity: 320000,
    position_value: 250000,
  },
  {
    agent_id: "retail_e",
    agent_type: "retail",
    lifecycle_state: "active",
    risk_state: "normal",
    equity: 280000,
    position_value: 220000,
  },
  {
    agent_id: "retail_f",
    agent_type: "retail",
    lifecycle_state: "active",
    risk_state: "normal",
    equity: 240000,
    position_value: 190000,
  },
  {
    agent_id: "retail_g",
    agent_type: "retail",
    lifecycle_state: "active",
    risk_state: "normal",
    equity: 210000,
    position_value: 160000,
  },
  {
    agent_id: "retail_h",
    agent_type: "retail",
    lifecycle_state: "active",
    risk_state: "normal",
    equity: 170000,
    position_value: 130000,
  },
  {
    agent_id: "retail_i",
    agent_type: "retail",
    lifecycle_state: "active",
    risk_state: "normal",
    equity: 140000,
    position_value: 105000,
  },
  {
    agent_id: "retail_j",
    agent_type: "retail",
    lifecycle_state: "active",
    risk_state: "warning",
    equity: 118000,
    position_value: 92000,
  },
  {
    agent_id: "retail_k",
    agent_type: "retail",
    lifecycle_state: "active",
    risk_state: "warning",
    equity: 96000,
    position_value: 78000,
  },
  {
    agent_id: "retail_l",
    agent_type: "retail",
    lifecycle_state: "margin_call",
    risk_state: "margin_call",
    equity: 72000,
    position_value: 65000,
  },
  {
    agent_id: "retail_m",
    agent_type: "retail",
    lifecycle_state: "liquidating",
    risk_state: "liquidating",
    equity: 12000,
    position_value: 30000,
  },
  {
    agent_id: "retail_n",
    agent_type: "retail",
    lifecycle_state: "terminated",
    risk_state: "terminated",
    equity: 50000,
    position_value: 40000,
  },
  // national_team: 1 agent
  {
    agent_id: "national_team_a",
    agent_type: "national_team",
    lifecycle_state: "active",
    risk_state: "normal",
    equity: 50000000,
    position_value: 30000000,
  },
];

// Belief score map - mutual_fund cautious (low), hot_money aggressive (high),
// retail mid-high (chasing rally), national_team mid.
const beliefByAgent: Record<string, number> = {
  mutual_fund_a: 0.22,
  mutual_fund_b: 0.28,
  mutual_fund_c: 0.31,
  mutual_fund_d: 0.18,
  hot_money_a: 0.86,
  hot_money_b: 0.81,
  hot_money_c: 0.78,
  hot_money_d: 0.74,
  hot_money_e: 0.69,
  retail_a: 0.62,
  retail_b: 0.58,
  retail_c: 0.66,
  retail_d: 0.71,
  retail_e: 0.74,
  retail_f: 0.79,
  retail_g: 0.83,
  retail_h: 0.88,
  retail_i: 0.92,
  retail_j: 0.71,
  retail_k: 0.65,
  retail_l: 0.42,
  retail_m: 0.25,
  retail_n: 0.15,
  national_team_a: 0.48,
};

const auditNodes: AuditGraphNode[] = agentRoster.map((agent) => ({
  agent_id: agent.agent_id,
  agent_type: agent.agent_type,
  belief_score: beliefByAgent[agent.agent_id] ?? 0.5,
  position_value: agent.position_value,
  risk_state: agent.risk_state,
}));

const auditEdges: AuditGraphEdge[] = [
  // High-influence edges (weight >= 0.6) — at least 3
  {
    source: "hot_money_a",
    target: "retail_h",
    weight: 0.78,
    reason_ref: "forum_post_201",
    public_reason: "游资甲发布看多帖触发散户八情绪共振。",
  },
  {
    source: "hot_money_b",
    target: "retail_i",
    weight: 0.71,
    reason_ref: "forum_post_201",
    public_reason: "游资乙在公开平台连发短评，散户九跟随放量买入。",
  },
  {
    source: "national_team_a",
    target: "mutual_fund_a",
    weight: 0.64,
    reason_ref: "official_002",
    public_reason: "国家队公告释放维稳信号，公募甲调整观望策略。",
  },
  // Medium edges (hot_money -> retail, the dominant influence pattern)
  {
    source: "hot_money_a",
    target: "retail_g",
    weight: 0.52,
    reason_ref: "forum_post_201",
    public_reason: "公开帖子被散户群体看到，看多预期上升。",
  },
  {
    source: "hot_money_b",
    target: "retail_f",
    weight: 0.46,
    reason_ref: "forum_post_201",
    public_reason: "游资乙转发热点帖，散户六跟单。",
  },
  {
    source: "hot_money_c",
    target: "retail_e",
    weight: 0.41,
    reason_ref: "forum_post_201",
    public_reason: "公开股吧热度上行，散户五入场。",
  },
  {
    source: "hot_money_c",
    target: "retail_d",
    weight: 0.38,
    reason_ref: "forum_post_201",
    public_reason: "短线讨论扩散，散户四提高仓位。",
  },
  {
    source: "hot_money_d",
    target: "retail_c",
    weight: 0.35,
    reason_ref: "forum_post_202",
    public_reason: "游资丁公开发声，散户三关注上行预期。",
  },
  {
    source: "hot_money_d",
    target: "retail_b",
    weight: 0.32,
    reason_ref: "forum_post_202",
    public_reason: "公开消息推动散户二跟风。",
  },
  {
    source: "hot_money_e",
    target: "retail_a",
    weight: 0.29,
    reason_ref: "forum_post_202",
    public_reason: "公开渠道情绪外溢，散户一加仓。",
  },
  // Market -> hot money risk pull-back
  {
    source: "market",
    target: "hot_money_a",
    weight: 0.36,
    reason_ref: "tape_alert_001",
    public_reason: "盘口卖压扩大后，游资甲风险偏好下降。",
  },
  {
    source: "market",
    target: "hot_money_b",
    weight: 0.34,
    reason_ref: "tape_alert_001",
    public_reason: "盘口下方承接减弱，游资乙降低敞口。",
  },
  {
    source: "market",
    target: "hot_money_c",
    weight: 0.31,
    reason_ref: "tape_alert_002",
    public_reason: "流动性收缩告警，游资丙转向防守。",
  },
  // Market -> retail (risk events broadcast to retail)
  {
    source: "market",
    target: "retail_j",
    weight: 0.42,
    reason_ref: "tape_alert_002",
    public_reason: "盘口异动叠加预警，散户十进入风险状态。",
  },
  {
    source: "market",
    target: "retail_k",
    weight: 0.39,
    reason_ref: "tape_alert_002",
    public_reason: "流动性预警触发散户十一调仓。",
  },
  {
    source: "market",
    target: "retail_l",
    weight: 0.56,
    reason_ref: "tape_alert_002",
    public_reason: "盘口快速下跌触发散户十二强平线。",
  },
  // Retail-to-retail (herding)
  {
    source: "retail_h",
    target: "retail_g",
    weight: 0.27,
    reason_ref: "forum_post_201",
    public_reason: "散户八公开发言后，散户七跟风加仓。",
  },
  {
    source: "retail_i",
    target: "retail_h",
    weight: 0.24,
    reason_ref: "forum_post_201",
    public_reason: "散户九的成交数据被同伴关注。",
  },
  {
    source: "retail_g",
    target: "retail_f",
    weight: 0.22,
    reason_ref: "forum_post_201",
    public_reason: "散户群体内部信念扩散。",
  },
  // Mutual fund -> peer signal (institutional caution)
  {
    source: "mutual_fund_a",
    target: "mutual_fund_b",
    weight: 0.33,
    reason_ref: "official_002",
    public_reason: "公募甲减仓动作引起公募乙参考。",
  },
  {
    source: "mutual_fund_b",
    target: "mutual_fund_c",
    weight: 0.28,
    reason_ref: "official_002",
    public_reason: "公募乙降低敞口，公募丙跟进。",
  },
  // Suspended fund -> still publishes prior view
  {
    source: "mutual_fund_d",
    target: "mutual_fund_a",
    weight: 0.18,
    reason_ref: "official_001",
    public_reason: "公募丁停牌期间留存的研究观点仍被同业引用。",
  },
  // National team -> hot money (signaling)
  {
    source: "national_team_a",
    target: "hot_money_e",
    weight: 0.36,
    reason_ref: "official_002",
    public_reason: "国家队公开维稳信号让游资戊降低空仓预期。",
  },
  // Cascade towards liquidation
  {
    source: "retail_l",
    target: "retail_m",
    weight: 0.31,
    reason_ref: "risk_event_001",
    public_reason: "散户十二被强平后，散户十三的清算压力进一步上升。",
  },
];

export const demoSeed: DemoSeed = {
  session: {
    session_id: sessionId,
    status: "running",
    current_tick_id: tickId,
    tick_state: "AGENT_STEP",
    agent_count: 24,
    active_agent_count: 21,
    created_at: "2024-01-02T09:29:30+08:00",
  },
  snapshot: {
    session_id: sessionId,
    last_seq: 1024,
    current_tick_id: tickId,
    tick_state: "COMMIT_TICK",
    market: {
      symbol,
      last_price: 15.2,
      volume: 100000,
      turnover: 1520000,
      limit_up: 16.5,
      limit_down: 13.5,
      limit_state: "normal",
      level2: {
        bids: [
          ["15.19", 12000],
          ["15.18", 9000],
          ["15.17", 6800],
        ],
        asks: [
          ["15.21", 8000],
          ["15.22", 11000],
          ["15.23", 7200],
        ],
      },
    },
    agents: agentRoster,
    audit_graph: {
      nodes: auditNodes,
      edges: auditEdges,
    },
    causal_chains: [
      {
        chain_id: "chain_001",
        title: "公开帖子触发散户追涨",
        summary: "公开股吧帖子推动散户信念上升，随后买单增加并抬高价格。",
        last_event_ref: "mkt_002",
      },
      {
        chain_id: "chain_002",
        title: "卖压扩大触发风险收缩",
        summary: "连续大额卖盘压低盘口承接，部分高杠杆账户进入风险状态。",
        last_event_ref: "risk_event_001",
      },
    ],
  },
  eventsPage: {
    events: [],
    next_from_seq: 1039,
    has_more: false,
  },
  feedEvents: [],
  market: {
    price: {
      symbol,
      last_price: 15.2,
      volume: 100000,
      turnover: 1520000,
      limit_up: 16.5,
      limit_down: 13.5,
      limit_state: "normal",
      level2: {
        bids: [
          ["15.19", 12000],
          ["15.18", 9000],
        ],
        asks: [
          ["15.21", 8000],
          ["15.22", 11000],
        ],
      },
    },
    tapeAlerts: [
      {
        symbol,
        alert_type: "large_sell_pressure",
        severity: "medium",
        public_text: "该股遭遇连续千手大单砸盘，当前跌幅扩大。",
        metrics: {
          price_change_pct: -3,
          sell_volume: 500000,
          bid_depth_change_pct: -35,
        },
      },
      {
        symbol,
        alert_type: "liquidity_drain",
        severity: "high",
        public_text: "盘口下方承接显著萎缩，流动性进入紧张区间。",
        metrics: {
          price_change_pct: -1.6,
          sell_volume: 320000,
          bid_depth_change_pct: -52,
        },
      },
    ],
    endOfDay: {
      symbol,
      close_price: 15.2,
      volume: 12000000,
      turnover: 182400000,
      dragon_tiger: {
        buy_rank: [
          {
            seat_name: "拉萨团结路",
            seat_type: "retail_cluster",
            buy_amount: 50000000,
            sell_amount: 12000000,
            net_amount: 38000000,
          },
          {
            seat_name: "深圳前海路",
            seat_type: "hot_money",
            buy_amount: 32000000,
            sell_amount: 8000000,
            net_amount: 24000000,
          },
        ],
        sell_rank: [
          {
            seat_name: "机构专用",
            seat_type: "institution",
            buy_amount: 10000000,
            sell_amount: 80000000,
            net_amount: -70000000,
          },
          {
            seat_name: "上海建国路",
            seat_type: "hot_money",
            buy_amount: 6000000,
            sell_amount: 42000000,
            net_amount: -36000000,
          },
        ],
      },
    },
  },
  agents: {
    roster: [],
    accountSnapshots: [
      {
        agent_id: "mutual_fund_a",
        agent_type: "mutual_fund",
        cash: 2200000,
        available_cash: 2200000,
        positions: { demo_stock: 360000 },
        available_shares: { demo_stock: 0 },
        frozen_shares: { demo_stock: 360000 },
        market_value: 5600000,
        equity: 7800000,
        risk_state: "normal",
      },
      {
        agent_id: "hot_money_a",
        agent_type: "hot_money",
        cash: 450000,
        available_cash: 450000,
        positions: { demo_stock: 160000 },
        available_shares: { demo_stock: 40000 },
        frozen_shares: { demo_stock: 120000 },
        market_value: 2400000,
        equity: 2850000,
        risk_state: "warning",
      },
      {
        agent_id: "retail_l",
        agent_type: "retail",
        cash: 7000,
        available_cash: 7000,
        positions: { demo_stock: 4300 },
        available_shares: { demo_stock: 0 },
        frozen_shares: { demo_stock: 4300 },
        market_value: 65000,
        equity: 72000,
        risk_state: "margin_call",
      },
      {
        agent_id: "retail_m",
        agent_type: "retail",
        cash: 0,
        available_cash: 0,
        positions: { demo_stock: 2000 },
        available_shares: { demo_stock: 0 },
        frozen_shares: { demo_stock: 2000 },
        market_value: 30000,
        equity: 12000,
        risk_state: "liquidating",
      },
    ],
    lifecycle: [
      {
        agent_id: "mutual_fund_d",
        agent_type: "mutual_fund",
        lifecycle_state: "suspended",
        reason_code: "ops_manual_suspend",
        public_label: "已挂起",
      },
      {
        agent_id: "retail_l",
        agent_type: "retail",
        lifecycle_state: "margin_call",
        reason_code: "equity_drawdown_limit",
        public_label: "已触发强平线",
      },
      {
        agent_id: "retail_m",
        agent_type: "retail",
        lifecycle_state: "liquidating",
        reason_code: "forced_liquidation",
        public_label: "进入清算流程",
      },
      {
        agent_id: "retail_n",
        agent_type: "retail",
        lifecycle_state: "terminated",
        reason_code: "session_terminated",
        public_label: "已终止",
      },
    ],
  },
  audit: {
    graph: {
      nodes: [],
      edges: [],
    },
    causalChains: [
      {
        chain_id: "chain_001",
        title: "公开帖子触发散户追涨",
        summary: "公开股吧帖子推动散户信念上升，随后买单增加并抬高价格。",
        last_event_ref: "mkt_002",
        steps: [
          {
            step_id: "step_001",
            step_type: "public_message",
            tick_id: tickEarlyAfternoon,
            actor_id: "hot_money_a",
            event_ref: "forum_post_201",
            label: "发布看多帖子",
            public_text: "游资甲在公开股吧发布看多帖。",
          },
          {
            step_id: "step_002",
            step_type: "belief_shift",
            tick_id: tickEarlyAfternoon,
            actor_id: "retail_h",
            event_ref: "audit_graph_001",
            label: "散户信念上升",
            public_text: "散户八等中等仓位账户对上涨叙事的信任增强。",
          },
          {
            step_id: "step_003",
            step_type: "order_flow",
            tick_id: tickId,
            actor_id: "retail_cluster",
            event_ref: "mkt_001",
            label: "买盘加厚",
            public_text: "散户方向买入意愿增强，盘口买盘变厚。",
          },
          {
            step_id: "step_004",
            step_type: "price_move",
            tick_id: tickId,
            actor_id: "market",
            event_ref: "mkt_002",
            label: "价格上行",
            public_text: "最新价上行并触发更多关注。",
          },
        ],
        metrics: {
          price_change_pct: 2.1,
          affected_agent_count: 9,
          confidence: 0.76,
        },
      },
      {
        chain_id: "chain_002",
        title: "卖压扩大触发风险收缩",
        summary:
          "连续大额卖盘压低盘口承接，部分高杠杆账户进入风险与强平状态。",
        last_event_ref: "risk_event_001",
        steps: [
          {
            step_id: "step_011",
            step_type: "tape_alert",
            tick_id: tickAlert,
            actor_id: "market",
            event_ref: "tape_alert_002",
            label: "盘口卖压告警",
            public_text: "盘口下方承接减弱，触发流动性收缩告警。",
          },
          {
            step_id: "step_012",
            step_type: "belief_shift",
            tick_id: tickAlert,
            actor_id: "hot_money_c",
            event_ref: "audit_graph_002",
            label: "游资降低风险偏好",
            public_text: "短线阵营在卖压扩大后转向防守，对下行风险定价上升。",
          },
          {
            step_id: "step_013",
            step_type: "order_flow",
            tick_id: tickAlert,
            actor_id: "hot_money_c",
            event_ref: "mkt_003",
            label: "撤单与减仓",
            public_text: "高敞口账户主动撤单减仓，盘口卖盘进一步加重。",
          },
          {
            step_id: "step_014",
            step_type: "risk_event",
            tick_id: tickAlert,
            actor_id: "retail_l",
            event_ref: "risk_event_001",
            label: "散户触发强平线",
            public_text: "高杠杆散户权益跌破强平线，进入强制平仓流程。",
          },
        ],
        metrics: {
          price_change_pct: -2.4,
          affected_agent_count: 6,
          confidence: 0.81,
        },
      },
    ],
  },
  chronos: {
    tracks: [
      {
        track_id: "official",
        label: "官方事实轨",
        events: [
          {
            tick_id: tickOpen,
            event_type: "official_news",
            visibility: "public",
            source: "exchange_notice",
            public_text: "交易日开盘，标的进入连续竞价。",
            event_ref: "official_001",
          },
          {
            tick_id: tickPreNoon,
            event_type: "official_news",
            visibility: "public",
            source: "exchange_notice",
            public_text: "盘中披露：标的成交量上行，未触发临时停牌。",
            event_ref: "official_002",
          },
          {
            tick_id: tickClose,
            event_type: "official_news",
            visibility: "public",
            source: "exchange_notice",
            public_text: "收盘披露：标的全天成交活跃，进入盘后披露窗口。",
            event_ref: "official_003",
          },
        ],
      },
      {
        track_id: "rumor",
        label: "公开传闻轨",
        events: [
          {
            tick_id: tickMid,
            event_type: "public_forum",
            visibility: "public",
            source: "forum",
            public_text: "公开股吧首条看多帖出现，讨论热度初步上升。",
            event_ref: "forum_post_201",
          },
          {
            tick_id: tickEarlyAfternoon,
            event_type: "public_forum",
            visibility: "public",
            source: "forum",
            public_text: "公开股吧出现看空提醒，关注流动性变化。",
            event_ref: "forum_post_202",
          },
          {
            tick_id: tickAlert,
            event_type: "market_alert",
            visibility: "public",
            source: "exchange_broadcaster",
            public_text: "盘口卖压扩大，下方承接减弱。",
            event_ref: "tape_alert_002",
          },
        ],
      },
    ],
  },
  dossier: {
    session_id: sessionId,
    symbol,
    generated_at: "2026-05-17T12:00:00+08:00",
    collapse_probability: 0.874,
    headline: "散户阵营在第 7 个节拍后出现不可逆踩踏。",
    summary:
      "公开消息、盘口卖压和高杠杆账户风险状态形成连续链路，最终导致流动性缺口扩大。",
    key_event_refs: [
      "forum_post_201",
      "forum_post_202",
      "tape_alert_001",
      "tape_alert_002",
      "risk_event_001",
      "official_003",
    ],
    risk_rank: [
      {
        agent_id: "retail_n",
        risk_state: "terminated",
        equity: 50000,
        public_reason: "账户已终止，无法继续承担交易。",
      },
      {
        agent_id: "retail_m",
        risk_state: "liquidating",
        equity: 12000,
        public_reason: "持仓进入强制清算流程，权益接近归零。",
      },
      {
        agent_id: "retail_l",
        risk_state: "margin_call",
        equity: 72000,
        public_reason: "权益回撤触发强平线，可用现金不足。",
      },
      {
        agent_id: "retail_j",
        risk_state: "warning",
        equity: 118000,
        public_reason: "杠杆敞口接近阈值，已触发预警。",
      },
      {
        agent_id: "retail_k",
        risk_state: "warning",
        equity: 96000,
        public_reason: "可用现金薄弱，应对下行能力下降。",
      },
      {
        agent_id: "hot_money_a",
        risk_state: "warning",
        equity: 2850000,
        public_reason: "短线敞口集中，盘口卖压扩大后风险暴露上升。",
      },
    ],
    forumPosts: [
      {
        post_id: "forum_post_201",
        author_agent_id: "hot_money_a",
        author_type: "hot_money",
        text: "公开股吧内容：午后承接增强，关注量能变化。",
        stance: "bullish",
        created_tick_id: tickMid,
      },
      {
        post_id: "forum_post_202",
        author_agent_id: "hot_money_d",
        author_type: "hot_money",
        text: "公开股吧内容：盘口下方承接转薄，注意短线下行风险。",
        stance: "bearish",
        created_tick_id: tickEarlyAfternoon,
      },
    ],
    endOfDay: {
      symbol,
      close_price: 15.2,
      volume: 12000000,
      turnover: 182400000,
      dragon_tiger: {
        buy_rank: [
          {
            seat_name: "拉萨团结路",
            seat_type: "retail_cluster",
            buy_amount: 50000000,
            sell_amount: 12000000,
            net_amount: 38000000,
          },
          {
            seat_name: "深圳前海路",
            seat_type: "hot_money",
            buy_amount: 32000000,
            sell_amount: 8000000,
            net_amount: 24000000,
          },
        ],
        sell_rank: [
          {
            seat_name: "机构专用",
            seat_type: "institution",
            buy_amount: 10000000,
            sell_amount: 80000000,
            net_amount: -70000000,
          },
          {
            seat_name: "上海建国路",
            seat_type: "hot_money",
            buy_amount: 6000000,
            sell_amount: 42000000,
            net_amount: -36000000,
          },
        ],
      },
    },
  },
};

demoSeed.eventsPage.events = [
  // 1. runtime.tick_state (MATCH_AND_CLEAR at tickAlert)
  {
    schema_version: "v1",
    seq: 1025,
    type: "runtime.tick_state",
    session_id: sessionId,
    tick_id: tickAlert,
    trace_id: "trace_runtime_001",
    server_time: "2024-01-02T14:02:01+08:00",
    visibility: "control_only_view",
    payload: {
      state: "MATCH_AND_CLEAR",
      previous_state: "AGENT_STEP",
      active_agent_count: 21,
      completed_agent_count: 21,
      timeout_agent_count: 0,
      can_advance: false,
    },
  },
  // 2. market.price at tickOpen (open)
  {
    schema_version: "v1",
    seq: 1026,
    type: "market.price",
    session_id: sessionId,
    tick_id: tickOpen,
    trace_id: "trace_market_open",
    server_time: "2024-01-02T09:30:02+08:00",
    visibility: "public",
    payload: {
      symbol,
      last_price: 14.5,
      volume: 20000,
      turnover: 290000,
      limit_up: 16.5,
      limit_down: 13.5,
      limit_state: "normal",
      level2: {
        bids: [
          ["14.49", 8000],
          ["14.48", 5400],
        ],
        asks: [
          ["14.51", 6200],
          ["14.52", 7800],
        ],
      },
    },
  },
  // 3. market.price at tickMid (morning rally)
  {
    schema_version: "v1",
    seq: 1027,
    type: "market.price",
    session_id: sessionId,
    tick_id: tickMid,
    trace_id: "trace_market_mid",
    server_time: "2024-01-02T10:30:02+08:00",
    visibility: "public",
    payload: {
      symbol,
      last_price: 14.85,
      volume: 45000,
      turnover: 668250,
      limit_up: 16.5,
      limit_down: 13.5,
      limit_state: "normal",
      level2: {
        bids: [
          ["14.84", 9200],
          ["14.83", 7100],
        ],
        asks: [
          ["14.86", 8200],
          ["14.87", 6500],
        ],
      },
    },
  },
  // 4. forum.post (bullish, posted at tickMid)
  {
    schema_version: "v1",
    seq: 1028,
    type: "forum.post",
    session_id: sessionId,
    tick_id: tickMid,
    trace_id: "trace_forum_201",
    server_time: "2024-01-02T10:30:05+08:00",
    visibility: "public",
    payload: demoSeed.dossier.forumPosts[0],
  },
  // 5. market.price at tickPreNoon (pre-noon level)
  {
    schema_version: "v1",
    seq: 1029,
    type: "market.price",
    session_id: sessionId,
    tick_id: tickPreNoon,
    trace_id: "trace_market_prenoon",
    server_time: "2024-01-02T11:30:02+08:00",
    visibility: "public",
    payload: {
      symbol,
      last_price: 15.05,
      volume: 62000,
      turnover: 933100,
      limit_up: 16.5,
      limit_down: 13.5,
      limit_state: "normal",
      level2: {
        bids: [
          ["15.04", 8800],
          ["15.03", 7600],
        ],
        asks: [
          ["15.06", 9100],
          ["15.07", 7200],
        ],
      },
    },
  },
  // 6. market.price at tickEarlyAfternoon (afternoon climb)
  {
    schema_version: "v1",
    seq: 1030,
    type: "market.price",
    session_id: sessionId,
    tick_id: tickEarlyAfternoon,
    trace_id: "trace_market_afternoon",
    server_time: "2024-01-02T14:00:02+08:00",
    visibility: "public",
    payload: {
      symbol,
      last_price: 15.32,
      volume: 84000,
      turnover: 1286880,
      limit_up: 16.5,
      limit_down: 13.5,
      limit_state: "normal",
      level2: {
        bids: [
          ["15.31", 9800],
          ["15.30", 8600],
        ],
        asks: [
          ["15.33", 7400],
          ["15.34", 6900],
        ],
      },
    },
  },
  // 7. forum.post (bearish, at tickEarlyAfternoon)
  {
    schema_version: "v1",
    seq: 1031,
    type: "forum.post",
    session_id: sessionId,
    tick_id: tickEarlyAfternoon,
    trace_id: "trace_forum_202",
    server_time: "2024-01-02T14:00:08+08:00",
    visibility: "public",
    payload: demoSeed.dossier.forumPosts[1],
  },
  // 8. market.price at tickAlert (current pull-back)
  {
    schema_version: "v1",
    seq: 1032,
    type: "market.price",
    session_id: sessionId,
    tick_id: tickAlert,
    trace_id: "trace_market_alert",
    server_time: "2024-01-02T14:02:02+08:00",
    visibility: "public",
    payload: demoSeed.market.price,
  },
  // 9. market.tape_alert (large sell pressure)
  {
    schema_version: "v1",
    seq: 1033,
    type: "market.tape_alert",
    session_id: sessionId,
    tick_id: tickAlert,
    trace_id: "trace_tape_001",
    server_time: "2024-01-02T14:02:03+08:00",
    visibility: "public",
    payload: demoSeed.market.tapeAlerts[0],
  },
  // 10. market.tape_alert (liquidity drain)
  {
    schema_version: "v1",
    seq: 1034,
    type: "market.tape_alert",
    session_id: sessionId,
    tick_id: tickAlert,
    trace_id: "trace_tape_002",
    server_time: "2024-01-02T14:02:04+08:00",
    visibility: "public",
    payload: demoSeed.market.tapeAlerts[1],
  },
  // 11. runtime.agent_lifecycle (retail_l triggers margin_call)
  {
    schema_version: "v1",
    seq: 1035,
    type: "runtime.agent_lifecycle",
    session_id: sessionId,
    tick_id: tickAlert,
    trace_id: "trace_lifecycle_001",
    server_time: "2024-01-02T14:02:05+08:00",
    visibility: "public",
    payload: {
      agent_id: "retail_l",
      agent_type: "retail",
      lifecycle_state: "margin_call",
      reason_code: "equity_drawdown_limit",
      public_label: "已触发强平线",
    },
  },
  // 12. agent.account_snapshot (retail_l private snapshot)
  {
    schema_version: "v1",
    seq: 1036,
    type: "agent.account_snapshot",
    session_id: sessionId,
    tick_id: tickAlert,
    trace_id: "trace_agent_001",
    server_time: "2024-01-02T14:02:06+08:00",
    visibility: "agent_private_snapshot",
    payload: demoSeed.agents.accountSnapshots[2],
  },
  // 13. audit.graph (full graph snapshot)
  {
    schema_version: "v1",
    seq: 1037,
    type: "audit.graph",
    session_id: sessionId,
    tick_id: tickAlert,
    trace_id: "trace_audit_001",
    server_time: "2024-01-02T14:02:07+08:00",
    visibility: "frontend_only",
    payload: demoSeed.snapshot.audit_graph,
  },
  // 14. audit.causal_chain
  {
    schema_version: "v1",
    seq: 1038,
    type: "audit.causal_chain",
    session_id: sessionId,
    tick_id: tickAlert,
    trace_id: "trace_chain_001",
    server_time: "2024-01-02T14:02:08+08:00",
    visibility: "frontend_only",
    payload: demoSeed.audit.causalChains[1],
  },
  // 15. market.end_of_day (close)
  {
    schema_version: "v1",
    seq: 1039,
    type: "market.end_of_day",
    session_id: sessionId,
    tick_id: tickClose,
    trace_id: "trace_eod_001",
    server_time: "2024-01-02T15:01:00+08:00",
    visibility: "public",
    payload: demoSeed.market.endOfDay,
  },
];

demoSeed.feedEvents = demoSeed.eventsPage.events;
demoSeed.agents.roster = demoSeed.snapshot.agents;
demoSeed.audit.graph = demoSeed.snapshot.audit_graph;

export const demoSession = demoSeed.session;
export const demoSnapshot = demoSeed.snapshot;
export const demoEvents = demoSeed.eventsPage.events;
export const demoMarket = demoSeed.market;
export const demoAgents = demoSeed.agents;
export const demoAudit = demoSeed.audit;
export const demoChronosTracks = demoSeed.chronos.tracks;
export const demoDossier = demoSeed.dossier;
