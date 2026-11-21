/** Client-generated session id. A fresh one is created on every page load and on "New chat". */
export function createSessionId(): string {
  // crypto.randomUUID only exists in secure contexts (https / localhost); fall back otherwise.
  if (typeof crypto.randomUUID === "function") return `s-${crypto.randomUUID()}`;
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return `s-${Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")}`;
}

export function shortSessionId(sessionId: string): string {
  return sessionId.length > 12 ? `${sessionId.slice(0, 10)}…` : sessionId;
}
