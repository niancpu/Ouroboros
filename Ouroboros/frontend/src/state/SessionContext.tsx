import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  type ReactNode,
} from "react";
import { ApiError } from "../api/errors";
import type { CreateSessionRequest, SessionData, StopSessionData } from "../types/api";
import { getRestClient } from "./restSingleton";
import type { SessionPhase } from "./types";

type Action =
  | { type: "create/start" }
  | { type: "create/success"; session: SessionData }
  | { type: "create/error"; error: ApiError }
  | { type: "refresh/success"; session: SessionData }
  | { type: "refresh/error"; error: ApiError }
  | { type: "control/error"; error: ApiError }
  | { type: "control/clear" }
  | { type: "terminal"; stop: StopSessionData }
  | { type: "reset"; error?: ApiError | null };

const INITIAL: SessionPhase = { kind: "none", lastError: null };

function reducer(state: SessionPhase, action: Action): SessionPhase {
  switch (action.type) {
    case "create/start":
      return { kind: "creating" };
    case "create/success":
      return { kind: "active", session: action.session, lastError: null };
    case "create/error":
      return { kind: "none", lastError: action.error };
    case "refresh/success":
      if (state.kind !== "active") return state;
      return {
        ...state,
        session: {
          ...action.session,
          start_tick_id: action.session.start_tick_id ?? state.session.start_tick_id,
          end_tick_id: action.session.end_tick_id ?? state.session.end_tick_id,
        },
      };
    case "refresh/error":
      if (state.kind !== "active") return state;
      return { ...state, lastError: action.error };
    case "control/error":
      if (state.kind !== "active") return state;
      return { ...state, lastError: action.error };
    case "control/clear":
      if (state.kind !== "active") return state;
      return { ...state, lastError: null };
    case "terminal":
      if (state.kind !== "active") return state;
      return {
        kind: "terminal",
        session: {
          ...state.session,
          status: action.stop.status,
        },
        reason: action.stop.completion_reason,
      };
    case "reset":
      return { kind: "none", lastError: action.error ?? null };
    default:
      return state;
  }
}

export interface SessionContextValue {
  phase: SessionPhase;
  sessionId: string | null;
  createSession(req: CreateSessionRequest): Promise<void>;
  refreshSession(): Promise<void>;
  recordControlError(error: ApiError): void;
  clearControlError(): void;
  markTerminal(stop: StopSessionData): void;
  reset(error?: ApiError | null): void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [phase, dispatch] = useReducer(reducer, INITIAL);
  const rest = getRestClient();

  const sessionId =
    phase.kind === "active" || phase.kind === "terminal" ? phase.session.session_id : null;

  const createSession = useCallback(
    async (req: CreateSessionRequest): Promise<void> => {
      dispatch({ type: "create/start" });
      try {
        const created = await rest.createSession(req);
        const session: SessionData = {
          session_id: created.session_id,
          status: created.status,
          current_tick_id: created.current_tick_id,
          start_tick_id: created.start_tick_id ?? req.start_tick_id,
          end_tick_id: created.end_tick_id ?? req.end_tick_id,
          tick_state: undefined,
          agent_count: 0,
          active_agent_count: 0,
          created_at: new Date().toISOString(),
        };
        dispatch({ type: "create/success", session });
      } catch (error) {
        dispatch({ type: "create/error", error: error as ApiError });
        throw error;
      }
    },
    [rest],
  );

  const refreshSession = useCallback(async (): Promise<void> => {
    if (phase.kind !== "active") return;
    try {
      const session = await rest.getSession(phase.session.session_id);
      dispatch({ type: "refresh/success", session });
    } catch (error) {
      dispatch({ type: "refresh/error", error: error as ApiError });
      throw error;
    }
  }, [phase, rest]);

  const recordControlError = useCallback((error: ApiError) => {
    dispatch({ type: "control/error", error });
  }, []);

  const clearControlError = useCallback(() => {
    dispatch({ type: "control/clear" });
  }, []);

  const markTerminal = useCallback(
    (stop: StopSessionData) => {
      if (phase.kind !== "active") return;
      dispatch({ type: "terminal", stop });
    },
    [phase],
  );

  const reset = useCallback((error?: ApiError | null) => {
    dispatch({ type: "reset", error });
  }, []);

  const value = useMemo<SessionContextValue>(
    () => ({
      phase,
      sessionId,
      createSession,
      refreshSession,
      recordControlError,
      clearControlError,
      markTerminal,
      reset,
    }),
    [phase, sessionId, createSession, refreshSession, recordControlError, clearControlError, markTerminal, reset],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}
