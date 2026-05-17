import {
  agentNameLabels,
  labelFrom,
  riskStateLabels,
  sessionLabels,
  symbolLabels,
} from "../i18n/labels";

export function formatTick(value: string | undefined | null): string {
  if (!value) return "";
  return value.replace("T", " ").replace("+08:00", "");
}

export function formatPercent(value: number): string {
  if (!Number.isFinite(value)) return "0%";
  return `${Math.round(value * 100)}%`;
}

export function formatAccountValue(label: string, value: unknown): string {
  if (typeof value === "number") return value.toLocaleString("en-US");
  if (label === "risk_state" && typeof value === "string") {
    return labelFrom(riskStateLabels, value);
  }
  return value === undefined || value === null ? "" : String(value);
}

export function displayAgentName(agentId: string): string {
  return labelFrom(agentNameLabels, agentId) || agentId;
}

export function displaySymbol(symbol: string): string {
  return labelFrom(symbolLabels, symbol) || symbol;
}

export function displaySession(sessionId: string): string {
  return labelFrom(sessionLabels, sessionId) || sessionId;
}

export function formatAgentCode(agentId: string, roster: ReadonlyArray<{ agent_id: string }>): string {
  const idx = roster.findIndex((entry) => entry.agent_id === agentId);
  if (idx >= 0) return `AGT-${String(idx + 1).padStart(2, "0")}`;
  let hash = 0;
  for (let i = 0; i < agentId.length; i += 1) {
    hash = (hash * 31 + agentId.charCodeAt(i)) & 0xffff;
  }
  return `AGT-${String((hash % 99) + 1).padStart(2, "0")}`;
}

export function formatErrorBadge(code: string, message: string): string {
  return `[ERR ${code}] ${message}`;
}
