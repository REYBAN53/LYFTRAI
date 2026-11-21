import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, api } from "../api/client";
import type { ChatMetadata } from "../api/types";
import { createSessionId } from "../lib/session";

export type UserItem = {
  kind: "user";
  id: string;
  content: string;
  createdAt: Date;
  status: "pending" | "sent" | "failed";
};

export type AssistantItem = {
  kind: "assistant";
  id: string;
  content: string;
  createdAt: Date;
  metadata: ChatMetadata;
  simulatedFailure?: string;
};

export type ErrorItem = {
  kind: "error";
  id: string;
  title: string;
  message: string;
  createdAt: Date;
  retryUserId: string;
};

export type ChatItem = UserItem | AssistantItem | ErrorItem;

export interface SendOptions {
  systemPrompt?: string;
  simulateFailure?: string;
}

let counter = 0;
const nextId = (prefix: string) => `${prefix}-${Date.now().toString(36)}-${(counter++).toString(36)}`;

export function useChat() {
  const [sessionId, setSessionId] = useState(createSessionId);
  const [items, setItems] = useState<ChatItem[]>([]);
  const [isSending, setIsSending] = useState(false);
  const inFlight = useRef<AbortController | null>(null);

  useEffect(() => () => inFlight.current?.abort(), []);

  const dispatch = useCallback(
    async (userItem: UserItem, options: SendOptions) => {
      const controller = new AbortController();
      inFlight.current = controller;
      setIsSending(true);
      try {
        const response = await api.chat(
          {
            session_id: sessionId,
            message: userItem.content,
            ...(options.systemPrompt?.trim() ? { system_prompt: options.systemPrompt.trim() } : {}),
          },
          { simulateFailure: options.simulateFailure, signal: controller.signal },
        );
        setItems((current) => [
          ...current.map((item) => (item.id === userItem.id ? { ...userItem, status: "sent" as const } : item)),
          {
            kind: "assistant",
            id: nextId("a"),
            content: response.reply,
            createdAt: new Date(),
            metadata: response.metadata,
            simulatedFailure: options.simulateFailure,
          },
        ]);
      } catch (error) {
        if (controller.signal.aborted) return; // conversation was reset while waiting
        const apiError =
          error instanceof ApiError
            ? error
            : new ApiError("server", "Something went wrong", "An unexpected error occurred. Please try again.");
        setItems((current) => [
          ...current.map((item) => (item.id === userItem.id ? { ...userItem, status: "failed" as const } : item)),
          {
            kind: "error",
            id: nextId("e"),
            title: apiError.title,
            message: apiError.message,
            createdAt: new Date(),
            retryUserId: userItem.id,
          },
        ]);
      } finally {
        if (inFlight.current === controller) {
          inFlight.current = null;
          setIsSending(false);
        }
      }
    },
    [sessionId],
  );

  const send = useCallback(
    (text: string, options: SendOptions = {}) => {
      const content = text.trim();
      if (!content || isSending) return;
      const userItem: UserItem = { kind: "user", id: nextId("u"), content, createdAt: new Date(), status: "pending" };
      setItems((current) => [...current, userItem]);
      void dispatch(userItem, options);
    },
    [dispatch, isSending],
  );

  /** Re-send a failed message. Failed turns are never stored server-side, so this is safe. */
  const retry = useCallback(
    (errorId: string, options: SendOptions = {}) => {
      if (isSending) return;
      const error = items.find((item): item is ErrorItem => item.kind === "error" && item.id === errorId);
      const original = items.find((item): item is UserItem => item.kind === "user" && item.id === error?.retryUserId);
      if (!error || !original) return;
      const pending: UserItem = { ...original, status: "pending" };
      setItems((current) =>
        current.filter((item) => item.id !== errorId).map((item) => (item.id === original.id ? pending : item)),
      );
      void dispatch(pending, options);
    },
    [dispatch, isSending, items],
  );

  const reset = useCallback(() => {
    inFlight.current?.abort();
    inFlight.current = null;
    setIsSending(false);
    setItems([]);
    setSessionId(createSessionId());
  }, []);

  return { sessionId, items, isSending, send, retry, reset };
}
