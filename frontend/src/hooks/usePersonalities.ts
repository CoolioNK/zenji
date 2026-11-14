/* Laden und Verwalten der Persönlichkeitsprofile (Control Center). */

import { useCallback, useEffect, useState } from "react";
import { api } from "../services/api";
import type { Personality } from "../types";

export function usePersonalities() {
  const [profiles, setProfiles] = useState<Personality[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setProfiles(await api.personalities());
      setError(null);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Profile nicht abrufbar.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const create = useCallback(async (body: Record<string, unknown>) => {
    const profile = await api.createPersonality(body);
    await refresh();
    return profile;
  }, [refresh]);

  const update = useCallback(async (id: string, patch: Record<string, unknown>) => {
    const profile = await api.updatePersonality(id, patch);
    await refresh();
    return profile;
  }, [refresh]);

  const activate = useCallback(async (id: string) => {
    await api.activatePersonality(id);
    await refresh();
  }, [refresh]);

  const remove = useCallback(async (id: string) => {
    await api.deletePersonality(id);
    await refresh();
  }, [refresh]);

  return { profiles, loading, error, refresh, create, update, activate, remove };
}
