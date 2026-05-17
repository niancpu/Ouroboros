import type { ApiError } from "../api/errors";
import type {
  ApiErrorBody,
  ServerEventEnvelope,
  SessionData,
  SnapshotData,
} from "../types/api";

export type VisualState =
  | "empty"
  | "loading"
  | "live"
  | "paused"
  | "recovering"
  | "error"
  | "terminal"
  | "replay";

export type ControlAction = "start" | "pause" | "step" | "stop";

export type SessionPhase =
  | { kind: "none"; lastError: ApiError | null }
  | { kind: "creating" }
  | { kind: "active"; session: SessionData; lastError: ApiError | null }
  | { kind: "terminal"; session: SessionData; reason: string };

export type SnapshotPhase =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; snapshot: SnapshotData; loadedAt: string }
  | { kind: "error"; error: ApiError };

export type RealtimePhase =
  | { kind: "idle" }
  | { kind: "connecting" }
  | { kind: "open" }
  | { kind: "recovering" }
  | { kind: "closed"; reason?: string }
  | { kind: "error"; error: ApiError };

export interface RealtimeStartHandlers {
  onEvent(event: ServerEventEnvelope): void;
  onSnapshotRequired(): void;
  onError?(error: ApiError): void;
}

export interface EventBufferState {
  events: ServerEventEnvelope[];
  bySeq: Map<number, number>;
}

export function emptySessionPhase(lastError: ApiError | null = null): SessionPhase {
  return { kind: "none", lastError };
}

export function apiErrorFromBody(body: ApiErrorBody): ApiError {
  return Object.assign(new Error(body.message), {
    name: "ApiError",
    code: body.code,
    retryable: body.retryable,
    details: body.details,
  }) as unknown as ApiError;
}
