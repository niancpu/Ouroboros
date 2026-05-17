import type { DemoSeed } from "../types/demo";

const sessionId = "sim_001";
const symbol = "demo_stock";
const tickId = "2024-01-02T14:02:00+08:00";

export const demoSeed: DemoSeed = {
  session: {
    session_id: sessionId,
    status: "running",
    current_tick_id: tickId,
    tick_state: "AGENT_STEP",
    agent_count: 24,
    active_agent_count: 23,
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
    agents: [
      {
        agent_id: "mutual_fund_a",
        agent_type: "mutual_fund",
        lifecycle_state: "active",
        risk_state: "normal",
        equity: 5760000,
        position_value: 4560000,
      },
      {
        agent_id: "hot_money_a",
        agent_type: "hot_money",
        lifecycle_state: "active",
        risk_state: "warning",
        equity: 2480000,
        position_value: 1824000,
      },
      {
        agent_id: "retail_b",
        agent_type: "retail",
        lifecycle_state: "margin_call",
        risk_state: "margin_call",
        equity: 152000,
        position_value: 121600,
      },
    ],
    audit_graph: {
      nodes: [
        {
          agent_id: "mutual_fund_a",
          agent_type: "mutual_fund",
          belief_score: 0.31,
          position_value: 4560000,
          risk_state: "normal",
        },
        {
          agent_id: "hot_money_a",
          agent_type: "hot_money",
          belief_score: 0.72,
          position_value: 1824000,
          risk_state: "warning",
        },
        {
          agent_id: "retail_b",
          agent_type: "retail",
          belief_score: 0.58,
          position_value: 121600,
          risk_state: "margin_call",
        },
      ],
      edges: [
        {
          source: "hot_money_a",
          target: "retail_b",
          weight: 0.34,
          reason_ref: "forum_post_123",
          public_reason: "公开股吧帖子影响散户群体后，买盘意愿上升。",
        },
        {
          source: "market",
          target: "hot_money_a",
          weight: 0.22,
          reason_ref: "tape_alert_001",
          public_reason: "盘口卖压扩大后，短线阵营风险偏好下降。",
        },
      ],
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
        last_event_ref: "risk_003",
      },
    ],
  },
  eventsPage: {
    events: [],
    next_from_seq: 1032,
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
        ],
        sell_rank: [
          {
            seat_name: "机构专用",
            seat_type: "institution",
            buy_amount: 10000000,
            sell_amount: 80000000,
            net_amount: -70000000,
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
        cash: 1200000,
        available_cash: 1200000,
        positions: { demo_stock: 300000 },
        available_shares: { demo_stock: 0 },
        frozen_shares: { demo_stock: 300000 },
        market_value: 4560000,
        equity: 5760000,
        risk_state: "normal",
      },
      {
        agent_id: "retail_b",
        agent_type: "retail",
        cash: 30400,
        available_cash: 30400,
        positions: { demo_stock: 8000 },
        available_shares: { demo_stock: 2000 },
        frozen_shares: { demo_stock: 6000 },
        market_value: 121600,
        equity: 152000,
        risk_state: "margin_call",
      },
    ],
    lifecycle: [
      {
        agent_id: "retail_b",
        agent_type: "retail",
        lifecycle_state: "margin_call",
        reason_code: "equity_drawdown_limit",
        public_label: "已触发强平线",
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
            tick_id: "2024-01-02T14:00:00+08:00",
            actor_id: "hot_money_a",
            event_ref: "forum_post_123",
            label: "发布看多帖子",
            public_text: "公开帖子被散户群体看到。",
          },
          {
            step_id: "step_002",
            step_type: "belief_shift",
            tick_id: tickId,
            actor_id: "retail_b",
            event_ref: "audit_graph_001",
            label: "散户信念上升",
            public_text: "散户 B 对上涨叙事的信任增强。",
          },
          {
            step_id: "step_003",
            step_type: "order_flow",
            tick_id: tickId,
            actor_id: "retail_cluster",
            event_ref: "mkt_001",
            label: "买盘增加",
            public_text: "散户方向买入意愿增强，盘口买盘变厚。",
          },
          {
            step_id: "step_004",
            step_type: "price_move",
            tick_id: "2024-01-02T14:03:00+08:00",
            actor_id: "market",
            event_ref: "mkt_002",
            label: "价格上涨",
            public_text: "最新价上行并触发更多关注。",
          },
        ],
        metrics: {
          price_change_pct: 2.1,
          affected_agent_count: 8,
          confidence: 0.76,
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
            tick_id: "2024-01-02T09:30:00+08:00",
            event_type: "official_news",
            visibility: "public",
            source: "exchange_notice",
            public_text: "交易日开盘，标的进入连续竞价。",
            event_ref: "official_001",
          },
        ],
      },
      {
        track_id: "rumor",
        label: "公开传闻轨",
        events: [
          {
            tick_id: "2024-01-02T14:00:00+08:00",
            event_type: "public_forum",
            visibility: "public",
            source: "forum",
            public_text: "公开股吧出现看多帖子，讨论热度上升。",
            event_ref: "forum_post_123",
          },
          {
            tick_id: tickId,
            event_type: "market_alert",
            visibility: "public",
            source: "exchange_broadcaster",
            public_text: "盘口卖压扩大，下方承接减弱。",
            event_ref: "tape_alert_001",
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
    key_event_refs: ["forum_post_123", "tape_alert_001", "risk_003"],
    risk_rank: [
      {
        agent_id: "retail_b",
        risk_state: "margin_call",
        equity: 152000,
        public_reason: "权益回撤触发强平线。",
      },
      {
        agent_id: "hot_money_a",
        risk_state: "warning",
        equity: 2480000,
        public_reason: "盘口卖压扩大后风险暴露上升。",
      },
    ],
    forumPosts: [
      {
        post_id: "forum_post_123",
        author_agent_id: "hot_money_a",
        author_type: "hot_money",
        text: "公开股吧内容：午后承接增强，关注量能变化。",
        stance: "bullish",
        created_tick_id: "2024-01-02T14:00:00+08:00",
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
        ],
        sell_rank: [
          {
            seat_name: "机构专用",
            seat_type: "institution",
            buy_amount: 10000000,
            sell_amount: 80000000,
            net_amount: -70000000,
          },
        ],
      },
    },
  },
};

