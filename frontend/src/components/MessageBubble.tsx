/* Einzelne Nachricht im Zenji Editorial Design-System (inspiriert von InteractivePreview). */

import { useState } from "react";
import type { Message } from "../types";
import { ResearchActivity } from "./ResearchActivity";
import symbolLogo from "../assets/zenji-symbol.png";
import { 
  Copy, 
  Check, 
  Terminal, 
  ThumbsUp, 
  ThumbsDown, 
  Sparkles, 
  ChevronDown, 
  ChevronUp 
} from "lucide-react";

/* Extrahiert optionale <think>...</think> Tags aus LLM-Antworten */
function extractThinking(content: string): { thought: string | null; response: string } {
  const closedMatch = content.match(/<think>([\s\S]*?)<\/think>/i);
  if (closedMatch) {
    const thought = closedMatch[1].trim();
    const response = content.replace(/<think>[\s\S]*?<\/think>/i, "").trim();
    return { thought, response };
  }

  // Für laufende Streaming-Antworten mit noch ungeschlossenem <think>
  const openMatch = content.match(/<think>([\s\S]*)$/i);
  if (openMatch) {
    return { thought: openMatch[1].trim(), response: "" };
  }

  return { thought: null, response: content };
}

/* Code-Block Komponente mit Sprach-Badge und Kopier-Button */
function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);

  const copyCode = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="my-3.5 overflow-hidden rounded-xl border border-border bg-black/40 font-mono text-xs shadow-md">
      <div className="flex items-center justify-between border-b border-border bg-card/60 px-4 py-2 text-muted-foreground">
        <span className="flex items-center gap-1.5 text-[11px] font-mono text-accent uppercase tracking-wider font-semibold">
          <Terminal className="h-3 w-3" />
          <span>{language || "code"}</span>
        </span>
        <button
          onClick={copyCode}
          className="flex items-center gap-1.5 rounded-full border border-border bg-card/80 px-2.5 py-1 text-[11px] text-muted-foreground hover:text-foreground hover:border-accent transition-all"
        >
          {copied ? (
            <>
              <Check className="h-3 w-3 text-emerald-400" />
              <span>Kopiert</span>
            </>
          ) : (
            <>
              <Copy className="h-3 w-3" />
              <span>Kopieren</span>
            </>
          )}
        </button>
      </div>
      <pre className="overflow-x-auto p-4 text-foreground leading-relaxed font-mono">
        <code>{code}</code>
      </pre>
    </div>
  );
}

