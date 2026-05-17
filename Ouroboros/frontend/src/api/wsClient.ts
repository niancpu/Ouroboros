import { ApiError } from "./errors";
import { createRequestId } from "./requestId";
import type {
  ApiErrorCode,
  ServerEventEnvelope,
  SystemErrorPayload,
} from "../types/api";

export type RealtimeTopic = "runtime" | "market" | "agent" | "audit";

export interface RealtimeClientOptions {
  sessionId: string;
  clientId: string;
  fromSeq?: number;
  baseUrl?: string;
  protocols?: string | string[];
  WebSocketImpl?: typeof WebSocket;
  requestIdFactory?: () => string;
}

export type RealtimeStatus =
  | "idle"
  | "connecting"
  | "open"
  | "snapshot_required"
  | "closed"
  | "error";

export interface RealtimeHandlers {
  onOpen?: () => void;
  onEvent?: (event: ServerEventEnvelope) => void;
  onControl?: (message: unknown) => void;
  onError?: (error: ApiError) => void;
  onStatus?: (status: RealtimeStatus) => void;
  onClose?: (event: CloseEvent) => void;
}

export class FrontendRealtimeClient {
  private readonly options: RealtimeClientOptions;
  private readonly requestIdFactory: () => string;
  private socket?: WebSocket;
  private lastSeq?: number;

  constructor(options: RealtimeClientOptions) {
    this.options = options;
    this.requestIdFactory = options.requestIdFactory ?? createRequestId;
    this.lastSeq = options.fromSeq;
  }

  connect(handlers: RealtimeHandlers = {}): WebSocket {
    const WebSocketCtor = this.options.WebSocketImpl ?? WebSocket;
    handlers.onStatus?.("connecting");
    const socket = new WebSocketCtor(this.buildUrl(), this.options.protocols);
    this.socket = socket;

    socket.addEventListener("open", () => {
      handlers.onStatus?.("open");
      handlers.onOpen?.();
    });

    socket.addEventListener("message", (message) => {
      const parsed = parseMessage(message.data);
      if (isServerEvent(parsed)) {
        this.lastSeq = parsed.seq;

        if (parsed.type === "system.error") {
          const error = createWsApiError(parsed as ServerEventEnvelope<SystemErrorPayload>);
          if (error.code === "SNAPSHOT_REQUIRED") {
            handlers.onStatus?.("snapshot_required");
          }
          handlers.onError?.(error);
          return;
        }

        handlers.onEvent?.(parsed);
        return;
      }

      handlers.onControl?.(parsed);
    });

    socket.addEventListener("error", () => {
      handlers.onStatus?.("error");
      handlers.onError?.(
        new ApiError({
          code: "INTERNAL_ERROR",
          message: "websocket connection error",
          retryable: true,
        }),
      );
    });

    socket.addEventListener("close", (event) => {
      handlers.onStatus?.("closed");
      handlers.onClose?.(event);
    });

    return socket;
  }

  subscribe(topics: RealtimeTopic[]): void {
    this.send({
      type: "subscribe",
      request_id: this.requestIdFactory(),
      topics,
    });
  }

  ack(lastSeq = this.lastSeq): void {
    if (lastSeq === undefined) {
      return;
    }

    this.send({
      type: "ack",
      request_id: this.requestIdFactory(),
      last_seq: lastSeq,
    });
  }

  ping(clientTime = new Date().toISOString()): void {
    this.send({
      type: "ping",
      request_id: this.requestIdFactory(),
      client_time: clientTime,
    });
  }

  close(code?: number, reason?: string): void {
    this.socket?.close(code, reason);
  }

  getLastSeq(): number | undefined {
    return this.lastSeq;
  }

  private send(message: Record<string, unknown>): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new ApiError({
        code: "SESSION_STATE_CONFLICT",
        message: "websocket is not open",
        retryable: true,
      });
    }

    this.socket.send(JSON.stringify(message));
  }

  private buildUrl(): string {
    const baseUrl = this.options.baseUrl ?? "/api/v1";
    const normalizedBase = baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
    const url = `${normalizedBase}/sessions/${encodeURIComponent(
      this.options.sessionId,
    )}/ws`;
    const params = new URLSearchParams({ client_id: this.options.clientId });

    if (this.options.fromSeq !== undefined) {
      params.set("from_seq", String(this.options.fromSeq));
    }

    if (url.startsWith("ws://") || url.startsWith("wss://")) {
      return `${url}?${params.toString()}`;
    }

    if (url.startsWith("http://") || url.startsWith("https://")) {
      return `${url.replace(/^http/, "ws")}?${params.toString()}`;
    }

    const origin =
      typeof location === "undefined"
        ? "ws://localhost"
        : location.origin.replace(/^http/, "ws");
    return `${origin}${url}?${params.toString()}`;
  }
}

function parseMessage(data: unknown): unknown {
  if (typeof data !== "string") {
    return data;
  }

  try {
    return JSON.parse(data);
  } catch {
    return data;
  }
}

function isServerEvent(value: unknown): value is ServerEventEnvelope {
  if (!value || typeof value !== "object") {
    return false;
  }

  const candidate = value as Partial<ServerEventEnvelope>;
  return (
    candidate.schema_version === "v1" &&
    typeof candidate.seq === "number" &&
    typeof candidate.type === "string" &&
    typeof candidate.session_id === "string" &&
    typeof candidate.payload === "object"
  );
}

function createWsApiError(event: ServerEventEnvelope<SystemErrorPayload>): ApiError {
  return new ApiError(event.payload, {
    requestId: undefined,
    traceId: event.trace_id,
    serverTime: event.server_time,
  });
}

export function isSnapshotRequired(error: unknown): error is ApiError & {
  code: Extract<ApiErrorCode, "SNAPSHOT_REQUIRED">;
} {
  return error instanceof ApiError && error.code === "SNAPSHOT_REQUIRED";
}
