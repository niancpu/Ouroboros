import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  type ReactNode,
} from "react";
import { EVENT_BUFFER_MAX } from "../config/constants";
import type { ServerEventEnvelope } from "../types/api";

type Action =
  | { type: "append"; event: ServerEventEnvelope }
  | { type: "appendBatch"; events: ServerEventEnvelope[] }
  | { type: "reset" };

interface State {
  events: ServerEventEnvelope[];
}

const INITIAL: State = { events: [] };

function appendOne(events: ServerEventEnvelope[], event: ServerEventEnvelope): ServerEventEnvelope[] {
  if (events.some((existing) => existing.seq === event.seq)) return events;
  if (events.length > 0 && event.tick_id && events[events.length - 1].tick_id) {
    const latestTickId = events[events.length - 1].tick_id;
    if (event.tick_id < latestTickId) {
      console.warn("EventBuffer: tick_id non-monotonic", { incoming: event.tick_id, latest: latestTickId, seq: event.seq });
    }
  }
  const next = events.concat(event);
  next.sort((a, b) => a.seq - b.seq);
  if (next.length > EVENT_BUFFER_MAX) {
    return next.slice(next.length - EVENT_BUFFER_MAX);
  }
  return next;
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "append":
      return { events: appendOne(state.events, action.event) };
    case "appendBatch": {
      let next = state.events;
      for (const event of action.events) {
        next = appendOne(next, event);
      }
      return { events: next };
    }
    case "reset":
      return INITIAL;
    default:
      return state;
  }
}

export interface EventBufferContextValue {
  events: ReadonlyArray<ServerEventEnvelope>;
  append(event: ServerEventEnvelope): void;
  appendBatch(events: ServerEventEnvelope[]): void;
  reset(): void;
}

const EventBufferContext = createContext<EventBufferContextValue | null>(null);

export function EventBufferProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, INITIAL);

  const append = useCallback((event: ServerEventEnvelope) => {
    dispatch({ type: "append", event });
  }, []);

  const appendBatch = useCallback((events: ServerEventEnvelope[]) => {
    dispatch({ type: "appendBatch", events });
  }, []);

  const reset = useCallback(() => {
    dispatch({ type: "reset" });
  }, []);

  const value = useMemo<EventBufferContextValue>(
    () => ({ events: state.events, append, appendBatch, reset }),
    [state.events, append, appendBatch, reset],
  );

  return <EventBufferContext.Provider value={value}>{children}</EventBufferContext.Provider>;
}

export function useEvents(): EventBufferContextValue {
  const ctx = useContext(EventBufferContext);
  if (!ctx) throw new Error("useEvents must be used within EventBufferProvider");
  return ctx;
}
