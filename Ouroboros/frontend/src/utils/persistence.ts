import { useCallback, useEffect, useState } from "react";
import { MODULE_KEYS, type ModuleKey, STORAGE_KEYS } from "../config/constants";

export function readStoredModule(): ModuleKey | null {
  if (typeof window === "undefined") return null;
  const stored = window.localStorage.getItem(STORAGE_KEYS.activeModule);
  return MODULE_KEYS.includes(stored as ModuleKey) ? (stored as ModuleKey) : null;
}

export function writeStoredModule(value: ModuleKey): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEYS.activeModule, value);
}

export function readOrCreateClientId(): string {
  if (typeof window === "undefined") return `client_${Date.now().toString(36)}`;
  const existing = window.localStorage.getItem(STORAGE_KEYS.clientId);
  if (existing) return existing;
  const fresh =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? `client_${crypto.randomUUID()}`
      : `client_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
  window.localStorage.setItem(STORAGE_KEYS.clientId, fresh);
  return fresh;
}

export function usePersistentModule(initialValue: ModuleKey): readonly [ModuleKey, (next: ModuleKey) => void] {
  const [value, setValue] = useState<ModuleKey>(() => readStoredModule() ?? initialValue);

  useEffect(() => {
    writeStoredModule(value);
  }, [value]);

  const setPersistentValue = useCallback((next: ModuleKey) => {
    setValue(next);
  }, []);

  return [value, setPersistentValue] as const;
}
