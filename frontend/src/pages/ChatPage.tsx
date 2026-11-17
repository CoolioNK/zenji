/* Seitenlayout: Einklappbare Sidebar + Chatbereich mit Top-Header + Command Palette + Control Center + Einstellungen. */

import { useCallback, useState, useEffect } from "react";
import { ChatArea } from "../components/ChatArea";
import { SettingsPanel } from "../components/SettingsPanel";
import { Sidebar } from "../components/Sidebar";
import { ControlCenter } from "../components/control/ControlCenter";
import { CommandPalette } from "../components/CommandPalette";
import { useChat } from "../hooks/useChat";
import { useConversations } from "../hooks/useConversations";
import { useHealth } from "../hooks/useHealth";
import { useSettings } from "../hooks/useSettings";
import type { ResearchMode } from "../types";

export function ChatPage() {
  const [activeId, setActiveId] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [controlOpen, setControlOpen] = useState(false);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  // Recherche läuft automatisch; kein manueller Web-Umschalter mehr.
  const researchMode: ResearchMode = "auto";
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() => {
    return localStorage.getItem("zenji-sidebar-collapsed") === "true";
  });

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

  const { messages, status, error, send, stop } = useChat(
    activeId,
    handleConversationCreated,
  );

  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem("zenji-sidebar-collapsed", String(next));
      return next;
    });
  }, []);

  const handleDelete = useCallback(
    async (id: string) => {
      await remove(id);
      if (id === activeId) setActiveId(null);
    },
    [remove, activeId],
  );

  const handleNewChat = useCallback(() => {
    stop();
    setActiveId(null);
  }, [stop]);

  const handleSaveSettings = useCallback(
    async (patch: Record<string, unknown>) => {
      await settings.save(patch);
      await refresh();
    },
    [settings, refresh],
  );

  // Globale Tastenkombinationen (Cmd+K: Palette, Cmd+B: Sidebar, Cmd+N: Neuer Chat)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const isCmdOrCtrl = e.metaKey || e.ctrlKey;
      if (isCmdOrCtrl && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCommandPaletteOpen((prev) => !prev);
      } else if (isCmdOrCtrl && e.key.toLowerCase() === "b") {
        e.preventDefault();
        toggleSidebar();
      } else if (isCmdOrCtrl && e.key.toLowerCase() === "n") {
        e.preventDefault();
        handleNewChat();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [toggleSidebar, handleNewChat]);

  const activeConversation = conversations.find((c) => c.id === activeId);

  return (
    <div className="flex h-full w-full bg-background text-foreground overflow-hidden font-sans selection:bg-accent selection:text-white">
      <Sidebar
        conversations={conversations}
        conversationsError={conversationsError}
        activeId={activeId}
        health={health}
        collapsed={sidebarCollapsed}
        onToggleCollapse={toggleSidebar}
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
        onOpenCommandPalette={() => setCommandPaletteOpen(true)}
      />

      <ChatArea
        messages={messages}
        streaming={status === "streaming"}
        chatError={error}
        health={health}
        onSend={(text, mode, research) => void send(text, mode, research ?? researchMode)}
        onStop={stop}
        sidebarCollapsed={sidebarCollapsed}
        onToggleSidebar={toggleSidebar}
        onOpenCommandPalette={() => setCommandPaletteOpen(true)}
        activeConversationTitle={activeConversation?.title}
        researchMode={researchMode}
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

      <CommandPalette
        open={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
        conversations={conversations}
        onSelectConversation={(id) => {
          stop();
          setActiveId(id);
        }}
        onNewChat={handleNewChat}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenControl={() => setControlOpen(true)}
        sidebarCollapsed={sidebarCollapsed}
        onToggleSidebar={toggleSidebar}
      />
    </div>
  );
}
