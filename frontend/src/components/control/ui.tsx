/* Geteilte kleine Bausteine des Control Centers (Design aus SettingsPanel). */

import type { ReactNode } from "react";

export function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h3 className="mb-3 text-[10px] font-semibold tracking-[0.16em] text-ink-500 uppercase">
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
    jade: "border-jade-600/60 bg-jade-600/10 text-jade-500",
    amber: "border-signal-amber/50 bg-signal-amber/10 text-signal-amber",
    quiet: "border-ink-600 bg-ink-800 text-ink-300",
    solid: "border-ink-500 bg-ink-700 text-ink-100",
  };
  return (
    <span
      className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-medium tracking-wide uppercase ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function Card({ children, selected = false }: { children: ReactNode; selected?: boolean }) {
  return (
    <div
      className={`rounded-xl border px-4 py-3 transition-colors ${
        selected
          ? "border-jade-600/70 bg-ink-900"
          : "border-ink-700 bg-ink-900 hover:border-ink-600"
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
      <span className="text-[12.5px] text-ink-200">{label}</span>
      <input
        type="text"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1.5 w-full rounded-lg border border-ink-600 bg-ink-900 px-3 py-2 text-[12.5px] text-ink-50 outline-none focus:border-jade-600"
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
      <span className="text-[12.5px] text-ink-200">{label}</span>
      <textarea
        rows={rows}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className={`mt-1.5 w-full resize-y rounded-lg border border-ink-600 bg-ink-900 px-3 py-2 text-[12.5px] leading-relaxed text-ink-50 outline-none focus:border-jade-600 ${
          mono ? "font-mono text-[11.5px]" : ""
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
      <span className="flex items-center justify-between text-[12.5px] text-ink-200">
        {label}
        <span className="text-[11px] text-ink-400">{Math.round(value * 100)}%</span>
      </span>
      <input
        type="range"
        min={0}
        max={1}
        step={0.05}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-1.5 w-full accent-jade-600"
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
      <span className="text-[12.5px] text-ink-200">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1.5 w-full rounded-lg border border-ink-600 bg-ink-900 px-3 py-2 text-[12.5px] text-ink-50 outline-none focus:border-jade-600"
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
      className="rounded-lg bg-jade-600 px-3.5 py-2 text-[12.5px] font-medium text-ink-950 transition-colors hover:bg-jade-500 disabled:bg-ink-700 disabled:text-ink-400"
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
      className={`rounded-lg border px-3 py-2 text-[12.5px] transition-colors disabled:cursor-not-allowed disabled:border-ink-700 disabled:text-ink-600 ${
        danger
          ? "border-signal-amber/40 text-signal-amber hover:bg-signal-amber/10"
          : "border-ink-600 text-ink-200 hover:bg-ink-800 hover:text-ink-50"
      }`}
    >
      {children}
    </button>
  );
}

export function Hint({ children }: { children: ReactNode }) {
  return <p className="text-[11.5px] leading-relaxed text-ink-400">{children}</p>;
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return <p className="text-[12px] text-signal-amber">{children}</p>;
}
