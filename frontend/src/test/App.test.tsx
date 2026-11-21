import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import type { ChatResponse } from "../api/types";

const liveReply: ChatResponse = {
  session_id: "ignored",
  reply: "The capital of France is **Paris**.",
  metadata: {
    resolution_source: "LIVE_INFERENCE",
    model: "gemini/gemini-flash-lite-latest",
    latency_ms: 812,
    input_tokens: 42,
    output_tokens: 9,
    key_id: "key_2",
    fallback_attempts: 1,
  },
};

const health = { status: "ok", keys_configured: 2, cache_enabled: true, model: "m", failure_simulation_enabled: true };

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

describe("App", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn((url: string) => (String(url).endsWith("/health") ? jsonResponse(health) : jsonResponse(liveReply)));
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("sends on Enter, clears the input and renders every metadata test id", async () => {
    const user = userEvent.setup();
    render(<App />);
    const input = screen.getByTestId("chat-input");
    await user.type(input, "What is the capital of France?{Enter}");

    expect(input).toHaveValue("");
    const message = await screen.findByTestId("assistant-message");
    expect(within(message).getByText("Paris")).toBeInTheDocument();
    expect(within(message).getByTestId("meta-source")).toHaveTextContent(/^LIVE_INFERENCE$/);
    expect(within(message).getByTestId("meta-model")).toHaveTextContent(/^gemini\/gemini-flash-lite-latest$/);
    expect(within(message).getByTestId("meta-latency")).toHaveTextContent(/^812 ms$/);
    expect(within(message).getByTestId("meta-input-tokens")).toHaveTextContent(/^42$/);
    expect(within(message).getByTestId("meta-output-tokens")).toHaveTextContent(/^9$/);

    const [, init] = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/chat"))!;
    const body = JSON.parse(init.body);
    expect(body.message).toBe("What is the capital of France?");
    expect(body.session_id).toMatch(/^s-/);
    expect(body).not.toHaveProperty("system_prompt");
  });

  it("disables the send button while a request is in flight and for empty input", async () => {
    let resolveChat: (value: Response) => void = () => {};
    fetchMock.mockImplementation((url: string) =>
      String(url).endsWith("/health") ? jsonResponse(health) : new Promise<Response>((resolve) => (resolveChat = resolve)),
    );
    const user = userEvent.setup();
    render(<App />);
    const button = screen.getByTestId("send-button");
    expect(button).toBeDisabled();

    await user.type(screen.getByTestId("chat-input"), "hello");
    expect(button).toBeEnabled();
    await user.click(button);
    await user.type(screen.getByTestId("chat-input"), "next");
    expect(button).toBeDisabled();
    expect(screen.getByTestId("loading-indicator")).toBeInTheDocument();

    resolveChat(new Response(JSON.stringify(liveReply), { status: 200 }));
    await screen.findByTestId("assistant-message");
    expect(button).toBeEnabled();
  });

  it("shows a readable error for a 503 and can retry", async () => {
    fetchMock.mockImplementation((url: string) =>
      String(url).endsWith("/health") ? jsonResponse(health) : jsonResponse({ detail: "all providers unavailable" }, 503),
    );
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByTestId("chat-input"), "hi{Enter}");
    const error = await screen.findByTestId("error-message");
    expect(error).toHaveTextContent("All model providers are unavailable");

    fetchMock.mockImplementation((url: string) => (String(url).endsWith("/health") ? jsonResponse(health) : jsonResponse(liveReply)));
    await user.click(within(error).getByRole("button", { name: /retry/i }));
    await screen.findByTestId("assistant-message");
    expect(screen.queryByTestId("error-message")).not.toBeInTheDocument();
    expect(screen.getAllByTestId("user-message")).toHaveLength(1);
  });

  it("shows 422 validation details in the chat", async () => {
    fetchMock.mockImplementation((url: string) =>
      String(url).endsWith("/health")
        ? jsonResponse(health)
        : jsonResponse({ detail: [{ loc: ["body", "message"], msg: "String should have at most 4000 characters" }] }, 422),
    );
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByTestId("chat-input"), "hi{Enter}");
    expect(await screen.findByTestId("error-message")).toHaveTextContent("message: String should have at most 4000 characters");
  });

  it("shows a network error instead of a blank screen", async () => {
    fetchMock.mockImplementation((url: string) =>
      String(url).endsWith("/health") ? jsonResponse(health) : Promise.reject(new TypeError("Failed to fetch")),
    );
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByTestId("chat-input"), "hi{Enter}");
    expect(await screen.findByTestId("error-message")).toHaveTextContent("Can't reach the server");
  });

  it("sends the system prompt and simulation header from settings", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: /settings/i }));
    await user.type(screen.getByTestId("system-prompt-input"), "Be brief.");
    await user.selectOptions(screen.getByTestId("simulate-failure-select"), "key_1=429");
    await user.keyboard("{Escape}");
    await user.type(screen.getByTestId("chat-input"), "hi{Enter}");
    await screen.findByTestId("assistant-message");

    const [, init] = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/chat"))!;
    expect(JSON.parse(init.body).system_prompt).toBe("Be brief.");
    expect(init.headers["X-Simulate-Failure"]).toBe("key_1=429");
  });

  it("starts a fresh session on New chat", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByTestId("chat-input"), "hi{Enter}");
    await screen.findByTestId("assistant-message");
    await user.click(screen.getByRole("button", { name: /new chat/i }));
    expect(screen.queryByTestId("assistant-message")).not.toBeInTheDocument();
    await user.type(screen.getByTestId("chat-input"), "again{Enter}");
    await screen.findByTestId("assistant-message");
    const sessions = fetchMock.mock.calls
      .filter(([url]) => String(url).endsWith("/chat"))
      .map(([, init]) => JSON.parse(init.body).session_id);
    expect(new Set(sessions).size).toBe(2);
  });
});
