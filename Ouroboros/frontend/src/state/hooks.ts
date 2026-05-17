import { useCallback, useMemo, useState } from "react";
import { ApiError } from "../api/errors";
import { useSession } from "./SessionContext";
import { useSnapshot } from "./SnapshotContext";
import { useRealtime } from "./RealtimeContext";
import { useUI } from "./UIContext";
import { getRestClient } from "./restSingleton";
import type { ControlAction, VisualState } from "./types";

export interface ControlCommandHook {
  run(): Promise<void>;
  inFlight: boolean;
  error: ApiError | null;
  clearError(): void;
}

export function useControlCommand(action: ControlAction): ControlCommandHook {
  const session = useSession();
  const ui = useUI();
  const [inFlight, setInFlight] = useState(false);
  const rest = getRestClient();

  const run = useCallback(async (): Promise<void> => {
    if (session.phase.kind !== "active") return;
    const sessionId = session.phase.session.session_id;
    setInFlight(true);
    ui.clearControlError(action);
    try {
      if (action === "start") {
        await rest.startSession(sessionId);
      } else if (action === "pause") {
        await rest.pauseSession(sessionId);
      } else if (action === "step") {
        await rest.stepSession(sessionId);
      } else if (action === "stop") {
        const data = await rest.stopSession(sessionId);
        session.markTerminal(data.completion_reason);
        return;
      }
      await session.refreshSession();
    } catch (error) {
      const apiError = error as ApiError;
      ui.recordControlError(action, apiError);
      session.recordControlError(apiError);
      throw apiError;
    } finally {
      setInFlight(false);
    }
  }, [action, rest, session, ui]);

  const clearError = useCallback(() => ui.clearControlError(action), [action, ui]);

  return useMemo(
    () => ({
      run,
      inFlight,
      error: ui.controlErrors[action],
      clearError,
    }),
    [run, inFlight, ui.controlErrors, action, clearError],
  );
}

export function useDerivedVisualState(): VisualState {
  const session = useSession();
  const snapshot = useSnapshot();
  const realtime = useRealtime();

  if (snapshot.phase.kind === "error" || realtime.phase.kind === "error") return "error";
  if (realtime.phase.kind === "recovering") return "recovering";
  if (snapshot.phase.kind === "loading") return "loading";
  if (session.phase.kind === "terminal") return "terminal";

  if (session.phase.kind === "active") {
    const status = session.phase.session.status;
    if (status === "completed" || status === "failed") return "terminal";
    if (status === "paused") return "paused";
    if (snapshot.phase.kind === "ready" && realtime.phase.kind === "open") return "live";
    if (snapshot.phase.kind === "idle") return "empty";
    return "loading";
  }

  return "empty";
}
