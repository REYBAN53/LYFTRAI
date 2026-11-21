import { API_BASE_URL, REQUEST_TIMEOUT_MS } from "../config";
import type { ChatRequest, ChatResponse, HealthResponse } from "./types";

export type ApiErrorKind = "validation" | "unavailable" | "network" | "timeout" | "server";

/** A failed API call, already translated into something a person can read. */
export class ApiError extends Error {
  constructor(
    readonly kind: ApiErrorKind,
    readonly title: string,
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface ValidationIssue {
  loc?: (string | number)[];
  msg?: string;
}

function describeDetail(detail: unknown): string | undefined {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const issues = (detail as ValidationIssue[])
      .map((issue) => {
        const field = issue.loc?.filter((part) => part !== "body").join(".");
        return issue.msg ? (field ? `${field}: ${issue.msg}` : issue.msg) : undefined;
      })
      .filter(Boolean);
    if (issues.length) return issues.join("; ");
  }
  return undefined;
}

async function toApiError(response: Response): Promise<ApiError> {
  let detail: string | undefined;
  try {
    detail = describeDetail((await response.json())?.detail);
  } catch {
    /* non-JSON body: fall through to a generic message */
  }
  if (response.status === 422) {
    return new ApiError("validation", "Message not accepted", detail ?? "The request was invalid.", 422);
  }
  if (response.status === 503) {
    return new ApiError(
      "unavailable",
      "All model providers are unavailable",
      "Every API key in the pool failed (rate limited, out of quota or a provider error). Your message was not saved, so you can safely retry.",
      503,
    );
  }
  return new ApiError(
    "server",
    "Something went wrong",
    detail ? `The server responded with ${response.status}: ${detail}` : `The server responded with ${response.status}.`,
    response.status,
  );
}

async function request<T>(path: string, init: RequestInit = {}, signal?: AbortSignal): Promise<T> {
  // Combine the caller's signal with a timeout without AbortSignal.any/timeout, which older
  // Safari versions lack.
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, REQUEST_TIMEOUT_MS);
  const onCallerAbort = () => controller.abort();
  signal?.addEventListener("abort", onCallerAbort, { once: true });
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, { ...init, signal: controller.signal });
  } catch (error) {
    if (signal?.aborted) throw error; // cancelled by the caller: not a user-facing error
    if (timedOut) {
      throw new ApiError("timeout", "Request timed out", "The server took too long to respond. Please try again.");
    }
    throw new ApiError(
      "network",
      "Can't reach the server",
      `No response from ${API_BASE_URL}. Check your connection or whether the backend is running.`,
    );
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onCallerAbort);
  }
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as T;
}

export const api = {
  chat(body: ChatRequest, options: { simulateFailure?: string; signal?: AbortSignal } = {}) {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (options.simulateFailure) headers["X-Simulate-Failure"] = options.simulateFailure;
    return request<ChatResponse>("/chat", { method: "POST", headers, body: JSON.stringify(body) }, options.signal);
  },
  health(signal?: AbortSignal) {
    return request<HealthResponse>("/health", {}, signal);
  },
};
