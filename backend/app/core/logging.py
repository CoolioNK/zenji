"""Logging-Konfiguration von ZENJI.

Konsole + rotierende Datei im Log-Verzeichnis (Standard: ``<SSD_ROOT>/logs``).
Fehlt die SSD, wird nur auf die Konsole geloggt – das Backend startet dann
trotzdem und meldet den Zustand über ``/api/health``.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(log_dir: Path | None, level: str = "INFO") -> logging.Logger:
    """Konfiguriert den Root-Logger neu, wenn sich das Ziel geändert hat
    (unterstützt mehrere App-Instanzen, z. B. in Tests)."""
    root = logging.getLogger("zenji")
    target = str(log_dir) if log_dir else ""
    if getattr(root, "_zenji_configured", False) and getattr(root, "_zenji_log_dir", None) == target:
        return root

    for old in list(root.handlers):
        root.removeHandler(old)
        try:
            old.close()
        except Exception:  # noqa: BLE001
            pass

    handler: logging.Handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(handler)

    if log_dir is not None:
        try:
            # Wichtig: nur **eine** Ebene erstellen (exist_ok ohne parents).
            # Existiert die übergeordnete SSD nicht, wird kein Ersatzpfad
            # erzeugt – dann läuft Logging nur auf die Konsole.
            log_dir.mkdir(exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                log_dir / "zenji-backend.log",
                maxBytes=2 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
            file_handler.setFormatter(logging.Formatter(_FORMAT))
            root.addHandler(file_handler)
        except OSError as exc:
            # SSD fehlt / nicht beschreibbar: nicht abbrechen, nur melden.
            root.warning("Log-Datei nicht aktiv (Speicherpfad nicht nutzbar): %s", exc)

    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.propagate = False
    root._zenji_configured = True  # type: ignore[attr-defined]
    root._zenji_log_dir = target  # type: ignore[attr-defined]

    # Uvicorn-Logger an ZENJI-Format angleichen (leiser Betrieb).
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = False
        uv_logger.addHandler(handler)

    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"zenji.{name}")
