import { labelFrom, runtimeStateLabels, visibilityLabels } from "../i18n/labels";
import type { ServerEventEnvelope } from "../types/api";

export function readPayloadField<TFallback extends string | number>(
  event: ServerEventEnvelope,
  field: string,
  fallback: TFallback,
): string | number | TFallback {
  const payload = event.payload as unknown;
  if (!payload || typeof payload !== "object") return fallback;
  const value = (payload as Record<string, unknown>)[field];
  return typeof value === "string" || typeof value === "number" ? value : fallback;
}

export function eventText(event: ServerEventEnvelope): string {
  const publicText = readPayloadField(event, "public_text", "");
  if (publicText) return String(publicText);
  const text = readPayloadField(event, "text", "");
  if (text) return String(text);
  const message = readPayloadField(event, "message", "");
  if (message) return String(message);
  const state = readPayloadField(event, "state", "");
  if (state) return labelFrom(runtimeStateLabels, String(state));
  return labelFrom(visibilityLabels, event.visibility);
}
