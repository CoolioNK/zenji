/* Chat-Hauptbereich im Zenji Editorial Design-System */

import { useEffect, useRef } from "react";
import { Composer } from "./Composer";
import { MessageBubble } from "./MessageBubble";
import symbolLogo from "../assets/zenji-symbol.png";
import type { ChatError, CommunicationModeKey, Health, Message, ResearchMode } from "../types";
import { 
  Sparkles, 
  PanelLeftOpen, 
  PanelLeftClose, 
  Download, 
  Search,
  Code2,
  PenTool,
  Compass,
  ArrowRight
} from "lucide-react";

const SUGGESTED_PROMPTS = [
  {
    num: "01",
    tag: "Strategie",
    title: "Ideen & Konzepte strukturieren",
    prompt: "Lass uns ein neues Vorhaben strukturieren und die wichtigsten Kernfragen sowie nächste Schritte definieren.",
    icon: Compass,
  },
  {
    num: "02",
    tag: "Schreiben",
    title: "Prägnante Texte & Gedanken",
    prompt: "Hilf mir, einen prägnanten Text mit klarer Haltung, Ruhe und eleganter Sprache zu verfassen.",
    icon: PenTool,
  },
  {
    num: "03",
    tag: "Philosophie",
    title: "Was unterscheidet Zenji?",
    prompt: "Was unterscheidet Zenji von herkömmlichen Chatbots und wie prägt die Philosophie das System?",
    icon: Sparkles,
  },
  {
    num: "04",
    tag: "Architektur",
    title: "System-Architektur & Inferenz",
    prompt: "Erkläre Zenjis System-Architektur und warum Unabhängigkeit der Kern ist.",
    icon: Code2,
  },
];

