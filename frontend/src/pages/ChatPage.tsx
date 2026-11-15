/* Seitenlayout: Sidebar + Chatbereich + Control Center + Einstellungen-Schublade. */

import { useCallback, useState } from "react";
import { ChatArea } from "../components/ChatArea";
import { SettingsPanel } from "../components/SettingsPanel";
import { Sidebar } from "../components/Sidebar";
import { ControlCenter } from "../components/control/ControlCenter";
import { useChat } from "../hooks/useChat";
import { useConversations } from "../hooks/useConversations";
import { useHealth } from "../hooks/useHealth";
import { useSettings } from "../hooks/useSettings";

export function ChatPage() {
  const [activeId, setActiveId] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [controlOpen, setControlOpen] = useState(false);

  const health = useHealth();
  const { conversations, error: conversationsError, refresh, rename, remove } = useConversations();
  const settings = useSettings();

  const handleConversationCreated = useCallback(
    (id: string) => {
      setActiveId(id);
      void refresh();
    },
    [refresh],
  );

  const { messages, status, error, send, stop } = useChat(activeId, handleConversationCreated);

  const handleDelete = useCallback(
    async (id: string) => {
      await remove(id);
      if (id === activeId) setActiveId(null);
    },
    [remove, activeId],
  );

  const handleNewChat = () => {
    stop();
    setActiveId(null);
  };

  const handleSaveSettings = useCallback(
    async (patch: Record<string, unknown>) => {
      await settings.save(patch);
      await refresh();
    },
    [settings, refresh],
  );

  return (
    <div className="flex h-full bg-ink-900 text-ink-100">
      <Sidebar
        conversations={conversations}
        conversationsError={conversationsError}
        activeId={activeId}
        health={health}
        onSelect={(id) => {
          stop();
          setActiveId(id);
        }}
        onNewChat={handleNewChat}
        onRename={async (id, title) => {
          await rename(id, title);
          await refresh();
        }}
        onDelete={handleDelete}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenControl={() => setControlOpen(true)}
      />

      <ChatArea
        messages={messages}
        streaming={status === "streaming"}
        chatError={error}
        health={health}
        onSend={(text, mode) => void send(text, mode)}
        onStop={stop}
      />

      <SettingsPanel
        open={settingsOpen}
        settings={settings.settings}
        loading={settings.loading}
        saving={settings.saving}
        onClose={() => setSettingsOpen(false)}
        onLoad={() => void settings.load()}
        onSave={(patch) => void handleSaveSettings(patch)}
      />

      <ControlCenter
        open={controlOpen}
        activeConversationId={activeId}
        onClose={() => setControlOpen(false)}
      />
    </div>
  );
}
