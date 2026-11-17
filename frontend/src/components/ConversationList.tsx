/* Konversationshistorie im Zenji Design-System mit dezenten Hover-Aktionen und Akzenten. */

import type { Conversation } from "../types";
import { MessageSquare, Edit2, Trash2, Clock } from "lucide-react";

function relativeDate(iso: string): string {
  const date = new Date(iso);
  const diff = Date.now() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "jetzt";
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return date.toLocaleDateString("de-DE", { day: "2-digit", month: "short" });
}

export function ConversationList({
  conversations,
  activeId,
  onSelect,
  onRename,
  onDelete,
}: {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
}) {
  if (conversations.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 px-3 text-center text-muted-foreground">
        <div className="flex h-10 w-10 items-center justify-center rounded-full border border-border bg-card/60 mb-3 text-accent">
          <Clock className="h-4 w-4" />
        </div>
        <p className="text-xs font-medium text-foreground">Keine Konversationen</p>
        <p className="text-[11px] text-muted-foreground mt-1">Beginne deinen ersten Dialog</p>
      </div>
    );
  }

  return (
    <ul className="space-y-1">
      {conversations.map((conv) => {
        const active = conv.id === activeId;
        return (
          <li key={conv.id} className="group relative">
            <button
              onClick={() => onSelect(conv.id)}
              className={`w-full rounded-xl px-3 py-2.5 text-left transition-all duration-200 flex flex-col justify-between ${
                active
                  ? "bg-card text-foreground shadow-sm border border-border border-l-2 border-l-accent"
                  : "text-muted-foreground hover:bg-card/60 hover:text-foreground border border-transparent"
              }`}
            >
              <div className="flex items-center justify-between gap-2 w-full">
                <span className={`truncate text-[13px] ${active ? "font-semibold text-foreground" : "font-normal"}`}>
                  {conv.title}
                </span>
                <span
                  className={`shrink-0 font-mono text-[10px] ${
                    active ? "text-accent font-semibold" : "text-muted-foreground"
                  }`}
                >
                  {relativeDate(conv.updated_at)}
                </span>
              </div>

              <div className="mt-1 flex items-center justify-between text-[11px] text-muted-foreground font-mono">
                <span className="flex items-center gap-1.5 opacity-80">
                  <MessageSquare className="h-2.5 w-2.5 text-accent" />
                  <span>{conv.message_count} {conv.message_count === 1 ? "Nachricht" : "Nachrichten"}</span>
                </span>
              </div>
            </button>

            {/* Quick Action Buttons on Hover */}
            <div className="absolute top-2.5 right-2 hidden items-center gap-1 group-hover:flex bg-card/95 backdrop-blur-md p-0.5 rounded-lg border border-border shadow-md">
              <button
                title="Titel bearbeiten"
                onClick={(e) => {
                  e.stopPropagation();
                  const title = window.prompt("Neuer Titel:", conv.title);
                  if (title && title.trim()) void onRename(conv.id, title.trim());
                }}
                className="flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-accent/10 transition-colors"
              >
                <Edit2 className="h-3 w-3" />
              </button>
              <button
                title="Löschen"
                onClick={(e) => {
                  e.stopPropagation();
                  if (window.confirm(`Konversation „${conv.title}“ löschen?`)) {
                    void onDelete(conv.id);
                  }
                }}
                className="flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground hover:text-signal-red hover:bg-signal-red/10 transition-colors"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
