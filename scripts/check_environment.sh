#!/usr/bin/env bash
# =============================================================
# ZENJI – Umgebung prüfen (macOS)
# Prüft: externe SSD, Python 3.12, Node, Ollama, Modell, Speicher.
# Harte Anforderungen: SSD, Python, Node.  Ollama/Modell = Warnung.
# =============================================================
set -uo pipefail

SSD_ROOT="${ZENJI_SSD_ROOT:-/Volumes/ZENJI-SSD}"
MODEL="${ZENJI_LLM_MODEL:-qwen3:8b}"
OLLAMA_URL="${ZENJI_OLLAMA_BASE_URL:-http://localhost:11434}"

OK="✅"; WARN="⚠️ "; FAIL="❌"
failures=0

say()  { printf '%s\n' "$1"; }
check_hard() { say "$FAIL $1"; failures=$((failures+1)); }
check_soft() { say "$WARN $1"; }

say "ZENJI Umgebungstest"
say "─────────────────────────────────────────────"

# 1) Externe SSD
if [ -d "$SSD_ROOT" ]; then
    if touch "$SSD_ROOT/.zenji-probe" 2>/dev/null; then
        rm -f "$SSD_ROOT/.zenji-probe"
        say "$OK Externe SSD verbunden und beschreibbar: $SSD_ROOT"
    else
        check_hard "SSD verbunden, aber nicht beschreibbar: $SSD_ROOT"
    fi
else
    check_hard "Externe SSD nicht verbunden unter $SSD_ROOT – bitte anschließen"
fi

# 2) Python 3.12
if command -v python3.12 >/dev/null 2>&1; then
    say "$OK Python 3.12: $(python3.12 --version 2>&1) ($(command -v python3.12))"
else
    check_hard "Python 3.12 nicht gefunden (erforderlich). Installation: brew install python@3.12"
fi

# 3) Node
if command -v node >/dev/null 2>&1; then
    node_major=$(node --version | sed 's/^v//' | cut -d. -f1)
    if [ "${node_major:-0}" -ge 20 ]; then
        say "$OK Node.js $(node --version)"
    else
        check_hard "Node.js zu alt ($(node --version)); mindestens v20 erforderlich"
    fi
else
    check_hard "Node.js nicht gefunden (erforderlich). Installation: https://nodejs.org"
fi

# 4) Git
command -v git >/dev/null 2>&1 && say "$OK Git $(git --version)" || check_soft "Git nicht gefunden (optional für Entwicklung)"

# 5) Ollama installiert + läuft
if command -v ollama >/dev/null 2>&1; then
    say "$OK Ollama installiert: $(ollama --version 2>&1)"
    if curl -s -m 3 "$OLLAMA_URL/api/version" >/dev/null 2>&1; then
        say "$OK Ollama-Server läuft unter $OLLAMA_URL"
        # 6) Modell verfügbar?
        if curl -s -m 5 "$OLLAMA_URL/api/tags" | grep -q "\"name\"[[:space:]]*:[[:space:]]*\"$MODEL\""; then
            say "$OK Modell '$MODEL' ist geladen"
        else
            check_soft "Modell '$MODEL' fehlt. Laden mit: ./scripts/download_model.sh"
        fi
    else
        check_soft "Ollama-Server läuft nicht. Start: 'ollama serve' oder ./scripts/start.sh"
    fi
else
    check_soft "Ollama nicht installiert. Download: https://ollama.com/download/mac"
fi

# 7) Freier Speicher auf SSD
if [ -d "$SSD_ROOT" ]; then
    free_gb=$(df -g "$SSD_ROOT" 2>/dev/null | awk 'NR==2{print $4}')
    [ -n "${free_gb:-}" ] && printf '   Freier Speicher auf SSD: %s GB\n' "$free_gb"
fi

say "─────────────────────────────────────────────"
if [ "$failures" -gt 0 ]; then
    say "Ergebnis: $failures kritische(r) Fehler. Siehe obige Meldungen."
    exit 1
fi
say "Ergebnis: Alle kritischen Anforderungen erfüllt."
