/* Control Center – Tab Core Status: Kern-Zustände und Kontext-Vorschau. */

import { useState } from "react";
import { useCoreStatus } from "../../hooks/useCoreStatus";
import { Badge, ErrorNote, Group, Hint, PrimaryButton } from "./ui";

export function CoreTab({ activeConversationId }: { activeConversationId: string | null }) {
  const { status, preview, loading, previewLoading, error, refresh, loadPreview } =
    useCoreStatus();
  const [message, setMessage] = useState("Was kannst du, ZENJI?");
  const [useHistory, setUseHistory] = useState(true);

  if (loading && !status) {
    return <p className="text-[13px] text-ink-400">Core-Status wird geladen …</p>;
  }

  const usage = preview
    ? Math.round((preview.used_tokens / Math.max(1, preview.budget_tokens)) * 100)
    : 0;

  return (
    <div className="space-y-6">
      {error && <ErrorNote>{error}</ErrorNote>}

      <Group title="Kern-Zustände">
        <div className="rounded-xl border border-ink-700 bg-ink-900 px-4 py-4">
          <dl className="space-y-2.5 text-[12.5px]">
            <Row label="Version">{status?.version ?? "–"}</Row>
            <Row label="Aktive Persönlichkeit">
              {status?.personality ? (
                <Badge tone="jade">{status.personality}</Badge>
              ) : (
                <span className="text-ink-400">kein Profil aktiv</span>
              )}
            </Row>
            <Row label="Aktive Regeln">{status?.active_policies ?? 0}</Row>
            <Row label="Regelkonflikte">{status?.policy_conflicts ?? 0}</Row>
            <Row label="Erinnerungen">
              {status ? `${status.memories.active} aktiv · ${status.memories.superseded} veraltet` : "–"}
            </Row>
            <Row label="Aktives Modell">Zenji Ango</Row>
            <Row label="Provider">{status?.provider ?? "–"}</Row>
            <Row label="Kontextfenster">
              {status ? `${status.num_ctx} Tokens (max. Ausgabe ${status.num_predict})` : "–"}
            </Row>
          </dl>
          <div className="mt-3">
            <PrimaryButton onClick={() => void refresh()}>Aktualisieren</PrimaryButton>
          </div>
        </div>
      </Group>

      <Group title="Kontext-Vorschau">
        <div className="flex gap-2">
          <input
            type="text"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Beispielnachricht …"
            className="flex-1 rounded-lg border border-ink-600 bg-ink-900 px-3 py-2 text-[12.5px] text-ink-50 outline-none focus:border-jade-600"
          />
          <PrimaryButton
            onClick={() => void loadPreview(message, useHistory ? activeConversationId : null)}
            disabled={previewLoading || !message.trim()}
          >
            Entwerfen
          </PrimaryButton>
        </div>
        <label className="flex items-center gap-2 text-[11.5px] text-ink-300">
          <input
            type="checkbox"
            checked={useHistory}
            onChange={(e) => setUseHistory(e.target.checked)}
            className="accent-jade-600"
          />
          Verlauf der aktuellen Konversation einbeziehen
          {activeConversationId ? "" : " (keine geöffnet)"}
        </label>

        {preview && (
          <div className="space-y-3">
            <div className="rounded-xl border border-ink-700 bg-ink-900 px-4 py-3">
              <div className="flex items-center justify-between text-[11.5px] text-ink-300">
                <span>Kontext-Auslastung</span>
                <span>
                  {preview.used_tokens} / {preview.budget_tokens} Tokens ({usage}%)
                </span>
              </div>
              <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-ink-700">
                <div
                  className="h-full rounded-full bg-jade-600"
                  style={{ width: `${Math.min(100, usage)}%` }}
                />
              </div>
              <p className="mt-2 text-[11px] text-ink-400">
                Verlauf: {preview.history_kept} behalten / {preview.history_dropped} zusammengefasst ·
                Erinnerungen: {preview.memories_kept} genutzt / {preview.memories_dropped} verworfen
                {preview.conflicts > 0 ? ` · ${preview.conflicts} Widerspruch(e)` : ""}
              </p>
            </div>

            {preview.flags.length > 0 && (
              <div className="rounded-xl border border-signal-amber/40 bg-signal-amber/5 px-4 py-3 text-[11.5px] text-signal-amber">
                Injection-Muster in der Beispielnachricht: {preview.flags.join(", ")}
              </div>
            )}

            <div className="space-y-1.5">
              {preview.sections.map((section) => (
                <div
                  key={section.key}
                  className="flex items-center justify-between rounded-lg border border-ink-700 bg-ink-900 px-3 py-2 text-[12px]"
                >
                  <span className="text-ink-100">{section.title}</span>
                  <span className="flex items-center gap-2 text-[11px] text-ink-400">
                    {section.detail && <span>{section.detail}</span>}
                    <Badge>~{section.tokens_est} T</Badge>
                  </span>
                </div>
              ))}
            </div>

            <div className="rounded-xl border border-ink-700 bg-ink-900 px-4 py-3">
              <p className="mb-2 text-[10px] font-semibold tracking-[0.16em] text-ink-500 uppercase">
                Zusammengeführte Systemnachricht
              </p>
              <pre className="max-h-72 overflow-y-auto whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-ink-300">
                {preview.system_text}
              </pre>
            </div>

            <div className="space-y-1.5">
              <p className="text-[10px] font-semibold tracking-[0.16em] text-ink-500 uppercase">
                Nachrichtenfolge
              </p>
              {preview.messages.map((item, index) => (
                <div key={index} className="flex gap-2 text-[11.5px]">
                  <Badge tone={item.role === "system" ? "solid" : "quiet"}>{item.role}</Badge>
                  <span className="min-w-0 flex-1 truncate text-ink-200">{item.content}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </Group>

      <Hint>
        Die Vorschau zeigt exakt, was ZENJI an das Sprachmodell senden würde – nachvollziehbar
        und ohne LLM-Aufruf. Erinnerungen stehen in [INHALT_BEGINN]/[INHALT_ENDE]-Blöcken und
        sind damit strikt als Daten markiert, niemals als Anweisungen.
      </Hint>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="text-ink-400">{label}</dt>
      <dd className="text-right text-ink-50">{children}</dd>
    </div>
  );
}
