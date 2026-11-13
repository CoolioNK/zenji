/* Laden und Speichern der ZENJI-Einstellungen. */

import { useCallback, useState } from "react";
import { api } from "../services/api";
import type { Settings } from "../types";

export function useSettings() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setSettings(await api.settings());
    } finally {
      setLoading(false);
    }
  }, []);

  const save = useCallback(async (patch: Record<string, unknown>) => {
    setSaving(true);
    try {
      setSettings(await api.patchSettings(patch));
    } finally {
      setSaving(false);
    }
  }, []);

  return { settings, loading, saving, load, save };
}
