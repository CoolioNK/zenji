/* Verwaltung der Konversationsliste. */

import { useCallback, useEffect, useState } from "react";
import { api } from "../services/api";
import type { Conversation } from "../types";

export function useConversations() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setConversations(await api.conversations());
      setError(null);
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Konversationen nicht abrufbar.");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const rename = useCallback(async (id: string, title: string) => {
    await api.renameConversation(id, title);
    await refresh();
  }, []);

  const remove = useCallback(
    async (id: string) => {
      await api.deleteConversation(id);
      await refresh();
    },
    [refresh],
  );

  return { conversations, error, refresh, rename, remove };
}
