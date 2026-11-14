# ZENJI – Quellcode-Staging & Lokal-Modus

## Lokal-Modus (aktuell, Entwicklung auf dem Mac)

Solange die externe SSD nicht verbunden ist, läuft ZENJI **lokal im Ordner
`Zenji KI/`**. Der Ordner übernimmt die Rolle des Speicher-Wurzelverzeichnisses
(`ZENJI_SSD_ROOT`) – ganz ohne Code-Änderung, nur über die vorhandene
Umgebungsvariable:

```
Zenji KI/                     ← ZENJI_SSD_ROOT (Lokal-Modus)
├── ZENJI/                    ← Projektcode + Datenbank (ZENJI/data/zenji.db)
├── models/                   ← Ollama-Modellgewichte (qwen3:8b, ~5 GB)
├── logs/                     ← backend.log, frontend.log, ollama.log
├── environments/zenji-venv/  ← Produktiv-venv
├── datasets/ · backups/      ← (Phase 2)
```

Start im Lokal-Modus:

```bash
export ZENJI_SSD_ROOT="/Users/gast/Downloads/Zenji KI"
./scripts/setup.sh && ./scripts/start.sh
```

Ollama muss mit `OLLAMA_MODELS="$ZENJI_SSD_ROOT/models"` laufen
(`./scripts/restart_ollama.sh` erledigt das). `backend/.env` enthält die
lokalen Werte für direkte `uvicorn`-Aufrufe; `start.sh` setzt die Variable
explizit und hat Vorrang.

## Wechsel auf die SSD (Produktivbetrieb)

1. SSD anschließen.
2. `export ZENJI_SSD_ROOT=/Volumes/ZENJI-SSD`
3. `./scripts/setup.sh` → überträgt das Projekt auf die SSD und erstellt dort
   Struktur + venv (bestehende Inhalte bleiben unberührt).
4. `./scripts/download_model.sh` → lädt qwen3:8b **auf die SSD**
   (`OLLAMA_MODELS=$SSD/models`, `restart_ollama.sh` stellt um).
5. `./scripts/start.sh` → Backend + Frontend von der SSD.

Die lokale Kopie in `Zenji KI/` kann danach als Entwicklungs-Checkout bleiben;
das Modell in `Zenji KI/models/` kann gelöscht und später auf der SSD neu
geladen werden (oder mit `rsync`/kopieren übertragen werden).

> **Achtung:** Der endgültige Produktionspfad ist die externe SSD unter
> `/Volumes/ZENJI-SSD/ZENJI`. Produktionsdaten (Datenbank, Logs, Modelle,
> venv) gehören dorthin – der Lokal-Modus ist eine Entwicklungsphase.
