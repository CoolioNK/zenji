/* ZENJI Control Center – rechte Schublade mit fünf Bereichen.
   Bereiche: Personality · Policies · Memory · Core Status · Web (v0.5.0). */

import { useState } from "react";
import { PersonalityTab } from "./PersonalityTab";
import { PoliciesTab } from "./PoliciesTab";
import { MemoryTab } from "./MemoryTab";
import { CoreTab } from "./CoreTab";
import { WebIntelligenceTab } from "./WebIntelligenceTab";

export type ControlTab = "personality" | "policies" | "memory" | "core" | "web";

const TABS: { key: ControlTab; label: string }[] = [
  { key: "personality", label: "Personality" },
  { key: "policies", label: "Policies" },
  { key: "memory", label: "Memory" },
  { key: "core", label: "Core Status" },
  { key: "web", label: "Web" },
];

export function ControlCenter({
  open,
  activeConversationId,
  onClose,
}: {
  open: boolean;
  activeConversationId: string | null;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<ControlTab>("personality");

  if (!open) return null;

  return (
    <div className="fixed inset-y-0 right-0 z-20 flex w-[600px] flex-col border-l border-ink-700 bg-ink-850 shadow-2xl">
      <div className="flex items-center justify-between border-b border-ink-700 px-5 py-4">
        <div>
          <h2 className="text-[14px] font-semibold tracking-wide text-ink-50">
            ZENJI Control Center
          </h2>
          <p className="mt-0.5 text-[11px] text-ink-400">
            Identität, Regeln, Gedächtnis und Kontext steuern
          </p>
        </div>
        <button
          onClick={onClose}
          className="rounded-md px-2 py-1 text-[13px] text-ink-300 hover:bg-ink-800 hover:text-ink-50"
          aria-label="Control Center schließen"
        >
          ✕
        </button>
      </div>

      <div
        className="flex gap-1 border-b border-ink-700 px-4 py-2"
        role="tablist"
        aria-label="Control Center Bereiche"
      >
        {TABS.map((entry) => (
          <button
            key={entry.key}
            role="tab"
            aria-selected={tab === entry.key}
            onClick={() => setTab(entry.key)}
            className={`rounded-lg px-3 py-1.5 text-[12.5px] transition-colors ${
              tab === entry.key
                ? "bg-ink-800 text-ink-50"
                : "text-ink-400 hover:bg-ink-800/60 hover:text-ink-200"
            }`}
          >
            {entry.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto px-5 py-5">
        {tab === "personality" && <PersonalityTab />}
        {tab === "policies" && <PoliciesTab />}
        {tab === "memory" && <MemoryTab />}
        {tab === "core" && <CoreTab activeConversationId={activeConversationId} />}
        {tab === "web" && <WebIntelligenceTab />}
      </div>
    </div>
  );
}
