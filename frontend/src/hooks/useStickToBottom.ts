import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

const THRESHOLD_PX = 120;

/**
 * Keeps a scroll container pinned to the newest message, unless the reader has scrolled up
 * to read history; in that case a "jump to latest" affordance is offered instead.
 */
export function useStickToBottom<T extends HTMLElement>(dependency: unknown) {
  const ref = useRef<T>(null);
  const pinned = useRef(true);
  const [showJump, setShowJump] = useState(false);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    const node = ref.current;
    if (!node) return;
    node.scrollTo({ top: node.scrollHeight, behavior });
    pinned.current = true;
    setShowJump(false);
  }, []);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const onScroll = () => {
      const distance = node.scrollHeight - node.scrollTop - node.clientHeight;
      pinned.current = distance < THRESHOLD_PX;
      setShowJump(!pinned.current);
    };
    node.addEventListener("scroll", onScroll, { passive: true });
    return () => node.removeEventListener("scroll", onScroll);
  }, []);

  useLayoutEffect(() => {
    if (pinned.current) scrollToBottom("smooth");
  }, [dependency, scrollToBottom]);

  return { ref, showJump, scrollToBottom };
}
