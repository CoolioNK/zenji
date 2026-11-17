/* ZENJI Control Center – rechte Schublade im Zenji Editorial Design-System */

import { useState } from "react";
import { PersonalityTab } from "./PersonalityTab";
import { PoliciesTab } from "./PoliciesTab";
import { MemoryTab } from "./MemoryTab";
import { CoreTab } from "./CoreTab";
import { WebIntelligenceTab } from "./WebIntelligenceTab";
import { X } from "lucide-react";

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
    <div className="fixed inset-y-0 right-0 z-40 flex w-full max-w-[620px] flex-col border-l border-border bg-card shadow-2xl backdrop-blur-2xl animate-fade-up">
      <div className="flex items-center justify-between border-b border-border px-6 py-4 bg-background/60">
        <div>
          <h2 className="text-base font-semibold tracking-wide text-foreground">
            ZENJI Control Center
          </h2>
          <p className="mt-0.5 text-xs text-muted-foreground font-mono">
            Identität, Regeln, Gedächtnis und Kontext steuern
          </p>
        </div>
        <button
          onClick={onClose}
          className="flex h-7 w-7 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground hover:text-foreground hover:border-accent transition-colors"
          aria-label="Control Center schließen"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div
        className="flex gap-2 border-b border-border px-6 py-2.5 bg-background/40"
        role="tablist"
        aria-label="Control Center Bereiche"
      >
        {TABS.map((entry) => (
          <button
            key={entry.key}
            role="tab"
            aria-selected={tab === entry.key}
            onClick={() => setTab(entry.key)}
            className={`rounded-full px-3.5 py-1.5 font-mono text-xs transition-colors ${
              tab === entry.key
                ? "bg-primary text-primary-foreground font-medium shadow-sm"
                : "text-muted-foreground hover:bg-card hover:text-foreground border border-transparent"
            }`}
          >
            {entry.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6">
        {tab === "personality" && <PersonalityTab />}
        {tab === "policies" && <PoliciesTab />}
        {tab === "memory" && <MemoryTab />}
        {tab === "core" && <CoreTab activeConversationId={activeConversationId} />}
        {tab === "web" && <WebIntelligenceTab />}
      </div>
    </div>
  );
}
