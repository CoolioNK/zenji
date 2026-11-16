/* Control Center – Tab Web Intelligence: Status, Einstellungen, Websuche,
   Recherche-Verlauf und Quellenverwaltung (v0.5.0). */

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../../services/api";
import type {
  ResearchSession,
  Source,
  WebSearchResponse,
  WebSettings,
  WebStatus,
} from "../../types";
import {
  Badge,
  ErrorNote,
  Group,
  Hint,
  PrimaryButton,
  QuietButton,
  SelectField,
  TextField,
} from "./ui";

/** Kompakte Statuszeile (dt. / Werte ehrlich aus der API). */
function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="text-ink-400">{label}</dt>
      <dd className="text-right text-ink-50">{children}</dd>
    </div>
  );
}

function availabilityBadge(available: boolean, detail?: string) {
  return (
    <Badge tone={available ? "jade" : "amber"}>
      {available ? "verfügbar" : detail ? detail.slice(0, 60) : "nicht verfügbar"}
    </Badge>
  );
}

export function WebIntelligenceTab() {
  const [status, setStatus] = useState<WebStatus | null>(null);
  const [settings, setSettings] = useState<WebSettings | null>(null);
  const [sessions, setSessions] = useState<ResearchSession[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  /* Einstellungen (lokaler Entwurf, Speichern per PATCH): */
  const [provider, setProvider] = useState("searxng");
  const [searxngUrl, setSearxngUrl] = useState("");
  const [language, setLanguage] = useState("");
  const [cacheTtl, setCacheTtl] = useState("");
  const [braveKeyInput, setBraveKeyInput] = useState("");

  /* Websuche: */
  const [query, setQuery] = useState("");
  const [searchProvider, setSearchProvider] = useState("");
  const [searchResult, setSearchResult] = useState<WebSearchResponse | null>(null);

  /* Quellenfilter: */
  const [domainFilter, setDomainFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [snapshot, setSnapshot] = useState<{ id: string; content: string } | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [statusData, settingsData, sessionData, sourceData] = await Promise.all([
        api.webStatus(),
        api.webSettings(),
        api.researchSessions(30),
        api.sources({ domain: domainFilter || undefined, type: typeFilter || undefined }),
      ]);
      setStatus(statusData);
      setSettings(settingsData);
      setProvider(settingsData.provider);
      setSearxngUrl(settingsData.searxng_url);
      setLanguage(settingsData.language);
      setCacheTtl(String(settingsData.cache_ttl_s));
      setSessions(sessionData);
      setSources(sourceData.sources);
      setError(null);
    } catch (exc) {
      setError(exc instanceof ApiError ? `${exc.code}: ${exc.message}` : String(exc));
    }
  }, [domainFilter, typeFilter]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const saveSettings = async () => {
    setBusy(true);
    setNotice(null);
    try {
      const patch: Record<string, unknown> = {};
      if (settings && provider !== settings.provider) patch.provider = provider;
      if (settings && searxngUrl !== settings.searxng_url) patch.searxng_url = searxngUrl;
      if (settings && language !== settings.language) patch.language = language;
      const ttl = Number(cacheTtl);
      if (settings && Number.isFinite(ttl) && ttl !== settings.cache_ttl_s) {
        patch.cache_ttl_s = ttl;
      }
      if (braveKeyInput.trim()) patch.brave_api_key = braveKeyInput.trim();
      if (Object.keys(patch).length === 0) {
        setNotice("Keine Änderungen zu speichern.");
        return;
      }
      await api.patchWebSettings(patch);
      setBraveKeyInput("");
      setNotice("Einstellungen gespeichert.");
      await refresh();
    } catch (exc) {
      setError(exc instanceof ApiError ? `${exc.code}: ${exc.message}` : String(exc));
    } finally {
      setBusy(false);
    }
  };

  const runSearch = async () => {
    if (!query.trim()) return;
    setBusy(true);
    setNotice(null);
    try {
      setSearchResult(await api.webSearch(query.trim(), searchProvider || undefined));
    } catch (exc) {
      setError(exc instanceof ApiError ? `${exc.code}: ${exc.message}` : String(exc));
    } finally {
      setBusy(false);
    }
  };

  const clearCache = async () => {
    setBusy(true);
    setNotice(null);
    try {
      const result = await api.clearWebCache();
      setNotice(`Cache geleert (${result.deleted} Einträge).`);
      await refresh();
    } catch (exc) {
      setError(exc instanceof ApiError ? `${exc.code}: ${exc.message}` : String(exc));
    } finally {
      setBusy(false);
    }
  };

  const deleteSession = async (id: string) => {
    try {
      await api.deleteResearch(id);
      setNotice("Recherche gelöscht.");
      await refresh();
    } catch (exc) {
      setError(exc instanceof ApiError ? `${exc.code}: ${exc.message}` : String(exc));
    }
  };

  const deleteSource = async (id: string) => {
    try {
      await api.deleteSource(id);
      setNotice("Quelle gelöscht.");
      if (snapshot?.id === id) setSnapshot(null);
      await refresh();
    } catch (exc) {
      setError(exc instanceof ApiError ? `${exc.code}: ${exc.message}` : String(exc));
    }
  };

  const showSnapshot = async (id: string) => {
    try {
      const data = await api.sourceSnapshot(id);
      setSnapshot({ id, content: data.content });
    } catch (exc) {
      setError(exc instanceof ApiError ? `${exc.code}: ${exc.message}` : String(exc));
    }
  };

  return (
    <div className="space-y-6">
      {error && <ErrorNote>{error}</ErrorNote>}
      {notice && <Hint>{notice}</Hint>}

      {/* --- Status -------------------------------------------------------- */}
      <Group title="Status">
        {!status ? (
          <p className="text-[13px] text-ink-400">Status wird geladen …</p>
        ) : (
          <div className="rounded-xl border border-ink-700 bg-ink-900 px-4 py-4">
            <dl className="space-y-2.5 text-[12.5px]">
              <Row label="Suchanbieter">
                <span className="flex items-center gap-2">
                  <span className="font-mono text-[11px]">{status.provider}</span>
                  {availabilityBadge(status.search.available, status.search.detail)}
                </span>
              </Row>
              <Row label="HTTP-Abrufe (httpx)">
                {availabilityBadge(status.browser.httpx.available, status.browser.httpx.detail)}
              </Row>
              <Row label="Browser-Rendering (Playwright)">
                {availabilityBadge(status.browser.playwright.available, status.browser.playwright.detail)}
              </Row>
              <Row label="robots.txt / Host-Pause">
                <span className="text-[11px] text-ink-300">
                  {status.browser.robots_respected ? "respektiert" : "aus"} · {status.browser.per_host_delay_s}s
                </span>
              </Row>
              <Row label="Cache">
                <span className="flex items-center gap-2">
                  <span className="text-[11px] text-ink-300">
                    {status.cache.total} Einträge · TTL {Math.round((status.cache.ttl_s ?? 0) / 60)} min
                  </span>
                  <QuietButton onClick={() => void clearCache()} disabled={busy}>
                    Leeren
                  </QuietButton>
                </span>
              </Row>
              <Row label="Speicher">
                <span className="text-[11px] text-ink-300">
                  {status.storage.research_sessions ?? 0} Recherche(n) · {status.storage.sources ?? 0} Quelle(n) ·{" "}
                  {status.storage.citations ?? 0} Zitat(e)
                </span>
              </Row>
            </dl>
          </div>
        )}
        <Hint>
          Der Status meldet nur echtes Verhalten – ein nicht erreichbarer Suchanbieter wird als
          „nicht verfügbar“ angezeigt, nie als verbunden.
        </Hint>
      </Group>

      {/* --- Einstellungen --------------------------------------------------- */}
      <Group title="Einstellungen">
        <SelectField
          label="Suchanbieter"
          value={provider}
          options={[
            { value: "searxng", label: "SearXNG (lokal, ohne API-Schlüssel)" },
            { value: "brave", label: "Brave Search (API-Schlüssel nötig)" },
          ]}
          onChange={setProvider}
        />
        {provider === "searxng" && (
          <TextField
            label="SearXNG-URL"
            value={searxngUrl}
            onChange={setSearxngUrl}
            placeholder="http://localhost:8888"
          />
        )}
        {provider === "brave" && (
          <>
            <TextField
              label="Brave API-Schlüssel (neu setzen – wird nie angezeigt)"
              value={braveKeyInput}
              onChange={setBraveKeyInput}
              placeholder="Leer lassen, um den vorhandenen Schlüssel zu behalten"
            />
            <Hint>
              {settings?.brave_api_key_set
                ? "Ein Schlüssel ist gespeichert."
                : "Kein Schlüssel gespeichert – Brave-Suche ist ohne Schlüssel nicht möglich."}
            </Hint>
          </>
        )}
        <TextField
          label="Sprache der Suchergebnisse (z. B. de, en)"
          value={language}
          onChange={setLanguage}
        />
        <TextField
          label="Cache-Gültigkeit in Sekunden (60–86400)"
          value={cacheTtl}
          onChange={setCacheTtl}
        />
        <div className="flex items-center gap-2">
          <PrimaryButton onClick={() => void saveSettings()} disabled={busy}>
            Speichern
          </PrimaryButton>
          <QuietButton onClick={() => void refresh()} disabled={busy}>
            Neu laden
          </QuietButton>
        </div>
      </Group>

      {/* --- Websuche --------------------------------------------------------- */}
      <Group title="Websuche (einzelne Anfrage)">
        <TextField
          label="Suchbegriff"
          value={query}
          onChange={setQuery}
          placeholder="z. B. neueste Python-Version"
        />
        <SelectField
          label="Anbieter (leer = Einstellung)"
          value={searchProvider}
          options={[
            { value: "", label: "Standard (Einstellung)" },
            { value: "searxng", label: "SearXNG" },
            { value: "brave", label: "Brave" },
          ]}
          onChange={setSearchProvider}
        />
        <PrimaryButton onClick={() => void runSearch()} disabled={busy || !query.trim()}>
          Suchen
        </PrimaryButton>
        {searchResult && (
          <div className="space-y-1.5">
            <p className="text-[10px] font-semibold tracking-[0.16em] text-ink-500 uppercase">
              {searchResult.results.length} Ergebnis(se) über {searchResult.provider}
            </p>
            {searchResult.results.map((hit) => (
              <a
                key={hit.url}
                href={hit.url}
                target="_blank"
                rel="noreferrer noopener"
                className="block rounded-lg border border-ink-700 bg-ink-900 px-3 py-2 transition-colors hover:border-accent/40"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="min-w-0 truncate text-[12.5px] text-ink-100">{hit.title || hit.url}</span>
                  <span className="font-mono text-[10px] text-ink-500">#{hit.rank}</span>
                </div>
                <p className="mt-1 truncate font-mono text-[10px] text-ink-400">{hit.domain}</p>
                {hit.snippet && <p className="mt-1 line-clamp-2 text-[11px] text-ink-300">{hit.snippet}</p>}
              </a>
            ))}
          </div>
        )}
      </Group>

      {/* --- Recherche-Verlauf -------------------------------------------------- */}
      <Group title="Recherche-Verlauf">
        {sessions.length === 0 ? (
          <p className="text-[12.5px] text-ink-400">Noch keine Recherche durchgeführt.</p>
        ) : (
          <div className="space-y-1.5">
            {sessions.map((session) => (
              <div
                key={session.session_id ?? session.created_at}
                className="flex items-center justify-between gap-3 rounded-lg border border-ink-700 bg-ink-900 px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="truncate text-[12.5px] text-ink-100">{session.question}</p>
                  <p className="mt-0.5 font-mono text-[10px] text-ink-500">
                    {session.mode} · {session.status} · {session.source_count} Quelle(n)
                    {session.created_at ? ` · ${new Date(session.created_at).toLocaleString("de-DE")}` : ""}
                  </p>
                </div>
                <QuietButton danger onClick={() => void deleteSession(session.session_id ?? "")} disabled={!session.session_id}>
                  Löschen
                </QuietButton>
              </div>
            ))}
          </div>
        )}
        <Hint>
          Recherche-Sitzungen sind Sitzungsdaten – sie gehen nicht automatisch ins Gedächtnis.
        </Hint>
      </Group>

      {/* --- Quellen ------------------------------------------------------------ */}
      <Group title="Quellen">
        <div className="flex gap-3">
          <div className="flex-1">
            <TextField
              label="Domain-Filter"
              value={domainFilter}
              onChange={setDomainFilter}
              placeholder="z. B. example.com"
            />
          </div>
          <div className="flex-1">
            <SelectField
              label="Quelltyp"
              value={typeFilter}
              options={[
                { value: "", label: "Alle" },
                { value: "offiziell", label: "Offiziell" },
                { value: "wissenschaftlich", label: "Wissenschaftlich" },
                { value: "fachquelle", label: "Fachquelle" },
                { value: "nachrichten", label: "Nachrichten" },
                { value: "community", label: "Community" },
                { value: "meinung", label: "Meinung" },
                { value: "unbekannt", label: "Unbekannt" },
              ]}
              onChange={setTypeFilter}
            />
          </div>
        </div>
        {sources.length === 0 ? (
          <p className="text-[12.5px] text-ink-400">Keine Quellen gespeichert.</p>
        ) : (
          <div className="space-y-1.5">
            {sources.map((source) => (
              <div key={source.id} className="rounded-lg border border-ink-700 bg-ink-900 px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-[12.5px] text-ink-100">{source.title || source.domain}</p>
                    <p className="truncate font-mono text-[10px] text-ink-400">{source.canonical_url}</p>
                  </div>
                  <Badge tone={source.status === "ok" ? "jade" : "amber"}>{source.source_type}</Badge>
                </div>
                <div className="mt-2 flex items-center gap-2">
                  <QuietButton onClick={() => void showSnapshot(source.id)}>Inhalt</QuietButton>
                  <QuietButton danger onClick={() => void deleteSource(source.id)}>
                    Löschen
                  </QuietButton>
                  <span className="ml-auto font-mono text-[10px] text-ink-500">
                    {source.content_chars} Zeichen · HTTP {source.http_status}
                  </span>
                </div>
                {snapshot?.id === source.id && (
                  <pre className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap rounded-lg border border-ink-700 bg-ink-950 px-3 py-2 font-mono text-[10.5px] leading-relaxed text-ink-300">
                    {snapshot.content.length > 8000 ? `${snapshot.content.slice(0, 8000)}\n\n… (gekürzt, ${snapshot.content.length} Zeichen gesamt)` : snapshot.content}
                  </pre>
                )}
              </div>
            ))}
          </div>
        )}
        <Hint>
          Gespeicherte Snapshots sind lokale Kopien der Seiteninhalte – Grundlage für
          nachvollziehbare Belege im Chat. Löschen entfernt sie endgültig.
        </Hint>
      </Group>
    </div>
  );
}
