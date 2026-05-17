import type { ApiErrorBody, ApiErrorCode, ApiErrorEnvelope } from "../types/api";

export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly retryable: boolean;
  readonly status?: number;
  readonly requestId?: string;
  readonly traceId?: string;
  readonly serverTime?: string;
  readonly details?: Record<string, unknown>;

  constructor(body: ApiErrorBody, context: ApiErrorContext = {}) {
    super(body.message);
    this.name = "ApiError";
    this.code = body.code;
    this.retryable = body.retryable;
    this.status = context.status;
    this.requestId = context.requestId;
    this.traceId = context.traceId;
    this.serverTime = context.serverTime;
    this.details = body.details;
  }
}

export interface ApiErrorContext {
  status?: number;
  requestId?: string;
  traceId?: string;
  serverTime?: string;
}

export function isApiErrorEnvelope(value: unknown): value is ApiErrorEnvelope {
  if (!value || typeof value !== "object") {
    return false;
  }

  const candidate = value as Partial<ApiErrorEnvelope>;
  return Boolean(candidate.error && typeof candidate.error.message === "string");
}

export function createApiErrorFromEnvelope(
  envelope: ApiErrorEnvelope,
  status?: number,
): ApiError {
  return new ApiError(envelope.error, {
    status,
    requestId: envelope.request_id,
    traceId: envelope.trace_id,
    serverTime: envelope.server_time,
  });
}

export function createNetworkApiError(message: string, status?: number): ApiError {
  return new ApiError(
    {
      code: "INTERNAL_ERROR",
      message,
      retryable: true,
    },
    { status },
  );
}
