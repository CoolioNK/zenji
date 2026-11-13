#!/usr/bin/env bash
# =============================================================
# ZENJI – Setup (macOS)
# 1. Externe SSD prüfen (kein Ersatzpfad!)
# 2. Projekt auf die SSD übertragen (falls nicht dort)
# 3. Ordnerstruktur erstellen (idempotent, löscht nichts)
# 4. Virtuelle Python-Umgebung auf der SSD erstellen
# 5. Abhängigkeiten installieren (Backend + Frontend)
# 6. .env vorbereiten
# 7. Ollama & Modell prüfen (nur Warnung, kein Abbruch)
# =============================================================
set -uo pipefail

SSD_ROOT="${ZENJI_SSD_ROOT:-/Volumes/ZENJI-SSD}"
SOURCE_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="$SSD_ROOT/ZENJI"
VENV_DIR="$SSD_ROOT/environments/zenji-venv"
MODEL="${ZENJI_LLM_MODEL:-qwen3:8b}"
OLLAMA_URL="${ZENJI_OLLAMA_BASE_URL:-http://localhost:11434}"
SYNC_ONLY=0
[ "${1:-}" = "--sync" ] && SYNC_ONLY=1

OK="✅"; WARN="⚠️ "; FAIL="❌"

say() { printf '%s\n' "$1"; }
die() { say "$FAIL $1"; exit 1; }

# --- 1) SSD prüfen ------------------------------------------------------------
say "ZENJI Setup – Zielspeicher: $SSD_ROOT"
[ -d "$SSD_ROOT" ] || die "Externe SSD nicht verbunden unter '$SSD_ROOT'. \
Bitte SSD anschließen und erneut ausführen. Es wird kein Ersatzspeicherpfad verwendet."
touch "$SSD_ROOT/.zenji-probe" 2>/dev/null || die "SSD ist nicht beschreibbar (schreibgeschützt?)."
rm -f "$SSD_ROOT/.zenji-probe"
say "$OK SSD verbunden und beschreibbar"

# --- 2) Projekt übertragen ------------------------------------------------------
if [ "$SOURCE_ROOT" != "$TARGET" ]; then
    if [ ! -d "$TARGET" ]; then
        say "→ Übertrage Projekt auf die SSD …"
        mkdir -p "$TARGET"
        rsync -a \
            --exclude node_modules --exclude .venv --exclude .git \
            --exclude dist --exclude __pycache__ --exclude .pytest_cache \
            --exclude "*.db" --exclude .DS_Store \
            "$SOURCE_ROOT/" "$TARGET/"
        say "$OK Projekt nach $TARGET übertragen"
    elif [ -d "$TARGET/backend" ]; then
        if [ "$SYNC_ONLY" = "1" ]; then
            say "→ Aktualisiere bestehendes Projekt (--sync, überschreibt geänderte Quelltexte) …"
            rsync -a \
                --exclude node_modules --exclude .venv --exclude .git \
                --exclude dist --exclude __pycache__ --exclude .pytest_cache \
                --exclude "*.db" --exclude .DS_Store \
                "$SOURCE_ROOT/" "$TARGET/"
            say "$OK Projekt aktualisiert"
        else
            say "$WARN Ziel '$TARGET' existiert bereits – Kopieren übersprungen (Daten bleiben unberührt)."
            say "   Zum Aktualisieren: ./scripts/setup.sh --sync"
        fi
    else
        die "Verzeichnis '$TARGET' existiert, enthält aber kein ZENJI-Projekt. \
Bitte prüfen – es wird nicht automatisch überschrieben."
    fi
fi
cd "$TARGET" || die "Wechsel zu $TARGET fehlgeschlagen."

# --- 3) Ordnerstruktur ------------------------------------------------------------
say "→ Erstelle Ordnerstruktur (idempotent, löscht nichts) …"
for dir in models datasets backups environments logs "$TARGET/data" "$TARGET/logs"; do
    mkdir -p "$dir"
done
say "$OK Struktur bereit: $SSD_ROOT/{ZENJI, models, datasets, backups, environments, logs}"

# --- 4) Python prüfen + venv auf SSD ------------------------------------------------
command -v python3.12 >/dev/null 2>&1 || die "Python 3.12 nicht gefunden: brew install python@3.12"
say "$OK Python: $(python3.12 --version 2>&1)"

if [ ! -x "$VENV_DIR/bin/python" ]; then
    say "→ Erstelle virtuelle Umgebung auf der SSD: $VENV_DIR"
    python3.12 -m venv "$VENV_DIR" || die "venv-Erstellung fehlgeschlagen"
else
    say "$OK Virtuelle Umgebung vorhanden"
fi

# --- 5) Abhängigkeiten ---------------------------------------------------------------
say "→ Installiere Backend-Abhängigkeiten (requirements.txt) …"
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$TARGET/backend/requirements.txt" || die "Backend-Installation fehlgeschlagen"
say "$OK Backend-Abhängigkeiten installiert"

command -v node >/dev/null 2>&1 || die "Node.js nicht gefunden: https://nodejs.org"
if [ ! -d "$TARGET/frontend/node_modules" ]; then
    say "→ Installiere Frontend-Abhängigkeiten (npm) …"
    (cd "$TARGET/frontend" && npm install --no-audit --no-fund) || die "Frontend-Installation fehlgeschlagen"
else
    say "$OK Frontend-Abhängigkeiten vorhanden"
fi

# --- 6) .env vorbereiten ----------------------------------------------------------------
ENV_FILE="$TARGET/backend/.env"
if [ ! -f "$ENV_FILE" ]; then
    cp "$TARGET/backend/.env.example" "$ENV_FILE"
    say "$OK backend/.env aus .env.example erstellt (bei Bedarf anpassen)"
else
    say "$WARN backend/.env existiert bereits – nicht verändert."
fi

# --- 7) Ollama & Modell prüfen (Warnung statt Abbruch) -------------------------------------
if command -v ollama >/dev/null 2>&1; then
    if curl -s -m 3 "$OLLAMA_URL/api/version" >/dev/null 2>&1; then
        say "$OK Ollama-Server läuft ($OLLAMA_URL)"
        if curl -s -m 5 "$OLLAMA_URL/api/tags" | grep -q "\"name\"[[:space:]]*:[[:space:]]*\"$MODEL\""; then
            say "$OK Modell '$MODEL' verfügbar"
        else
            say "$WARN Modell '$MODEL' fehlt. Nach dem ersten Start: ./scripts/download_model.sh"
        fi
    else
        say "$WARN Ollama läuft nicht – start.sh versucht es zu starten."
    fi
else
    say "$WARN Ollama nicht installiert: https://ollama.com/download/mac"
fi

say "─────────────────────────────────────────────"
say "$OK Setup abgeschlossen."
say "Start danach:   cd $TARGET && ./scripts/start.sh"
