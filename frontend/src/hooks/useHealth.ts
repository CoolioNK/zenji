/* Status-Polling: Backend, Ollama, Modell. */

import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { Health } from "../types";

export function useHealth(intervalMs = 8000): Health | null {
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    let alive = true;

    const refresh = async () => {
      try {
        const data = await api.health();
        if (alive) setHealth(data);
      } catch {
        if (alive) {
          setHealth(null); // Backend nicht erreichbar
        }
      }
    };

    void refresh();
    const timer = setInterval(refresh, intervalMs);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [intervalMs]);

  return health;
}
