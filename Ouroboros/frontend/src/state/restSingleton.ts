import { ControlRestClient, type RestClientOptions } from "../api/restClient";

let singleton: ControlRestClient | null = null;

export function getRestClient(options?: RestClientOptions): ControlRestClient {
  if (!singleton) {
    singleton = new ControlRestClient(options);
  }
  return singleton;
}

export function resetRestClient(): void {
  singleton = null;
}
