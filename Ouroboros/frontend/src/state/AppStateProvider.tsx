import { type ReactNode } from "react";
import { EventBufferProvider } from "./EventBufferContext";
import { RealtimeProvider } from "./RealtimeContext";
import { SessionProvider } from "./SessionContext";
import { SnapshotProvider } from "./SnapshotContext";
import { UIProvider } from "./UIContext";

export function AppStateProvider({ children }: { children: ReactNode }) {
  return (
    <UIProvider>
      <SessionProvider>
        <SnapshotProvider>
          <EventBufferProvider>
            <RealtimeProvider>{children}</RealtimeProvider>
          </EventBufferProvider>
        </SnapshotProvider>
      </SessionProvider>
    </UIProvider>
  );
}
