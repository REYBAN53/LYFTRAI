const DEFAULT_API_BASE_URL = "http://localhost:8000";

function resolveApiBaseUrl(): string {
  const runtime = typeof window !== "undefined" ? window.__APP_CONFIG__?.API_BASE_URL : undefined;
  const url = runtime || import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL;
  return url.replace(/\/+$/, "");
}

export const API_BASE_URL = resolveApiBaseUrl();
export const MAX_MESSAGE_CHARS = 4000;
export const REQUEST_TIMEOUT_MS = 90_000;
