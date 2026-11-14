/* Laden und Verwalten der Erinnerungen (Control Center). */

import { useCallback, useEffect, useState } from "react";
import { api } from "../services/api";
import type { Memory, MemoryListResponse } from "../types";

export function useMemories() {
  const [data, setData] = useState<MemoryListResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.memories());
      setError(null);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Erinnerungen nicht abrufbar.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const create = useCallback(async (body: Record<string, unknown>) => {
    const memory = await api.createMemory(body);
    await refresh();
    return memory;
  }, [refresh]);

  const update = useCallback(async (id: string, patch: Record<string, unknown>) => {
    const memory = await api.updateMemory(id, patch);
    await refresh();
    return memory;
  }, [refresh]);

  const remove = useCallback(async (id: string) => {
    await api.deleteMemory(id);
    await refresh();
  }, [refresh]);

  const search = useCallback(
    async (query: string, memoryType?: string, category?: string) => {
      const results = await api.searchMemories(query, memoryType, category);
      return results;
    },
    [],
  );

  return { data, memories: (data?.memories ?? []) as Memory[], loading, error, refresh, create, update, remove, search };
}
