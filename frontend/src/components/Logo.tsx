/* Offizielles ZENJI-Markenzeichen mit Kreis-Emblem und japanisch-inspirierter Editorial-Typografie. */

import symbolLogo from "../assets/zenji-symbol.png";

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-3 select-none group cursor-pointer">
      {/* Das präzise Kreis-Emblem */}
      <div className="relative flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-full border border-border/80 bg-background transition-transform duration-700 group-hover:rotate-[360deg] shadow-sm">
        <img
          src={symbolLogo}
          alt="Zenji"
          className="h-full w-full object-contain p-0.5"
        />
      </div>

      {!compact && (
        <div className="flex flex-col leading-tight">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold tracking-[0.28em] text-foreground transition-colors group-hover:text-accent">
              ZENJI
            </span>
            <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse-dot" />
          </div>
          <span className="text-[9px] font-mono tracking-widest text-muted-foreground uppercase mt-0.5">
            Independent AI
          </span>
        </div>
      )}
    </div>
  );
}
