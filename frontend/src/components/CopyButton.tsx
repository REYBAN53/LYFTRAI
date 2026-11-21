import { useEffect, useState } from "react";

import { CheckIcon, CopyIcon } from "./icons";

export function CopyButton({ text, label = "Copy response" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = window.setTimeout(() => setCopied(false), 1600);
    return () => window.clearTimeout(timer);
  }, [copied]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      /* clipboard unavailable (insecure context / permissions): fail quietly */
    }
  };

  return (
    <button type="button" className="icon-button" onClick={copy} aria-label={copied ? "Copied" : label} title={copied ? "Copied" : label}>
      {copied ? <CheckIcon /> : <CopyIcon />}
    </button>
  );
}
