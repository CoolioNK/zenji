import { AuthProvider, useAuth } from "./lib/auth";
import { isSupabaseConfigured } from "./lib/supabase";
import { useHealth } from "./hooks/useHealth";
import { AuthScreen } from "./components/AuthScreen";
import { ChatPage } from "./pages/ChatPage";

function SetupNotice() {
  return (
    <div className="flex h-full w-full items-center justify-center bg-background px-6">
      <div className="max-w-md rounded-2xl border border-border bg-card p-6 text-center">
        <h1 className="mb-3 text-lg font-semibold text-foreground">
          Supabase ist noch nicht vollständig verbunden
        </h1>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Im Frontend sind URL und Publishable-Key gesetzt, aber im Backend fehlt
          noch die Datenbank-Verbindung. Bitte{" "}
          <code className="rounded bg-background px-1.5 py-0.5 text-xs text-accent">
            ZENJI_SUPABASE_DB_URL
          </code>{" "}
          in <code className="rounded bg-background px-1.5 py-0.5 text-xs text-accent">backend/.env</code>{" "}
          eintragen und das Backend neu starten.
        </p>
      </div>
    </div>
  );
}

function Gate() {
  const { session, loading } = useAuth();
  const health = useHealth();

  // Ohne Supabase-Konfiguration: lokaler Single-User-Modus (kein Login).
  if (!isSupabaseConfigured) return <ChatPage />;

  // Frontend ist auf Supabase eingestellt, Backend aber (noch) nicht:
  // lieber klar hinweisen, statt Login zu zeigen und lokal zu speichern.
  if (health && health.supabase === false) return <SetupNotice />;

  if (loading) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-background text-sm text-muted-foreground">
        Wird geladen …
      </div>
    );
  }

  if (!session) return <AuthScreen />;
  return <ChatPage />;
}

export default function App() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  );
}