import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";

import { MAX_MESSAGE_CHARS } from "../config";
import { SendIcon } from "./icons";

interface ComposerProps {
  onSend: (text: string) => void;
  isSending: boolean;
  autoFocusKey?: string;
}

export function Composer({ onSend, isSending, autoFocusKey }: ComposerProps) {
  const [value, setValue] = useState("");
  const textarea = useRef<HTMLTextAreaElement>(null);
  const trimmedLength = value.trim().length;
  const tooLong = trimmedLength > MAX_MESSAGE_CHARS;
  const canSend = trimmedLength > 0 && !tooLong && !isSending;

  useEffect(() => {
    textarea.current?.focus();
  }, [autoFocusKey]);

  // Auto-grow the textarea up to a max height (CSS caps it and scrolls beyond that).
  useEffect(() => {
    const node = textarea.current;
    if (!node) return;
    node.style.height = "auto";
    node.style.height = `${node.scrollHeight}px`;
  }, [value]);

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    if (!canSend) return;
    onSend(value);
    setValue("");
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends, Shift+Enter inserts a newline; never send mid IME composition.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <form className="composer" onSubmit={submit}>
      <div className={`composer-box ${tooLong ? "is-invalid" : ""}`}>
        <label htmlFor="chat-input" className="sr-only">
          Message
        </label>
        <textarea
          id="chat-input"
          ref={textarea}
          data-testid="chat-input"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask anything…"
          rows={1}
          aria-invalid={tooLong}
          aria-describedby="composer-hint"
        />
        <button
          type="submit"
          className="send-button"
          data-testid="send-button"
          disabled={!canSend}
          aria-label={isSending ? "Waiting for response" : "Send message"}
          title="Send (Enter)"
        >
          {isSending ? <span className="spinner" aria-hidden="true" /> : <SendIcon />}
        </button>
      </div>
      <div className="composer-hint" id="composer-hint">
        <span>
          <kbd>Enter</kbd> to send · <kbd>Shift</kbd>+<kbd>Enter</kbd> for a new line
        </span>
        {trimmedLength > MAX_MESSAGE_CHARS * 0.8 && (
          <span className={tooLong ? "count is-over" : "count"}>
            {trimmedLength.toLocaleString()} / {MAX_MESSAGE_CHARS.toLocaleString()}
          </span>
        )}
      </div>
    </form>
  );
}
