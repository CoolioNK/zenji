#!/usr/bin/env bash
# =============================================================
# ZENJI – Ollama mit SSD-Modellspeicher neu starten
# Notwendig, wenn Ollama bereits läuft, aber seine Gewichte noch
# auf dem internen Datenträger lädt.  Beendet laufende ollama-
# Instanzen und startet sie mit OLLAMA_MODELS auf der SSD.
# =============================================================
set -uo pipefail

SSD_ROOT="${ZENJI_SSD_ROOT:-/Volumes/ZENJI-SSD}"
LOG_DIR="$SSD_ROOT/logs"
RUN_DIR="$SSD_ROOT/ZENJI/run"
OLLAMA_MODELS_DIR="$SSD_ROOT/models"
OLLAMA_URL="${ZENJI_OLLAMA_BASE_URL:-http://localhost:11434}"

say() { printf '%s\n' "$1"; }
die() { printf '%s\n' "❌ $1"; exit 1; }

[ -d "$SSD_ROOT" ] || die "Externe SSD nicht verbunden unter '$SSD_ROOT' – Neustart abgebrochen."
command -v ollama >/dev/null 2>&1 || die "Ollama ist nicht installiert."

mkdir -p "$LOG_DIR" "$RUN_DIR" "$OLLAMA_MODELS_DIR"

say "→ Beende laufende Ollama-Instanz(en) …"
pkill -x ollama 2>/dev/null || true
sleep 2
if pgrep -x ollama >/dev/null 2>&1; then
    pkill -9 -x ollama 2>/dev/null || true
    sleep 1
fi

# macOS: Auch die Menüleisten-App beenden – sie startet den Server sonst
# automatisch neu (mit Standard-OLLAMA_MODELS auf dem internen Datenträger).
osascript -e 'tell application "Ollama" to quit' >/dev/null 2>&1 || true
pkill -f "Ollama.app/Contents/MacOS/Ollama" 2>/dev/null || true
sleep 1
if pgrep -f "Ollama.app/Contents/MacOS/Ollama" >/dev/null 2>&1; then
    pkill -9 -f "Ollama.app/Contents/MacOS/Ollama" 2>/dev/null || true
    sleep 1
fi

say "→ Starte Ollama mit OLLAMA_MODELS=$OLLAMA_MODELS_DIR"
OLLAMA_MODELS="$OLLAMA_MODELS_DIR" nohup ollama serve > "$LOG_DIR/ollama.log" 2>&1 &
echo $! > "$RUN_DIR/ollama.pid"

for _ in $(seq 1 20); do
    curl -s -m 2 "$OLLAMA_URL/api/version" >/dev/null 2>&1 && break
    sleep 0.5
done

curl -s -m 3 "$OLLAMA_URL/api/version" >/dev/null 2>&1 \
    && say "✅ Ollama läuft – Modellgewichte landen ab jetzt unter $OLLAMA_MODELS_DIR" \
    || die "Ollama startete nicht. Log: $LOG_DIR/ollama.log"

say "Nächster Schritt (falls Modell fehlt): ./scripts/download_model.sh"
