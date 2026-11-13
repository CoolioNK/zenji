#!/usr/bin/env bash
# =============================================================
# ZENJI – Stop
# Beendet Backend und Frontend (und Ollama nur, wenn start.sh
# es selbst gestartet hat).  Nutzdaten bleiben unberührt.
# =============================================================
set -uo pipefail

SSD_ROOT="${ZENJI_SSD_ROOT:-/Volumes/ZENJI-SSD}"
PROJECT="$SSD_ROOT/ZENJI"
RUN_DIR="$PROJECT/run"

OK="✅"; WARN="⚠️ "

say() { printf '%s\n' "$1"; }

stop_pid_file() {
    local name="$1" file="$2"
    if [ -f "$file" ]; then
        local pid
        pid="$(cat "$file" 2>/dev/null)"
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
            for _ in $(seq 1 10); do
                kill -0 "$pid" 2>/dev/null || break
                sleep 0.3
            done
            kill -9 "$pid" 2>/dev/null || true
            say "$OK $name beendet (PID $pid)"
        else
            say "$WARN $name lief nicht (PID $pid)"
        fi
        rm -f "$file"
    else
        say "$WARN Keine $name-PID-Datei vorhanden"
    fi
}

stop_pid_file "Frontend" "$RUN_DIR/frontend.pid" 2>/dev/null || true
stop_pid_file "Backend"  "$RUN_DIR/backend.pid"
stop_pid_file "Ollama (von ZENJI gestartet)" "$RUN_DIR/ollama.pid"

# Fallback: laufende Instanzen per Prozessname finden (ohne PID-Datei).
pkill -f "uvicorn app.main:app" 2>/dev/null && say "$OK Restliche uvicorn-Instanz beendet" || true

say "ZENJI gestoppt. Daten bleiben auf der SSD erhalten."
