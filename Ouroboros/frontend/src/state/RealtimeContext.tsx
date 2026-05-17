import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  type ReactNode,
} from "react";
import { ApiError } from "../api/errors";
import { FrontendRealtimeClient } from "../api/wsClient";
import { REALTIME_TOPICS } from "../config/constants";
import type { ServerEventEnvelope } from "../types/api";
import { readOrCreateClientId } from "../utils/persistence";
import type { RealtimePhase, RealtimeStartHandlers } from "./types";

type Action =
  | { type: "connecting" }
  | { type: "open" }
  | { type: "recovering" }
  | { type: "closed"; reason?: string }
  | { type: "error"; error: ApiError }
  | { type: "reset" };

const INITIAL: RealtimePhase = { kind: "idle" };

function reducer(state: RealtimePhase, action: Action): RealtimePhase {
  switch (action.type) {
    case "connecting":
      return { kind: "connecting" };
    case "open":
      return { kind: "open" };
    case "recovering":
      return { kind: "recovering" };
    case "closed":
      return { kind: "closed", reason: action.reason };
    case "error":
      return { kind: "error", error: action.error };
    case "reset":
      return INITIAL;
    default:
      return state;
  }
}

export interface RealtimeContextValue {
  phase: RealtimePhase;
  clientId: string;
  start(sessionId: string, fromSeq: number, handlers: RealtimeStartHandlers): void;
  stop(reason?: string): void;
  ack(lastSeq?: number): void;
}

const RealtimeContext = createContext<RealtimeContextValue | null>(null);

const PING_INTERVAL_MS = 25_000;

export function RealtimeProvider({ children }: { children: ReactNode }) {
  const [phase, dispatch] = useReducer(reducer, INITIAL);
  const clientIdRef = useRef<string>(readOrCreateClientId());
  const wsClientRef = useRef<FrontendRealtimeClient | null>(null);
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearPing = useCallback(() => {
    if (pingTimerRef.current) {
      clearInterval(pingTimerRef.current);
      pingTimerRef.current = null;
    }
  }, []);

  const stop = useCallback(
    (reason?: string) => {
      clearPing();
      wsClientRef.current?.close(1000, reason);
      wsClientRef.current = null;
      dispatch({ type: "closed", reason });
    },
    [clearPing],
  );

  const start = useCallback(
    (sessionId: string, fromSeq: number, handlers: RealtimeStartHandlers) => {
      stop();
      dispatch({ type: "connecting" });
      const client = new FrontendRealtimeClient({
        sessionId,
        clientId: clientIdRef.current,
        fromSeq,
      });
      wsClientRef.current = client;

      client.connect({
        onOpen: () => {
          dispatch({ type: "open" });
          try {
            client.subscribe([...REALTIME_TOPICS]);
          } catch (error) {
            dispatch({ type: "error", error: error as ApiError });
          }
          pingTimerRef.current = setInterval(() => {
            try {
              client.ping();
            } catch {
              /* socket may not be open yet — next interval retries */
            }
          }, PING_INTERVAL_MS);
        },
        onEvent: (event: ServerEventEnvelope) => {
          handlers.onEvent(event);
        },
        onError: (error: ApiError) => {
          if (error.code === "SNAPSHOT_REQUIRED") {
            dispatch({ type: "recovering" });
            handlers.onSnapshotRequired();
            return;
          }
          handlers.onError?.(error);
          dispatch({ type: "error", error });
        },
        onClose: (closeEvent) => {
          clearPing();
          dispatch({ type: "closed", reason: closeEvent.reason });
        },
        onStatus: () => {
          /* phase mirroring is handled per-event above */
        },
      });
    },
    [clearPing, stop],
  );

  const ack = useCallback((lastSeq?: number) => {
    try {
      wsClientRef.current?.ack(lastSeq);
    } catch {
      /* swallow when socket not open; next reconnect handles backfill */
    }
  }, []);

  useEffect(() => {
    return () => {
      clearPing();
      wsClientRef.current?.close(1000, "unmount");
      wsClientRef.current = null;
    };
  }, [clearPing]);

  const value = useMemo<RealtimeContextValue>(
    () => ({ phase, clientId: clientIdRef.current, start, stop, ack }),
    [phase, start, stop, ack],
  );

  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
}

export function useRealtime(): RealtimeContextValue {
  const ctx = useContext(RealtimeContext);
  if (!ctx) throw new Error("useRealtime must be used within RealtimeProvider");
  return ctx;
}