demoSeed.eventsPage.events = [
  {
    schema_version: "v1",
    seq: 1025,
    type: "runtime.tick_state",
    session_id: sessionId,
    tick_id: tickId,
    trace_id: "trace_runtime_001",
    server_time: "2024-01-02T14:02:01+08:00",
    visibility: "control_only_view",
    payload: {
      state: "MATCH_AND_CLEAR",
      previous_state: "AGENT_STEP",
      active_agent_count: 23,
      completed_agent_count: 23,
      timeout_agent_count: 1,
      can_advance: false,
    },
  },
  {
    schema_version: "v1",
    seq: 1026,
    type: "market.price",
    session_id: sessionId,
    tick_id: tickId,
    trace_id: "trace_market_001",
    server_time: "2024-01-02T14:02:02+08:00",
    visibility: "public",
    payload: demoSeed.market.price,
  },
  {
    schema_version: "v1",
    seq: 1027,
    type: "market.tape_alert",
    session_id: sessionId,
    tick_id: tickId,
    trace_id: "trace_tape_001",
    server_time: "2024-01-02T14:02:03+08:00",
    visibility: "public",
    payload: demoSeed.market.tapeAlerts[0],
  },
  {
    schema_version: "v1",
    seq: 1028,
    type: "forum.post",
    session_id: sessionId,
    tick_id: "2024-01-02T14:00:00+08:00",
    trace_id: "trace_forum_001",
    server_time: "2024-01-02T14:00:01+08:00",
    visibility: "public",
    payload: demoSeed.dossier.forumPosts[0],
  },
  {
    schema_version: "v1",
    seq: 1029,
    type: "agent.account_snapshot",
    session_id: sessionId,
    tick_id: tickId,
    trace_id: "trace_agent_001",
    server_time: "2024-01-02T14:02:04+08:00",
    visibility: "agent_private_snapshot",
    payload: demoSeed.agents.accountSnapshots[1],
  },
  {
    schema_version: "v1",
    seq: 1030,
    type: "audit.graph",
    session_id: sessionId,
    tick_id: tickId,
    trace_id: "trace_audit_001",
    server_time: "2024-01-02T14:02:05+08:00",
    visibility: "frontend_only",
    payload: demoSeed.snapshot.audit_graph,
  },
  {
    schema_version: "v1",
    seq: 1031,
    type: "audit.causal_chain",
    session_id: sessionId,
    tick_id: tickId,
    trace_id: "trace_chain_001",
    server_time: "2024-01-02T14:02:06+08:00",
    visibility: "frontend_only",
    payload: demoSeed.audit.causalChains[0],
  },
  {
    schema_version: "v1",
    seq: 1032,
    type: "market.end_of_day",
    session_id: sessionId,
    tick_id: "2024-01-02T15:00:00+08:00",
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
