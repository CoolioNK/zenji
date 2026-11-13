/* Konversationshistorie in der Sidebar. */

import type { Conversation } from "../types";

function relativeDate(iso: string): string {
  const date = new Date(iso);
  const diff = Date.now() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "jetzt";
  if (minutes < 60) return `${minutes} Min.`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} Std.`;
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
      <p className="px-2 py-6 text-center text-[12px] leading-relaxed text-ink-400">
        Noch keine Konversationen.
        <br />
        Starte einen neuen Chat.
      </p>
    );
  }

  return (
    <ul className="space-y-0.5">
      {conversations.map((conv) => {
        const active = conv.id === activeId;
        return (
          <li key={conv.id} className="group relative">
            <button
              onClick={() => onSelect(conv.id)}
              className={`w-full rounded-lg px-3 py-2 text-left transition-colors ${
                active
                  ? "bg-ink-700 text-ink-50"
                  : "text-ink-200 hover:bg-ink-800 hover:text-ink-50"
              }`}
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate text-[13px] font-medium">{conv.title}</span>
                <span
                  className={`shrink-0 text-[10px] ${active ? "text-ink-300" : "text-ink-500"}`}
                >
                  {relativeDate(conv.updated_at)}
                </span>
              </div>
              <div className="mt-0.5 text-[11px] text-ink-400">
                {conv.message_count} {conv.message_count === 1 ? "Nachricht" : "Nachrichten"}
              </div>
            </button>
            <div className="absolute top-1.5 right-1.5 hidden gap-1 group-hover:flex">
              <button
                title="Umbenennen"
                onClick={(e) => {
                  e.stopPropagation();
                  const title = window.prompt("Neuer Titel:", conv.title);
                  if (title && title.trim()) void onRename(conv.id, title.trim());
                }}
                className="rounded-md bg-ink-850/90 px-1.5 py-1 text-[11px] text-ink-300 hover:text-ink-50"
              >
                ✎
              </button>
              <button
                title="Löschen"
                onClick={(e) => {
                  e.stopPropagation();
                  if (window.confirm(`Konversation „${conv.title}“ löschen?`)) {
                    void onDelete(conv.id);
                  }
                }}
                className="rounded-md bg-ink-850/90 px-1.5 py-1 text-[11px] text-ink-300 hover:text-signal-red"
              >
                ✕
              </button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
