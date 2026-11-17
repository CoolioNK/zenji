/* Einklappbare Sidebar im Zenji Editorial Design-System */

import { useState, useEffect } from "react";
import { 
  Plus, 
  Sliders, 
  Settings2, 
  Sun, 
  Moon, 
  PanelLeftClose, 
  Search,
  MessageSquare,
  LogOut
} from "lucide-react";
import { ConversationList } from "./ConversationList";
import { Logo } from "./Logo";
import { StatusFooter } from "./StatusFooter";
import { isSupabaseConfigured, supabase } from "../lib/supabase";
import { useAuth } from "../lib/auth";
import type { Conversation, Health } from "../types";

export function Sidebar({
  conversations,
  conversationsError,
  activeId,
  health,
  onSelect,
  onNewChat,
  onRename,
  onDelete,
  onOpenSettings,
  onOpenControl,
  collapsed,
  onToggleCollapse,
  onOpenCommandPalette,
}: {
  conversations: Conversation[];
  conversationsError: string | null;
  activeId: string | null;
  health: Health | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
  onOpenSettings: () => void;
  onOpenControl: () => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
  onOpenCommandPalette?: () => void;
}) {
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const { user } = useAuth();

  const signOut = () => {
    void supabase.auth.signOut();
  };

  useEffect(() => {
    const saved = localStorage.getItem("zenji-app-theme") as "dark" | "light" | null;
    const initialTheme = saved || "dark";
    setTheme(initialTheme);
    document.documentElement.setAttribute("data-theme", initialTheme);
    if (initialTheme === "dark") {
      document.documentElement.classList.add("dark");
      document.documentElement.classList.remove("theme-light");
    } else {
      document.documentElement.classList.remove("dark");
      document.documentElement.classList.add("theme-light");
    }
  }, []);

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    if (next === "dark") {
      document.documentElement.classList.add("dark");
      document.documentElement.classList.remove("theme-light");
    } else {
      document.documentElement.classList.remove("dark");
      document.documentElement.classList.add("theme-light");
    }
    localStorage.setItem("zenji-app-theme", next);
  };

  const modelOk = health?.model.available ?? false;

  return (
    <aside
      className={`relative flex h-full shrink-0 flex-col border-r border-border bg-card/40 backdrop-blur-xl select-none transition-all duration-300 ease-in-out z-20 ${
        collapsed ? "w-[68px]" : "w-[290px]"
      }`}
    >
      {/* Brand Header */}
      <div
        className={`flex items-center pt-5 pb-4 border-b border-border ${
          collapsed ? "justify-center px-2" : "justify-between px-5"
        }`}
      >
        <div onClick={onNewChat} className="cursor-pointer">
          <Logo compact={collapsed} />
        </div>

        {!collapsed && (
          <div className="flex items-center gap-1.5">
            <button
              onClick={toggleTheme}
              title={theme === "dark" ? "Zu Washi-Light wechseln" : "Zu Charcoal-Dark wechseln"}
              className="flex h-7 w-7 items-center justify-center rounded-lg border border-border bg-card/60 text-muted-foreground transition-colors hover:border-accent hover:text-foreground hover:bg-accent/10"
              aria-label="Theme umschalten"
            >
              {theme === "dark" ? (
                <Sun className="h-3.5 w-3.5 text-accent" />
              ) : (
                <Moon className="h-3.5 w-3.5 text-accent" />
              )}
            </button>

            <button
              onClick={onToggleCollapse}
              title="Seitenleiste einklappen (⌘B)"
              className="flex h-7 w-7 items-center justify-center rounded-lg border border-border bg-card/60 text-muted-foreground transition-colors hover:border-accent hover:text-foreground hover:bg-accent/10"
              aria-label="Seitenleiste einklappen"
            >
              <PanelLeftClose className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </div>

      {/* Action Controls */}
      <div className={`pt-4 ${collapsed ? "px-2.5 flex flex-col items-center gap-2" : "px-4 space-y-2.5"}`}>
        {collapsed ? (
          <>
            <button
              onClick={onNewChat}
              title="Neuer Chat (⌘N)"
              className="flex h-10 w-10 items-center justify-center rounded-full bg-primary text-primary-foreground transition-all duration-300 hover:bg-accent hover:text-white shadow-sm"
              aria-label="Neuer Dialog"
            >
              <Plus className="h-4 w-4" />
            </button>
            {onOpenCommandPalette && (
              <button
                onClick={onOpenCommandPalette}
                title="Befehle & Suche (⌘K)"
                className="flex h-9 w-9 items-center justify-center rounded-full border border-border bg-card/60 text-muted-foreground hover:text-foreground hover:border-accent transition-colors"
                aria-label="Befehle öffnen"
              >
                <Search className="h-3.5 w-3.5 text-accent" />
              </button>
            )}
          </>
        ) : (
          <>
            <button
              onClick={onNewChat}
              className="group flex w-full items-center justify-between rounded-full bg-primary px-4 py-2.5 text-xs font-medium text-primary-foreground transition-all duration-300 hover:bg-accent hover:text-white hover:shadow-md"
            >
              <span className="flex items-center gap-2">
                <Plus className="h-3.5 w-3.5" />
                <span>Neuer Dialog</span>
              </span>
              <span className="font-mono text-[10px] opacity-70 group-hover:opacity-100">⌘N</span>
            </button>

            {onOpenCommandPalette && (
              <button
                onClick={onOpenCommandPalette}
                className="flex w-full items-center justify-between rounded-full border border-border bg-card/60 px-3.5 py-2 text-xs text-muted-foreground hover:border-accent hover:text-foreground hover:bg-accent/10 transition-all"
              >
                <span className="flex items-center gap-2 font-mono text-[11px]">
                  <Search className="h-3.5 w-3.5 text-accent" />
                  <span>Befehle & Suche…</span>
                </span>
                <span className="font-mono text-[10px] text-muted-foreground bg-background border border-border px-1.5 py-0.5 rounded">⌘K</span>
              </button>
            )}
          </>
        )}
      </div>

      {/* Conversation History / Collapsed Mini-Rail */}
      {collapsed ? (
        <div className="flex-1 flex flex-col items-center pt-6 space-y-3 overflow-y-auto px-1">
          <div className="relative group">
            <button
              onClick={onToggleCollapse}
              title={`${conversations.length} Konversationen (Klicken zum Öffnen)`}
              className="flex h-10 w-10 items-center justify-center rounded-xl border border-border bg-card text-muted-foreground hover:text-foreground hover:border-accent transition-colors"
            >
              <MessageSquare className="h-4 w-4" />
            </button>
            <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-accent text-[9px] font-mono font-bold text-white shadow">
              {conversations.length}
            </span>
          </div>
        </div>
      ) : (
        <>
          <div className="mt-6 flex items-center justify-between px-5 eyebrow">
            <span>Verlauf</span>
            <span className="text-accent font-semibold">{conversations.length}</span>
          </div>

          <nav className="mt-2.5 flex-1 overflow-y-auto px-3 pb-3">
            {conversationsError && (
              <p className="px-2 py-3 text-[12px] text-signal-amber">{conversationsError}</p>
            )}
            <ConversationList
              conversations={conversations}
              activeId={activeId}
              onSelect={onSelect}
              onRename={onRename}
              onDelete={onDelete}
            />
          </nav>
        </>
      )}

      {/* Navigation Footer Controls */}
      {collapsed ? (
        <div className="flex flex-col items-center gap-2 border-t border-border py-4 bg-background/50 backdrop-blur-md">
          <button
            onClick={onOpenControl}
            title="Control Center"
            className="flex h-9 w-9 items-center justify-center rounded-xl text-muted-foreground hover:text-foreground hover:bg-card transition-colors"
          >
            <Sliders className="h-4 w-4 text-accent" />
          </button>
          <button
            onClick={onOpenSettings}
            title="Einstellungen"
            className="flex h-9 w-9 items-center justify-center rounded-xl text-muted-foreground hover:text-foreground hover:bg-card transition-colors"
          >
            <Settings2 className="h-4 w-4 text-accent" />
          </button>
          {isSupabaseConfigured && (
            <button
              onClick={signOut}
              title="Abmelden"
              className="flex h-9 w-9 items-center justify-center rounded-xl text-muted-foreground hover:text-foreground hover:bg-card transition-colors"
            >
              <LogOut className="h-4 w-4 text-accent" />
            </button>
          )}
          <button
            onClick={toggleTheme}
            title="Theme umschalten"
            className="flex h-9 w-9 items-center justify-center rounded-xl text-muted-foreground hover:text-foreground hover:bg-card transition-colors"
          >
            {theme === "dark" ? <Sun className="h-4 w-4 text-accent" /> : <Moon className="h-4 w-4 text-accent" />}
          </button>
          <div
            className="mt-1 h-2 w-2 rounded-full"
            style={{ backgroundColor: modelOk ? "var(--color-accent)" : "var(--color-signal-amber)" }}
            title={modelOk ? "Bereit" : "Nicht verbunden"}
          />
        </div>
      ) : (
        <div className="space-y-1.5 border-t border-border px-3.5 py-3 bg-background/60 backdrop-blur-md">
          <button
            onClick={onOpenControl}
            className="flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-[12.5px] text-muted-foreground transition-colors hover:bg-card hover:text-foreground"
          >
            <Sliders className="h-4 w-4 text-accent" />
            <span>Control Center</span>
          </button>

          <button
            onClick={onOpenSettings}
            className="flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-[12.5px] text-muted-foreground transition-colors hover:bg-card hover:text-foreground"
          >
            <Settings2 className="h-4 w-4 text-accent" />
            <span>Einstellungen</span>
          </button>

          {isSupabaseConfigured && (
            <button
              onClick={signOut}
              title={user?.email ? `Abmelden (${user.email})` : "Abmelden"}
              className="flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-[12.5px] text-muted-foreground transition-colors hover:bg-card hover:text-foreground"
            >
              <LogOut className="h-4 w-4 text-accent" />
              <span>Abmelden</span>
            </button>
          )}
          
          <div className="pt-2 border-t border-border">
            <StatusFooter health={health} />
          </div>
        </div>
      )}
    </aside>
  );
}
