/* Laden und Verwalten der Verhaltensregeln (Control Center). */

import { useCallback, useEffect, useState } from "react";
import { api } from "../services/api";
import type { PoliciesResponse } from "../types";

export function usePolicies() {
  const [data, setData] = useState<PoliciesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.policies());
      setError(null);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Regeln nicht abrufbar.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const create = useCallback(async (body: Record<string, unknown>) => {
    const policy = await api.createPolicy(body);
    await refresh();
    return policy;
  }, [refresh]);

  const update = useCallback(async (id: string, patch: Record<string, unknown>) => {
    const policy = await api.updatePolicy(id, patch);
    await refresh();
    return policy;
  }, [refresh]);

  const remove = useCallback(async (id: string) => {
    await api.deletePolicy(id);
    await refresh();
  }, [refresh]);

  return { data, loading, error, refresh, create, update, remove };
}
