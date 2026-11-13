#!/usr/bin/env bash
# =============================================================
# ZENJI – Start (macOS)
# 1. Externe SSD prüfen          (harte Anforderung)
# 2. Ollama prüfen/starten       (Gewichte auf SSD via OLLAMA_MODELS)
# 3. Backend starten (FastAPI)   → http://localhost:8000
# 4. Frontend starten (Vite)     → http://localhost:5173
# 5. Status ausgeben
# Fehlendes Modell = Warnung, kein Abbruch.
# =============================================================
set -uo pipefail

SSD_ROOT="${ZENJI_SSD_ROOT:-/Volumes/ZENJI-SSD}"
PROJECT="$SSD_ROOT/ZENJI"
VENV_DIR="$SSD_ROOT/environments/zenji-venv"
MODEL="${ZENJI_LLM_MODEL:-qwen3:8b}"
OLLAMA_URL="${ZENJI_OLLAMA_BASE_URL:-http://localhost:11434}"
OLLAMA_MODELS_DIR="$SSD_ROOT/models"
LOG_DIR="$SSD_ROOT/logs"
RUN_DIR="$PROJECT/run"

OK="✅"; WARN="⚠️ "; FAIL="❌"
BACKEND_ONLY=0
[ "${1:-}" = "--backend-only" ] && BACKEND_ONLY=1

say() { printf '%s\n' "$1"; }
die() { say "$FAIL $1"; exit 1; }

# --- 1) SSD ------------------------------------------------------------------
[ -d "$SSD_ROOT" ] || die "Externe SSD nicht verbunden unter '$SSD_ROOT'. Start abgebrochen – kein Ersatzspeicherpfad."
touch "$SSD_ROOT/.zenji-probe" 2>/dev/null || die "SSD nicht beschreibbar."
rm -f "$SSD_ROOT/.zenji-probe"
say "$OK Externe SSD: $SSD_ROOT"

[ -d "$PROJECT/backend" ] || die "Kein ZENJI-Projekt unter $PROJECT. Erst ./scripts/setup.sh ausführen."
[ -x "$VENV_DIR/bin/python" ] || die "Keine virtuelle Umgebung unter $VENV_DIR. Erst ./scripts/setup.sh ausführen."

mkdir -p "$RUN_DIR" "$LOG_DIR"

# --- .env laden ------------------------------------------------------------------
if [ -f "$PROJECT/backend/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT/backend/.env"
    set +a
fi

# --- Bereits laufende Instanzen? ------------------------------------------------------
if [ -f "$RUN_DIR/backend.pid" ] && kill -0 "$(cat "$RUN_DIR/backend.pid")" 2>/dev/null; then
    die "Backend läuft bereits (PID $(cat "$RUN_DIR/backend.pid")). ./scripts/stop.sh zuerst."
fi
if [ "$BACKEND_ONLY" = "0" ] && [ -f "$RUN_DIR/frontend.pid" ] && kill -0 "$(cat "$RUN_DIR/frontend.pid")" 2>/dev/null; then
    die "Frontend läuft bereits (PID $(cat "$RUN_DIR/frontend.pid")). ./scripts/stop.sh zuerst."
fi

# --- 2) Ollama -----------------------------------------------------------------------
if curl -s -m 3 "$OLLAMA_URL/api/version" >/dev/null 2>&1; then
    say "$OK Ollama läuft bereits ($OLLAMA_URL)"
    # Prüfen, ob die laufende Instanz die SSD als Modellspeicher nutzt.
    if [ -d "$OLLAMA_MODELS_DIR" ] && [ -z "$(ls -A "$OLLAMA_MODELS_DIR" 2>/dev/null)" ] && [ -n "$(ls -A "$HOME/.ollama/models" 2>/dev/null)" ]; then
        say "$WARN Die laufende Ollama-Instanz nutzt vermutlich noch das interne Verzeichnis."
        say "   Modellgewichte auf die SSD verlagern: ./scripts/restart_ollama.sh"
    fi
else
    if command -v ollama >/dev/null 2>&1; then
        say "→ Starte Ollama mit Modellgewichten auf der SSD (OLLAMA_MODELS=$OLLAMA_MODELS_DIR) …"
        OLLAMA_MODELS="$OLLAMA_MODELS_DIR" nohup ollama serve > "$LOG_DIR/ollama.log" 2>&1 &
        echo $! > "$RUN_DIR/ollama.pid"
        for _ in $(seq 1 20); do
            curl -s -m 2 "$OLLAMA_URL/api/version" >/dev/null 2>&1 && break
            sleep 0.5
        done
        curl -s -m 3 "$OLLAMA_URL/api/version" >/dev/null 2>&1 \
            && say "$OK Ollama gestartet" \
            || say "$WARN Ollama konnte nicht gestartet werden – Backend bleibt dennoch aktiv."
    else
        say "$WARN Ollama nicht installiert – Chat bleibt deaktiviert (siehe README)."
    fi
fi

# --- 3) Backend -----------------------------------------------------------------------
say "→ Starte ZENJI Backend (FastAPI) …"
(
    cd "$PROJECT/backend"
    export ZENJI_SSD_ROOT="$SSD_ROOT"
    exec "$VENV_DIR/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8000
) > "$LOG_DIR/backend.log" 2>&1 &
echo $! > "$RUN_DIR/backend.pid"

backend_ok=0
for _ in $(seq 1 30); do
    if curl -s -m 2 http://localhost:8000/api/health >/dev/null 2>&1; then backend_ok=1; break; fi
    sleep 0.5
done
[ "$backend_ok" = "1" ] || die "Backend nicht erreichbar. Log: $LOG_DIR/backend.log"
say "$OK Backend läuft: http://localhost:8000 (Log: $LOG_DIR/backend.log)"

# --- 4) Frontend -----------------------------------------------------------------------
if [ "$BACKEND_ONLY" = "0" ]; then
    say "→ Starte ZENJI Frontend (Vite) …"
    (
        cd "$PROJECT/frontend"
        [ -d node_modules ] || npm install --no-audit --no-fund >/dev/null 2>&1
        exec npm run dev
    ) > "$LOG_DIR/frontend.log" 2>&1 &
    echo $! > "$RUN_DIR/frontend.pid"

    frontend_ok=0
    for _ in $(seq 1 30); do
        if curl -s -m 2 http://localhost:5173/ >/dev/null 2>&1; then frontend_ok=1; break; fi
        sleep 0.5
    done
    [ "$frontend_ok" = "1" ] && say "$OK Frontend läuft: http://localhost:5173 (Log: $LOG_DIR/frontend.log)" \
        || say "$WARN Frontend nicht erreichbar. Log: $LOG_DIR/frontend.log"
fi

# --- 5) Status --------------------------------------------------------------------------
say "─────────────────────────────────────────────"
health=$(curl -s -m 5 http://localhost:8000/api/health 2>/dev/null || echo "")
if [ -n "$health" ]; then
    printf '   Datenbank : %s\n' "$(echo "$health" | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin)["database"]["ok"])' 2>/dev/null || '?')"
    printf '   Ollama    : %s\n' "$(echo "$health" | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin)["ollama"]["available"])' 2>/dev/null || '?')"
    printf '   Modell    : %s\n' "$(echo "$health" | /usr/bin/python3 -c 'import json,sys; print(json.load(sys.stdin)["model"]["available"])' 2>/dev/null || '?')"
fi
if [ "$BACKEND_ONLY" = "0" ] && [ "$frontend_ok" = "1" ]; then
    say ""
    say "ZENJI öffnen:  http://localhost:5173"
fi
say "Beenden mit :  ./scripts/stop.sh"
