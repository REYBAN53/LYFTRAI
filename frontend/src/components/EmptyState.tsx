import { LogoMark } from "./icons";

const SUGGESTIONS = [
  { title: "What is the capital of France?", hint: "Send it twice in new chats to see a cache hit" },
  { title: "Explain API key failover in two sentences", hint: "Resilience basics" },
  { title: "Write a haiku about response caching", hint: "Something creative" },
  { title: "Give me 3 tips for clean React components", hint: "Practical advice" },
];

export function EmptyState({ onPick, disabled }: { onPick: (text: string) => void; disabled: boolean }) {
  return (
    <div className="empty">
      <div className="empty-logo">
        <LogoMark />
      </div>
      <h1>How can I help today?</h1>
      <p className="empty-sub">
        Every reply shows where it came from: live inference or the response cache, which model and key answered,
        latency and token usage.
      </p>
      <div className="suggestions">
        {SUGGESTIONS.map((suggestion) => (
          <button
            key={suggestion.title}
            type="button"
            className="suggestion"
            onClick={() => onPick(suggestion.title)}
            disabled={disabled}
          >
            <span className="suggestion-title">{suggestion.title}</span>
            <span className="suggestion-hint">{suggestion.hint}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
