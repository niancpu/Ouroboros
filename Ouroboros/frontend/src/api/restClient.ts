import {
  createApiErrorFromEnvelope,
  createNetworkApiError,
  isApiErrorEnvelope,
} from "./errors";
import { createRequestId } from "./requestId";
import type {
  ApiSuccessEnvelope,
  CreateSessionData,
  CreateSessionRequest,
  EventsPage,
  PauseSessionData,
  PauseSessionRequest,
  SessionData,
  SnapshotData,
  StartSessionData,
  StartSessionRequest,
  StepSessionData,
  StepSessionRequest,
  StopSessionData,
  StopSessionRequest,
} from "../types/api";

export interface RestClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  requestIdFactory?: () => string;
}

export interface EventsQuery {
  fromSeq?: number;
  limit?: number;
}

const DEFAULT_BASE_URL = "/api/v1";

export class ControlRestClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  private readonly requestIdFactory: () => string;

  constructor(options: RestClientOptions = {}) {
    this.baseUrl = trimTrailingSlash(options.baseUrl ?? DEFAULT_BASE_URL);
    this.fetchImpl = options.fetchImpl ?? fetch.bind(globalThis);
    this.requestIdFactory = options.requestIdFactory ?? createRequestId;
  }

  createSession(request: CreateSessionRequest): Promise<CreateSessionData> {
    return this.request<CreateSessionData>("/sessions", {
      method: "POST",
      body: request,
    });
  }

  getSession(sessionId: string): Promise<SessionData> {
    return this.request<SessionData>(`/sessions/${encodeURIComponent(sessionId)}`);
  }

  startSession(
    sessionId: string,
    request: StartSessionRequest = { mode: "continuous" },
  ): Promise<StartSessionData> {
    return this.request<StartSessionData>(
      `/sessions/${encodeURIComponent(sessionId)}/start`,
      {
        method: "POST",
        body: request,
      },
    );
  }

  pauseSession(
    sessionId: string,
    request: PauseSessionRequest = { reason: "operator_pause" },
  ): Promise<PauseSessionData> {
    return this.request<PauseSessionData>(
      `/sessions/${encodeURIComponent(sessionId)}/pause`,
      {
        method: "POST",
        body: request,
      },
    );
  }

  stepSession(
    sessionId: string,
    request: StepSessionRequest = { ticks: 1 },
  ): Promise<StepSessionData> {
    return this.request<StepSessionData>(
      `/sessions/${encodeURIComponent(sessionId)}/step`,
      {
        method: "POST",
        body: request,
      },
    );
  }

  stopSession(
    sessionId: string,
    request: StopSessionRequest = { reason: "operator_stop" },
  ): Promise<StopSessionData> {
    return this.request<StopSessionData>(
      `/sessions/${encodeURIComponent(sessionId)}/stop`,
      {
        method: "POST",
        body: request,
      },
    );
  }

  getSnapshot(sessionId: string): Promise<SnapshotData> {
    return this.request<SnapshotData>(
      `/sessions/${encodeURIComponent(sessionId)}/snapshot`,
    );
  }

  getEvents(sessionId: string, query: EventsQuery = {}): Promise<EventsPage> {
    const params = new URLSearchParams();
    if (query.fromSeq !== undefined) {
      params.set("from_seq", String(query.fromSeq));
    }
    if (query.limit !== undefined) {
      params.set("limit", String(query.limit));
    }

    const suffix = params.size > 0 ? `?${params.toString()}` : "";
    return this.request<EventsPage>(
      `/sessions/${encodeURIComponent(sessionId)}/events${suffix}`,
    );
  }

  private async request<TData>(
    path: string,
    options: { method?: string; body?: unknown } = {},
  ): Promise<TData> {
    const requestId = this.requestIdFactory();
    const headers = new Headers({
      "X-Request-Id": requestId,
    });

    const init: RequestInit = {
      method: options.method ?? "GET",
      headers,
    };

    if (options.body !== undefined) {
      headers.set("Content-Type", "application/json");
      init.body = JSON.stringify(options.body);
    }

    let response: Response;
    try {
      response = await this.fetchImpl(`${this.baseUrl}${path}`, init);
    } catch (error) {
      throw createNetworkApiError(
        error instanceof Error ? error.message : "network request failed",
      );
    }

    const payload = await parseJson(response);
    if (isApiErrorEnvelope(payload)) {
      throw createApiErrorFromEnvelope(payload, response.status);
    }

    if (!response.ok) {
      throw createNetworkApiError(response.statusText || "request failed", response.status);
    }

    return (payload as ApiSuccessEnvelope<TData>).data;
  }
}

async function parseJson(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return {};
  }

  try {
    return JSON.parse(text);
  } catch {
    throw createNetworkApiError("response body is not valid JSON", response.status);
  }
}

function trimTrailingSlash(value: string): string {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}
