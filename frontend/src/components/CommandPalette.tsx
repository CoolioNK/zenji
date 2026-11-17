/* Command Palette (Cmd+K / Ctrl+K) im Zenji Editorial Design-System */

import { useState, useEffect, useRef } from "react";
import { 
  Search, 
  Plus, 
  Sliders, 
  Settings2, 
  Sun, 
  MessageSquare, 
  PanelLeftClose, 
  PanelLeftOpen, 
  Download, 
  X 
} from "lucide-react";
import type { Conversation } from "../types";

export function CommandPalette({
  open,
  onClose,
  conversations,
  onSelectConversation,
  onNewChat,
  onOpenSettings,
  onOpenControl,
  sidebarCollapsed,
  onToggleSidebar,
  onExportChat,
}: {
  open: boolean;
  onClose: () => void;
  conversations: Conversation[];
  onSelectConversation: (id: string) => void;
  onNewChat: () => void;
  onOpenSettings: () => void;
  onOpenControl: () => void;
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
  onExportChat?: () => void;
}) {
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  if (!open) return null;

  const filteredConversations = conversations.filter((c) =>
    c.title.toLowerCase().includes(query.toLowerCase())
  );

  const toggleTheme = () => {
    const cur = document.documentElement.getAttribute("data-theme");
    const next = cur === "light" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", next);
    if (next === "dark") {
      document.documentElement.classList.add("dark");
      document.documentElement.classList.remove("theme-light");
    } else {
      document.documentElement.classList.remove("dark");
      document.documentElement.classList.add("theme-light");
    }
    localStorage.setItem("zenji-app-theme", next);
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-24 px-4 bg-black/60 backdrop-blur-md animate-fade-up"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl overflow-hidden rounded-2xl border border-border bg-card shadow-2xl backdrop-blur-2xl transition-all"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search Input Bar */}
        <div className="flex items-center gap-3 border-b border-border px-4 py-3.5 bg-background/60">
          <Search className="h-4 w-4 text-accent shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Befehl eingeben oder Chat suchen …"
            className="w-full bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground font-sans"
            onKeyDown={(e) => {
              if (e.key === "Escape") onClose();
            }}
          />
          <button
            onClick={onClose}
            className="flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-card transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Action & Results List */}
        <div className="max-h-[380px] overflow-y-auto p-2 space-y-4">
          {/* Quick Actions */}
          {!query && (
            <div>
              <div className="px-3 py-1 eyebrow">
                Aktionen
              </div>
              <div className="space-y-0.5 mt-1">
                <button
                  onClick={() => {
                    onNewChat();
                    onClose();
                  }}
                  className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-xs text-foreground hover:bg-background hover:text-accent transition-colors"
                >
                  <Plus className="h-4 w-4 text-accent" />
                  <span className="flex-1 font-medium">Neuer Dialog</span>
                  <span className="font-mono text-[10px] text-muted-foreground">⌘N</span>
                </button>

                <button
                  onClick={() => {
                    onToggleSidebar();
                    onClose();
                  }}
                  className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-xs text-foreground hover:bg-background hover:text-accent transition-colors"
                >
                  {sidebarCollapsed ? (
                    <PanelLeftOpen className="h-4 w-4 text-accent" />
                  ) : (
                    <PanelLeftClose className="h-4 w-4 text-accent" />
                  )}
                  <span className="flex-1 font-medium">
                    Seitenleiste {sidebarCollapsed ? "ausklappen" : "einklappen"}
                  </span>
                  <span className="font-mono text-[10px] text-muted-foreground">⌘B</span>
                </button>

                <button
                  onClick={toggleTheme}
                  className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-xs text-foreground hover:bg-background hover:text-accent transition-colors"
                >
                  <Sun className="h-4 w-4 text-accent" />
                  <span className="flex-1 font-medium">Theme umschalten (Washi / Charcoal)</span>
                </button>

                <button
                  onClick={() => {
                    onOpenControl();
                    onClose();
                  }}
                  className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-xs text-foreground hover:bg-background hover:text-accent transition-colors"
                >
                  <Sliders className="h-4 w-4 text-accent" />
                  <span className="flex-1 font-medium">Control Center öffnen</span>
                </button>

                <button
                  onClick={() => {
                    onOpenSettings();
                    onClose();
                  }}
                  className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-xs text-foreground hover:bg-background hover:text-accent transition-colors"
                >
                  <Settings2 className="h-4 w-4 text-accent" />
                  <span className="flex-1 font-medium">Einstellungen öffnen</span>
                </button>

                {onExportChat && (
                  <button
                    onClick={() => {
                      onExportChat();
                      onClose();
                    }}
                    className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-xs text-foreground hover:bg-background hover:text-accent transition-colors"
                  >
                    <Download className="h-4 w-4 text-accent" />
                    <span className="flex-1 font-medium">Aktuelle Konversation exportieren (.md)</span>
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Conversations Section */}
          <div>
            <div className="px-3 py-1 eyebrow">
              Konversationen ({filteredConversations.length})
            </div>
            {filteredConversations.length === 0 ? (
              <p className="px-3 py-4 text-xs text-muted-foreground text-center">
                Keine Konversationen gefunden.
              </p>
            ) : (
              <div className="space-y-0.5 mt-1">
                {filteredConversations.slice(0, 8).map((conv) => (
                  <button
                    key={conv.id}
                    onClick={() => {
                      onSelectConversation(conv.id);
                      onClose();
                    }}
                    className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-xs text-foreground hover:bg-background hover:text-accent transition-colors"
                  >
                    <MessageSquare className="h-3.5 w-3.5 text-accent shrink-0" />
                    <span className="truncate flex-1">{conv.title}</span>
                    <span className="font-mono text-[10px] text-muted-foreground shrink-0">
                      {conv.message_count} msgs
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Command Palette Footer */}
        <div className="border-t border-border bg-background/60 px-4 py-2 flex items-center justify-between text-[11px] font-mono text-muted-foreground">
          <span>ZENJI Intelligent Command Hub</span>
          <div className="flex gap-2">
            <span>ESC zum Schließen</span>
          </div>
        </div>
      </div>
    </div>
  );
}
