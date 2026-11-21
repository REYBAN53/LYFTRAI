import type { AssistantItem, ErrorItem, UserItem } from "../hooks/useChat";
import { formatTime } from "../lib/format";
import { CopyButton } from "./CopyButton";
import { AlertIcon, LogoMark, RetryIcon } from "./icons";
import { Markdown } from "./Markdown";
import { MessageMeta } from "./MessageMeta";

export function UserMessage({ item }: { item: UserItem }) {
  return (
    <div className={`row row-user ${item.status === "failed" ? "is-failed" : ""}`}>
      <div className="bubble bubble-user" data-testid="user-message">
        <p>{item.content}</p>
      </div>
      <time className="timestamp" dateTime={item.createdAt.toISOString()}>
        {item.status === "failed" ? "Not sent · " : ""}
        {formatTime(item.createdAt)}
      </time>
    </div>
  );
}

export function AssistantMessage({ item }: { item: AssistantItem }) {
  return (
    <div className="row row-assistant">
      <div className="avatar" aria-hidden="true">
        <LogoMark />
      </div>
      <article className="assistant" data-testid="assistant-message">
        <Markdown content={item.content} />
        <MessageMeta metadata={item.metadata} />
        <div className="assistant-actions">
          <CopyButton text={item.content} />
          <time className="timestamp" dateTime={item.createdAt.toISOString()}>
            {formatTime(item.createdAt)}
          </time>
          {item.simulatedFailure && <span className="timestamp">· simulated: {item.simulatedFailure}</span>}
        </div>
      </article>
    </div>
  );
}

export function ErrorMessage({ item, onRetry, disabled }: { item: ErrorItem; onRetry: () => void; disabled: boolean }) {
  return (
    <div className="row row-assistant">
      <div className="avatar avatar-error" aria-hidden="true">
        <AlertIcon width={14} height={14} />
      </div>
      <div className="error-card" role="alert" data-testid="error-message">
        <div className="error-title">{item.title}</div>
        <p>{item.message}</p>
        <button type="button" className="button button-ghost" onClick={onRetry} disabled={disabled}>
          <RetryIcon width={14} height={14} /> Retry
        </button>
      </div>
    </div>
  );
}

export function TypingIndicator() {
  return (
    <div className="row row-assistant" aria-live="polite">
      <div className="avatar" aria-hidden="true">
        <LogoMark />
      </div>
      <div className="typing" data-testid="loading-indicator">
        <span className="dot" />
        <span className="dot" />
        <span className="dot" />
        <span className="sr-only">Generating a response…</span>
      </div>
    </div>
  );
}
