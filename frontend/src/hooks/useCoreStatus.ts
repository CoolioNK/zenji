/* Kern-Status und Kontext-Vorschau (Control Center). */

import { useCallback, useEffect, useState } from "react";
import { api } from "../services/api";
import type { ContextPreview, CoreStatus } from "../types";

export function useCoreStatus() {
  const [status, setStatus] = useState<CoreStatus | null>(null);
  const [preview, setPreview] = useState<ContextPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setStatus(await api.coreStatus());
      setError(null);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Core-Status nicht abrufbar.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const loadPreview = useCallback(
    async (message: string, conversationId: string | null) => {
      setPreviewLoading(true);
      try {
        setPreview(await api.contextPreview(message, conversationId));
      } catch (exc) {
        setError(exc instanceof Error ? exc.message : "Vorschau nicht abrufbar.");
      } finally {
        setPreviewLoading(false);
      }
    },
    [],
  );

  return { status, preview, loading, previewLoading, error, refresh, loadPreview };
}
