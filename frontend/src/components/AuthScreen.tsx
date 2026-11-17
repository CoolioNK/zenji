/* Login-/Registrierungsseite (Supabase Auth, E-Mail + Passwort). */

import { useState, type FormEvent } from "react";
import { Logo } from "./Logo";
import { isSupabaseConfigured, supabase } from "../lib/supabase";

type Mode = "login" | "register";

export function AuthScreen() {
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const switchMode = (next: Mode) => {
    setMode(next);
    setError(null);
    setMessage(null);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setMessage(null);

    if (!isSupabaseConfigured) {
      setError(
        "Supabase ist nicht konfiguriert. Bitte VITE_SUPABASE_URL und VITE_SUPABASE_ANON_KEY in der .env setzen.",
      );
      return;
    }

    setLoading(true);
    try {
      if (mode === "register") {
        const { data, error: signUpError } = await supabase.auth.signUp({
          email,
          password,
        });
        if (signUpError) throw signUpError;
        if (data.session) {
          // E-Mail-Bestätigung deaktiviert → direkt eingeloggt.
          setMessage("Account erstellt. Du wirst eingeloggt …");
        } else {
          setMessage(
            "Account erstellt. Bitte prüfe deine E-Mails und bestätige die Adresse.",
          );
        }
      } else {
        const { error: signInError } = await supabase.auth.signInWithPassword({
          email,
          password,
        });
        if (signInError) throw signInError;
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Anmeldung fehlgeschlagen.");
    } finally {
      setLoading(false);
    }
  };

  const resetPassword = async () => {
    setError(null);
    setMessage(null);
    if (!email.trim()) {
      setError("Bitte zuerst deine E-Mail-Adresse eingeben.");
      return;
    }
    setLoading(true);
    try {
      const appUrl = (import.meta.env.VITE_PUBLIC_APP_URL as string | undefined)?.trim() || window.location.origin;

      const { error: resetError } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: appUrl,
      });
      if (resetError) throw resetError;
      setMessage("Falls ein Account existiert, wurde eine E-Mail zum Zurücksetzen gesendet.");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Zurücksetzen fehlgeschlagen.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-full w-full items-center justify-center bg-background px-4">
      <div className="w-full max-w-[400px] animate-fade-up">
        <div className="mb-8 flex justify-center">
          <Logo />
        </div>

        <div className="rounded-2xl border border-border bg-card p-6 shadow-2xl zenji-subtle-glow">
          <div className="mb-6 flex rounded-lg border border-border bg-background p-1">
            <button
              type="button"
              onClick={() => switchMode("login")}
              className={`flex-1 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                mode === "login"
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Anmelden
            </button>
            <button
              type="button"
              onClick={() => switchMode("register")}
              className={`flex-1 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                mode === "register"
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Registrieren
            </button>
          </div>

          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                E-Mail
              </label>
              <input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="du@beispiel.de"
                className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground/60 focus:border-accent"
              />
            </div>

            <div>
              <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                Passwort
              </label>
              <input
                type="password"
                autoComplete={mode === "register" ? "new-password" : "current-password"}
                required
                minLength={6}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground/60 focus:border-accent"
              />
            </div>

            {error && (
              <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                {error}
              </div>
            )}
            {message && (
              <div className="rounded-lg border border-signal-green/40 bg-signal-green/10 px-3 py-2 text-xs text-signal-green">
                {message}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-accent-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {loading
                ? "Bitte warten …"
                : mode === "login"
                  ? "Anmelden"
                  : "Account erstellen"}
            </button>
          </form>

          {mode === "login" && (
            <button
              type="button"
              onClick={() => void resetPassword()}
              className="mt-4 w-full text-center text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              Passwort vergessen?
            </button>
          )}
        </div>

        <p className="mt-6 text-center text-[11px] leading-relaxed text-muted-foreground">
          Dein Account und alle Chats liegen in Supabase und sind nur für dich
          sichtbar.
        </p>
      </div>
    </div>
  );
}