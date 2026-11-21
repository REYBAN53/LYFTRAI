import { useCallback, useState } from "react";

import { Composer } from "./components/Composer";
import { EmptyState } from "./components/EmptyState";
import { ArrowDownIcon, LogoMark, PlusIcon, SlidersIcon } from "./components/icons";
import { AssistantMessage, ErrorMessage, TypingIndicator, UserMessage } from "./components/Messages";
import { SettingsPanel } from "./components/SettingsPanel";
import { useChat } from "./hooks/useChat";
import { useHealth } from "./hooks/useHealth";
import { useStickToBottom } from "./hooks/useStickToBottom";
import { shortSessionId } from "./lib/session";

export default function App() {
  const { sessionId, items, isSending, send, retry, reset } = useChat();
  const health = useHealth();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [systemPrompt, setSystemPrompt] = useState("");
  const [simulateFailure, setSimulateFailure] = useState("");
  const { ref: scrollRef, showJump, scrollToBottom } = useStickToBottom<HTMLDivElement>(`${items.length}:${isSending}`);

  const options = { systemPrompt, simulateFailure: simulateFailure || undefined };
  const handleSend = (text: string) => {
    send(text, options);
    scrollToBottom("smooth");
  };
  const closeSettings = useCallback(() => setSettingsOpen(false), []);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <LogoMark />
          <span className="brand-name">Lyftr Chat</span>
          <HealthBadge health={health} />
        </div>
        <div className="topbar-actions">
          <span className="session-chip" title={`Session ${sessionId}`}>
            {shortSessionId(sessionId)}
          </span>
          {simulateFailure && (
            <span className="sim-chip" title="X-Simulate-Failure is active for new messages">
              sim: {simulateFailure}
            </span>
          )}
          <button
            type="button"
            className="button button-ghost"
            onClick={() => setSettingsOpen(true)}
            aria-haspopup="dialog"
            aria-expanded={settingsOpen}
          >
            <SlidersIcon /> <span className="hide-sm">Settings</span>
          </button>
          <button type="button" className="button" onClick={reset} disabled={items.length === 0 && !isSending}>
            <PlusIcon /> <span className="hide-sm">New chat</span>
          </button>
        </div>
      </header>

      <main className="conversation" ref={scrollRef} aria-live="polite" aria-busy={isSending}>
        <div className="conversation-inner">
          {items.length === 0 ? (
            <EmptyState onPick={handleSend} disabled={isSending} />
          ) : (
            items.map((item) => {
              switch (item.kind) {
                case "user":
                  return <UserMessage key={item.id} item={item} />;
                case "assistant":
                  return <AssistantMessage key={item.id} item={item} />;
                case "error":
                  return (
                    <ErrorMessage
                      key={item.id}
                      item={item}
                      disabled={isSending}
                      onRetry={() => retry(item.id, options)}
                    />
                  );
              }
            })
          )}
          {isSending && <TypingIndicator />}
        </div>
      </main>

      <footer className="dock">
        {showJump && (
          <button type="button" className="jump" onClick={() => scrollToBottom("smooth")} aria-label="Jump to latest message">
            <ArrowDownIcon />
          </button>
        )}
        <Composer onSend={handleSend} isSending={isSending} autoFocusKey={sessionId} />
      </footer>

      <SettingsPanel
        open={settingsOpen}
        onClose={closeSettings}
        systemPrompt={systemPrompt}
        onSystemPromptChange={setSystemPrompt}
        simulateFailure={simulateFailure}
        onSimulateFailureChange={setSimulateFailure}
        simulationAvailable={health.status === "ok" ? health.data.failure_simulation_enabled : undefined}
      />
    </div>
  );
}

function HealthBadge({ health }: { health: ReturnType<typeof useHealth> }) {
  if (health.status === "checking") return <span className="health is-checking">connecting…</span>;
  if (health.status === "down") return <span className="health is-down" title="GET /health failed">API offline</span>;
  const { data } = health;
  const title = `${data.model ?? "model"} · ${data.keys_configured} keys · cache ${data.cache_enabled ? "on" : "off"}`;
  return (
    <span className="health is-ok" title={title}>
      <span className="hide-sm">{data.model ?? "online"}</span>
      <span className="health-keys">{data.keys_configured} keys</span>
    </span>
  );
}
