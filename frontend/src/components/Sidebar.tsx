/* Sidebar: Logo, neuer Chat, Verlauf, Einstellungen, Status. */

import { ConversationList } from "./ConversationList";
import { Logo } from "./Logo";
import { StatusFooter } from "./StatusFooter";
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
}) {
  return (
    <aside className="flex h-full w-[280px] shrink-0 flex-col border-r border-ink-700 bg-ink-850">
      <div className="px-5 pt-5 pb-4">
        <Logo />
      </div>

      <div className="px-3">
        <button
          onClick={onNewChat}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-jade-600 px-3 py-2.5 text-[13px] font-medium text-ink-950 transition-colors hover:bg-jade-500"
        >
          <span className="text-[15px] leading-none">+</span> Neuer Chat
        </button>
      </div>

      <div className="mt-5 px-4 text-[10px] font-semibold tracking-[0.16em] text-ink-500 uppercase">
        Verlauf
      </div>
      <nav className="mt-1.5 flex-1 overflow-y-auto px-3 pb-2">
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

      <div className="space-y-3 border-t border-ink-700 px-4 py-4">
        <button
          onClick={onOpenControl}
          className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-[13px] text-ink-200 transition-colors hover:bg-ink-800 hover:text-ink-50"
        >
          <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
            <rect x="2.5" y="2.5" width="6" height="6" rx="1.2" />
            <rect x="11.5" y="2.5" width="6" height="6" rx="1.2" />
            <rect x="2.5" y="11.5" width="6" height="6" rx="1.2" />
            <rect x="11.5" y="11.5" width="6" height="6" rx="1.2" />
          </svg>
          Control Center
        </button>
        <button
          onClick={onOpenSettings}
          className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-[13px] text-ink-200 transition-colors hover:bg-ink-800 hover:text-ink-50"
        >
          <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
            <circle cx="10" cy="10" r="2.6" />
            <path d="M10 2.5v2.2M10 15.3v2.2M17.5 10h-2.2M4.7 10H2.5M15.3 4.7l-1.6 1.6M6.3 13.7l-1.6 1.6M15.3 15.3l-1.6-1.6M6.3 6.3L4.7 4.7" strokeLinecap="round" />
          </svg>
          Einstellungen
        </button>
        <StatusFooter health={health} />
      </div>
    </aside>
  );
}
