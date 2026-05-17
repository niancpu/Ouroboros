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
const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;
const RECONNECT_MAX_ATTEMPTS = 8;

export function RealtimeProvider({ children }: { children: ReactNode }) {
  const [phase, dispatch] = useReducer(reducer, INITIAL);
  const clientIdRef = useRef<string>(readOrCreateClientId());
  const wsClientRef = useRef<FrontendRealtimeClient | null>(null);
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptsRef = useRef<number>(0);
  const intentionalStopRef = useRef<boolean>(false);
  const lastStartArgsRef = useRef<{
    sessionId: string;
    fromSeq: number;
    handlers: RealtimeStartHandlers;
  } | null>(null);
  // Holds latest start fn reference to avoid stale closure in onClose
  const reconnectRef = useRef<(() => void) | null>(null);

  const clearPing = useCallback(() => {
    if (pingTimerRef.current) {
      clearInterval(pingTimerRef.current);
      pingTimerRef.current = null;
    }
  }, []);

  const clearReconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const stop = useCallback(
    (reason?: string) => {
      intentionalStopRef.current = true;
      clearReconnect();
      clearPing();
      wsClientRef.current?.close(1000, reason);
      wsClientRef.current = null;
      dispatch({ type: "closed", reason });
    },
    [clearPing, clearReconnect],
  );

  const start = useCallback(
    (sessionId: string, fromSeq: number, handlers: RealtimeStartHandlers) => {
      intentionalStopRef.current = false;
      reconnectAttemptsRef.current = 0;
      lastStartArgsRef.current = { sessionId, fromSeq, handlers };

      // Update reconnect ref so onClose closure always calls latest start
      reconnectRef.current = () => start(sessionId, fromSeq, handlers);

      stop();
      // stop() sets intentionalStopRef = true, reset after
      intentionalStopRef.current = false;

      dispatch({ type: "connecting" });
      const client = new FrontendRealtimeClient({
        sessionId,
        clientId: clientIdRef.current,
        fromSeq,
      });
      wsClientRef.current = client;

      client.connect({
        onOpen: () => {
          reconnectAttemptsRef.current = 0;
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

          if (
            !intentionalStopRef.current &&
            lastStartArgsRef.current &&
            reconnectAttemptsRef.current < RECONNECT_MAX_ATTEMPTS
          ) {
            const attempts = reconnectAttemptsRef.current;
            const delay = Math.min(
              RECONNECT_BASE_MS * Math.pow(2, attempts),
              RECONNECT_MAX_MS,
            );
            reconnectAttemptsRef.current = attempts + 1;
            reconnectTimerRef.current = setTimeout(() => {
              if (!intentionalStopRef.current && reconnectRef.current) {
                reconnectRef.current();
              }
            }, delay);
          }
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
      intentionalStopRef.current = true;
      clearReconnect();
      clearPing();
      wsClientRef.current?.close(1000, "unmount");
      wsClientRef.current = null;
    };
  }, [clearPing, clearReconnect]);

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
