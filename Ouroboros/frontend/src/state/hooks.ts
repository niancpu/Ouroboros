import { useCallback, useMemo, useState } from "react";
import { ApiError } from "../api/errors";
import { useEvents } from "./EventBufferContext";
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

// module-level shared lock — prevents duplicate non-stop control commands per session
const _activeSessionCommands = new Map<string, ControlAction>();
const TERMINAL_SESSION_STATUSES = new Set(["completed", "failed"]);

export function useControlCommand(action: ControlAction): ControlCommandHook {
  const session = useSession();
  const snapshot = useSnapshot();
  const events = useEvents();
  const realtime = useRealtime();
  const ui = useUI();
  const [inFlight, setInFlight] = useState(false);
  const rest = getRestClient();

  const run = useCallback(async (): Promise<void> => {
    if (session.phase.kind !== "active") return;
    const sessionId = session.phase.session.session_id;
    const commandKey = sessionId;
    const activeCommand = _activeSessionCommands.get(commandKey);
    if (activeCommand) {
      if (action !== "stop" || activeCommand === "stop") return;
    }
    if (TERMINAL_SESSION_STATUSES.has(session.phase.session.status)) return;

    _activeSessionCommands.set(commandKey, action);
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
        session.markTerminal(data);
        return;
      }
      await session.refreshSession();
    } catch (error) {
      const apiError = error as ApiError;
      if (apiError.code === "SESSION_NOT_FOUND") {
        realtime.stop("session_not_found");
        events.reset();
        snapshot.reset();
        session.reset(apiError);
        ui.clearControlErrors();
        ui.setSelectedAgentId(null);
        ui.setActiveModule("CONFIG");
      }
      ui.recordControlError(action, apiError);
      session.recordControlError(apiError);
      throw apiError;
    } finally {
      if (_activeSessionCommands.get(commandKey) === action) {
        _activeSessionCommands.delete(commandKey);
      }
      setInFlight(false);
    }
  }, [action, events, realtime, rest, session, snapshot, ui]);

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
