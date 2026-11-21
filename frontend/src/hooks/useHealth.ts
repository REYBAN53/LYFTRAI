import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { HealthResponse } from "../api/types";

export type HealthState = { status: "checking" } | { status: "ok"; data: HealthResponse } | { status: "down" };

export function useHealth(): HealthState {
  const [state, setState] = useState<HealthState>({ status: "checking" });
  useEffect(() => {
    const controller = new AbortController();
    api
      .health(controller.signal)
      .then((data) => setState({ status: "ok", data }))
      .catch(() => {
        if (!controller.signal.aborted) setState({ status: "down" });
      });
    return () => controller.abort();
  }, []);
  return state;
}
