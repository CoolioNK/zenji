# ZENJI – Quellcode-Staging

> **Achtung:** Der endgültige Produktionspfad ist die externe SSD unter
> `/Volumes/ZENJI-SSD/ZENJI`. Dieses Verzeichnis ist die Quelle, die
> `scripts/setup.sh` dorthin überträgt. Produktionsdaten (Datenbank, Logs,
> Modelle, venv) liegen ausschließlich auf der SSD.

Sobald die SSD angeschlossen ist:

```bash
cd ZENJI
./scripts/setup.sh   # überträgt das Projekt + erstellt Struktur auf der SSD
```
