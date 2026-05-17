import type {
  AgentType,
  ApiErrorCode,
  CausalStepType,
  EventType,
  LifecycleState,
  RiskState,
  SessionStatus,
  TickState,
  WebApiVisibility,
} from "../types/api";

export const sessionStatusLabels: Record<SessionStatus, string> = {
  created: "已创建",
  running: "运行中",
  paused: "已暂停",
  completed: "已完成",
  failed: "已失败",
};

export const connectionLabels: Record<string, string> = {
  IDLE: "未连接",
  CONNECTING: "连接中",
  OPEN: "已连接",
  RECOVERING: "恢复中",
  CLOSED: "已断开",
  ERROR: "连接异常",
  BACKEND_UNREACHABLE: "后端不可达",
};

export const eventTypeLabels: Record<EventType, string> = {
  "runtime.tick_state": "运行节拍",
  "runtime.agent_lifecycle": "生命周期",
  "market.price": "行情价格",
  "market.tape_alert": "盘口异动",
  "market.end_of_day": "盘后披露",
  "forum.post": "公开论坛",
  "agent.account_snapshot": "账户快照",
  "audit.graph": "审计图谱",
  "audit.causal_chain": "因果链",
  "system.error": "系统错误",
};

export const agentTypeLabels: Record<AgentType, string> = {
  mutual_fund: "公募机构",
  hot_money: "游资",
  quant_algo: "量化算法",
  retail: "散户",
  retail_cluster: "散户集群",
  institution: "机构",
  national_team: "国家队",
  market: "市场",
};

export const riskStateLabels: Record<RiskState, string> = {
  normal: "正常",
  warning: "预警",
  margin_call: "强平线",
  liquidating: "清算中",
  terminated: "已终止",
};

export const lifecycleStateLabels: Record<LifecycleState, string> = {
  active: "活跃",
  suspended: "已挂起",
  margin_call: "强平线",
  liquidating: "清算中",
  terminated: "已终止",
};

export const lifecycleBadgeLabels: Record<LifecycleState, string> = {
  active: "",
  suspended: "SUSPENDED",
  margin_call: "MARGIN CALL",
  liquidating: "LIQUIDATING",
  terminated: "TERMINATED",
};

export const causalStepTypeLabels: Record<CausalStepType, string> = {
  official_news: "官方新闻",
  public_message: "公开消息",
  tape_alert: "盘口异动",
  belief_shift: "信念变化",
  order_flow: "订单流",
  price_move: "价格变化",
  risk_event: "风险事件",
  end_of_day_disclosure: "盘后披露",
};

export const visibilityLabels: Record<WebApiVisibility, string> = {
  public: "公开",
  control_only_view: "控制视图",
  agent_private_snapshot: "智能体私有快照",
  frontend_only: "前端审计视图",
};

export const runtimeStateLabels: Record<TickState, string> = {
  CHRONOS_SEED: "时间种子",
  PAYLOAD_SPLIT: "载荷分发",
  AGENT_STEP: "智能体行动",
  MATCH_AND_CLEAR: "撮合清算",
  COMMIT_TICK: "提交节拍",
  FAILED: "失败",
};

export const accountFieldLabels: Record<string, string> = {
  cash: "现金",
  available_cash: "可用现金",
  positions: "持仓",
  available_shares: "可用股份",
  frozen_shares: "冻结股份",
  market_value: "市值",
  equity: "权益",
  risk_state: "风险状态",
};

export const apiErrorCodeLabels: Record<ApiErrorCode, string> = {
  BAD_REQUEST: "参数非法",
  UNAUTHORIZED: "未认证",
  FORBIDDEN: "无访问权限",
  SESSION_NOT_FOUND: "会话不存在",
  SESSION_STATE_CONFLICT: "状态冲突",
  SCHEMA_VERSION_UNSUPPORTED: "协议版本不支持",
  RATE_LIMITED: "请求过快",
  ORCHESTRATOR_BUSY: "控制面忙",
  SNAPSHOT_REQUIRED: "需要重新拉快照",
  WS_BACKPRESSURE: "消费过慢",
  INTERNAL_ERROR: "服务端错误",
};

export const symbolLabels: Record<string, string> = {
  demo_stock: "样例标的",
};

export const sessionLabels: Record<string, string> = {
  sim_001: "演示会话一",
};

export const agentNameLabels: Record<string, string> = {
  mutual_fund_a: "公募甲",
  mutual_fund_b: "公募乙",
  mutual_fund_c: "公募丙",
  mutual_fund_d: "公募丁",
  hot_money_a: "游资甲",
  hot_money_b: "游资乙",
  hot_money_c: "游资丙",
  hot_money_d: "游资丁",
  hot_money_e: "游资戊",
  quant_algo_a: "量化甲",
  quant_algo_b: "量化乙",
  retail_a: "散户一",
  retail_b: "散户二",
  retail_c: "散户三",
  retail_d: "散户四",
  retail_e: "散户五",
  retail_f: "散户六",
  retail_g: "散户七",
  retail_h: "散户八",
  retail_i: "散户九",
  retail_j: "散户十",
  retail_k: "散户十一",
  retail_l: "散户十二",
  retail_m: "散户十三",
  retail_n: "散户十四",
  retail_o: "散户十五",
  retail_p: "散户十六",
  national_team_a: "国家队甲",
  national_team_b: "国家队乙",
  retail_cluster: "散户群体",
  market: "市场",
};

export const moduleLabels: Record<string, string> = {
  CONFIG: "初始化",
  LIVE: "实时推演",
  ENTITY: "智能体",
  CHRONOS: "时间轴",
  DOSSIER: "白皮书",
};

export function labelFrom(labels: Record<string, string>, value: string | undefined | null): string {
  if (value === undefined || value === null || value === "") return "";
  return labels[value] ?? value;
}
