/* Kompakter Recherche-Agent: Fortschritt und Quellen direkt an der Assistant-Antwort. */

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Loader2,
  Search,
} from "lucide-react";
import type { ChatResearchSummary, ResearchProgressEvent } from "../types";

const STEP_LABELS: Record<string, string> = {
  started: "Recherche gestartet",
  searching: "Suche läuft",
  searched: "Suche abgeschlossen",
  selecting: "Quellen werden ausgewählt",
  selected: "Quellen ausgewählt",
  fetching: "Quelle wird geladen",
  fetched: "Quelle geladen",
  comparing: "Quellen werden verglichen",
  comparing_sources: "Quellen werden verglichen",
  extracting: "Fakten werden extrahiert",
  extracted: "Fakten extrahiert",
  partial: "Teilweise abgeschlossen",
  completed: "Abgeschlossen",
  failed: "Fehlgeschlagen",
};

const STATUS_LABELS: Record<string, string> = {
  complete: "abgeschlossen",
  completed: "abgeschlossen",
  partial: "teilweise",
  degraded: "teilweise",
  failed: "fehlgeschlagen",
  error: "fehlgeschlagen",
};

function eventLabel(step: string): string {
  const key = step.trim().toLowerCase();
  return STEP_LABELS[key] ?? step;
}

function eventDetail(event: ResearchProgressEvent): string {
  const detail = event.detail;
  if (typeof detail !== "string") return "";
  return detail.trim();
}

function summaryStatus(summary: ChatResearchSummary | null): string {
  if (!summary) return "beendet";
  const raw = summary.status?.trim().toLowerCase() ?? "";
  return STATUS_LABELS[raw] ?? (summary.status?.trim() || "abgeschlossen");
}

export function ResearchActivity({
  events = [],
  summary = null,
  streaming = false,
}: {
  events?: ResearchProgressEvent[];
  summary?: ChatResearchSummary | null;
  streaming?: boolean;
}) {
  const running = streaming && !summary;
  const [expanded, setExpanded] = useState(streaming && !summary);

  useEffect(() => {
    if (running) setExpanded(true);
  }, [running]);

  useEffect(() => {
    if (summary) setExpanded(false);
  }, [summary]);

  if (events.length === 0 && !summary) return null;

  const lastEvent = events[events.length - 1];
  const status = running ? "läuft" : summaryStatus(summary);
  const sourceCount = summary?.sources.length ?? 0;
  const warnings = summary?.warnings ?? [];
  const hasWarnings = warnings.length > 0 || summary?.status === "partial" || summary?.status === "degraded";
  const compactDetail = running && lastEvent
    ? eventLabel(lastEvent.step)
    : sourceCount > 0
      ? `${sourceCount} ${sourceCount === 1 ? "Quelle" : "Quellen"}`
      : "Recherche";

  return (
    <div className="overflow-hidden rounded-xl border border-border/70 bg-card/40">
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        aria-expanded={expanded}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-card/70"
      >
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border/70 bg-background/70">
          {running ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" />
          ) : (
            <Search className="h-3.5 w-3.5 text-accent" />
          )}
        </span>

        <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          Recherche-Agent
        </span>

        <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground">
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              running
                ? "bg-accent animate-pulse-dot"
                : hasWarnings
                  ? "bg-signal-amber"
                  : "bg-emerald-400"
            }`}
          />
          {status}
        </span>

        <span className="ml-auto truncate text-[10px] text-muted-foreground/80">
          {compactDetail}
        </span>

        {expanded ? (
          <ChevronUp className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        )}
      </button>

      {expanded && (
        <div className="space-y-2.5 border-t border-border/60 px-3 py-2.5">
          {events.length > 0 && (
            <ul className="space-y-1">
              {events.slice(-8).map((event, index) => {
                const detail = eventDetail(event);
                return (
                  <li
                    key={`${event.step}-${index}`}
                    className="flex gap-2 text-[11px] leading-relaxed text-muted-foreground"
                  >
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent/70" />
                    <span className="min-w-0">
                      <span className="text-foreground/80">{eventLabel(event.step)}</span>
                      {detail && <span className="text-muted-foreground"> · {detail}</span>}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}

          {sourceCount > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {summary?.sources.map((source) => (
                <a
                  key={`${source.marker ?? "source"}-${source.url}`}
                  href={source.url}
                  target="_blank"
                  rel="noreferrer"
                  title={source.url}
                  className="inline-flex max-w-full items-center gap-1 rounded-full border border-border bg-background/60 px-2 py-0.5 font-mono text-[10px] text-muted-foreground transition-colors hover:border-accent hover:text-foreground"
                >
                  <span className="text-accent">[{source.marker ?? "?"}]</span>
                  <span className="max-w-[220px] truncate">{source.title || source.url}</span>
                  <ExternalLink className="h-2.5 w-2.5 opacity-60" />
                </a>
              ))}
            </div>
          )}

          {(summary?.contradiction_count ?? 0) > 0 && (
            <div className="flex items-center gap-1.5 text-[10px] text-signal-amber">
              <AlertTriangle className="h-3 w-3" />
              <span>
                {summary?.contradiction_count} Widerspruch/Widersprüche zwischen Quellen
              </span>
            </div>
          )}

          {warnings.length > 0 && (
            <div className="flex items-start gap-1.5 text-[10px] leading-relaxed text-signal-amber">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
              <span>{warnings.join(" ")}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}