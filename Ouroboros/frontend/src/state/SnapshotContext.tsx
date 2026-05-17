import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  type ReactNode,
} from "react";
import { ApiError } from "../api/errors";
import type { SnapshotData } from "../types/api";
import { getRestClient } from "./restSingleton";
import type { SnapshotPhase } from "./types";

type Action =
  | { type: "load/start" }
  | { type: "load/success"; snapshot: SnapshotData; loadedAt: string }
  | { type: "load/error"; error: ApiError }
  | { type: "invalidate" }
  | { type: "reset" };

const INITIAL: SnapshotPhase = { kind: "idle" };

function reducer(state: SnapshotPhase, action: Action): SnapshotPhase {
  switch (action.type) {
    case "load/start":
      return { kind: "loading" };
    case "load/success":
      return { kind: "ready", snapshot: action.snapshot, loadedAt: action.loadedAt };
    case "load/error":
      return { kind: "error", error: action.error };
    case "invalidate":
      if (state.kind === "ready") return { kind: "idle" };
      return state;
    case "reset":
      return INITIAL;
    default:
      return state;
  }
}

export interface SnapshotContextValue {
  phase: SnapshotPhase;
  load(sessionId: string): Promise<SnapshotData>;
  invalidate(): void;
  reset(): void;
}

const SnapshotContext = createContext<SnapshotContextValue | null>(null);

export function SnapshotProvider({ children }: { children: ReactNode }) {
  const [phase, dispatch] = useReducer(reducer, INITIAL);
  const rest = getRestClient();

  const load = useCallback(
    async (sessionId: string): Promise<SnapshotData> => {
      dispatch({ type: "load/start" });
      try {
        const snapshot = await rest.getSnapshot(sessionId);
        dispatch({
          type: "load/success",
          snapshot,
          loadedAt: new Date().toISOString(),
        });
        return snapshot;
      } catch (error) {
        dispatch({ type: "load/error", error: error as ApiError });
        throw error;
      }
    },
    [rest],
  );

  const invalidate = useCallback(() => {
    dispatch({ type: "invalidate" });
  }, []);

  const reset = useCallback(() => {
    dispatch({ type: "reset" });
  }, []);

  const value = useMemo<SnapshotContextValue>(
    () => ({ phase, load, invalidate, reset }),
    [phase, load, invalidate, reset],
  );

  return <SnapshotContext.Provider value={value}>{children}</SnapshotContext.Provider>;
}

export function useSnapshot(): SnapshotContextValue {
  const ctx = useContext(SnapshotContext);
  if (!ctx) throw new Error("useSnapshot must be used within SnapshotProvider");
  return ctx;
}
