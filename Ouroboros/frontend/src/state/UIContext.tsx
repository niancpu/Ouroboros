import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { ApiError } from "../api/errors";
import { type ModuleKey } from "../config/constants";
import { usePersistentModule } from "../utils/persistence";
import type { ControlAction } from "./types";

type ControlErrorMap = Record<ControlAction, ApiError | null>;

const EMPTY_CONTROL_ERRORS: ControlErrorMap = {
  start: null,
  pause: null,
  step: null,
  stop: null,
};

export interface UIContextValue {
  activeModule: ModuleKey;
  setActiveModule(next: ModuleKey): void;
  selectedAgentId: string | null;
  setSelectedAgentId(next: string | null): void;
  controlErrors: ControlErrorMap;
  recordControlError(action: ControlAction, error: ApiError): void;
  clearControlError(action: ControlAction): void;
  globalError: ApiError | null;
  setGlobalError(next: ApiError | null): void;
}

const UIContext = createContext<UIContextValue | null>(null);

export function UIProvider({ children }: { children: ReactNode }) {
  const [activeModule, setActiveModule] = usePersistentModule("CONFIG");
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [controlErrors, setControlErrors] = useState<ControlErrorMap>(EMPTY_CONTROL_ERRORS);
  const [globalError, setGlobalError] = useState<ApiError | null>(null);

  const recordControlError = useCallback((action: ControlAction, error: ApiError) => {
    setControlErrors((current) => ({ ...current, [action]: error }));
  }, []);

  const clearControlError = useCallback((action: ControlAction) => {
    setControlErrors((current) => ({ ...current, [action]: null }));
  }, []);

  const value = useMemo<UIContextValue>(
    () => ({
      activeModule,
      setActiveModule,
      selectedAgentId,
      setSelectedAgentId,
      controlErrors,
      recordControlError,
      clearControlError,
      globalError,
      setGlobalError,
    }),
    [
      activeModule,
      setActiveModule,
      selectedAgentId,
      controlErrors,
      recordControlError,
      clearControlError,
      globalError,
    ],
  );

  return <UIContext.Provider value={value}>{children}</UIContext.Provider>;
}

export function useUI(): UIContextValue {
  const ctx = useContext(UIContext);
  if (!ctx) throw new Error("useUI must be used within UIProvider");
  return ctx;
}