/* Formatierte Text-Darstellung (Code-Blocks, Fette Schrift, Listen, Inline-Code) */
function FormattedContent({ content }: { content: string }) {
  const parts = content.split(/(```[\s\S]*?```)/g);

  return (
    <div className="space-y-2">
      {parts.map((part, index) => {
        if (part.startsWith("```") && part.endsWith("```")) {
          const lines = part.slice(3, -3).trim().split("\n");
          const firstLine = lines[0].trim();
          const hasLang = /^[a-zA-Z0-9_-]+$/.test(firstLine);
          const lang = hasLang ? firstLine : "";
          const code = (hasLang ? lines.slice(1) : lines).join("\n");
          return <CodeBlock key={index} language={lang} code={code} />;
        }

        const paragraphs = part.split("\n\n");
        return (
          <div key={index} className="space-y-2">
            {paragraphs.map((para, pIdx) => {
              if (!para.trim()) return null;
              
              const lines = para.split("\n");
              return (
                <p key={pIdx} className="leading-relaxed">
                  {lines.map((line, lIdx) => {
                    const isBullet = line.trim().startsWith("- ") || line.trim().startsWith("• ");
                    const cleanLine = isBullet ? line.trim().slice(2) : line;

                    return (
                      <span key={lIdx} className={isBullet ? "block pl-4 relative my-1" : "block"}>
                        {isBullet && (
                          <span className="absolute left-0 text-accent font-bold">›</span>
                        )}
                        <InlineMarkdown text={cleanLine} />
                      </span>
                    );
                  })}
                </p>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}

function InlineMarkdown({ text }: { text: string }) {
  const tokens = text.split(/(\*\*.*?\*\*|`.*?`)/g);

  return (
    <>
      {tokens.map((token, i) => {
        if (token.startsWith("**") && token.endsWith("**")) {
          return (
            <strong key={i} className="font-semibold text-foreground">
              {token.slice(2, -2)}
            </strong>
          );
        }
        if (token.startsWith("`") && token.endsWith("`")) {
          return (
            <code
              key={i}
              className="rounded bg-background px-1.5 py-0.5 font-mono text-[12px] text-accent border border-border"
            >
              {token.slice(1, -1)}
            </code>
          );
        }
        return <span key={i}>{token}</span>;
      })}
    </>
  );
}

export function MessageBubble({
  message,
  streaming,
}: {
  message: Message;
  streaming?: boolean;
}) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);
  const [showThought, setShowThought] = useState(false);

  const { thought, response } = !isUser
    ? extractThinking(message.content)
    : { thought: null, response: message.content };

  const copyText = () => {
    navigator.clipboard.writeText(response || message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (isUser) {
    return (
      <div className="flex items-start gap-3.5 justify-end group animate-fade-up">
        <div className="rounded-2xl rounded-tr-sm border border-border/80 bg-card/80 px-5 py-3.5 text-sm md:text-base leading-relaxed text-foreground max-w-2xl shadow-sm">
          {message.content}
        </div>
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-border text-xs font-mono font-medium text-foreground">
          DU
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start gap-4 group animate-fade-up">
      {/* Zenji Avatar Emblem */}
      <div className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-border bg-background overflow-hidden p-0.5 shadow-sm">
        <img src={symbolLogo} alt="Zenji" className="h-full w-full object-contain" />
      </div>

      <div className="flex-1 space-y-3 max-w-3xl">
        {/* Denkprozess (Gedankenkette & Validierung) wie in InteractivePreview */}
        {thought && (
          <div className="rounded-lg border border-border/80 bg-card/40 overflow-hidden">
            <button
              onClick={() => setShowThought(!showThought)}
              className="flex w-full items-center justify-between px-4 py-2.5 text-xs font-mono text-muted-foreground hover:text-foreground transition-colors"
            >
              <span className="flex items-center gap-2">
                <Sparkles className="h-3.5 w-3.5 text-accent" />
                <span>Interner Denkprozess (Gedankenkette & Validierung)</span>
              </span>
              {showThought ? (
                <ChevronUp className="h-3.5 w-3.5" />
              ) : (
                <ChevronDown className="h-3.5 w-3.5" />
              )}
            </button>
            {showThought && (
              <div className="border-t border-border/50 px-4 py-3 font-mono text-xs text-muted-foreground/90 whitespace-pre-line leading-relaxed bg-black/10">
                {thought}
              </div>
            )}
          </div>
        )}

        {/* Recherche als kompakter Subagent direkt über der Antwort */}
        <ResearchActivity
          events={message.researchEvents}
          summary={message.researchSummary}
          streaming={streaming}
        />

        {/* Main Response Box */}
        <div className="rounded-2xl rounded-tl-sm border border-border/80 bg-card/60 p-5 md:p-6 text-sm md:text-base leading-relaxed text-foreground/95 shadow-sm font-sans">
          <FormattedContent content={response} />
          {streaming && (
            <span className="inline-block h-4 w-1.5 ml-1 bg-accent animate-pulse align-middle" />
          )}
        </div>

        {/* Action Controls on Hover */}
        {!streaming && (
          <div className="flex items-center gap-2 pt-1 opacity-60 group-hover:opacity-100 transition-opacity">
            <button
              onClick={copyText}
              title="Antwort kopieren"
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-card/60 px-2.5 py-1 text-[11px] font-mono text-muted-foreground hover:text-foreground hover:border-accent transition-colors"
            >
              {copied ? (
                <>
                  <Check className="h-3 w-3 text-emerald-400" />
                  <span>Kopiert</span>
                </>
              ) : (
                <>
                  <Copy className="h-3 w-3" />
                  <span>Kopieren</span>
                </>
              )}
            </button>

            <button
              onClick={() => setFeedback(feedback === "up" ? null : "up")}
              title="Gute Antwort"
              className={`flex h-6 w-6 items-center justify-center rounded-full border border-border bg-card/60 text-muted-foreground transition-colors ${
                feedback === "up" ? "border-accent text-accent bg-accent/10" : "hover:text-foreground hover:border-accent"
              }`}
            >
              <ThumbsUp className="h-3 w-3" />
            </button>

            <button
              onClick={() => setFeedback(feedback === "down" ? null : "down")}
              title="Verbesserungswürdig"
              className={`flex h-6 w-6 items-center justify-center rounded-full border border-border bg-card/60 text-muted-foreground transition-colors ${
                feedback === "down" ? "border-accent text-accent bg-accent/10" : "hover:text-foreground hover:border-accent"
              }`}
            >
              <ThumbsDown className="h-3 w-3" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