export function ChatArea({
  messages,
  streaming,
  chatError,
  health,
  onSend,
  onStop,
  sidebarCollapsed,
  onToggleSidebar,
  onOpenCommandPalette,
  activeConversationTitle,
  researchMode = "auto",
}: {
  messages: Message[];
  streaming: boolean;
  chatError: ChatError | null;
  health: Health | null;
  onSend: (text: string, mode: CommunicationModeKey | null, research?: ResearchMode) => void;
  onStop: () => void;
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
  onOpenCommandPalette: () => void;
  activeConversationTitle?: string | null;
  researchMode?: ResearchMode;
}) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const serviceUnavailable = health !== null && (!health.ollama.available || !health.model.available);

  /* Export der Konversation als formatierte Markdown-Datei */
  const exportAsMarkdown = () => {
    if (messages.length === 0) return;
    const title = activeConversationTitle || "Zenji-Konversation";
    let md = `# ${title}\n\n*Exportiert aus ZENJI (${new Date().toLocaleString("de-DE")})*\n\n---\n\n`;
    messages.forEach((m) => {
      const role = m.role === "user" ? "### Du" : "### Zenji";
      md += `${role}\n\n${m.content}\n\n`;
    });

    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${title.toLowerCase().replace(/[^a-z0-9_-]/g, "_")}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="flex h-full min-w-0 flex-1 flex-col bg-background relative overflow-hidden text-foreground">
      {/* Background Japanese Grid Texture aus der Zenji Info Seite */}
      <div className="pointer-events-none absolute inset-0 [background-image:linear-gradient(var(--border)_1px,transparent_1px),linear-gradient(90deg,var(--border)_1px,transparent_1px)] [background-size:80px_80px] opacity-25 [mask-image:radial-gradient(ellipse_at_center,black_40%,transparent_80%)]" />
      {/* Subtiler roter Ambient-Glow */}
      <div className="pointer-events-none absolute top-0 inset-x-0 h-[480px] bg-[radial-gradient(ellipse_80%_60%_at_50%_-10%,rgba(166,59,54,0.12),transparent_70%)]" />

      {/* Header Bar im Zenji Info Stil */}
      <header className="flex h-16 shrink-0 items-center justify-between border-b border-border bg-card/60 px-5 backdrop-blur-md z-10 select-none">
        <div className="flex items-center gap-3">
          <button
            onClick={onToggleSidebar}
            title={sidebarCollapsed ? "Seitenleiste ausklappen (⌘B)" : "Seitenleiste einklappen (⌘B)"}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-background text-muted-foreground hover:text-foreground hover:border-accent transition-colors"
          >
            {sidebarCollapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </button>

          <div className="flex items-center gap-2.5 max-w-[280px] sm:max-w-md">
            <span className="truncate text-sm font-medium text-foreground tracking-tight">
              {activeConversationTitle || "Neuer Dialog"}
            </span>
            {messages.length > 0 && (
              <span className="font-mono text-[10px] text-muted-foreground bg-background border border-border px-2 py-0.5 rounded-full shrink-0">
                {messages.length} {messages.length === 1 ? "Nachricht" : "Nachrichten"}
              </span>
            )}
          </div>
        </div>

        {/* Header Actions */}
        <div className="flex items-center gap-2">
          {messages.length > 0 && (
            <button
              onClick={exportAsMarkdown}
              title="Als Markdown exportieren"
              className="flex h-8 items-center gap-1.5 rounded-full border border-border bg-card/60 px-3 text-xs font-mono text-muted-foreground hover:text-foreground hover:border-accent transition-colors"
            >
              <Download className="h-3.5 w-3.5 text-accent" />
              <span className="hidden sm:inline">Export</span>
            </button>
          )}

          <button
            onClick={onOpenCommandPalette}
            title="Befehlspalette öffnen (⌘K)"
            className="hidden sm:flex h-8 items-center gap-1.5 rounded-full border border-border bg-card/60 px-3 text-xs font-mono text-muted-foreground hover:text-foreground hover:border-accent transition-colors"
          >
            <Search className="h-3.5 w-3.5 text-accent" />
            <span>⌘K</span>
          </button>
        </div>
      </header>

      {/* Message Scroll Area */}
      <div className="flex-1 overflow-y-auto px-4 py-6 md:px-8 z-0">
        <div className="mx-auto max-w-4xl space-y-6">
          {/* Status Alert bei fehlender Backend-Verbindung */}
          {serviceUnavailable && (
            <div className="rounded-xl border border-signal-amber/40 bg-card p-4 text-xs font-mono text-signal-amber flex items-center justify-between">
              <span>Lokales Backend oder LLM-Inferenz nicht erreichbar. Prüfe bitte Port 8000 & Ollama 11434.</span>
            </div>
          )}

          {/* Chat-Fehleranzeige */}
          {chatError && (
            <div className="rounded-xl border border-signal-red/40 bg-card p-4 text-xs font-mono text-signal-red">
              <span className="font-semibold">Fehler ({chatError.code}):</span> {chatError.message}
            </div>
          )}

          {/* Hero Welcome View (wie Hero-Bereich der Zenji Info Seite) */}
          {messages.length === 0 && !chatError && !serviceUnavailable && (
            <div className="flex flex-col items-center justify-center pt-10 pb-12 text-center animate-fade-up">
              {/* Kinetische Ensō & Offizielles Zenji Emblem */}
              <div className="relative flex h-28 w-28 items-center justify-center my-2" aria-hidden="true">
                {/* Roter Ambient Glow */}
                <div className="absolute inset-2 rounded-full bg-accent/20 blur-2xl animate-red-glow" />

                {/* Äußerer Orbit */}
                <svg viewBox="0 0 160 160" className="absolute inset-0 h-full w-full animate-orbit text-border" aria-hidden="true">
                  <circle cx="80" cy="80" r="76" fill="none" stroke="currentColor" strokeWidth="1" strokeDasharray="3 6" />
                  <circle cx="80" cy="4" r="3" className="fill-accent" />
                </svg>

                {/* Innerer Gegendreh-Orbit */}
                <svg viewBox="0 0 160 160" className="absolute inset-2 h-[88%] w-[88%] animate-orbit-rev text-border/70" aria-hidden="true">
                  <circle cx="80" cy="80" r="76" fill="none" stroke="currentColor" strokeWidth="1" />
                  <circle cx="4" cy="80" r="2.5" className="fill-foreground" />
                </svg>

                {/* Zentrales Zenji-Emblem */}
                <div className="relative flex h-16 w-16 items-center justify-center rounded-full border border-border/80 bg-background/80 shadow-2xl p-2.5 animate-breathe">
                  <img
                    src={symbolLogo}
                    alt="Zenji Emblem"
                    className="h-full w-full object-contain filter drop-shadow-md"
                  />
                </div>
              </div>

              {/* Main Headline */}
              <h1 className="display mt-6 text-3xl md:text-5xl font-medium tracking-tight text-foreground leading-[0.94]">
                Intelligence, <span className="serif-italic text-accent">reimagined.</span>
              </h1>

              <p className="serif-italic mt-3 text-lg md:text-xl text-foreground/90">
                Build intelligence. Shape the future.
              </p>

              <p className="mt-3 max-w-md text-xs md:text-sm leading-relaxed text-muted-foreground">
                Unabhängige Architektur, lokaler Inferenz-Kern und japanisch inspirierte Gestaltungsphilosophie.
              </p>

              {/* Architectural Starter Cards im Zenji Info Layout */}
              <div className="mt-10 grid w-full grid-cols-1 sm:grid-cols-2 gap-4 text-left">
                {SUGGESTED_PROMPTS.map((item) => {
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.num}
                      onClick={() => onSend(item.prompt, null)}
                      className="group relative flex flex-col justify-between rounded-xl border border-border bg-card/60 p-5 text-left transition-all duration-300 hover:border-accent hover:bg-card hover:shadow-md cursor-pointer"
                    >
                      <div className="flex items-center justify-between w-full">
                        <span className="font-mono text-xs text-accent font-semibold">{item.num}</span>
                        <span className="eyebrow text-[10px] group-hover:text-foreground transition-colors">
                          {item.tag}
                        </span>
                      </div>

                      <div className="mt-4">
                        <h3 className="text-sm font-medium text-foreground group-hover:text-accent transition-colors">
                          {item.title}
                        </h3>
                        <p className="mt-1.5 text-xs text-muted-foreground leading-relaxed line-clamp-2">
                          {item.prompt}
                        </p>
                      </div>

                      <div className="mt-4 pt-3 border-t border-border flex items-center justify-between text-xs font-mono text-muted-foreground group-hover:text-accent transition-colors">
                        <span className="inline-flex items-center gap-1.5">
                          <Icon className="h-3 w-3" />
                          <span>Ausführen</span>
                        </span>
                        <ArrowRight className="h-3 w-3 transition-transform group-hover:translate-x-1" />
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Messages Stream */}
          {messages.map((message) => (
            <MessageBubble
              key={message.id}
              message={message}
              streaming={streaming && message === messages[messages.length - 1] && message.role === "assistant"}
            />
          ))}
          <div ref={endRef} />
        </div>
      </div>

      <Composer
        disabled={health === null}
        streaming={streaming}
        onSend={onSend}
        onStop={onStop}
        research={researchMode}
      />
    </section>
  );
}
