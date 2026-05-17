export type ModuleKey = "CONFIG" | "LIVE" | "ENTITY" | "CHRONOS" | "DOSSIER";

export const MODULE_KEYS: ModuleKey[] = ["CONFIG", "LIVE", "ENTITY", "CHRONOS", "DOSSIER"];

export const REALTIME_TOPICS = ["runtime", "market", "agent", "audit"] as const;

export const EVENT_BUFFER_MAX = 5000;

export const FEED_EVENT_TYPES = [
  "runtime.tick_state",
  "runtime.agent_lifecycle",
  "market.tape_alert",
  "forum.post",
  "system.error",
] as const;

export const LIVE_FALLBACK_TICKS = [
  "2024-01-02T09:30:00+08:00",
  "2024-01-02T10:30:00+08:00",
  "2024-01-02T11:30:00+08:00",
  "2024-01-02T14:00:00+08:00",
  "2024-01-02T14:02:00+08:00",
  "2024-01-02T15:00:00+08:00",
];

export const STORAGE_KEYS = {
  activeModule: "ouroboros.activeModule",
  clientId: "ouroboros.clientId",
} as const;
