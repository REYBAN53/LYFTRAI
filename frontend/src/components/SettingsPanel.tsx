import { useEffect, useRef } from "react";

import { CloseIcon } from "./icons";

export const SIMULATION_PRESETS = [
  { value: "", label: "Off: normal behaviour" },
  { value: "key_1=429", label: "key_1=429: first key rate-limited" },
  { value: "key_1=500", label: "key_1=500: first key server error" },
  { value: "key_1=429,key_2=500", label: "key_1=429,key_2=500: two keys down" },
  { value: "*=429", label: "*=429: every key fails (503)" },
];

interface SettingsPanelProps {
  open: boolean;
  onClose: () => void;
  systemPrompt: string;
  onSystemPromptChange: (value: string) => void;
  simulateFailure: string;
  onSimulateFailureChange: (value: string) => void;
  simulationAvailable: boolean | undefined;
}

export function SettingsPanel(props: SettingsPanelProps) {
  const { open, onClose } = props;
  const panel = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    panel.current?.querySelector<HTMLElement>("textarea, select")?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <>
      <div className={`scrim ${open ? "is-open" : ""}`} onClick={onClose} aria-hidden="true" />
      <aside
        ref={panel}
        className={`settings ${open ? "is-open" : ""}`}
        aria-label="Session settings"
        aria-hidden={!open}
        inert={!open}
      >
        <header className="settings-header">
          <h2>Session settings</h2>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close settings">
            <CloseIcon />
          </button>
        </header>

        <section className="field">
          <label htmlFor="system-prompt">System prompt</label>
          <textarea
            id="system-prompt"
            data-testid="system-prompt-input"
            rows={6}
            maxLength={8000}
            placeholder="e.g. You are a senior engineer. Answer briefly, with code where useful."
            value={props.systemPrompt}
            onChange={(event) => props.onSystemPromptChange(event.target.value)}
          />
          <p className="field-hint">
            Sent with each message and stored for this session on the server. Leave empty to use the default prompt.
            Never shown in the history.
          </p>
        </section>

        <section className="field">
          <label htmlFor="simulate-failure">Failover simulation</label>
          <select
            id="simulate-failure"
            data-testid="simulate-failure-select"
            value={props.simulateFailure}
            onChange={(event) => props.onSimulateFailureChange(event.target.value)}
          >
            {SIMULATION_PRESETS.map((preset) => (
              <option key={preset.value} value={preset.value}>
                {preset.label}
              </option>
            ))}
          </select>
          <p className="field-hint">
            Adds an <code>X-Simulate-Failure</code> header to your next messages so chosen keys fail for that request
            only. Real keys are never exhausted.
            {props.simulationAvailable === false && (
              <strong className="field-warn"> The backend has ENABLE_FAILURE_SIMULATION off, so it will ignore this.</strong>
            )}
          </p>
        </section>
      </aside>
    </>
  );
}
