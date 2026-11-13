/* ZENJI-Wortmarke mit Enso-Zeichen. */

export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-3 select-none">
      <svg viewBox="0 0 64 64" className="h-7 w-7 shrink-0" aria-hidden="true">
        <circle
          cx="32"
          cy="32"
          r="24"
          fill="none"
          stroke="#46b592"
          strokeWidth="5"
          strokeLinecap="round"
          strokeDasharray="132 20"
          transform="rotate(-70 32 32)"
        />
      </svg>
      {!compact && (
        <div className="leading-none">
          <div className="text-[17px] font-semibold tracking-[0.28em] text-ink-50">
            ZENJI
          </div>
          <div className="mt-1 text-[10px] tracking-[0.18em] text-ink-400 uppercase">
            Lokales KI-System
          </div>
        </div>
      )}
    </div>
  );
}
