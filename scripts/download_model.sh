#!/usr/bin/env bash
# =============================================================
# ZENJI – Primärmodell laden (qwen3:8b)
# Ladet die Modellgewichte via Ollama.  Die Gewichte landen in
# OLLAMA_MODELS (Standard: SSD), sofern die SSD aktiv ist.
# =============================================================
set -uo pipefail

SSD_ROOT="${ZENJI_SSD_ROOT:-/Volumes/ZENJI-SSD}"
MODEL="${ZENJI_LLM_MODEL:-qwen3:8b}"
OLLAMA_MODELS_DIR="$SSD_ROOT/models"
OLLAMA_URL="${ZENJI_OLLAMA_BASE_URL:-http://localhost:11434}"

say() { printf '%s\n' "$1"; }
die() { printf '%s\n' "❌ $1"; exit 1; }

[ -d "$SSD_ROOT" ] || die "Externe SSD nicht verbunden unter '$SSD_ROOT'. \
Gewichte sollen auf der SSD liegen – kein Download auf den internen Speicher."
command -v ollama >/dev/null 2>&1 || die "Ollama ist nicht installiert."
mkdir -p "$OLLAMA_MODELS_DIR"

if ! curl -s -m 3 "$OLLAMA_URL/api/version" >/dev/null 2>&1; then
    say "→ Ollama läuft nicht – starte es mit SSD-Modellspeicher …"
    OLLAMA_MODELS="$OLLAMA_MODELS_DIR" nohup ollama serve > "$SSD_ROOT/logs/ollama.log" 2>&1 &
    for _ in $(seq 1 20); do
        curl -s -m 2 "$OLLAMA_URL/api/version" >/dev/null 2>&1 && break
        sleep 0.5
    done
fi

say "→ Lade '$MODEL' (~5 GB, Gewichte → $OLLAMA_MODELS_DIR) …"
OLLAMA_MODELS="$OLLAMA_MODELS_DIR" ollama pull "$MODEL" || die "Download fehlgeschlagen – bitte Verbindung prüfen und erneut ausführen."

say "✅ Modell '$MODEL' geladen. ZENJI ist einsatzbereit: ./scripts/start.sh"
