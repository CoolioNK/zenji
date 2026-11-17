/* Geteilte kleine Bausteine des Control Centers im Zenji Design-System. */

import type { ReactNode } from "react";

export function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-background/50 p-4">
      <h3 className="mb-3 eyebrow text-accent">
        {title}
      </h3>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

export function Badge({
  children,
  tone = "quiet",
}: {
  children: ReactNode;
  tone?: "jade" | "amber" | "quiet" | "solid";
}) {
  const tones: Record<string, string> = {
    jade: "border-accent/40 bg-accent/10 text-accent",
    amber: "border-signal-amber/40 bg-signal-amber/10 text-signal-amber",
    quiet: "border-border bg-card text-muted-foreground",
    solid: "border-border bg-primary text-primary-foreground",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function Card({ children, selected = false }: { children: ReactNode; selected?: boolean }) {
  return (
    <div
      className={`rounded-xl border p-4 transition-colors ${
        selected
          ? "border-accent bg-accent/5 shadow-sm"
          : "border-border bg-card hover:border-foreground/30"
      }`}
    >
      {children}
    </div>
  );
}

export function TextField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="block">
      <span className="text-xs text-foreground">{label}</span>
      <input
        type="text"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-1.5 font-mono text-xs text-foreground outline-none focus:border-accent transition-colors"
      />
    </label>
  );
}

export function TextArea({
  label,
  value,
  onChange,
  rows = 3,
  mono = false,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  rows?: number;
  mono?: boolean;
  placeholder?: string;
}) {
  return (
    <label className="block">
      <span className="text-xs text-foreground">{label}</span>
      <textarea
        rows={rows}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className={`mt-1.5 w-full resize-y rounded-lg border border-border bg-background p-3 text-xs leading-relaxed text-foreground outline-none focus:border-accent transition-colors ${
          mono ? "font-mono text-xs" : "font-sans"
        }`}
      />
    </label>
  );
}

export function SliderField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="block">
      <span className="flex items-center justify-between text-xs text-foreground">
        {label}
        <span className="font-mono text-[11px] text-accent font-medium">{Math.round(value * 100)}%</span>
      </span>
      <input
        type="range"
        min={0}
        max={1}
        step={0.05}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-2 w-full accent-accent"
      />
    </label>
  );
}

export function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="block">
      <span className="text-xs text-foreground">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2 text-xs text-foreground outline-none focus:border-accent transition-colors"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function PrimaryButton({
  children,
  onClick,
  disabled,
}: {
  children: ReactNode;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center justify-center rounded-full bg-primary px-4 py-2 text-xs font-medium text-primary-foreground transition-all duration-300 hover:bg-accent hover:text-white disabled:opacity-40 shadow-sm cursor-pointer"
    >
      {children}
    </button>
  );
}

export function QuietButton({
  children,
  onClick,
  disabled,
  danger = false,
}: {
  children: ReactNode;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`rounded-full border px-3.5 py-1.5 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
        danger
          ? "border-signal-amber/40 text-signal-amber hover:bg-signal-amber/10"
          : "border-border text-muted-foreground hover:bg-card hover:text-foreground"
      }`}
    >
      {children}
    </button>
  );
}

export function Hint({ children }: { children: ReactNode }) {
  return <p className="text-xs leading-relaxed text-muted-foreground">{children}</p>;
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return <p className="text-xs text-signal-amber">{children}</p>;
}
